import os
import json
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename

# Import our modularized components
from config import Config
from extractor import Extractor
from generator import FormGenerator

app = Flask(__name__)
app.config.from_object(Config)

# Ensure metadata directory exists for storing JSON outputs
os.makedirs(app.config['METADATA_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    """Serves the frontend upload UI."""
    return render_template('index.html')

@app.route('/api/templates', methods=['GET'])
def get_templates():
    """Returns a list of available template files."""
    templates_dir = app.config['PATENT_TEMPLATES_DIR']
    # Create directory if it doesn't exist just to be safe
    os.makedirs(templates_dir, exist_ok=True)
    
    # Grab all .docx files in the templates folder (Case-insensitive)
    templates = [f for f in os.listdir(templates_dir) if f.lower().endswith('.docx')]
    
    # Print to the console to help you debug
    print(f"👀 Scanning for templates in: {templates_dir}")
    print(f"📄 Found: {templates}")
    
    return jsonify({
        'templates': templates,
        'scanned_path': templates_dir
    })

@app.route('/api/generate', methods=['POST'])
def generate_document():
    """Handles file upload, metadata extraction, and multi-docx generation."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    use_llm = request.form.get('use_llm', 'false').lower() == 'true'
    selected_templates = request.form.getlist('templates')
    
    if not selected_templates:
        return jsonify({'error': 'No templates selected'}), 400
    
    try:
        # 1. Save uploaded file temporarily
        filename = secure_filename(file.filename)
        input_filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(input_filepath)
        
        # 2. Extract Data from uploaded file (Only need to do this once!)
        extractor = Extractor()
        text = extractor.extract_text(input_filepath)
        metadata = extractor.parse_details(text, use_llm=use_llm)
        
        safe_title = metadata.get('title_of_invention', 'Unknown')[:15].replace(' ', '_')
        
        # Save a copy of the extracted metadata to a JSON file for review/debugging
        metadata_filename = f"metadata_{safe_title}.json"
        metadata_filepath = os.path.join(app.config['METADATA_FOLDER'], metadata_filename)
        with open(metadata_filepath, 'w', encoding='utf-8') as json_file:
            json.dump(metadata, json_file, indent=4, ensure_ascii=False)
        print(f"Extracted metadata saved to: {metadata_filepath}")
        
        # 3. Generate requested forms
        generated_files = []
        for tpl_name in selected_templates:
            tpl_path = os.path.join(app.config['PATENT_TEMPLATES_DIR'], tpl_name)
            
            if os.path.exists(tpl_path):
                output_filename = f"{tpl_name.replace('.docx', '')}_{safe_title}.docx"
                output_filepath = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
                
                generator = FormGenerator(
                    template_path=tpl_path, 
                    static_data_path=app.config['STATIC_DATA_PATH']
                )
                generator.generate_docx(metadata, output_filepath)
                
                # Append info for the UI to create a download link
                generated_files.append({
                    'name': output_filename,
                    'url': f"/api/download/{output_filename}"
                })
        
        # Clean up the input file
        if os.path.exists(input_filepath):
            os.remove(input_filepath)
        
        # 4. Return the list of generated files
        return jsonify({'files': generated_files})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<filename>', methods=['GET'])
def download_file(filename):
    """Serves the generated files for download."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    # Ensure templates directory exists for the index.html
    os.makedirs('templates', exist_ok=True)
    print(f"Server starting on http://127.0.0.1:5000")
    print(f"Make sure 'FORM 1.docx' is placed in: {Config.BASE_DIR}")
    app.run(debug=True, port=5000)