"""
Scale and Barcode Printing API Routes

This module provides API endpoints for:
- Scale connection and communication
- Weight reading
- Barcode generation
- Label printing

Scale Requirements:
- USB / RS232 weighing scale (COM Port based)
- Baud rate: 9600
- Data bits: 8
- Parity: None
- Stop bit: 1
- Weight unit: KG
- Continuous weight reading mode
- Read stable weight only
"""

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from app.models import db, Setting, Product
from app.utils.permissions import require_permission
from app.utils.scale_communication import ScaleManager, scale
from app.utils.barcode_generator import barcode_generator, barcode
from app.utils.thermal_printer import LabelPrinter58mm, LabelPrinter80mm
from app import csrf
import io
import base64
import json


scale_bp = Blueprint('scale', __name__, template_folder='../../templates')


def get_scale_settings():
    """Get scale settings from database."""
    from app.utils.security import get_company_id
    from sqlalchemy import or_
    settings = {}
    query = Setting.query.filter_by(setting_category='scale')
    company_id = get_company_id()
    if company_id and hasattr(Setting, 'company_id'):
        query = query.filter(Setting.company_id == company_id)
    scale_settings = query.all()
    for s in scale_settings:
        settings[s.setting_key] = s.setting_value
    return settings


def get_printer_settings():
    """Get printer settings from database."""
    from app.utils.security import get_company_id
    from sqlalchemy import or_
    settings = {}
    query = Setting.query.filter_by(setting_category='printer')
    company_id = get_company_id()
    if company_id and hasattr(Setting, 'company_id'):
        query = query.filter(Setting.company_id == company_id)
    printer_settings = query.all()
    for s in printer_settings:
        settings[s.setting_key] = s.setting_value
    return settings


def save_setting(category, key, value):
    """Save a setting to database."""
    from app.utils.security import get_company_id
    from sqlalchemy import or_
    company_id = get_company_id()
    query = Setting.query.filter_by(
        setting_category=category,
        setting_key=key
    )
    if company_id and hasattr(Setting, 'company_id'):
        query = query.filter(Setting.company_id == company_id)
    setting = query.first()
    
    if setting:
        setting.setting_value = str(value)
    else:
        setting = Setting(
            setting_category=category,
            setting_key=key,
            setting_value=str(value),
            company_id=company_id
        )
        db.session.add(setting)
    
    db.session.commit()


# ========== Scale Endpoints ==========

