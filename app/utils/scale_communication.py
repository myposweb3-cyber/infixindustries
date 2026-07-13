"""
Scale Communication Module for USB/RS232 Weighing Scales

This module provides serial communication with weighing scales that support
continuous weight reading mode. Compatible with scales that output weight data
in formats like:
- CAS ER JR / ER Jr Pro
- DIGI DS-788
- Other scales with similar output format

Scale Configuration:
- Baud rate: 9600
- Data bits: 8
- Parity: None
- Stop bit: 1
- Weight unit: KG
- Continuous weight reading mode
- Read stable weight only
"""

import serial
import serial.tools.list_ports
import time
import re
import threading
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime


class ScaleCommunication:
    """Handles serial communication with weighing scales."""
    
    # Common scale data patterns
    # Format: ST,UU,PPPPPP.GG,NN\r\n
    # ST: Status (ST=Stable, US=Unstable, OL=Over Load)
    # UU: Unit (KG, G, LB, OZ)
    # PPPPPP.GG: Weight value
    # NN: Checksum/CRC
    
    SCALE_PATTERNS = [
        # Pattern 1: ST,KG,1.234KG\r\n
        re.compile(r'ST,(KG|G|lb),([0-9.]+)KG\s*\r\n'),
        # Pattern 2: ST,KG,001.234,00\r\n
        re.compile(r'ST,(KG|G|lb),([0-9.]+)(KG)?,?\s*\r\n'),
        # Pattern 3: 0x02 ST, KG,   1.234 KG 0x03
        re.compile(r'ST,\s*(KG|G|lb),\s*([0-9.]+)\s*KG\s*'),
        # Pattern 4: Simple numeric with decimal
        re.compile(r'([0-9]+\.[0-9]{1,3})'),
    ]
    
    def __init__(self):
        self.serial_port: Optional[serial.Serial] = None
        self.is_connected: bool = False
        self.current_weight: float = 0.0
        self.is_stable: bool = False
        self.unit: str = 'KG'
        self.last_reading_time: Optional[datetime] = None
        self._read_thread: Optional[threading.Thread] = None
        self._stop_reading: bool = False
        self._weight_callback: Optional[Callable] = None
        
    @staticmethod
    def get_available_ports() -> List[Dict[str, str]]:
        """Get list of available COM ports."""
        ports = serial.tools.list_ports.comports()
        port_list = []
        for port in ports:
            port_list.append({
                'port': port.device,
                'name': port.name,
                'description': port.description,
                'hwid': port.hwid
            })
        return port_list
    
    @staticmethod
    def get_scale_ports() -> List[Dict[str, str]]:
        """Get ports that are likely connected to scales (heuristic)."""
        all_ports = ScaleCommunication.get_available_ports()
        # Filter out ports that are likely not scales
        scale_ports = []
        for port in all_ports:
            # Include USB serial ports (common for USB scales)
            if 'USB' in port.get('description', '').upper() or \
               'SERIAL' in port.get('description', '').upper() or \
               'COM' in port.get('port', '').upper():
                scale_ports.append(port)
        return scale_ports if scale_ports else all_ports
    
    def connect(self, port: str, baudrate: int = 9600, 
                bytesize: int = serial.EIGHTBITS,
                parity: str = serial.PARITY_NONE,
                stopbits: int = serial.STOPBITS_ONE,
                timeout: float = 1.0) -> Dict[str, Any]:
        """
        Connect to the scale via serial port.
        
        Args:
            port: COM port (e.g., 'COM1' or '/dev/ttyUSB0')
            baudrate: Baud rate (default: 9600)
            bytesize: Data bits (default: 8)
            parity: Parity (default: None)
            stopbits: Stop bits (default: 1)
            timeout: Read timeout in seconds
            
        Returns:
            Dictionary with connection status
        """
        try:
            # Close existing connection if any
            if self.is_connected:
                self.disconnect()
            
            # Create new serial connection
            self.serial_port = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=bytesize,
                parity=parity,
                stopbits=stopbits,
                timeout=timeout,
                write_timeout=1.0
            )
            
            # Give scale time to initialize
            time.sleep(0.5)
            
            # Flush any existing data
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()
            
            self.is_connected = True
            
            return {
                'success': True,
                'message': f'Connected to scale on {port}',
                'port': port,
                'baudrate': baudrate
            }
            
        except serial.SerialException as e:
            self.is_connected = False
            return {
                'success': False,
                'message': f'Failed to connect: {str(e)}',
                'error': str(e)
            }
        except Exception as e:
            self.is_connected = False
            return {
                'success': False,
                'message': f'Unexpected error: {str(e)}',
                'error': str(e)
            }
    
    def disconnect(self) -> None:
        """Disconnect from the scale."""
        self._stop_reading = True
        
        if self._read_thread and self._read_thread.is_alive():
            self._read_thread.join(timeout=2.0)
        
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
            except Exception:
                pass
        
        self.is_connected = False
        self.serial_port = None
    
    def start_continuous_reading(self, callback: Callable[[float, bool], None], 
                                  interval: float = 0.1) -> None:
        """
        Start continuous weight reading in a background thread.
        
        Args:
            callback: Function to call with (weight, is_stable) parameters
            interval: Time between readings in seconds
        """
        if not self.is_connected:
            raise RuntimeError('Scale not connected')
        
        self._weight_callback = callback
        self._stop_reading = False
        self._read_thread = threading.Thread(
            target=self._continuous_read_loop,
            args=(interval,),
            daemon=True
        )
        self._read_thread.start()
    
    def _continuous_read_loop(self, interval: float) -> None:
        """Background loop for continuous reading."""
        while not self._stop_reading:
            try:
                weight, is_stable = self.read_weight()
                self.current_weight = weight
                self.is_stable = is_stable
                self.last_reading_time = datetime.now()
                
                if self._weight_callback:
                    self._weight_callback(weight, is_stable)
                    
            except Exception as e:
                # Continue reading even on errors
                pass
            
            time.sleep(interval)
    
    def stop_continuous_reading(self) -> None:
        """Stop continuous weight reading."""
        self._stop_reading = True
        if self._read_thread and self._read_thread.is_alive():
            self._read_thread.join(timeout=2.0)
    
    def read_weight(self) -> tuple:
        """
        Read current weight from scale.
        
        Returns:
            Tuple of (weight_in_kg, is_stable)
        """
        if not self.is_connected or not self.serial_port:
            return 0.0, False
        
        try:
            # Wait for data
            if self.serial_port.in_waiting == 0:
                time.sleep(0.05)
                if self.serial_port.in_waiting == 0:
                    return self.current_weight, self.is_stable
            
            # Read available data
            raw_data = self.serial_port.read(self.serial_port.in_waiting)
            
            if not raw_data:
                return self.current_weight, self.is_stable
            
            # Decode and parse
            try:
                data_str = raw_data.decode('ascii', errors='ignore')
            except Exception:
                data_str = raw_data.decode('utf-8', errors='ignore')
            
            # Parse the weight data
            weight, is_stable = self._parse_weight(data_str)
            
            if weight is not None:
                self.current_weight = weight
                self.is_stable = is_stable
                self.unit = 'KG'  # Assuming KG based on requirements
            
            return self.current_weight, self.is_stable
            
        except Exception as e:
            return self.current_weight, self.is_stable
    
    def _parse_weight(self, data: str) -> tuple:
        """
        Parse weight data from scale output.
        
        Args:
            data: Raw string data from scale
            
        Returns:
            Tuple of (weight_in_kg, is_stable)
        """
        # Try each pattern
        for pattern in self.SCALE_PATTERNS:
            match = pattern.search(data)
            if match:
                try:
                    if len(match.groups()) >= 2:
                        # Format with unit
                        unit = match.group(1).strip()
                        weight_str = match.group(2).strip()
                    else:
                        # Just numeric
                        weight_str = match.group(1).strip()
                        unit = 'KG'
                    
                    weight = float(weight_str)
                    
                    # Convert to KG if needed
                    if unit.upper() == 'G':
                        weight = weight / 1000.0
                    elif unit.upper() == 'LB':
                        weight = weight * 0.453592
                    
                    # Check if stable (ST in the data)
                    is_stable = 'ST,' in data or 'ST,' in data or 'ST ' in data
                    
                    return weight, is_stable
                    
                except (ValueError, IndexError):
                    continue
        
        return None, False
    
    def get_status(self) -> Dict[str, Any]:
        """Get current scale status."""
        return {
            'connected': self.is_connected,
            'port': self.serial_port.port if self.serial_port else None,
            'current_weight': self.current_weight,
            'is_stable': self.is_stable,
            'unit': self.unit,
            'last_reading': self.last_reading_time.isoformat() if self.last_reading_time else None
        }
    
    def auto_connect(self, baudrate: int = 9600) -> Dict[str, Any]:
        """
        Try to automatically connect to a scale.
        
        Args:
            baudrate: Baud rate to try
            
        Returns:
            Connection result dictionary
        """
        ports = self.get_available_ports()
        
        if not ports:
            return {
                'success': False,
                'message': 'No COM ports found'
            }
        
        # Try each port
        for port_info in ports:
            port = port_info['port']
            
            result = self.connect(port, baudrate)
            
            if result['success']:
                # Try to read weight to verify it's a scale
                time.sleep(0.5)
                weight, _ = self.read_weight()
                
                if weight >= 0:
                    return {
                        'success': True,
                        'message': f'Auto-connected to scale on {port}',
                        'port': port,
                        'baudrate': baudrate
                    }
                else:
                    # Connected but no valid weight - might not be a scale
                    self.disconnect()
        
        return {
            'success': False,
            'message': 'No scale found on any COM port'
        }
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()


class ScaleManager:
    """Global scale manager for the application."""
    
    _instance: Optional['ScaleManager'] = None
    _scale: Optional[ScaleCommunication] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._scale = ScaleCommunication()
        return cls._instance
    
    @classmethod
    def get_scale(cls) -> ScaleCommunication:
        """Get the global scale instance."""
        if cls._scale is None:
            cls._scale = ScaleCommunication()
        return cls._scale
    
    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Get scale connection status."""
        if cls._scale:
            return cls._scale.get_status()
        return {'connected': False}
    
    @classmethod
    def disconnect(cls) -> None:
        """Disconnect the scale."""
        if cls._scale:
            cls._scale.disconnect()


# Global scale instance
scale = ScaleManager.get_scale()
