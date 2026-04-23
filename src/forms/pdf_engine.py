"""
PDF Engine for Sentience v3.0
Handles PDF form field detection, filling, digital signatures, and generation.
"""

import os
import io
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, BinaryIO
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

try:
    from pypdf import PdfReader, PdfWriter, PdfReaderError
    from pypdf.generic import (
        DictionaryObject, 
        ArrayObject, 
        NameObject, 
        TextStringObject, 
        BooleanObject,
        NumberObject,
        FloatObject,
    )
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False
    # Define fallback types for when pypdf is not installed
    ArrayObject = list
    DictionaryObject = dict
    NameObject = str
    TextStringObject = str
    BooleanObject = bool
    NumberObject = int
    FloatObject = float

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import black, gray
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

logger = logging.getLogger(__name__)


class FieldType(Enum):
    """PDF form field types."""
    TEXT = "text"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    DROPDOWN = "dropdown"
    SIGNATURE = "signature"
    BUTTON = "button"
    UNKNOWN = "unknown"


@dataclass
class PDFField:
    """Represents a PDF form field."""
    name: str
    field_type: FieldType
    value: Any = None
    default_value: Any = None
    required: bool = False
    readonly: bool = False
    options: List[str] = field(default_factory=list)
    page_number: int = 0
    rect: tuple = (0, 0, 0, 0)
    tooltip: str = ""
    alternate_name: str = ""


@dataclass
class PDFSignature:
    """Represents a digital signature."""
    name: str
    location: str = ""
    reason: str = ""
    contact: str = ""
    date: datetime = field(default_factory=datetime.now)
    certificate_path: Optional[str] = None


