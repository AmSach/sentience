"""
Agent Tools for Sentience v3.0 Forms Module
Provides tools for AI agents to interact with PDF/DOCX forms.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Type
from dataclasses import dataclass, asdict

from .pdf_engine import PDFEngine, fill_pdf_form, get_pdf_fields
from .docx_engine import DOCXEngine, fill_docx_template, mail_merge_docs, get_docx_fields
from .field_detector import FieldDetector, DetectedField, DetectedFieldType
from .filler import FormFiller, fill_form, bulk_fill_forms
from .templates import (
    TemplateManager,
    Template,
    TemplateVariable,
    TemplateType,
)

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Standard result format for agent tools."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FormTools:
    """
    Collection of tools for AI agents to interact with forms.
    
    Tools:
    - fill_pdf: Fill a PDF form with data
    - fill_docx: Fill a DOCX template with data
    - detect_fields: Detect fields in a PDF or DOCX
    - create_template: Create a template from a file
    - list_templates: List available templates
    - fill_template: Fill a stored template
    - bulk_fill: Fill multiple forms at once
    """
    
    def __init__(self, storage_dir: Optional[Union[str, Path]] = None):
        """Initialize form tools."""
        self.template_manager = TemplateManager(storage_dir)
        self.filler = FormFiller()
        self.detector = FieldDetector()
    
    # ==================== PDF Tools ====================
    
    def fill_pdf(
        self,
        pdf_path: str,
        field_values: Dict[str, Any],
        output_path: str,
        validate: bool = True
    ) -> ToolResult:
        """
        Fill a PDF form with provided field values.
        
        Args:
            pdf_path: Path to the source PDF file.
            field_values: Dictionary mapping field names to values.
            output_path: Path to save the filled PDF.
            validate: Whether to validate values before filling.
            
        Returns:
            ToolResult with success status and details.
        """
        try:
            pdf_path = Path(pdf_path)
            output_path = Path(output_path)
            
            if not pdf_path.exists():
                return ToolResult(
                    success=False,
                    message="PDF file not found",
                    error=f"File not found: {pdf_path}"
                )
            
            # Detect fields first
            self.detector.detect_pdf_fields(pdf_path)
            
            # Validate if requested
            if validate:
                errors = self.detector.validate_values(field_values)
                if errors:
                    return ToolResult(
                        success=False,
                        message="Validation failed",
                        data={"validation_errors": errors}
                    )
            
            # Fill the form
            result = fill_pdf_form(pdf_path, field_values, output_path)
            
            return ToolResult(
                success=True,
                message=f"Successfully filled PDF with {len(field_values)} values",
                data={
                    "output_path": str(output_path),
                    "fields_filled": len(field_values),
                    "field_summary": result.get("field_summary", {})
                }
            )
            
        except Exception as e:
            logger.error(f"fill_pdf failed: {e}")
            return ToolResult(
                success=False,
                message="Failed to fill PDF",
                error=str(e)
            )
    
    def detect_pdf_fields(
        self,
        pdf_path: str
    ) -> ToolResult:
        """
        Detect all form fields in a PDF.
        
        Args:
            pdf_path: Path to the PDF file.
            
        Returns:
            ToolResult with detected fields and their types.
        """
        try:
            pdf_path = Path(pdf_path)
            
            if not pdf_path.exists():
                return ToolResult(
                    success=False,
                    message="PDF file not found",
                    error=f"File not found: {pdf_path}"
                )
            
            fields = self.detector.detect_pdf_fields(pdf_path)
            schema = self.detector.get_field_schema()
            
            # Build readable field list
            field_list = [
                {
                    "name": name,
                    "type": field.field_type.value,
                    "required": field.metadata.get("required", False),
                    "options": field.metadata.get("options", [])
                }
                for name, field in fields.items()
            ]
            
            return ToolResult(
                success=True,
                message=f"Detected {len(fields)} fields in PDF",
                data={
                    "total_fields": len(fields),
                    "fields": field_list,
                    "schema": schema
                }
            )
            
        except Exception as e:
            logger.error(f"detect_pdf_fields failed: {e}")
            return ToolResult(
                success=False,
                message="Failed to detect PDF fields",
                error=str(e)
            )
    
    # ==================== DOCX Tools ====================
    
    def fill_docx(
        self,
        docx_path: str,
        values: Dict[str, Any],
        output_path: str,
        preserve_style: bool = True
    ) -> ToolResult:
        """
        Fill a DOCX template with provided values.
        
        Args:
            docx_path: Path to the source DOCX template.
            values: Dictionary mapping placeholder names to values.
            output_path: Path to save the filled DOCX.
            preserve_style: Whether to preserve text formatting.
            
        Returns:
            ToolResult with success status and details.
        """
        try:
            docx_path = Path(docx_path)
            output_path = Path(output_path)
            
            if not docx_path.exists():
                return ToolResult(
                    success=False,
                    message="DOCX file not found",
                    error=f"File not found: {docx_path}"
                )
            
            result = fill_docx_template(docx_path, values, output_path, preserve_style)
            
            return ToolResult(
                success=True,
                message=f"Successfully filled DOCX with {len(values)} values",
                data={
                    "output_path": str(output_path),
                    "fields_filled": len(values),
                    "field_summary": result.get("field_summary", {})
                }
            )
            
        except Exception as e:
            logger.error(f"fill_docx failed: {e}")
            return ToolResult(
                success=False,
                message="Failed to fill DOCX",
                error=str(e)
            )
    
    def detect_docx_fields(
        self,
        docx_path: str,
        placeholder_style: str = "curly_braces"
    ) -> ToolResult:
        """
        Detect all placeholder fields in a DOCX template.
        
        Args:
            docx_path: Path to the DOCX file.
            placeholder_style: Style of placeholders (curly_braces, double_brackets, percent).
            
        Returns:
            ToolResult with detected placeholders.
        """
        try:
            docx_path = Path(docx_path)
            
            if not docx_path.exists():
                return ToolResult(
                    success=False,
                    message="DOCX file not found",
                    error=f"File not found: {docx_path}"
                )
            
            fields = self.detector.detect_docx_fields(docx_path, placeholder_style)
            schema = self.detector.get_field_schema()
            
            field_list = [
                {
                    "name": name,
                    "type": field.field_type.value,
                    "placeholder": field.placeholder,
                    "location": field.metadata.get("location", "text")
                }
                for name, field in fields.items()
            ]
            
            return ToolResult(
                success=True,
                message=f"Detected {len(fields)} placeholders in DOCX",
                data={
                    "total_fields": len(fields),
                    "fields": field_list,
                    "schema": schema,
                    "placeholder_style": placeholder_style
                }
            )
            
        except Exception as e:
            logger.error(f"detect_docx_fields failed: {e}")
            return ToolResult(
                success=False,
                message="Failed to detect DOCX fields",
                error=str(e)
            )
    
    def mail_merge(
        self,
        template_path: str,
        data_rows: List[Dict[str, Any]],
        output_dir: str
    ) -> ToolResult:
        """
        Perform mail merge on a DOCX template.
        
        Args:
            template_path: Path to DOCX template.
            data_rows: List of data dictionaries for each output.
            output_dir: Directory for generated documents.
            
        Returns:
            ToolResult with list of generated files.
        """
        try:
            template_path = Path(template_path)
            output_dir = Path(output_dir)
            
            if not template_path.exists():
                return ToolResult(
                    success=False,
                    message="Template file not found",
                    error=f"File not found: {template_path}"
                )
            
            files = mail_merge_docs(template_path, data_rows, output_dir)
            
            return ToolResult(
                success=True,
                message=f"Generated {len(files)} documents via mail merge",
                data={
                    "documents_generated": len(files),
                    "output_files": [str(f) for f in files],
                    "output_directory": str(output_dir)
                }
            )
            
        except Exception as e:
            logger.error(f"mail_merge failed: {e}")
            return ToolResult(
                success=False,
                message="Failed to perform mail merge",
                error=str(e)
            )
    
    # ==================== Template Tools ====================
    
    def create_template(
        self,
        name: str,
        source_file: str,
        description: str = "",
        category: str = "general",
        tags: List[str] = None
    ) -> ToolResult:
        """
        Create a new template from a file.
        
        Args:
            name: Name for the template.
            source_file: Path to source PDF or DOCX file.
            description: Template description.
            category: Template category.
            tags: List of tags for organization.
            
        Returns:
            ToolResult with created template details.
        """
        try:
            source_file = Path(source_file)
            
            if not source_file.exists():
                return ToolResult(
                    success=False,
                    message="Source file not found",
                    error=f"File not found: {source_file}"
                )
            
            template = self.template_manager.create_template(
                name=name,
                source_file=source_file,
                description=description,
                category=category,
                tags=tags or []
            )
            
            return ToolResult(
                success=True,
                message=f"Created template: {name}",
                data={
                    "template_id": template.template_id,
                    "name": template.name,
                    "type": template.template_type.value,
                    "variables": [asdict(v) for v in template.variables],
                    "variable_count": len(template.variables)
                }
            )
            
        except Exception as e:
            logger.error(f"create_template failed: {e}")
            return ToolResult(
                success=False,
                message="Failed to create template",
                error=str(e)
            )
    
    def get_template(self, template_id: str) -> ToolResult:
        """
        Get a stored template by ID or name.
        
        Args:
            template_id: Template ID or name.
            
        Returns:
            ToolResult with template details.
        """
        try:
            # Try by ID first
            template = self.template_manager.get_template(template_id)
            
            # Try by name if not found
            if not template:
                template = self.template_manager.get_template_by_name(template_id)
            
            if not template:
                return ToolResult(
                    success=False,
                    message="Template not found",
                    error=f"No template with ID/name: {template_id}"
                )
            
            return ToolResult(
                success=True,
                message=f"Found template: {template.name}",
                data={
                    "template_id": template.template_id,
                    "name": template.name,
                    "description": template.description,
                    "type": template.template_type.value,
                    "category": template.category,
                    "tags": template.tags,
                    "variables": [asdict(v) for v in template.variables],
                    "current_version": template.current_version,
                    "created_at": template.created_at,
                    "updated_at": template.updated_at
                }
            )
            
        except Exception as e:
            logger.error(f"get_template failed: {e}")
            return ToolResult(
                success=False,
                message="Failed to get template",
                error=str(e)
            )
    
    def list_templates(
        self,
        category: str = None,
        template_type: str = None,
        tags: List[str] = None,
        search: str = None
    ) -> ToolResult:
        """
        List available templates with optional filtering.
        
        Args:
            category: Filter by category.
            template_type: Filter by type ('pdf' or 'docx').
            tags: Filter by tags.
            search: Search in name and description.
            
        Returns:
            ToolResult with list of templates.
        """
        try:
            type_enum = None
            if template_type:
                type_enum = TemplateType(template_type.lower())
            
            templates = self.template_manager.list_templates(
                category=category,
                template_type=type_enum,
                tags=tags,
                search=search
            )
            
            template_list = [
                {
                    "template_id": t.template_id,
                    "name": t.name,
                    "type": t.template_type.value,
                    "category": t.category,
                    "variable_count": len(t.variables),
                    "current_version": t.current_version
                }
                for t in templates
            ]
            
            return ToolResult(
                success=True,
                message=f"Found {len(templates)} templates",
                data={
                    "total": len(templates),
                    "templates": template_list
                }
            )
            
        except Exception as e:
            logger.error(f"list_templates failed: {e}")
            return ToolResult(
                success=False,
                message="Failed to list templates",
                error=str(e)
            )
    
    def delete_template(
        self,
        template_id: str,
        keep_files: bool = False
    ) -> ToolResult:
        """
        Delete a template.
        
        Args:
            template_id: Template ID or name.
            keep_files: Whether to keep the stored files.
            
        Returns:
            ToolResult with deletion status.
        """
        try:
            # Get template first for name
            template = self.template_manager.get_template(template_id)
            if not template:
                template = self.template_manager.get_template_by_name(template_id)
                if template:
                    template_id = template.template_id
            
            deleted = self.template_manager.delete_template(
                template_id, keep_files=keep_files
            )
            
            if deleted:
                return ToolResult(
                    success=True,
                    message=f"Deleted template: {template_id}"
                )
            else:
                return ToolResult(
                    success=False,
                    message="Template not found",
                    error=f"No template with ID: {template_id}"
                )
            
        except Exception as e:
            logger.error(f"delete_template failed: {e}")
            return ToolResult(
                success=False,
                message="Failed to delete template",
                error=str(e)
            )
    
    def fill_template(
        self,
        template_id: str,
        data: Dict[str, Any],
        output_path: str,
        validate: bool = True
    ) -> ToolResult:
        """
        Fill a stored template with data.
        
        Args:
            template_id: Template ID or name.
            data: Data dictionary to fill.
            output_path: Path to save the filled form.
            validate: Whether to validate before filling.
            
        Returns:
            ToolResult with fill results.
        """
        try:
            # Get template
            template = self.template_manager.get_template(template_id)
            if not template:
                template = self.template_manager.get_template_by_name(template_id)
            
            if not template:
                return ToolResult(
                    success=False,
                    message="Template not found",
                    error=f"No template with ID/name: {template_id}"
                )
            
            # Get template file
            template_file = self.template_manager.get_template_file(template.template_id)
            if not template_file:
                return ToolResult(
                    success=False,
                    message="Template file not found",
                    error="The template's file is missing from storage"
                )
            
            # Auto-map fields
            self.filler.auto_map_fields(template_file, list(data.keys()))
            
            # Fill the form
            result = self.filler.fill_auto(
                template_file,
                data,
                output_path,
                validate=validate
            )
            
            return ToolResult(
                success=result.get("success", True),
                message=f"Filled template: {template.name}",
                data={
                    "output_path": str(output_path),
                    "template_name": template.name,
                    "template_type": template.template_type.value,
                    "fields_filled": result.get("fields_filled", len(data)),
                    "validation_errors": result.get("validation_errors")
                }
            )
            
        except Exception as e:
            logger.error(f"fill_template failed: {e}")
            return ToolResult(
                success=False,
                message="Failed to fill template",
                error=str(e)
            )
    
    def bulk_fill(
        self,
        template_id: str,
        data_rows: List[Dict[str, Any]],
        output_dir: str,
        filename_template: str = "filled_{index}.{ext}"
    ) -> ToolResult:
        """
        Fill multiple forms from a template with different data.
        
        Args:
            template_id: Template ID or name.
            data_rows: List of data dictionaries.
            output_dir: Output directory for filled forms.
            filename_template: Template for output filenames.
            
        Returns:
            ToolResult with bulk fill results.
        """
        try:
            # Get template
            template = self.template_manager.get_template(template_id)
            if not template:
                template = self.template_manager.get_template_by_name(template_id)
            
            if not template:
                return ToolResult(
                    success=False,
                    message="Template not found",
                    error=f"No template with ID/name: {template_id}"
                )
            
            template_file = self.template_manager.get_template_file(template.template_id)
            if not template_file:
                return ToolResult(
                    success=False,
                    message="Template file not found",
                    error="The template's file is missing from storage"
                )
            
            # Auto-map from first row
            if data_rows:
                self.filler.auto_map_fields(template_file, list(data_rows[0].keys()))
            
            # Bulk fill
            results = self.filler.bulk_fill(
                template_file,
                data_rows,
                output_dir,
                filename_template,
                continue_on_error=True
            )
            
            successful = sum(1 for r in results if r.get("success", False))
            failed = len(results) - successful
            
            return ToolResult(
                success=successful > 0,
                message=f"Bulk fill complete: {successful} succeeded, {failed} failed",
                data={
                    "total": len(data_rows),
                    "successful": successful,
                    "failed": failed,
                    "results": results,
                    "output_directory": str(output_dir)
                }
            )
            
        except Exception as e:
            logger.error(f"bulk_fill failed: {e}")
            return ToolResult(
                success=False,
                message="Failed to perform bulk fill",
                error=str(e)
            )
    
    # ==================== Utility Tools ====================
    
    def detect_fields(
        self,
        file_path: str,
        placeholder_style: str = "curly_braces"
    ) -> ToolResult:
        """
        Detect fields in any supported file (PDF or DOCX).
        
        Args:
            file_path: Path to the file.
            placeholder_style: For DOCX, the placeholder style.
            
        Returns:
            ToolResult with detected fields.
        """
        try:
            file_path = Path(file_path)
            
            if not file_path.exists():
                return ToolResult(
                    success=False,
                    message="File not found",
                    error=f"File not found: {file_path}"
                )
            
            suffix = file_path.suffix.lower()
            
            if suffix == ".pdf":
                return self.detect_pdf_fields(str(file_path))
            elif suffix in (".docx", ".doc"):
                return self.detect_docx_fields(str(file_path), placeholder_style)
            else:
                return ToolResult(
                    success=False,
                    message="Unsupported file type",
                    error=f"Unsupported file extension: {suffix}"
                )
            
        except Exception as e:
            logger.error(f"detect_fields failed: {e}")
            return ToolResult(
                success=False,
                message="Failed to detect fields",
                error=str(e)
            )
    
    def validate_data(
        self,
        file_path: str,
        data: Dict[str, Any]
    ) -> ToolResult:
        """
        Validate data against form fields.
        
        Args:
            file_path: Path to form/template.
            data: Data dictionary to validate.
            
        Returns:
            ToolResult with validation results.
        """
        try:
            file_path = Path(file_path)
            
            if not file_path.exists():
                return ToolResult(
                    success=False,
                    message="File not found",
                    error=f"File not found: {file_path}"
                )
            
            suffix = file_path.suffix.lower()
            
            if suffix == ".pdf":
                self.detector.detect_pdf_fields(file_path)
            else:
                self.detector.detect_docx_fields(file_path)
            
            errors = self.detector.validate_values(data)
            
            if errors:
                return ToolResult(
                    success=False,
                    message="Validation failed",
                    data={
                        "valid": False,
                        "validation_errors": errors,
                        "fields_with_errors": list(errors.keys())
                    }
                )
            else:
                return ToolResult(
                    success=True,
                    message="Data is valid",
                    data={
                        "valid": True,
                        "fields_validated": len(data)
                    }
                )
            
        except Exception as e:
            logger.error(f"validate_data failed: {e}")
            return ToolResult(
                success=False,
                message="Failed to validate data",
                error=str(e)
            )
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Get tool definitions for agent registration.
        
        Returns:
            List of tool definition dictionaries.
        """
        return [
            {
                "name": "fill_pdf",
                "description": "Fill a PDF form with provided field values",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pdf_path": {"type": "string", "description": "Path to source PDF"},
                        "field_values": {"type": "object", "description": "Field name to value mapping"},
                        "output_path": {"type": "string", "description": "Path to save filled PDF"},
                        "validate": {"type": "boolean", "default": True, "description": "Validate before filling"}
                    },
                    "required": ["pdf_path", "field_values", "output_path"]
                }
            },
            {
                "name": "fill_docx",
                "description": "Fill a DOCX template with provided values",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "docx_path": {"type": "string", "description": "Path to source DOCX"},
                        "values": {"type": "object", "description": "Placeholder to value mapping"},
                        "output_path": {"type": "string", "description": "Path to save filled DOCX"},
                        "preserve_style": {"type": "boolean", "default": True, "description": "Preserve text formatting"}
                    },
                    "required": ["docx_path", "values", "output_path"]
                }
            },
            {
                "name": "detect_fields",
                "description": "Detect form fields in a PDF or DOCX file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to file"},
                        "placeholder_style": {"type": "string", "default": "curly_braces", "description": "Placeholder style for DOCX"}
                    },
                    "required": ["file_path"]
                }
            },
            {
                "name": "create_template",
                "description": "Create a new template from a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Template name"},
                        "source_file": {"type": "string", "description": "Path to source file"},
                        "description": {"type": "string", "default": "", "description": "Template description"},
                        "category": {"type": "string", "default": "general", "description": "Template category"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags for organization"}
                    },
                    "required": ["name", "source_file"]
                }
            },
            {
                "name": "list_templates",
                "description": "List available templates with optional filtering",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "description": "Filter by category"},
                        "template_type": {"type": "string", "description": "Filter by type (pdf/docx)"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "Filter by tags"},
                        "search": {"type": "string", "description": "Search in name/description"}
                    }
                }
            },
            {
                "name": "fill_template",
                "description": "Fill a stored template with data",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "template_id": {"type": "string", "description": "Template ID or name"},
                        "data": {"type": "object", "description": "Data to fill"},
                        "output_path": {"type": "string", "description": "Path to save filled form"},
                        "validate": {"type": "boolean", "default": True, "description": "Validate before filling"}
                    },
                    "required": ["template_id", "data", "output_path"]
                }
            },
            {
                "name": "bulk_fill",
                "description": "Fill multiple forms from a template with different data",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "template_id": {"type": "string", "description": "Template ID or name"},
                        "data_rows": {"type": "array", "items": {"type": "object"}, "description": "List of data dictionaries"},
                        "output_dir": {"type": "string", "description": "Output directory"},
                        "filename_template": {"type": "string", "default": "filled_{index}.{ext}", "description": "Filename template"}
                    },
                    "required": ["template_id", "data_rows", "output_dir"]
                }
            },
            {
                "name": "mail_merge",
                "description": "Perform mail merge on a DOCX template",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "template_path": {"type": "string", "description": "Path to DOCX template"},
                        "data_rows": {"type": "array", "items": {"type": "object"}, "description": "List of data dictionaries"},
                        "output_dir": {"type": "string", "description": "Output directory"}
                    },
                    "required": ["template_path", "data_rows", "output_dir"]
                }
            },
            {
                "name": "validate_data",
                "description": "Validate data against form fields",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to form/template"},
                        "data": {"type": "object", "description": "Data to validate"}
                    },
                    "required": ["file_path", "data"]
                }
            }
        ]


