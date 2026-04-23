"""Form tools - auto-fill, template-based, multi-doc reference."""
import json, time
from typing import Dict, List, Any, Optional
from ..storage import get_db

def register_tools(registry):
    from ..forms.engine import list_available_templates, create_form_from_template, extract_form_fields, AutoFillEngine
    
    @registry.tool("form_list_templates", "List all available form templates for auto-fill.")
    def list_form_templates() -> Dict:
        templates = list_available_templates()
        return {"templates": templates, "count": len(templates)}
    
    @registry.tool("form_create", "Create a form from a named template.", {
        "template_name": "Name of the template (e.g. visa_application, job_application, government_form)"
    })
    def create_form(template_name: str) -> Dict:
        try:
            form = create_form_from_template(template_name)
            return {"success": True, "form": {"name": form.name, "type": form.type, "fields": [{"name": f.name, "type": f.type, "label": f.label, "required": f.required} for f in form.fields]}}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @registry.tool("form_extract_fields", "Extract form fields from a document file.")
    def extract_fields(file_path: str) -> Dict:
        try:
            form = extract_form_fields(file_path)
            return {"success": True, "form": {"name": form.name, "type": form.type, "fields": [{"name": f.name, "type": f.type, "label": f.label} for f in form.fields]}}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @registry.tool("form_fill", "Auto-fill a form using reference documents and user profile.", {
        "form_type": "Type of form template to create",
        "reference_docs": "List of document paths to extract data from",
        "user_profile": "Dict of known user data (name, address, etc)"
    })
    def fill_form(form_type: str, reference_docs: List[str] = None, user_profile: Dict = None) -> Dict:
        try:
            form = create_form_from_template(form_type)
            engine = AutoFillEngine(None)
            filled = engine.fill_form(form, reference_docs or [], user_profile or {})
            return {"success": True, "filled_fields": [{"name": f.name, "value": f.value, "confidence": f.confidence} for f in filled.fields]}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @registry.tool("form_export", "Export a filled form as JSON or text.")
    def export_form(form_data: Dict, format: str = "json") -> str:
        if format == "json":
            return json.dumps(form_data, indent=2)
        elif format == "text":
            lines = [f"=== {form_data.get('name', 'Form')} ==="]
            for k, v in form_data.get("fields", {}).items():
                lines.append(f"{k}: {v}")
            return "\n".join(lines)
        return str(form_data)
