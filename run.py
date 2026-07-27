import os
import sys

# Reconfigure stdout/stderr to use UTF-8 to prevent encoding errors on Windows when printing emojis in app.py
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

import time
import subprocess
import platform
import tempfile
import re
from werkzeug.utils import secure_filename

# 1. Setup paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
backend_path = os.path.join(BASE_DIR, "backend")
frontend_path = os.path.join(BASE_DIR, "patentform-main", "frontend")

# 2. Add backend path to sys.path to dynamically import its components
sys.path.insert(0, backend_path)

from flask import request, jsonify, send_file
from app import app
from extractor import Extractor
from generator import FormGenerator
from config import Config

# Helper: format description dictionary to single string
def format_description(desc_dict):
    if not desc_dict:
        return ""
    if isinstance(desc_dict, str):
        return desc_dict
    desc_sections = []
    for key, val in desc_dict.items():
        if val:
            header = key.replace('_', ' ').upper()
            if header == "TECHNICAL FIELD": header = "TECHNICAL FIELD OF THE INVENTION"
            if header == "BACKGROUND": header = "BACKGROUND OF THE INVENTION"
            if header == "OBJECTIVES": header = "OBJECTIVES OF THE INVENTION"
            desc_sections.append(f"{header}\n{val}")
    return "\n\n".join(desc_sections)

# Helper: parse description string back into dict structure expected by Python generator
def parse_description_to_dict(desc_str):
    sections = {
        "technical_field": "",
        "background": "",
        "objectives": "",
        "system_architecture": "",
        "workflow_methodology": "",
        "exemplary_implementation": "",
        "uniqueness": "",
        "references": ""
    }
    
    if not desc_str:
        return sections
        
    headers = [
        ("TECHNICAL FIELD OF THE INVENTION", "technical_field"),
        ("TECHNICAL FIELD", "technical_field"),
        ("BACKGROUND OF THE INVENTION", "background"),
        ("BACKGROUND", "background"),
        ("OBJECTIVES OF THE INVENTION", "objectives"),
        ("OBJECTIVES", "objectives"),
        ("SYSTEM ARCHITECTURE", "system_architecture"),
        ("WORKFLOW METHODOLOGY", "workflow_methodology"),
        ("EXEMPLARY IMPLEMENTATION", "exemplary_implementation"),
        ("UNIQUENESS", "uniqueness"),
        ("REFERENCES", "references")
    ]
    
    found = []
    lower_desc = desc_str.lower()
    for header_name, key in headers:
        idx = lower_desc.find(header_name.lower())
        if idx != -1:
            found.append((idx, len(header_name), key))
            
    # Sort by start index
    found.sort()
    
    # If no headers found, assign the whole text to technical field
    if not found:
        sections["technical_field"] = desc_str.strip()
        return sections
        
    for i in range(len(found)):
        start_idx = found[i][0] + found[i][1]
        end_idx = found[i+1][0] if i + 1 < len(found) else len(desc_str)
        content = desc_str[start_idx:end_idx].strip()
        key = found[i][2]
        if sections[key]:
            sections[key] += "\n\n" + content
        else:
            sections[key] = content
            
    return sections