# Module-level tool instance for convenience
_default_tools = None


def get_tools(storage_dir: Optional[Union[str, Path]] = None) -> FormTools:
    """Get or create default FormTools instance."""
    global _default_tools
    if _default_tools is None:
        _default_tools = FormTools(storage_dir)
    return _default_tools


# Expose tool functions at module level
def fill_pdf(pdf_path: str, field_values: Dict, output_path: str, **kwargs) -> Dict:
    """Module-level fill_pdf tool."""
    return get_tools().fill_pdf(pdf_path, field_values, output_path, **kwargs).to_dict()


def fill_docx(docx_path: str, values: Dict, output_path: str, **kwargs) -> Dict:
    """Module-level fill_docx tool."""
    return get_tools().fill_docx(docx_path, values, output_path, **kwargs).to_dict()


def detect_fields(file_path: str, **kwargs) -> Dict:
    """Module-level detect_fields tool."""
    return get_tools().detect_fields(file_path, **kwargs).to_dict()


def create_template(name: str, source_file: str, **kwargs) -> Dict:
    """Module-level create_template tool."""
    return get_tools().create_template(name, source_file, **kwargs).to_dict()


def list_templates(**kwargs) -> Dict:
    """Module-level list_templates tool."""
    return get_tools().list_templates(**kwargs).to_dict()


def fill_template(template_id: str, data: Dict, output_path: str, **kwargs) -> Dict:
    """Module-level fill_template tool."""
    return get_tools().fill_template(template_id, data, output_path, **kwargs).to_dict()
