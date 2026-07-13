import os
import uuid
import pandas as pd
from werkzeug.utils import secure_filename
from flask import current_app
from PIL import Image
import csv
from datetime import datetime

class FileManager:
    """File upload and download manager for the POS system."""

    ALLOWED_EXTENSIONS = {
        'images': {'png', 'jpg', 'jpeg', 'gif', 'webp'},
        'documents': {'pdf', 'csv', 'xlsx', 'xls'},
        'backups': {'zip', 'sql'}
    }

    MAX_FILE_SIZE = {
        'images': 5 * 1024 * 1024,  # 5MB
        'documents': 10 * 1024 * 1024,  # 10MB
        'backups': 100 * 1024 * 1024  # 100MB
    }

    @staticmethod
    def allowed_file(filename, file_type='images'):
        """Check if file extension is allowed."""
        if '.' not in filename:
            return False
        ext = filename.rsplit('.', 1)[1].lower()
        return ext in FileManager.ALLOWED_EXTENSIONS.get(file_type, set())

    @staticmethod
    def get_file_size(file):
        """Get file size in bytes."""
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)
        return size

    @staticmethod
    def validate_file(file, file_type='images'):
        """Validate file type and size."""
        if not file or not file.filename:
            return False, "No file provided"

        if not FileManager.allowed_file(file.filename, file_type):
            return False, f"File type not allowed. Allowed types: {', '.join(FileManager.ALLOWED_EXTENSIONS[file_type])}"

        file_size = FileManager.get_file_size(file)
        max_size = FileManager.MAX_FILE_SIZE.get(file_type, 1024 * 1024)  # Default 1MB

        if file_size > max_size:
            return False, f"File too large. Maximum size: {max_size / (1024*1024):.1f}MB"

        return True, "File is valid"

    @staticmethod
    def save_image(file, subfolder='products'):
        """Save and process image file."""
        if not file or not file.filename:
            return None

        # Validate file
        is_valid, message = FileManager.validate_file(file, 'images')
        if not is_valid:
            raise ValueError(message)

        # Generate unique filename
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}.{ext}"

        # Create upload directory
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', subfolder)
        os.makedirs(upload_dir, exist_ok=True)

        # Save original file
        file_path = os.path.join(upload_dir, unique_filename)
        file.save(file_path)

        # Process image (resize if too large)
        try:
            with Image.open(file_path) as img:
                # Resize if larger than 800px on any side
                max_size = (800, 800)
                if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                    img.thumbnail(max_size, Image.Resampling.LANCZOS)
                    img.save(file_path, quality=85, optimize=True)
        except Exception as e:
            current_app.logger.warning(f"Could not process image {filename}: {str(e)}")

        return f"uploads/{subfolder}/{unique_filename}"
    
    @staticmethod
    def save_profile_picture(file, rotation=0):
        """Save and optimize profile picture file (500x500).
        
        Args:
            file: Werkzeug file object
            rotation: Rotation angle in degrees (0, 90, 180, 270)
        """
        if not file or not file.filename:
            return None

        # Validate file
        is_valid, message = FileManager.validate_file(file, 'images')
        if not is_valid:
            raise ValueError(message)

        # Generate unique filename
        filename = secure_filename(file.filename)
        ext = 'png'  # Always convert to PNG for profiles
        unique_filename = f"{uuid.uuid4().hex}.{ext}"

        # Create upload directory
        upload_dir = os.path.join(os.path.dirname(current_app.root_path), 'uploads', 'profiles')
        os.makedirs(upload_dir, exist_ok=True)

        # Save original file temporarily
        file_path = os.path.join(upload_dir, unique_filename)
        file.save(file_path)

        # Process image - optimize for profile
        try:
            with Image.open(file_path) as img:
                # Rotate if needed
                if rotation:
                    rotation = int(rotation) % 360
                    if rotation == 90:
                        img = img.rotate(-90, expand=False)
                    elif rotation == 180:
                        img = img.rotate(180, expand=False)
                    elif rotation == 270:
                        img = img.rotate(90, expand=False)
                
                # Convert to RGB if necessary
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'RGBA':
                        background.paste(img, mask=img.split()[3])
                    else:
                        background.paste(img)
                    img = background
                
                # Auto-crop to 500x500 from center
                # Calculate the crop box (square, centered)
                width, height = img.size
                size = min(width, height)
                left = (width - size) // 2
                top = (height - size) // 2
                right = left + size
                bottom = top + size
                
                img = img.crop((left, top, right, bottom))
                
                # Resize to exactly 500x500
                if img.size != (500, 500):
                    img = img.resize((500, 500), Image.Resampling.LANCZOS)
                
                # Save with high quality
                img.save(file_path, 'PNG', quality=90, optimize=True)
        except Exception as e:
            current_app.logger.warning(f"Could not process profile picture {filename}: {str(e)}")

        return f"uploads/profiles/{unique_filename}"

    @staticmethod
    def delete_file(file_path):
        """Delete a file from the filesystem."""
        if not file_path:
            return

        # Remove 'static/' prefix if present
        if file_path.startswith('static/'):
            file_path = file_path[7:]
        elif file_path.startswith('/static/'):
            file_path = file_path[8:]

        full_path = os.path.join(current_app.root_path, 'static', file_path)

        try:
            if os.path.exists(full_path):
                os.remove(full_path)
        except Exception as e:
            current_app.logger.error(f"Could not delete file {file_path}: {str(e)}")

    @staticmethod
    def export_to_csv(data, filename, fields=None):
        """Export data to CSV format."""
        if not data:
            return None

        # Create exports directory
        export_dir = os.path.join(current_app.root_path, 'static', 'exports')
        os.makedirs(export_dir, exist_ok=True)

        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{filename}_{timestamp}.csv"
        file_path = os.path.join(export_dir, unique_filename)

        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                if fields:
                    writer = csv.DictWriter(csvfile, fieldnames=fields)
                    writer.writeheader()
                    for row in data:
                        writer.writerow({field: row.get(field, '') for field in fields})
                else:
                    # Auto-detect fields from first row
                    if isinstance(data[0], dict):
                        fieldnames = list(data[0].keys())
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(data)

            return f"exports/{unique_filename}"

        except Exception as e:
            current_app.logger.error(f"Could not export to CSV: {str(e)}")
            return None

    @staticmethod
    def export_to_excel(data, filename, fields=None):
        """Export data to Excel format."""
        if not data:
            return None

        # Create exports directory
        export_dir = os.path.join(current_app.root_path, 'static', 'exports')
        os.makedirs(export_dir, exist_ok=True)

        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{filename}_{timestamp}.xlsx"
        file_path = os.path.join(export_dir, unique_filename)

        try:
            if fields:
                df = pd.DataFrame(data)[fields]
            else:
                df = pd.DataFrame(data)

            df.to_excel(file_path, index=False, engine='openpyxl')
            return f"exports/{unique_filename}"

        except Exception as e:
            current_app.logger.error(f"Could not export to Excel: {str(e)}")
            return None

    @staticmethod
    def import_from_csv(file_path, required_fields=None):
        """Import data from CSV file."""
        try:
            df = pd.read_csv(file_path)

            # Validate required fields
            if required_fields:
                missing_fields = [field for field in required_fields if field not in df.columns]
                if missing_fields:
                    raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

            return df.to_dict('records')

        except Exception as e:
            current_app.logger.error(f"Could not import from CSV: {str(e)}")
            raise

    @staticmethod
    def import_from_excel(file_path, required_fields=None):
        """Import data from Excel file."""
        try:
            df = pd.read_excel(file_path, engine='openpyxl')

            # Validate required fields
            if required_fields:
                missing_fields = [field for field in required_fields if field not in df.columns]
                if missing_fields:
                    raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

            return df.to_dict('records')

        except Exception as e:
            current_app.logger.error(f"Could not import from Excel: {str(e)}")
            raise

    @staticmethod
    def create_backup_filename():
        """Generate a backup filename with timestamp."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"backup_{timestamp}.zip"