# 3. Add CORS headers Hook to the Flask app
@app.after_request
def add_cors_headers(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# 4. Implement /api/patent/parse Route
@app.route('/api/patent/parse', methods=['POST', 'OPTIONS'])
def parse_patent():
    if request.method == 'OPTIONS':
        return '', 200
        
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    try:
        # Save file to temp folder
        filename = secure_filename(file.filename)
        temp_dir = tempfile.gettempdir()
        input_filepath = os.path.join(temp_dir, filename)
        file.save(input_filepath)
        
        # Parse data using Extractor
        extractor = Extractor()
        text = extractor.extract_text(input_filepath)
        metadata = extractor.parse_details(text, use_llm=False)
        
        # Clean up input file
        if os.path.exists(input_filepath):
            os.remove(input_filepath)
            
        inv_addr = metadata.get("inventor_address") or {}
        inventors_list = metadata.get("inventors") or []
        
        # Map to React format DTO
        response_data = {
            "applicationType": "Ordinary",
            "applicant": {
                "name": "",
                "nationality": "Indian",
                "country": "India",
                "address": {
                    "street": inv_addr.get("street", ""),
                    "city": inv_addr.get("city", ""),
                    "district": "",
                    "state": inv_addr.get("state", ""),
                    "country": inv_addr.get("country", "India"),
                    "pincode": inv_addr.get("pin_code", "")
                }
            },
            "inventors": [
                {
                    "name": inv.get("name", ""),
                    "nationality": inv.get("nationality", "Indian"),
                    "country": inv.get("country_of_residence", "India")
                }
                for inv in inventors_list
            ],
            "titleOfInvention": metadata.get("title_of_invention", ""),
            "description": format_description(metadata.get("description", {})),
            "claims": "",
            "abstractText": metadata.get("abstract", ""),
            "attachments": {
                "specificationPages": 0,
                "claimsCount": 0,
                "drawingsCount": 0
            }
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# 5. Implement /api/patent/download Route
@app.route('/api/patent/download', methods=['POST', 'OPTIONS'])
def download_patent():
    if request.method == 'OPTIONS':
        return '', 200
        
    react_data = request.json or {}
    formType = request.args.get('formType', 'form1')
    
    try:
        # Reconstruct metadata for generator.py
        app_data = react_data.get("applicant") or {}
        addr_data = app_data.get("address") or {}
        
        python_metadata = {
            "title_of_invention": react_data.get("titleOfInvention", ""),
            "abstract": react_data.get("abstractText", ""),
            "description": parse_description_to_dict(react_data.get("description", "")),
            "applicant": {
                "name": app_data.get("name", ""),
                "nationality": app_data.get("nationality", "Indian"),
                "country_of_residence": app_data.get("country", "India"),
                "address": {
                    "house_no": "",
                    "street": addr_data.get("street", ""),
                    "city": addr_data.get("city", ""),
                    "state": addr_data.get("state", ""),
                    "country": addr_data.get("country", "India"),
                    "pin_code": addr_data.get("pincode", "")
                }
            },
            "inventor_address": {
                "house_no": "",
                "street": addr_data.get("street", ""),
                "city": addr_data.get("city", ""),
                "state": addr_data.get("state", ""),
                "country": addr_data.get("country", "India"),
                "pin_code": addr_data.get("pincode", "")
            },
            "inventors": [
                {
                    "name": inv.get("name", ""),
                    "nationality": inv.get("nationality", "Indian"),
                    "country_of_residence": inv.get("country", "India")
                }
                for inv in react_data.get("inventors") or []
            ]
        }
        
        # Load appropriate template file
        form_map = {
            "form1": "Form 1.docx",
            "form2": "Form 2.docx",
            "form3": "Form 3.docx",
            "form5": "Form 5.docx",
            "form9": "Form 9.docx",
            "form28": "Form 28.docx"
        }
        template_filename = form_map.get(formType.lower(), "Form 1.docx")
        
        templates_dir = os.path.join(backend_path, 'patent_templates')
        template_path = os.path.join(templates_dir, template_filename)
        
        if not os.path.exists(template_path):
            return jsonify({'error': f"Template file {template_filename} not found."}), 404
            
        output_filename = f"Filled_Patent_{template_filename.replace(' ', '_')}"
        temp_dir = tempfile.gettempdir()
        output_filepath = os.path.join(temp_dir, output_filename)
        
        static_data_path = os.path.join(backend_path, 'static_data.json')
        generator = FormGenerator(template_path=template_path, static_data_path=static_data_path)
        generator.generate_docx(python_metadata, output_filepath)
        
        return send_file(output_filepath, as_attachment=True, download_name=output_filename)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# 6. Main runner
if __name__ == '__main__':
    vite_process = None
    try:
        # Start React frontend via Vite
        print(f"[*] Starting React frontend (Vite) in: {frontend_path}")
        cmd = "npm.cmd" if platform.system() == "Windows" else "npm"
        vite_process = subprocess.Popen(
            [cmd, "run", "dev"],
            cwd=frontend_path
        )
        time.sleep(2)
        
        # Start Flask app on port 8080 (debug=False to prevent double process spawn)
        print("[*] Starting Flask backend on http://localhost:8080...")
        app.run(host='0.0.0.0', port=8080, debug=False)
        
    except KeyboardInterrupt:
        print("\n[!] Stopping server processes...")
    finally:
        if vite_process:
            print("[*] Terminating Vite process...")
            vite_process.terminate()
            try:
                vite_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                vite_process.kill()
        print("[*] Clean exit.")
