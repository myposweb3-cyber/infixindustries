"""
Barcode Generator Module for POS System

This module provides barcode generation functionality for product labels.
Supports Code128 and EAN-13 barcode formats.

Barcode Data Format:
- Product Code
- Weight (in grams)
- Total Price

Label Format:
--------------------------------
Product Name
Weight: 0.750 KG
Price/KG: 1200 LKR
Total: 900 LKR
[BARCODE]
--------------------------------
"""

import io
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont
from typing import Tuple, Optional, Dict, Any
import os


class BarcodeGenerator:
    """Generate barcodes for product labels."""
    
    # Supported barcode formats
    CODE128 = 'code128'
    EAN13 = 'ean13'
    EAN8 = 'ean8'
    UPC = 'upc'
    
    # Label dimensions (in pixels at 203 DPI for thermal printers)
    LABEL_WIDTH_58MM = 384  # 58mm at 203 DPI
    LABEL_WIDTH_80MM = 576  # 80mm at 203 DPI
    
    # Label dimensions with margins
    LABEL_MARGIN = 10
    
    def __init__(self, label_width: int = LABEL_WIDTH_58MM):
        """
        Initialize barcode generator.
        
        Args:
            label_width: Label width in pixels (default: 58mm/384px)
        """
        self.label_width = label_width
        self.label_height = None  # Will be calculated based on content
    
    def generate_barcode_image(self, data: str, barcode_type: str = CODE128, 
                               height: int = 50) -> Image.Image:
        """
        Generate a barcode image.
        
        Args:
            data: Data to encode in barcode
            barcode_type: Type of barcode (code128, ean13, etc.)
            height: Barcode height in pixels
            
        Returns:
            PIL Image object
        """
        # Create barcode object
        if barcode_type == self.EAN13:
            # EAN-13 requires 12 digits (checksum will be calculated)
            data = data[:12].zfill(12)
            bc = barcode.get_barcode_class(barcode_type)
            barcode_obj = bc(data, writer=ImageWriter())
        elif barcode_type == self.EAN8:
            data = data[:7].zfill(7)
            bc = barcode.get_barcode_class(barcode_type)
            barcode_obj = bc(data, writer=ImageWriter())
        else:
            # Code128 doesn't have length requirements
            bc = barcode.get_barcode_class(barcode_type)
            barcode_obj = bc(str(data), writer=ImageWriter())
        
        # Render to bytes
        buffer = io.BytesIO()
        barcode_obj.write(buffer)
        buffer.seek(0)
        
        # Open as image
        img = Image.open(buffer)
        
        # Resize if needed
        if img.height > height:
            ratio = height / img.height
            new_width = int(img.width * ratio)
            img = img.resize((new_width, height), Image.LANCZOS)
        
        return img
    
    def create_label_image(self, product_name: str, weight_kg: float, 
                          price_per_kg: float, total_price: float,
                          product_code: str = '',
                          barcode_type: str = CODE128,
                          currency: str = 'LKR') -> Image.Image:
        """
        Create a complete label image with barcode.
        
        Args:
            product_name: Name of the product
            weight_kg: Weight in KG
            price_per_kg: Price per KG
            total_price: Total price
            product_code: Product code for barcode
            barcode_type: Type of barcode
            currency: Currency symbol
            
        Returns:
            PIL Image object
        """
        # Calculate weight in grams for barcode data
        weight_grams = int(weight_kg * 1000)
        
        # Create barcode data: PRODUCT_CODE + WEIGHT(5 digits) + PRICE(6 digits)
        # Format: XXXXX + NNNNN + NNNNNN
        barcode_data = self._create_barcode_data(product_code, weight_grams, int(total_price))
        
        # Generate barcode image
        barcode_img = self.generate_barcode_image(barcode_data, barcode_type, height=60)
        
        # Calculate label dimensions
        content_width = self.label_width - (2 * self.LABEL_MARGIN)
        barcode_width = barcode_img.width
        
        # Calculate total height
        line_height = 22
        text_height = 0
        text_lines = [
            product_name[:30],  # Truncate if too long
            f"Weight: {weight_kg:.3f} KG",
            f"Price/{currency}: {price_per_kg:.0f}",
            f"Total: {total_price:.0f} {currency}"
        ]
        
        # Estimate text height (using simple approximation)
        text_height = len(text_lines) * line_height
        
        # Add spacing
        spacing = 15
        barcode_spacing = 10
        
        total_height = self.LABEL_MARGIN + text_height + spacing + barcode_img.height + self.LABEL_MARGIN
        
        # Create label image (white background)
        label_img = Image.new('RGB', (self.label_width, total_height), 'white')
        draw = ImageDraw.Draw(label_img)
        
        # Draw text lines
        y_pos = self.LABEL_MARGIN
        
        # Try to use a font, fallback to default if not available
        try:
            # Try to load a larger font
            font_size = 14
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except:
                font = ImageFont.load_default()
        except:
            font = ImageFont.load_default()
        
        # Draw each line of text
        for i, line in enumerate(text_lines):
            # Draw text
            draw.text((self.LABEL_MARGIN, y_pos), line, fill='black', font=font)
            y_pos += line_height
        
        # Draw barcode
        barcode_x = (self.label_width - barcode_img.width) // 2
        label_img.paste(barcode_img, (barcode_x, y_pos + spacing))
        
        return label_img
    
    def _create_barcode_data(self, product_code: str, weight_grams: int, 
                            price: int) -> str:
        """
        Create barcode data string.
        
        Format: PRODUCT_CODE(5 chars) + WEIGHT(5 digits) + PRICE(6 digits)
        Example: ABCDE00123 000900
        
        Args:
            product_code: Product code
            weight_grams: Weight in grams
            price: Total price (rounded to integer)
            
        Returns:
            Barcode data string
        """
        # Pad product code to 5 characters
        pc = str(product_code)[:5].ljust(5, '0')
        
        # Pad weight to 5 digits
        wt = str(weight_grams % 100000).zfill(5)
        
        # Pad price to 6 digits (max 999999)
        pr = str(price % 1000000).zfill(6)
        
        return pc + wt + pr
    
    def parse_barcode_data(self, barcode_data: str) -> Dict[str, Any]:
        """
        Parse barcode data back to components.
        
        Args:
            barcode_data: Barcode data string
            
        Returns:
            Dictionary with parsed components
        """
        if len(barcode_data) < 16:
            return {
                'product_code': '',
                'weight_grams': 0,
                'price': 0,
                'valid': False
            }
        
        product_code = barcode_data[:5].lstrip('0')
        weight_grams = int(barcode_data[5:10])
        price = int(barcode_data[10:16])
        
        return {
            'product_code': product_code,
            'weight_grams': weight_grams,
            'price': price,
            'valid': True
        }
    
    def save_label(self, image: Image.Image, filepath: str) -> bool:
        """
        Save label image to file.
        
        Args:
            image: PIL Image object
            filepath: Path to save the image
            
        Returns:
            True if successful
        """
        try:
            # Create directory if needed
            directory = os.path.dirname(filepath)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            
            image.save(filepath, 'PNG')
            return True
        except Exception as e:
            print(f"Error saving label: {e}")
            return False
    
    def get_label_bytes(self, image: Image.Image, format: str = 'PNG') -> bytes:
        """
        Get label image as bytes.
        
        Args:
            image: PIL Image object
            format: Image format (PNG, JPEG, etc.)
            
        Returns:
            Image bytes
        """
        buffer = io.BytesIO()
        image.save(buffer, format=format)
        buffer.seek(0)
        return buffer.read()
    
    @staticmethod
    def create_58mm_label(product_name: str, weight_kg: float,
                        price_per_kg: float, total_price: float,
                        product_code: str = '', barcode_type: str = 'code128',
                        currency: str = 'LKR') -> Image.Image:
        """Create a 58mm width label."""
        generator = BarcodeGenerator(BarcodeGenerator.LABEL_WIDTH_58MM)
        return generator.create_label_image(
            product_name, weight_kg, price_per_kg, total_price,
            product_code, barcode_type, currency
        )
    
    @staticmethod
    def create_80mm_label(product_name: str, weight_kg: float,
                        price_per_kg: float, total_price: float,
                        product_code: str = '', barcode_type: str = 'code128',
                        currency: str = 'LKR') -> Image.Image:
        """Create an 80mm width label."""
        generator = BarcodeGenerator(BarcodeGenerator.LABEL_WIDTH_80MM)
        return generator.create_label_image(
            product_name, weight_kg, price_per_kg, total_price,
            product_code, barcode_type, currency
        )