class PDFEngine:
    """
    PDF form operations engine.
    
    Handles:
    - Form field detection and mapping
    - Field value filling
    - Digital signatures
    - PDF generation from scratch
    """
    
    def __init__(self, pdf_path: Optional[Union[str, Path]] = None):
        """Initialize PDF engine with optional PDF file."""
        self.pdf_path = Path(pdf_path) if pdf_path else None
        self.reader: Optional[PdfReader] = None
        self.writer: Optional[PdfWriter] = None
        self.fields: Dict[str, PDFField] = {}
        
        if not PYPDF_AVAILABLE:
            raise ImportError("pypdf is required for PDF operations. Install with: pip install pypdf")
        
        if self.pdf_path and self.pdf_path.exists():
            self._load_pdf()
    
    def _load_pdf(self) -> None:
        """Load PDF file for reading."""
        try:
            self.reader = PdfReader(str(self.pdf_path))
            logger.info(f"Loaded PDF: {self.pdf_path} with {len(self.reader.pages)} pages")
        except Exception as e:
            logger.error(f"Failed to load PDF: {e}")
            raise
    
    def create_writer(self) -> None:
        """Create a new PDF writer."""
        self.writer = PdfWriter()
        if self.reader:
            for page in self.reader.pages:
                self.writer.add_page(page)
    
    def detect_fields(self) -> Dict[str, PDFField]:
        """
        Detect and map all form fields in the PDF.
        
        Returns:
            Dictionary mapping field names to PDFField objects.
        """
        if not self.reader:
            raise ValueError("No PDF loaded")
        
        self.fields.clear()
        
        if not self.reader.form_fields:
            logger.info("No form fields detected in PDF")
            return self.fields
        
        for page_num, page in enumerate(self.reader.pages):
            if "/Annots" in page:
                self._process_annotations(page["/Annots"], page_num)
        
        # Also process form fields from the reader
        for field_name, field_value in self.reader.form_fields.items():
            if field_name not in self.fields:
                field = self._parse_form_field(field_name, field_value)
                self.fields[field_name] = field
        
        logger.info(f"Detected {len(self.fields)} form fields")
        return self.fields
    
    def _process_annotations(self, annotations: ArrayObject, page_num: int) -> None:
        """Process page annotations to extract form fields."""
        for annot in annotations:
            if isinstance(annot, dict):
                annot_dict = annot.get_object() if hasattr(annot, 'get_object') else annot
                
                if annot_dict.get("/Subtype") == "/Widget":
                    field_name = self._get_field_name(annot_dict)
                    if field_name and field_name not in self.fields:
                        field = self._parse_annotation_field(annot_dict, page_num)
                        self.fields[field_name] = field
    
    def _get_field_name(self, annot: dict) -> Optional[str]:
        """Extract field name from annotation."""
        if "/T" in annot:
            name = annot["/T"]
            if hasattr(name, 'original_bytes'):
                return name.original_bytes.decode('utf-8', errors='ignore')
            return str(name)
        return None
    
    def _parse_form_field(self, name: str, value: Any) -> PDFField:
        """Parse a form field from reader.form_fields."""
        field_type = FieldType.TEXT
        
        if isinstance(value, bool):
            field_type = FieldType.CHECKBOX
        elif isinstance(value, str) and "/" in value:
            field_type = FieldType.DROPDOWN
        elif isinstance(value, (list, tuple)):
            field_type = FieldType.RADIO
        
        return PDFField(
            name=name,
            field_type=field_type,
            value=value if value else None,
            default_value=value
        )
    
    def _parse_annotation_field(self, annot: dict, page_num: int) -> PDFField:
        """Parse form field from annotation dictionary."""
        name = self._get_field_name(annot) or f"field_{len(self.fields)}"
        
        # Determine field type
        ft = annot.get("/FT", "")
        field_type = self._determine_field_type(ft, annot)
        
        # Get field value
        v = annot.get("/V")
        dv = annot.get("/DV")
        
        # Get flags
        ff = annot.get("/Ff", 0)
        required = bool(ff & 0x00000002) if isinstance(ff, int) else False
        readonly = bool(ff & 0x00000001) if isinstance(ff, int) else False
        
        # Get options for dropdowns/radio
        options = []
        if "/Opt" in annot:
            opt_obj = annot["/Opt"]
            if hasattr(opt_obj, '__iter__'):
                options = [str(o) for o in opt_obj]
        
        # Get rectangle
        rect = annot.get("/Rect", (0, 0, 0, 0))
        
        # Get tooltip and alternate name
        tooltip = str(annot.get("/TU", ""))
        alternate_name = str(annot.get("/TM", ""))
        
        return PDFField(
            name=name,
            field_type=field_type,
            value=self._parse_value(v),
            default_value=self._parse_value(dv),
            required=required,
            readonly=readonly,
            options=options,
            page_number=page_num,
            rect=tuple(rect) if rect else (0, 0, 0, 0),
            tooltip=tooltip,
            alternate_name=alternate_name
        )
    
    def _determine_field_type(self, ft: str, annot: dict) -> FieldType:
        """Determine field type from FT and annotation properties."""
        if ft == "/Tx":
            return FieldType.TEXT
        elif ft == "/Btn":
            flags = annot.get("/Ff", 0)
            if isinstance(flags, int):
                if flags & 0x00010000:
                    return FieldType.RADIO
                elif flags & 0x00010000 == 0:
                    return FieldType.CHECKBOX
            return FieldType.BUTTON
        elif ft == "/Ch":
            return FieldType.DROPDOWN
        elif ft == "/Sig":
            return FieldType.SIGNATURE
        return FieldType.UNKNOWN
    
    def _parse_value(self, value: Any) -> Any:
        """Parse field value from PDF object."""
        if value is None:
            return None
        if hasattr(value, 'original_bytes'):
            return value.original_bytes.decode('utf-8', errors='ignore')
        if isinstance(value, str):
            return value
        if isinstance(value, bool):
            return value
        return str(value)
    
    def fill_fields(self, field_values: Dict[str, Any]) -> None:
        """
        Fill form fields with provided values.
        
        Args:
            field_values: Dictionary mapping field names to values.
        """
        if not self.writer:
            self.create_writer()
        
        # Update writer form fields
        for field_name, value in field_values.items():
            if field_name in self.fields:
                self._update_field_value(field_name, value)
                self.fields[field_name].value = value
            else:
                logger.warning(f"Field '{field_name}' not found in PDF form")
        
        logger.info(f"Filled {len(field_values)} fields")
    
    def _update_field_value(self, name: str, value: Any) -> None:
        """Update a single field value in the writer."""
        if not self.writer:
            return
        
        # Update the form field in the writer's catalog
        if hasattr(self.writer, 'update_page_form_field_values'):
            self.writer.update_page_form_field_values(
                self.writer.pages[0],
                {name: value}
            )
        
        # Alternative: direct annotation update
        for page in self.writer.pages:
            if "/Annots" in page:
                for annot in page["/Annots"]:
                    annot_obj = annot.get_object() if hasattr(annot, 'get_object') else annot
                    if self._get_field_name(annot_obj) == name:
                        self._set_annotation_value(annot_obj, value)
    
    def _set_annotation_value(self, annot: dict, value: Any) -> None:
        """Set value in annotation dictionary."""
        field = self.fields.get(self._get_field_name(annot) or "")
        
        if field and field.field_type == FieldType.CHECKBOX:
            # Handle checkbox
            annot[NameObject("/V")] = NameObject("/Yes") if value else NameObject("/Off")
            annot[NameObject("/AS")] = NameObject("/Yes") if value else NameObject("/Off")
        elif field and field.field_type == FieldType.DROPDOWN:
            # Handle dropdown
            annot[NameObject("/V")] = TextStringObject(str(value))
        else:
            # Handle text field
            annot[NameObject("/V")] = TextStringObject(str(value) if value else "")
    
    def add_digital_signature(
        self,
        signature: PDFSignature,
        output_path: Optional[Union[str, Path]] = None
    ) -> bool:
        """
        Add a digital signature to the PDF.
        
        Note: This creates a signature field placeholder. Full PKCS#7 
        signing requires additional crypto libraries.
        
        Args:
            signature: PDFSignature object with signature details.
            output_path: Path to save signed PDF.
            
        Returns:
            True if signature was added successfully.
        """
        if not self.writer:
            self.create_writer()
        
        # Create signature dictionary
        sig_dict = DictionaryObject()
        sig_dict[NameObject("/Type")] = NameObject("/Sig")
        sig_dict[NameObject("/Filter")] = NameObject("/Adobe.PPKLite")
        sig_dict[NameObject("/SubFilter")] = NameObject("/adbe.pkcs7.detached")
        sig_dict[NameObject("/M")] = TextStringObject(
            f"D:{signature.date.strftime('%Y%m%d%H%M%S')}"
        )
        
        if signature.name:
            sig_dict[NameObject("/Name")] = TextStringObject(signature.name)
        if signature.location:
            sig_dict[NameObject("/Location")] = TextStringObject(signature.location)
        if signature.reason:
            sig_dict[NameObject("/Reason")] = TextStringObject(signature.reason)
        if signature.contact:
            sig_dict[NameObject("/ContactInfo")] = TextStringObject(signature.contact)
        
        # Create signature field
        sig_field = DictionaryObject()
        sig_field[NameObject("/FT")] = NameObject("/Sig")
        sig_field[NameObject("/V")] = sig_dict
        sig_field[NameObject("/T")] = TextStringObject(signature.name or "Signature")
        
        # Add to form fields
        if "/AcroForm" not in self.writer.root_object:
            self.writer.root_object[NameObject("/AcroForm")] = DictionaryObject()
        
        acroform = self.writer.root_object["/AcroForm"]
        if "/Fields" not in acroform:
            acroform[NameObject("/Fields")] = ArrayObject()
        
        acroform["/Fields"].append(sig_field)
        
        logger.info(f"Added digital signature field for: {signature.name}")
        
        if output_path:
            self.save(output_path)
        
        return True
    
    @staticmethod
    def generate_pdf(
        output_path: Union[str, Path],
        content: List[Dict[str, Any]],
        title: str = "Generated PDF",
        page_size: str = "letter"
    ) -> bool:
        """
        Generate a new PDF document from content specification.
        
        Args:
            output_path: Path to save the PDF.
            content: List of content blocks (text, image, table).
            title: PDF document title.
            page_size: Page size ('letter' or 'A4').
            
        Returns:
            True if PDF was generated successfully.
        """
        if not REPORTLAB_AVAILABLE:
            raise ImportError("reportlab is required for PDF generation. Install with: pip install reportlab")
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        size = letter if page_size.lower() == "letter" else A4
        
        c = canvas.Canvas(str(output_path), pagesize=size)
        c.setTitle(title)
        
        y_position = size[1] - 50  # Start from top
        
        for block in content:
            block_type = block.get("type", "text")
            
            if block_type == "text":
                y_position = PDFEngine._add_text_block(c, block, y_position, size)
            elif block_type == "header":
                y_position = PDFEngine._add_header_block(c, block, y_position, size)
            elif block_type == "table":
                y_position = PDFEngine._add_table_block(c, block, y_position, size)
            elif block_type == "spacer":
                y_position -= block.get("height", 20)
            
            # Check if we need a new page
            if y_position < 100:
                c.showPage()
                y_position = size[1] - 50
        
        c.save()
        logger.info(f"Generated PDF: {output_path}")
        return True
    
    @staticmethod
    def _add_text_block(c: canvas.Canvas, block: dict, y: float, size: tuple) -> float:
        """Add text block to canvas."""
        text = block.get("text", "")
        font = block.get("font", "Helvetica")
        size_pt = block.get("font_size", 11)
        
        c.setFont(font, size_pt)
        c.drawString(50, y, text)
        return y - (size_pt + 5)
    
    @staticmethod
    def _add_header_block(c: canvas.Canvas, block: dict, y: float, size: tuple) -> float:
        """Add header block to canvas."""
        text = block.get("text", "")
        font = block.get("font", "Helvetica-Bold")
        size_pt = block.get("font_size", 16)
        
        c.setFont(font, size_pt)
        c.drawString(50, y, text)
        
        # Add underline
        c.line(50, y - 2, 50 + len(text) * size_pt * 0.6, y - 2)
        
        return y - (size_pt + 15)
    
    @staticmethod
    def _add_table_block(c: canvas.Canvas, block: dict, y: float, size: tuple) -> float:
        """Add table block to canvas."""
        headers = block.get("headers", [])
        rows = block.get("rows", [])
        col_widths = block.get("col_widths", [100] * len(headers))
        
        # Draw headers
        c.setFont("Helvetica-Bold", 10)
        x = 50
        for i, header in enumerate(headers):
            c.drawString(x, y, str(header))
            x += col_widths[i] if i < len(col_widths) else 100
        y -= 15
        
        # Draw rows
        c.setFont("Helvetica", 10)
        for row in rows:
            x = 50
            for i, cell in enumerate(row):
                c.drawString(x, y, str(cell))
                x += col_widths[i] if i < len(col_widths) else 100
            y -= 12
        
        return y - 10
    
    def get_field_summary(self) -> Dict[str, Dict[str, Any]]:
        """Get a summary of all detected fields."""
        return {
            name: {
                "type": field.field_type.value,
                "value": field.value,
                "required": field.required,
                "readonly": field.readonly,
                "options": field.options if field.options else None,
                "page": field.page_number,
                "tooltip": field.tooltip
            }
            for name, field in self.fields.items()
        }
    
    def validate_values(self, field_values: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Validate field values against field constraints.
        
        Returns:
            Dictionary mapping field names to list of validation errors.
        """
        errors = {}
        
        for name, value in field_values.items():
            field_errors = []
            
            if name not in self.fields:
                field_errors.append(f"Field '{name}' does not exist")
                continue
            
            field = self.fields[name]
            
            # Check required
            if field.required and (value is None or value == ""):
                field_errors.append("Field is required")
            
            # Check readonly
            if field.readonly:
                field_errors.append("Field is read-only")
            
            # Check options for dropdown/radio
            if field.field_type in (FieldType.DROPDOWN, FieldType.RADIO):
                if field.options and str(value) not in [str(o) for o in field.options]:
                    field_errors.append(f"Value must be one of: {field.options}")
            
            # Type-specific validation
            if field.field_type == FieldType.CHECKBOX:
                if not isinstance(value, (bool, int, str)):
                    field_errors.append("Checkbox value must be boolean, int, or string")
            
            if field_errors:
                errors[name] = field_errors
        
        return errors
    
    def save(self, output_path: Union[str, Path]) -> bool:
        """
        Save the modified PDF to a file.
        
        Args:
            output_path: Path to save the PDF.
            
        Returns:
            True if saved successfully.
        """
        if not self.writer:
            raise ValueError("No PDF writer initialized")
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(output_path, "wb") as f:
                self.writer.write(f)
            
            logger.info(f"Saved PDF to: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save PDF: {e}")
            raise
    
    def get_bytes(self) -> bytes:
        """Get the modified PDF as bytes."""
        if not self.writer:
            raise ValueError("No PDF writer initialized")
        
        buffer = io.BytesIO()
        self.writer.write(buffer)
        return buffer.getvalue()
    
    def close(self) -> None:
        """Clean up resources."""
        self.reader = None
        self.writer = None
        self.fields.clear()


# Convenience functions
def fill_pdf_form(
    pdf_path: Union[str, Path],
    field_values: Dict[str, Any],
    output_path: Union[str, Path]
) -> Dict[str, Any]:
    """
    Convenience function to fill a PDF form.
    
    Args:
        pdf_path: Path to source PDF.
        field_values: Dictionary of field values.
        output_path: Path to save filled PDF.
        
    Returns:
        Dictionary with field summary and status.
    """
    engine = PDFEngine(pdf_path)
    engine.detect_fields()
    
    # Validate
    errors = engine.validate_values(field_values)
    if errors:
        logger.warning(f"Validation errors: {errors}")
    
    # Fill fields
    engine.fill_fields(field_values)
    
    # Save
    engine.save(output_path)
    
    result = {
        "success": True,
        "output_path": str(output_path),
        "fields_filled": len(field_values),
        "field_summary": engine.get_field_summary(),
        "validation_errors": errors if errors else None
    }
    
    engine.close()
    return result


def get_pdf_fields(pdf_path: Union[str, Path]) -> Dict[str, PDFField]:
    """Convenience function to get PDF form fields."""
    engine = PDFEngine(pdf_path)
    fields = engine.detect_fields()
    engine.close()
    return fields
