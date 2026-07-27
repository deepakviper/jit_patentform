import re
import json
import docx

# Attempt to import ollama for local LLM integration
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

class Extractor:
    """Handles text extraction and dynamic metadata parsing from any uploaded student document."""
    
    def extract_text(self, filepath: str) -> str:
        """Extracts raw text from .docx using python-docx."""
        doc = docx.Document(filepath)
        return "\n".join([para.text for para in doc.paragraphs])

    def parse_details(self, text: str, use_llm: bool = False) -> dict:
        """Routes to either LLM or Regex extraction based on user preference."""
        if use_llm and OLLAMA_AVAILABLE:
            return self._extract_llm(text)
        return self._extract_regex(text)

    def _extract_regex(self, text: str) -> dict:
        """Dynamically extracts metadata from the new file using Regular Expressions."""
        
        metadata = {
            "title_of_invention": "",
            "inventors": [],
            "inventor_address": {
                "house_no": "",
                "street": "",
                "city": "",
                "state": "",
                "country": "India",
                "pin_code": ""
            },
            "abstract": "",
            "description": {
                "technical_field": "",
                "background": "",
                "objectives": "",
                "system_architecture": "",
                "workflow_methodology": "",
                "exemplary_implementation": "",
                "uniqueness": "",
                "references": ""
            }
        }

        # 1. Extract Title dynamically
        title_match = re.search(r"Title of the (?:Project|Invention)[^\n]*:\s*([^\n]+)", text, re.IGNORECASE)
        if title_match:
            metadata["title_of_invention"] = title_match.group(1).strip()

        inventor_match = re.search(r"Names of (?:Project Team Students|Inventors)[\s\S]*?:\s*\n([\s\S]*?)(?:ABSTRACT|DESCRIPTION):", text, re.IGNORECASE)
        if inventor_match:
            raw_lines = inventor_match.group(1).strip().split('\n')
            
            for line in raw_lines:
                clean_line = line.strip().strip(',')
                if not clean_line:
                    continue
                
                lower_line = clean_line.lower()
                # Split by comma to separate Department and Institute if they are on the same line
                if "department" in lower_line or "institute" in lower_line or "college" in lower_line:
                    parts = [p.strip() for p in clean_line.split(',')]
                    for part in parts:
                        lower_part = part.lower()
                        if "department" in lower_part:
                            metadata["inventor_address"]["house_no"] = part
                        elif "institute" in lower_part or "college" in lower_part or "university" in lower_part:
                            metadata["inventor_address"]["street"] = part
                elif "tamil nadu" in lower_line or "india" in lower_line or re.search(r'\d{6}', lower_line):
                    parts = [p.strip() for p in clean_line.split(',')]
                    if len(parts) > 0: metadata["inventor_address"]["city"] = parts[0]
                    metadata["inventor_address"]["state"] = "Tamil Nadu"
                    pin_match = re.search(r'\d{6}', clean_line)
                    if pin_match: metadata["inventor_address"]["pin_code"] = pin_match.group(0)
                elif len(clean_line) > 2:
                    metadata["inventors"].append({
                        "name": clean_line,
                        "nationality": "Indian",
                        "country_of_residence": "India"
                    })

        def extract_section(start_kw, end_kw):
            """Extracts multiline text strictly between two keywords."""
            pattern = rf"{start_kw}(.*?)(?:{end_kw}|$)"
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            return match.group(1).strip() if match else ""

        metadata["abstract"] = extract_section(r"ABSTRACT\s*:", r"DESCRIPTION\s*:|TECHNICAL FIELD")
        metadata["description"]["technical_field"] = extract_section(r"TECHNICAL FIELD OF THE INVENTION", r"BACKGROUND OF THE INVENTION")
        metadata["description"]["background"] = extract_section(r"BACKGROUND OF THE INVENTION", r"OBJECTIVES OF THE INVENTION")
        metadata["description"]["objectives"] = extract_section(r"OBJECTIVES OF THE INVENTION", r"SYSTEM ARCHITECTURE\s*:")
        metadata["description"]["system_architecture"] = extract_section(r"SYSTEM ARCHITECTURE\s*:", r"WORKFLOW METHODOLOGY\s*:")
        metadata["description"]["workflow_methodology"] = extract_section(r"WORKFLOW METHODOLOGY\s*:", r"EXEMPLARY IMPLEMENTATION SCENARIO\s*:")
        metadata["description"]["exemplary_implementation"] = extract_section(r"EXEMPLARY IMPLEMENTATION SCENARIO\s*:", r"UNIQUENESS\s*:")
        metadata["description"]["uniqueness"] = extract_section(r"UNIQUENESS\s*:", r"REFERENCES\s*:")
        metadata["description"]["references"] = extract_section(r"REFERENCES\s*:", r"EOF_IMPOSSIBLE_MATCH") # Pulls to end of file

        return metadata

    def _extract_llm(self, text: str) -> dict:
        """Dynamically extracts all metadata and full text sections using a local Gemma 3 model."""
        
        prompt = f"""
        Analyze the following document text and extract ALL project details, including the full text of each section.
        Return ONLY a valid JSON object matching exactly this structure based on the text provided:
        {{
            "title_of_invention": "Extracted Title Here",
            "inventors": [
                {{"name": "Inventor Name 1", "nationality": "Indian", "country_of_residence": "India"}}
            ],
            "inventor_address": {{
                "house_no": "Extracted Department name ONLY (e.g., Department of CSE)",
                "street": "Extracted Institution name ONLY (e.g., Jeppiaar Institute of Technology)",
                "city": "Extracted City",
                "state": "Extracted State",
                "country": "India",
                "pin_code": "Extracted Pin code"
            }},
            "abstract": "Full text of the abstract",
            "description": {{
                "technical_field": "Full text of Technical Field",
                "background": "Full text of Background",
                "objectives": "Full text of Objectives",
                "system_architecture": "Full text of System Architecture",
                "workflow_methodology": "Full text of Workflow Methodology",
                "exemplary_implementation": "Full text of Exemplary Implementation",
                "uniqueness": "Full text of Uniqueness",
                "references": "Full text of References"
            }}
        }}

        Document Text:
        ---
        {text}
        ---
        """
        try:
            response = ollama.chat(
                model='gemma3',
                messages=[{'role': 'user', 'content': prompt}]
            )
            result_text = response['message']['content'].strip()
            
            # Clean up markdown formatting if present
            result_text = re.sub(r'^```(?:json)?\n?', '', result_text, flags=re.IGNORECASE).strip()
            result_text = re.sub(r'\n?```$', '', result_text).strip()
            
            return json.loads(result_text)
        except Exception as e:
            print(f"LLM Error: {e}. Falling back to Regex.")
            return self._extract_regex(text)