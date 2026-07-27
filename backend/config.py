import os
import tempfile

class Config:
    """Application configuration and file path settings."""
    
    # Base directory of the application
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Upload settings
    UPLOAD_FOLDER = tempfile.gettempdir()
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max limit
    
    # Directory to store extracted metadata JSON files for template editing
    METADATA_FOLDER = os.path.join(BASE_DIR, 'extracted_data')
    
    # Templates directory (Move your FORM 1.docx and any other forms here)
    PATENT_TEMPLATES_DIR = os.path.join(BASE_DIR, 'patent_templates')
    
    # File Paths
    STATIC_DATA_PATH = os.path.join(BASE_DIR, 'static_data.json')