@scale_bp.route('/api/scale/ports')
@csrf.exempt
@login_required
@require_permission('can_access_scale')
def get_available_ports():
    """Get list of available COM ports."""
    try:
        from app.utils.scale_communication import ScaleCommunication
        ports = ScaleCommunication.get_available_ports()
        return jsonify({
            'success': True,
            'ports': ports
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@scale_bp.route('/api/scale/status')
@csrf.exempt
@login_required
@require_permission('can_access_scale')
def get_scale_status():
    """Get current scale connection status."""
    try:
        status = ScaleManager.get_status()
        return jsonify({
            'success': True,
            'status': status
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@scale_bp.route('/api/scale/connect', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_scale')
def connect_scale():
    """Connect to scale."""
    data = request.get_json() or {}
    
    port = data.get('port')
    baudrate = int(data.get('baudrate', 9600))
    
    if not port:
        return jsonify({
            'success': False,
            'error': 'Port is required'
        }), 400
    
    try:
        # Get scale instance
        scale = ScaleManager.get_scale()
        
        # Connect to scale
        result = scale.connect(port, baudrate)
        
        if result.get('success'):
            # Save settings
            save_setting('scale', 'port', port)
            save_setting('scale', 'baudrate', baudrate)
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@scale_bp.route('/api/scale/connect/auto', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_scale')
def auto_connect_scale():
    """Auto-detect and connect to scale."""
    data = request.get_json() or {}
    baudrate = int(data.get('baudrate', 9600))
    
    try:
        scale = ScaleManager.get_scale()
        result = scale.auto_connect(baudrate)
        
        if result.get('success'):
            save_setting('scale', 'port', result.get('port'))
            save_setting('scale', 'baudrate', baudrate)
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@scale_bp.route('/api/scale/disconnect', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_scale')
def disconnect_scale():
    """Disconnect from scale."""
    try:
        ScaleManager.disconnect()
        return jsonify({
            'success': True,
            'message': 'Scale disconnected'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@scale_bp.route('/api/scale/weight')
@csrf.exempt
@login_required
@require_permission('can_access_scale')
def get_weight():
    """Get current weight from scale."""
    try:
        scale = ScaleManager.get_scale()
        
        if not scale.is_connected:
            return jsonify({
                'success': False,
                'error': 'Scale not connected'
            }), 400
        
        weight, is_stable = scale.read_weight()
        
        return jsonify({
            'success': True,
            'weight': weight,
            'weight_kg': weight,
            'weight_grams': weight * 1000,
            'is_stable': is_stable,
            'unit': 'KG'
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@scale_bp.route('/api/scale/weight/continuous', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_scale')
def start_continuous_weight():
    """Start continuous weight reading."""
    # Note: This would require WebSocket for real-time updates
    # For now, return a simple response
    return jsonify({
        'success': True,
        'message': 'Use polling to get continuous weight'
    })


# ========== Barcode Endpoints ==========

@scale_bp.route('/api/barcode/generate', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_scale')
def generate_barcode():
    """Generate barcode image."""
    data = request.get_json() or {}
    
    product_name = data.get('product_name', '')
    product_code = data.get('product_code', '')
    weight_kg = float(data.get('weight_kg', 0))
    price_per_kg = float(data.get('price_per_kg', 0))
    total_price = float(data.get('total_price', 0))
    barcode_type = data.get('barcode_type', 'code128')
    label_width = data.get('label_width', '58mm')
    
    if weight_kg <= 0 or total_price <= 0:
        return jsonify({
            'success': False,
            'error': 'Invalid weight or price'
        }), 400
    
    try:
        # Create barcode data
        weight_grams = int(weight_kg * 1000)
        barcode_data = barcode_generator._create_barcode_data(
            product_code, weight_grams, int(total_price)
        )
        
        # Create label image
        if label_width == '80mm':
            label_img = barcode_generator.create_80mm_label(
                product_name, weight_kg, price_per_kg, total_price,
                product_code, barcode_type
            )
        else:
            label_img = barcode_generator.create_58mm_label(
                product_name, weight_kg, price_per_kg, total_price,
                product_code, barcode_type
            )
        
        # Convert to base64
        img_buffer = io.BytesIO()
        label_img.save(img_buffer, format='PNG')
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'barcode_data': barcode_data,
            'image': f'data:image/png;base64,{img_base64}',
            'weight_kg': weight_kg,
            'weight_grams': weight_grams,
            'total_price': total_price
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@scale_bp.route('/api/barcode/parse', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_scale')
def parse_barcode():
    """Parse barcode data."""
    data = request.get_json() or {}
    barcode_data = data.get('barcode_data', '')
    
    try:
        parsed = barcode_generator.parse_barcode_data(barcode_data)
        return jsonify({
            'success': True,
            'parsed': parsed
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ========== Printer Endpoints ==========

@scale_bp.route('/api/printer/settings', methods=['GET'])
@csrf.exempt
@login_required
@require_permission('can_access_scale')
def get_printer_settings_api():
    """Get printer settings."""
    try:
        settings = get_printer_settings()
        return jsonify({
            'success': True,
            'settings': settings
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@scale_bp.route('/api/printer/settings', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_scale')
def save_printer_settings():
    """Save printer settings."""
    data = request.get_json() or {}
    
    try:
        # Save printer settings
        for key, value in data.items():
            save_setting('printer', key, value)
        
        return jsonify({
            'success': True,
            'message': 'Printer settings saved'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@scale_bp.route('/api/printer/test', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_scale')
def test_printer():
    """Test printer connection."""
    data = request.get_json() or {}
    
    printer_type = data.get('printer_type', 'usb')
    port = data.get('port')
    baudrate = int(data.get('baudrate', 9600))
    host = data.get('host')
    port_num = int(data.get('port_num', 9100))
    
    try:
        if printer_type == 'network':
            printer = LabelPrinter80mm(
                printer_type='network',
                host=host,
                port_num=port_num
            )
        else:
            printer = LabelPrinter80mm(
                printer_type='serial',
                port=port,
                baudrate=baudrate
            )
        
        result = printer.connect()
        
        if result.get('success'):
            printer.initialize()
            printer.print_line('Test Print - POS System')
            printer.print_line('Printer is working!')
            printer.feed_and_cut(3)
            printer.disconnect()
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@scale_bp.route('/api/label/print', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_scale')
def print_label():
    """Print weight label."""
    data = request.get_json() or {}
    
    product_name = data.get('product_name', '')
    product_code = data.get('product_code', '')
    weight_kg = float(data.get('weight_kg', 0))
    price_per_kg = float(data.get('price_per_kg', 0))
    total_price = float(data.get('total_price', 0))
    barcode_type = data.get('barcode_type', 'code128')
    label_width = data.get('label_width', '58mm')
    
    # Get printer settings
    printer_settings = get_printer_settings()
    printer_type = printer_settings.get('printer_type', 'usb')
    port = printer_settings.get('port', 'COM1')
    baudrate = int(printer_settings.get('baudrate', 9600))
    host = printer_settings.get('host', '192.168.1.100')
    port_num = int(printer_settings.get('port_num', 9100))
    
    if weight_kg <= 0 or total_price <= 0:
        return jsonify({
            'success': False,
            'error': 'Invalid weight or price'
        }), 400
    
    try:
        # Create barcode data
        weight_grams = int(weight_kg * 1000)
        barcode_data = barcode_generator._create_barcode_data(
            product_code, weight_grams, int(total_price)
        )
        
        # Select printer
        if label_width == '80mm':
            if printer_type == 'network':
                printer = LabelPrinter80mm(printer_type='network', host=host, port_num=port_num)
            else:
                printer = LabelPrinter80mm(printer_type='serial', port=port, baudrate=baudrate)
        else:
            if printer_type == 'network':
                printer = LabelPrinter58mm(printer_type='network', host=host, port_num=port_num)
            else:
                printer = LabelPrinter58mm(printer_type='serial', port=port, baudrate=baudrate)
        
        # Connect and print
        result = printer.connect()
        
        if not result.get('success'):
            return jsonify({
                'success': False,
                'error': f"Failed to connect to printer: {result.get('message')}"
            }), 500
        
        # Print label
        printer.print_weight_label(
            product_name, weight_kg, price_per_kg, total_price, barcode_data
        )
        
        printer.disconnect()
        
        return jsonify({
            'success': True,
            'message': 'Label printed successfully',
            'barcode_data': barcode_data
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@scale_bp.route('/api/label/preview', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_scale')
def preview_label():
    """Generate label preview (for display)."""
    data = request.get_json() or {}
    
    product_name = data.get('product_name', '')
    product_code = data.get('product_code', '')
    weight_kg = float(data.get('weight_kg', 0))
    price_per_kg = float(data.get('price_per_kg', 0))
    total_price = float(data.get('total_price', 0))
    barcode_type = data.get('barcode_type', 'code128')
    label_width = data.get('label_width', '58mm')
    
    if weight_kg <= 0 or total_price <= 0:
        return jsonify({
            'success': False,
            'error': 'Invalid weight or price'
        }), 400
    
    try:
        # Create label image
        if label_width == '80mm':
            label_img = barcode_generator.create_80mm_label(
                product_name, weight_kg, price_per_kg, total_price,
                product_code, barcode_type
            )
        else:
            label_img = barcode_generator.create_58mm_label(
                product_name, weight_kg, price_per_kg, total_price,
                product_code, barcode_type
            )
        
        # Convert to base64
        img_buffer = io.BytesIO()
        label_img.save(img_buffer, format='PNG')
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'image': f'data:image/png;base64,{img_base64}'
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ========== Weighted Product Endpoints ==========

@scale_bp.route('/api/products/weighted', methods=['GET'])
@csrf.exempt
@login_required
@require_permission('can_access_scale')
def get_weighted_products():
    """Get list of products sold by weight."""
    try:
        products = Product.query.filter(
            Product.unit_type.in_(['kg', 'g', 'L', 'ml'])
        ).all()
        
        result = []
        for p in products:
            result.append({
                'id': p.id,
                'name': p.name,
                'barcode': p.barcode,
                'unit_type': p.unit_type,
                'price': p.price,
                'price_per_kg': getattr(p, 'price_per_kg', p.price),
                'stock': p.stock
            })
        
        return jsonify({
            'success': True,
            'products': result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ========== Settings Endpoints ==========

@scale_bp.route('/api/scale/settings', methods=['GET'])
@csrf.exempt
@login_required
@require_permission('can_access_scale')
def get_scale_settings_api():
    """Get scale settings."""
    try:
        settings = get_scale_settings()
        return jsonify({
            'success': True,
            'settings': settings
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@scale_bp.route('/api/scale/settings', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_scale')
@require_permission('can_access_settings')
def save_scale_settings():
    """Save scale settings."""
    data = request.get_json() or {}
    
    try:
        for key, value in data.items():
            save_setting('scale', key, value)
        
        return jsonify({
            'success': True,
            'message': 'Scale settings saved'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