class LabelPrinter:
    """Handle thermal printer operations."""
    
    def __init__(self):
        """Initialize label printer."""
        self.escpos_commands = ESCPOSCommands()
    
    def print_label(self, label_image: Image.Image, printer_name: str = None) -> Dict[str, Any]:
        """
        Print label to thermal printer.
        
        Args:
            label_image: PIL Image to print
            printer_name: Optional printer name (Windows only)
            
        Returns:
            Result dictionary
        """
        try:
            # Convert image to ESC/POS commands
            img_bytes = self.escpos_commands.image_to_raster_bitmap(label_image)
            
            # In a real implementation, this would send to the printer
            # For now, we'll return success
            return {
                'success': True,
                'message': 'Label prepared for printing',
                'data_length': len(img_bytes)
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Print error: {str(e)}',
                'error': str(e)
            }
    
    def cut_paper(self) -> bytes:
        """Get ESC/POS command to cut paper."""
        return self.escpos_commands.cut_paper()
    
    def feed_and_cut(self, lines: int = 3) -> bytes:
        """Get ESC/POS command to feed and cut paper."""
        return self.escpos_commands.feed_and_cut(lines)


class ESCPOSCommands:
    """ESC/POS command constants for thermal printers."""
    
    # ESC/POS Control commands
    ESC = b'\x1b'
    GS = b'\x1d'
    LF = b'\x0a'
    CR = b'\x0d'
    
    # Initialize printer
    def initialize(self) -> bytes:
        """Initialize printer command."""
        return self.ESC + b'@'
    
    # Cut paper
    def cut_paper(self, partial: bool = True) -> bytes:
        """Cut paper command."""
        if partial:
            return self.GS + b'V\x01'
        return self.GS + b'V\x00'
    
    def feed_and_cut(self, lines: int = 3) -> bytes:
        """Feed lines and cut paper."""
        cmd = b''
        for _ in range(lines):
            cmd += self.LF
        cmd += self.GS + b'V\x01'
        return cmd
    
    # Text formatting
    def set_alignment(self, alignment: int) -> bytes:
        """Set text alignment (0=left, 1=center, 2=right)."""
        return self.ESC + b'a' + bytes([alignment])
    
    def set_bold(self, enable: bool) -> bytes:
        """Enable/disable bold text."""
        return self.ESC + b'E' + (b'\x01' if enable else b'\x00')
    
    def set_underline(self, enable: bool) -> bytes:
        """Enable/disable underline text."""
        return self.ESC + b'-' + (b'\x01' if enable else b'\x00')
    
    def set_font(self, font: int) -> bytes:
        """Set font (0=font A, 1=font B)."""
        return self.ESC + b'M' + bytes([font])
    
    def set_text_size(self, width: int, height: int) -> bytes:
        """Set text size (1-8 for each dimension)."""
        size = ((width & 0x07) << 4) | (height & 0x07)
        return self.GS + b'!' + bytes([size])
    
    # Line spacing
    def set_line_spacing(self, spacing: int) -> bytes:
        """Set line spacing in dots."""
        return self.ESC + b'3' + bytes([spacing])
    
    def default_line_spacing(self) -> bytes:
        """Set default line spacing."""
        return self.ESC + b'2'
    
    # Print and feed
    def print_and_feed(self, lines: int) -> bytes:
        """Print and feed n lines."""
        return self.ESC + b'd' + bytes([lines])
    
    # Image printing
    def image_to_raster_bitmap(self, image: Image.Image, 
                               mode: int = 0) -> bytes:
        """
        Convert image to ESC/POS raster bitmap.
        
        Args:
            image: PIL Image
            mode: 0 = normal, 1 = double-width, 2 = double-height, 3 = quadruple
            
        Returns:
            ESC/POS command bytes
        """
        # Convert to grayscale if needed
        if image.mode != 'L':
            image = image.convert('L')
        
        # Convert to 1-bit (black and white)
        threshold = 128
        image = image.point(lambda x: 0 if x < threshold else 255, '1')
        
        width = image.width
        height = image.height
        
        # Align width to 8 bits
        width_bytes = (width + 7) // 8
        
        # ESC * m nL nH
        cmd = self.ESC + b'*' + bytes([mode, width_bytes & 0xFF, (width_bytes >> 8) & 0xFF])
        
        # Image data
        img_data = list(image.tobytes())
        
        # Send data in chunks
        chunk_size = 2048
        for i in range(0, len(img_data), chunk_size):
            chunk = img_data[i:i+chunk_size]
            cmd += bytes(chunk)
            cmd += self.LF
        
        return cmd
    
    # Barcode printing (Code128)
    def print_barcode_code128(self, data: str, 
                             height: int = 50,
                             text_position: int = 2) -> bytes:
        """
        Print barcode using ESC/POS commands.
        
        Args:
            data: Barcode data
            height: Barcode height in dots
            text_position: 0=none, 1=above, 2=below, 3=both
            
        Returns:
            ESC/POS command bytes
        """
        cmd = b''
        
        # Set barcode height
        cmd += self.GS + b'h' + bytes([height])
        
        # Set barcode width (2-6)
        cmd += self.GS + b'w' + bytes([2])
        
        # Set print position
        cmd += self.GS + b'H' + bytes([text_position])
        
        # Set font for HRI (human readable interpretation)
        cmd += self.GS + b'f' + bytes([0])
        
        # Print barcode
        cmd += self.GS + b'k' + bytes([73])  # 73 = CODE128
        
        # Add data with null terminator
        cmd += data.encode('ascii') + b'\x00'
        
        return cmd
    
    # Beep
    def beep(self, count: int = 1, duration: int = 200) -> bytes:
        """Beep command."""
        return self.ESC + b'B' + bytes([count, duration])
    
    # Cash drawer
    def open_cash_drawer(self) -> bytes:
        """Open cash drawer."""
        return self.ESC + b'p' + b'\x00' + b'\x19'


# Global barcode generator instance
barcode_generator = BarcodeGenerator()
label_printer = LabelPrinter()
