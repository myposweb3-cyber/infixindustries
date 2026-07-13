"""
Thermal Printer Utility Module for POS System

This module provides thermal printer functionality using ESC/POS commands.
Supports both USB and network-connected thermal printers.

Supported Printers:
- 58mm Thermal Printers
- 80mm Thermal Printers
- USB Serial Printers
- Network Printers (TCP/IP)

Features:
- Text formatting (bold, underline, size)
- Barcode printing
- QR code printing
- Image printing
- Cash drawer control
- Paper cut
"""

import socket
import io
import time
from typing import Optional, Dict, Any, List
from PIL import Image


class ThermalPrinter:
    """Handle thermal printer operations via USB/Serial or Network."""
    
    def __init__(self, printer_type: str = 'usb', port: str = None, 
                 baudrate: int = 9600, host: str = None, port_num: int = None):
        """
        Initialize thermal printer.
        
        Args:
            printer_type: 'usb', 'serial', or 'network'
            port: Serial port (e.g., 'COM1', '/dev/ttyUSB0')
            baudrate: Baud rate for serial printers
            host: IP address for network printers
            port_num: Port number for network printers
        """
        self.printer_type = printer_type
        self.port = port
        self.baudrate = baudrate
        self.host = host
        self.port_num = port_num
        self.socket: Optional[socket.socket] = None
        self.serial_port = None
        self.is_connected = False
        
        # ESC/POS Commands
        self.ESC = b'\x1b'
        self.GS = b'\x1d'
        self.LF = b'\x0a'
        self.CR = b'\x0d'
    
    def connect(self) -> Dict[str, Any]:
        """Connect to the printer."""
        try:
            if self.printer_type == 'network':
                return self._connect_network()
            elif self.printer_type == 'serial':
                return self._connect_serial()
            else:
                return {'success': False, 'message': 'Invalid printer type'}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def _connect_network(self) -> Dict[str, Any]:
        """Connect to network printer."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((self.host, self.port_num))
            self.is_connected = True
            return {'success': True, 'message': f'Connected to {self.host}:{self.port_num}'}
        except Exception as e:
            self.is_connected = False
            return {'success': False, 'message': f'Connection failed: {str(e)}'}
    
    def _connect_serial(self) -> Dict[str, Any]:
        """Connect to serial printer."""
        try:
            import serial
            self.serial_port = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=5
            )
            self.is_connected = True
            return {'success': True, 'message': f'Connected to {self.port}'}
        except Exception as e:
            self.is_connected = False
            return {'success': False, 'message': f'Connection failed: {str(e)}'}
    
    def disconnect(self) -> None:
        """Disconnect from printer."""
        try:
            if self.socket:
                self.socket.close()
                self.socket = None
            if self.serial_port:
                self.serial_port.close()
                self.serial_port = None
        except Exception:
            pass
        self.is_connected = False
    
    def send(self, data: bytes) -> bool:
        """Send data to printer."""
        if not self.is_connected:
            return False
        
        try:
            if self.socket:
                self.socket.sendall(data)
                return True
            elif self.serial_port:
                self.serial_port.write(data)
                return True
            return False
        except Exception as e:
            print(f"Error sending data: {e}")
            return False
    
    # ========== Printer Commands ==========
    
    def initialize(self) -> bool:
        """Initialize printer."""
        return self.send(self.ESC + b'@')
    
    def cut_paper(self, partial: bool = True) -> bool:
        """Cut paper."""
        if partial:
            return self.send(self.GS + b'V\x01')
        return self.send(self.GS + b'V\x00')
    
    def feed_and_cut(self, lines: int = 3) -> bool:
        """Feed lines and cut."""
        cmd = b''
        for _ in range(lines):
            cmd += self.LF
        cmd += self.GS + b'V\x01'
        return self.send(cmd)
    
    def print_text(self, text: str, encoding: str = 'utf-8') -> bool:
        """Print text."""
        return self.send(text.encode(encoding))
    
    def print_line(self, text: str = '') -> bool:
        """Print text with newline."""
        return self.send((text + '\n').encode('utf-8'))
    
    # ========== Text Formatting ==========
    
    def set_alignment(self, align: int) -> bool:
        """Set alignment: 0=left, 1=center, 2=right"""
        return self.send(self.ESC + b'a' + bytes([align]))
    
    def set_bold(self, enable: bool) -> bool:
        """Enable/disable bold."""
        return self.send(self.ESC + b'E' + (b'\x01' if enable else b'\x00'))
    
    def set_underline(self, enable: bool) -> bool:
        """Enable/disable underline."""
        return self.send(self.ESC + b'-' + (b'\x01' if enable else b'\x00'))
    
    def set_font(self, font: int) -> bool:
        """Set font: 0=normal, 1=alternate"""
        return self.send(self.ESC + b'M' + bytes([font]))
    
    def set_text_size(self, width: int, height: int) -> bool:
        """Set text size (1-8)."""
        size = ((width & 0x07) << 4) | (height & 0x07)
        return self.send(self.GS + b'!' + bytes([size]))
    
    def set_line_spacing(self, dots: int) -> bool:
        """Set line spacing in dots."""
        return self.send(self.ESC + b'3' + bytes([dots]))
    
    def default_line_spacing(self) -> bool:
        """Set default line spacing."""
        return self.send(self.ESC + b'2')
    
    # ========== Barcode ==========
    
    def print_barcode(self, data: str, barcode_type: str = 'CODE128',
                     height: int = 50, text_pos: int = 2) -> bool:
        """
        Print barcode.
        
        Args:
            data: Barcode data
            barcode_type: CODE128, EAN13, EAN8, UPC-A, CODE39
            height: Barcode height in dots
            text_pos: 0=none, 1=above, 2=below
        """
        barcode_types = {
            'CODE128': 73,
            'EAN13': 67,
            'EAN8': 68,
            'UPC_A': 65,
            'CODE39': 69
        }
        
        bc_type = barcode_types.get(barcode_type.upper(), 73)
        
        # Set barcode height
        self.send(self.GS + b'h' + bytes([height]))
        # Set barcode width
        self.send(self.GS + b'w' + bytes([2]))
        # Set HRI position
        self.send(self.GS + b'H' + bytes([text_pos]))
        # Set HRI font
        self.send(self.GS + b'f' + bytes([0]))
        # Print barcode
        self.send(self.GS + b'k' + bytes([bc_type]))
        self.send(data.encode('ascii') + b'\x00')
        
        return True
    
    # ========== QR Code ==========
    
    def print_qrcode(self, data: str, size: int = 6) -> bool:
        """
        Print QR code.
        
        Args:
            data: QR code data
            size: Module size (1-8)
        """
        # Set QR code size
        self.send(self.GS + b'w' + bytes([size]))
        # Set error correction level (L=48, M=49, Q=50, H=51)
        self.send(self.GS + b'k' + bytes([48]))
        # Send data
        data_bytes = data.encode('utf-8')
        # Calculate length
        length = len(data_bytes) + 3
        self.send(self.GS + b'k' + bytes([49]))
        self.send(bytes([length & 0xFF, (length >> 8) & 0xFF]))
        self.send(data_bytes)
        
        return True
    
    # ========== Image ==========
    
    def print_image(self, image: Image.Image, width: int = 384) -> bool:
        """
        Print image.
        
        Args:
            image: PIL Image
            width: Maximum width in dots
        """
        # Convert to grayscale
        if image.mode != 'L':
            image = image.convert('L')
        
        # Convert to 1-bit
        threshold = 128
        image = image.point(lambda x: 0 if x < threshold else 255, '1')
        
        img_width = image.width
        img_height = image.height
        
        # Calculate width in bytes (must be multiple of 8)
        width_bytes = (img_width + 7) // 8
        
        # Send raster image command
        self.send(self.ESC + b'*')
        self.send(bytes([0, width_bytes & 0xFF, (width_bytes >> 8) & 0xFF]))
        
        # Send image data
        img_bytes = list(image.tobytes())
        
        for row in range(img_height):
            row_start = row * width_bytes
            row_end = row_start + width_bytes
            row_data = img_bytes[row_start:row_end]
            self.send(bytes(row_data))
            self.send(self.LF)
        
        return True
    
    # ========== Cash Drawer ==========
    
    def open_cash_drawer(self) -> bool:
        """Open cash drawer."""
        return self.send(self.ESC + b'p' + b'\x00' + b'\x19')
    
    def beep(self, count: int = 3, interval: int = 200) -> bool:
        """Beep."""
        return self.send(self.ESC + b'B' + bytes([count, interval]))
    
    # ========== Convenience Methods ==========
    
    def print_label_format(self, lines: List[str], 
                          center: bool = True) -> bool:
        """Print formatted label lines."""
        if center:
            self.set_alignment(1)
        else:
            self.set_alignment(0)
        
        for line in lines:
            self.print_line(line)
        
        return True
    
    def print_receipt_header(self, business_name: str, 
                            address: str = '', phone: str = '') -> bool:
        """Print receipt header."""
        self.initialize()
        self.set_alignment(1)
        self.set_bold(True)
        self.set_text_size(2, 2)
        self.print_line(business_name)
        
        self.set_bold(False)
        self.set_text_size(1, 1)
        
        if address:
            self.print_line(address)
        if phone:
            self.print_line(phone)
        
        self.print_line('-' * 42)
        return True
    
    def print_receipt_footer(self, footer: str = '') -> bool:
        """Print receipt footer."""
        self.set_alignment(1)
        self.print_line(footer)
        self.print_line('')
        self.print_line('')
        self.feed_and_cut(3)
        return True
    
    @staticmethod
    def get_printers() -> List[Dict[str, Any]]:
        """Get list of available printers (placeholder)."""
        # In a real implementation, this would scan for available printers
        return [
            {'name': 'USB Printer', 'type': 'usb'},
            {'name': 'Serial Printer', 'type': 'serial'},
            {'name': 'Network Printer', 'type': 'network'}
        ]


class LabelPrinter58mm(ThermalPrinter):
    """58mm Thermal Label Printer."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.width = 384  # 58mm at 203 DPI
    
    def print_weight_label(self, product_name: str, weight_kg: float,
                          price_per_kg: float, total_price: float,
                          barcode_data: str, currency: str = 'LKR') -> bool:
        """Print weight label."""
        self.initialize()
        self.set_alignment(1)
        self.set_bold(True)
        self.set_text_size(1, 1)
        self.print_line(product_name[:20])
        
        self.set_bold(False)
        self.set_text_size(1, 1)
        self.set_alignment(0)
        
        self.print_line(f'Weight: {weight_kg:.3f} KG')
        self.print_line(f'Price/{currency}: {price_per_kg:.0f}')
        self.set_bold(True)
        self.print_line(f'Total: {total_price:.0f} {currency}')
        self.set_bold(False)
        
        self.print_line('')
        
        # Print barcode
        self.set_alignment(1)
        self.print_barcode(barcode_data)
        
        self.print_line('')
        self.feed_and_cut(3)
        
        return True


class LabelPrinter80mm(ThermalPrinter):
    """80mm Thermal Label Printer."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.width = 576  # 80mm at 203 DPI
    
    def print_weight_label(self, product_name: str, weight_kg: float,
                          price_per_kg: float, total_price: float,
                          barcode_data: str, currency: str = 'LKR') -> bool:
        """Print weight label (larger format)."""
        self.initialize()
        self.set_alignment(1)
        self.set_bold(True)
        self.set_text_size(2, 2)
        self.print_line(product_name[:25])
        
        self.set_bold(False)
        self.set_text_size(1, 1)
        self.set_alignment(0)
        
        self.print_line(f'Weight: {weight_kg:.3f} KG')
        self.print_line(f'Price/{currency}: {price_per_kg:.0f}')
        self.set_bold(True)
        self.set_text_size(1, 1)
        self.print_line(f'Total: {total_price:.0f} {currency}')
        self.set_bold(False)
        
        self.print_line('')
        
        # Print barcode
        self.set_alignment(1)
        self.print_barcode(barcode_data)
        
        self.print_line('')
        self.feed_and_cut(3)
        
        return True


# Global printer utility
printer = ThermalPrinter()
