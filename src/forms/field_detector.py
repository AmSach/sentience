"""
Field Detector for Sentience v3.0
Detects and analyzes form fields in PDF and DOCX documents.
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from .pdf_engine import PDFEngine, PDFField, FieldType as PDFFieldType
from .docx_engine import DOCXEngine, DOCXField

logger = logging.getLogger(__name__)


class DetectedFieldType(Enum):
    """Detected field types with semantic meaning."""
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    EMAIL = "email"
    PHONE = "phone"
    URL = "url"
    CURRENCY = "currency"
    PERCENTAGE = "percentage"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    DROPDOWN = "dropdown"
    SIGNATURE = "signature"
    TEXTAREA = "textarea"
    NAME = "name"
    ADDRESS = "address"
    ZIP = "zip"
    SSN = "ssn"
    TAX_ID = "tax_id"
    ACCOUNT_NUMBER = "account_number"
    UNKNOWN = "unknown"


@dataclass
class ValidationRule:
    """Validation rule for a field."""
    rule_type: str
    value: Any
    message: str = ""
    
    def validate(self, input_value: Any) -> Tuple[bool, str]:
        """Validate input against this rule."""
        validators = {
            "required": self._validate_required,
            "min_length": self._validate_min_length,
            "max_length": self._validate_max_length,
            "min_value": self._validate_min_value,
            "max_value": self._validate_max_value,
            "pattern": self._validate_pattern,
            "enum": self._validate_enum,
            "type": self._validate_type,
        }
        
        validator = validators.get(self.rule_type)
        if validator:
            return validator(input_value)
        return True, ""
    
    def _validate_required(self, value: Any) -> Tuple[bool, str]:
        if value is None or (isinstance(value, str) and not value.strip()):
            return False, self.message or "This field is required"
        return True, ""
    
    def _validate_min_length(self, value: Any) -> Tuple[bool, str]:
        if not isinstance(value, (str, list)):
            return True, ""
        if len(value) < self.value:
            return False, self.message or f"Minimum length is {self.value}"
        return True, ""
    
    def _validate_max_length(self, value: Any) -> Tuple[bool, str]:
        if not isinstance(value, (str, list)):
            return True, ""
        if len(value) > self.value:
            return False, self.message or f"Maximum length is {self.value}"
        return True, ""
    
    def _validate_min_value(self, value: Any) -> Tuple[bool, str]:
        try:
            if float(value) < self.value:
                return False, self.message or f"Minimum value is {self.value}"
        except (TypeError, ValueError):
            pass
        return True, ""
    
    def _validate_max_value(self, value: Any) -> Tuple[bool, str]:
        try:
            if float(value) > self.value:
                return False, self.message or f"Maximum value is {self.value}"
        except (TypeError, ValueError):
            pass
        return True, ""
    
    def _validate_pattern(self, value: Any) -> Tuple[bool, str]:
        if not isinstance(value, str):
            return True, ""
        if not re.match(self.value, value):
            return False, self.message or f"Invalid format"
        return True, ""
    
    def _validate_enum(self, value: Any) -> Tuple[bool, str]:
        if str(value) not in [str(v) for v in self.value]:
            return False, self.message or f"Must be one of: {self.value}"
        return True, ""
    
    def _validate_type(self, value: Any) -> Tuple[bool, str]:
        type_validators = {
            "number": lambda v: isinstance(v, (int, float)) or str(v).replace(".", "").isdigit(),
            "email": lambda v: bool(re.match(r"^[^@]+@[^@]+\.[^@]+$", str(v))),
            "phone": lambda v: bool(re.match(r"^[\d\s\-\(\)\+]{10,}$", str(v))),
            "url": lambda v: bool(re.match(r"^https?://", str(v))),
            "date": self._is_valid_date,
        }
        
        validator = type_validators.get(self.value)
        if validator:
            if not validator(value):
                return False, self.message or f"Invalid {self.value} format"
        return True, ""
    
    def _is_valid_date(self, value: Any) -> bool:
        """Check if value is a valid date."""
        date_patterns = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
            "%B %d, %Y",
            "%b %d, %Y",
        ]
        for pattern in date_patterns:
            try:
                datetime.strptime(str(value), pattern)
                return True
            except ValueError:
                continue
        return False


@dataclass
class DetectedField:
    """Represents a detected form field with inferred type and validation."""
    name: str
    field_type: DetectedFieldType
    source_type: str  # "pdf" or "docx"
    original_field: Any  # Original PDFField or DOCXField
    placeholder: str = ""
    inferred_type: bool = False
    validation_rules: List[ValidationRule] = field(default_factory=list)
    suggested_values: List[Any] = field(default_factory=list)
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class FieldDetector:
    """
    Field detection and analysis engine.
    
    Handles:
    - PDF form field mapping
    - DOCX placeholder detection
    - Field type inference
    - Validation rule generation
    """
    
    # Field name patterns for type inference
    FIELD_PATTERNS = {
        DetectedFieldType.EMAIL: [
            r"email", r"e-mail", r"mail", r"correo",
        ],
        DetectedFieldType.PHONE: [
            r"phone", r"tel", r"mobile", r"cell", r"fax", r"telefono",
        ],
        DetectedFieldType.DATE: [
            r"date", r"dob", r"birth", r"fecha", r"deadline", r"expiry",
            r"start.*date", r"end.*date", r"fecha",
        ],
        DetectedFieldType.NAME: [
            r"^name$", r"first.*name", r"last.*name", r"full.*name",
            r"nombre", r"apellido",
        ],
        DetectedFieldType.ADDRESS: [
            r"address", r"street", r"direccion", r"city", r"state", r"province",
        ],
        DetectedFieldType.ZIP: [
            r"zip", r"postal", r"postcode", r"codigo",
        ],
        DetectedFieldType.SSN: [
            r"ssn", r"social.*security", r"ss",
        ],
        DetectedFieldType.TAX_ID: [
            r"tax.*id", r"ein", r"taxpayer", r"rut", r"cuit",
        ],
        DetectedFieldType.ACCOUNT_NUMBER: [
            r"account", r"account.*num", r"acc.*num",
        ],
        DetectedFieldType.CURRENCY: [
            r"amount", r"price", r"cost", r"salary", r"wage", r"monto",
            r"total", r"subtotal", r"fee",
        ],
        DetectedFieldType.PERCENTAGE: [
            r"percent", r"rate", r"porcentaje", r"iva", r"tax.*rate",
        ],
        DetectedFieldType.URL: [
            r"url", r"website", r"link", r"sitio",
        ],
    }
    
    # Validation patterns
    VALIDATION_PATTERNS = {
        DetectedFieldType.EMAIL: (r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", "Invalid email format"),
        DetectedFieldType.PHONE: (r"^[\d\s\-\(\)\+]{10,15}$", "Invalid phone format"),
        DetectedFieldType.URL: (r"^https?://[^\s]+$", "Invalid URL format"),
        DetectedFieldType.ZIP: (r"^\d{4,10}(-\d{4})?$", "Invalid ZIP code"),
        DetectedFieldType.SSN: (r"^\d{3}-?\d{2}-?\d{4}$", "Invalid SSN format"),
        DetectedFieldType.DATE: (r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}", "Invalid date format"),
    }
    
    def __init__(self):
        """Initialize field detector."""
        self.detected_fields: Dict[str, DetectedField] = {}
    
    def detect_pdf_fields(
        self,
        pdf_path: Union[str, Path]
    ) -> Dict[str, DetectedField]:
        """
        Detect fields in a PDF form.
        
        Args:
            pdf_path: Path to PDF file.
            
        Returns:
            Dictionary of detected fields.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        engine = PDFEngine(pdf_path)
        pdf_fields = engine.detect_fields()
        
        self.detected_fields.clear()
        
        for name, pdf_field in pdf_fields.items():
            detected = self._process_pdf_field(pdf_field)
            self.detected_fields[name] = detected
        
        engine.close()
        logger.info(f"Detected {len(self.detected_fields)} PDF fields")
        return self.detected_fields
    
    def detect_docx_fields(
        self,
        docx_path: Union[str, Path],
        placeholder_style: str = "curly_braces"
    ) -> Dict[str, DetectedField]:
        """
        Detect placeholder fields in a DOCX template.
        
        Args:
            docx_path: Path to DOCX file.
            placeholder_style: Placeholder format style.
            
        Returns:
            Dictionary of detected fields.
        """
        docx_path = Path(docx_path)
        if not docx_path.exists():
            raise FileNotFoundError(f"DOCX not found: {docx_path}")
        
        engine = DOCXEngine(docx_path, placeholder_style)
        docx_fields = engine.detect_fields()
        
        self.detected_fields.clear()
        
        for name, docx_field in docx_fields.items():
            detected = self._process_docx_field(docx_field)
            self.detected_fields[name] = detected
        
        engine.close()
        logger.info(f"Detected {len(self.detected_fields)} DOCX fields")
        return self.detected_fields
    
    def _process_pdf_field(self, pdf_field: PDFField) -> DetectedField:
        """Process a PDF field and create DetectedField."""
        # Map PDF field type to detected type
        type_mapping = {
            PDFFieldType.TEXT: DetectedFieldType.TEXT,
            PDFFieldType.CHECKBOX: DetectedFieldType.CHECKBOX,
            PDFFieldType.RADIO: DetectedFieldType.RADIO,
            PDFFieldType.DROPDOWN: DetectedFieldType.DROPDOWN,
            PDFFieldType.SIGNATURE: DetectedFieldType.SIGNATURE,
            PDFFieldType.BUTTON: DetectedFieldType.TEXT,
            PDFFieldType.UNKNOWN: DetectedFieldType.UNKNOWN,
        }
        
        initial_type = type_mapping.get(pdf_field.field_type, DetectedFieldType.TEXT)
        
        # Infer semantic type from field name
        inferred_type, confidence = self._infer_field_type(pdf_field.name, initial_type)
        
        # Generate validation rules
        validation_rules = self._generate_validation_rules(pdf_field, inferred_type)
        
        return DetectedField(
            name=pdf_field.name,
            field_type=inferred_type,
            source_type="pdf",
            original_field=pdf_field,
            inferred_type=inferred_type != initial_type,
            validation_rules=validation_rules,
            confidence=confidence,
            metadata={
                "required": pdf_field.required,
                "readonly": pdf_field.readonly,
                "options": pdf_field.options,
                "page_number": pdf_field.page_number,
                "tooltip": pdf_field.tooltip,
            }
        )
    
    def _process_docx_field(self, docx_field: DOCXField) -> DetectedField:
        """Process a DOCX field and create DetectedField."""
        # Infer type from field name
        inferred_type, confidence = self._infer_field_type(docx_field.name, DetectedFieldType.TEXT)
        
        # Generate validation rules
        validation_rules = self._generate_docx_validation_rules(docx_field, inferred_type)
        
        return DetectedField(
            name=docx_field.name,
            field_type=inferred_type,
            source_type="docx",
            original_field=docx_field,
            placeholder=docx_field.placeholder,
            inferred_type=True,
            validation_rules=validation_rules,
            confidence=confidence,
            metadata={
                "location": docx_field.location,
                "table_index": docx_field.table_index,
            }
        )
    
    def _infer_field_type(
        self,
        field_name: str,
        default_type: DetectedFieldType
    ) -> Tuple[DetectedFieldType, float]:
        """
        Infer semantic field type from field name.
        
        Returns:
            Tuple of (inferred_type, confidence).
        """
        name_lower = field_name.lower().replace("_", " ").replace("-", " ")
        
        best_match = default_type
        best_confidence = 0.0
        
        for field_type, patterns in self.FIELD_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, name_lower, re.IGNORECASE):
                    # Calculate confidence based on pattern specificity
                    confidence = 0.8 if len(pattern) > 5 else 0.6
                    
                    # Higher confidence for exact matches
                    if re.match(f"^{pattern}$", name_lower, re.IGNORECASE):
                        confidence = 0.95
                    
                    if confidence > best_confidence:
                        best_match = field_type
                        best_confidence = confidence
        
        # If no match found, use default with low confidence
        if best_confidence == 0.0:
            best_confidence = 0.3
        
        return best_match, best_confidence
    
    def _generate_validation_rules(
        self,
        pdf_field: PDFField,
        field_type: DetectedFieldType
    ) -> List[ValidationRule]:
        """Generate validation rules for a PDF field."""
        rules = []
        
        # Required rule
        if pdf_field.required:
            rules.append(ValidationRule(
                rule_type="required",
                value=True,
                message=f"{pdf_field.name} is required"
            ))
        
        # Type-specific validation
        if field_type in self.VALIDATION_PATTERNS:
            pattern, message = self.VALIDATION_PATTERNS[field_type]
            rules.append(ValidationRule(
                rule_type="pattern",
                value=pattern,
                message=message
            ))
        
        # Enum validation for dropdowns/radio
        if pdf_field.options:
            rules.append(ValidationRule(
                rule_type="enum",
                value=pdf_field.options,
                message=f"Must be one of: {', '.join(pdf_field.options)}"
            ))
        
        return rules
    
    def _generate_docx_validation_rules(
        self,
        docx_field: DOCXField,
        field_type: DetectedFieldType
    ) -> List[ValidationRule]:
        """Generate validation rules for a DOCX field."""
        rules = []
        
        # Type-specific validation
        if field_type in self.VALIDATION_PATTERNS:
            pattern, message = self.VALIDATION_PATTERNS[field_type]
            rules.append(ValidationRule(
                rule_type="pattern",
                value=pattern,
                message=message
            ))
        
        # Add type validation for special types
        if field_type in (DetectedFieldType.EMAIL, DetectedFieldType.URL, 
                         DetectedFieldType.PHONE, DetectedFieldType.DATE):
            rules.append(ValidationRule(
                rule_type="type",
                value=field_type.value,
                message=f"Invalid {field_type.value} format"
            ))
        
        return rules
    
    def validate_values(
        self,
        values: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        """
        Validate provided values against detected fields.
        
        Args:
            values: Dictionary of field values to validate.
            
        Returns:
            Dictionary mapping field names to list of error messages.
        """
        errors = {}
        
        for name, value in values.items():
            if name not in self.detected_fields:
                errors[name] = ["Unknown field"]
                continue
            
            field = self.detected_fields[name]
            field_errors = []
            
            for rule in field.validation_rules:
                valid, message = rule.validate(value)
                if not valid:
                    field_errors.append(message)
            
            if field_errors:
                errors[name] = field_errors
        
        return errors
    
    def suggest_mappings(
        self,
        data_keys: List[str]
    ) -> Dict[str, List[str]]:
        """
        Suggest field mappings between data keys and detected fields.
        
        Args:
            data_keys: List of available data keys.
            
        Returns:
            Dictionary mapping field names to suggested data keys.
        """
        suggestions = {}
        
        for field_name, detected_field in self.detected_fields.items():
            matches = []
            field_name_lower = field_name.lower()
            
            for key in data_keys:
                key_lower = key.lower()
                
                # Exact match
                if field_name_lower == key_lower:
                    matches.insert(0, key)  # Highest priority
                # Partial match
                elif field_name_lower in key_lower or key_lower in field_name_lower:
                    matches.append(key)
                # Semantic match
                elif self._are_semantically_similar(field_name_lower, key_lower):
                    matches.append(key)
            
            if matches:
                suggestions[field_name] = matches
        
        return suggestions
    
    def _are_semantically_similar(self, name1: str, name2: str) -> bool:
        """Check if two field names are semantically similar."""
        # Common synonyms
        synonyms = {
            "email": ["email", "mail", "email_address", "emailaddress"],
            "phone": ["phone", "telephone", "phone_number", "tel", "mobile"],
            "name": ["name", "full_name", "fullname", "full name"],
            "address": ["address", "street", "location", "addr"],
            "city": ["city", "town", "municipality"],
            "state": ["state", "province", "region"],
            "country": ["country", "nation"],
            "zip": ["zip", "postal", "zip_code", "zipcode", "postcode"],
        }
        
        for canonical, variants in synonyms.items():
            if name1 in variants and name2 in variants:
                return True
        
        return False
    
    def get_field_schema(self) -> Dict[str, Any]:
        """
        Get a JSON schema representation of detected fields.
        
        Returns:
            JSON schema dictionary.
        """
        properties = {}
        required = []
        
        for name, field in self.detected_fields.items():
            prop = {
                "type": self._field_type_to_json_type(field.field_type),
                "description": f"{field.field_type.value} field",
            }
            
            # Add format for special types
            if field.field_type == DetectedFieldType.EMAIL:
                prop["format"] = "email"
            elif field.field_type == DetectedFieldType.DATE:
                prop["format"] = "date"
            elif field.field_type == DetectedFieldType.URL:
                prop["format"] = "uri"
            
            # Add enum for dropdowns/radio
            if field.field_type in (DetectedFieldType.DROPDOWN, DetectedFieldType.RADIO):
                if hasattr(field.original_field, 'options') and field.original_field.options:
                    prop["enum"] = field.original_field.options
            
            properties[name] = prop
            
            # Track required fields
            if field.metadata.get("required"):
                required.append(name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required if required else None,
        }
    
    def _field_type_to_json_type(self, field_type: DetectedFieldType) -> str:
        """Convert detected field type to JSON schema type."""
        type_map = {
            DetectedFieldType.TEXT: "string",
            DetectedFieldType.NUMBER: "number",
            DetectedFieldType.DATE: "string",
            DetectedFieldType.EMAIL: "string",
            DetectedFieldType.PHONE: "string",
            DetectedFieldType.URL: "string",
            DetectedFieldType.CURRENCY: "number",
            DetectedFieldType.PERCENTAGE: "number",
            DetectedFieldType.CHECKBOX: "boolean",
            DetectedFieldType.RADIO: "string",
            DetectedFieldType.DROPDOWN: "string",
            DetectedFieldType.SIGNATURE: "string",
            DetectedFieldType.TEXTAREA: "string",
            DetectedFieldType.NAME: "string",
            DetectedFieldType.ADDRESS: "string",
            DetectedFieldType.ZIP: "string",
            DetectedFieldType.SSN: "string",
            DetectedFieldType.TAX_ID: "string",
            DetectedFieldType.ACCOUNT_NUMBER: "string",
            DetectedFieldType.UNKNOWN: "string",
        }
        return type_map.get(field_type, "string")
    
    def export_field_mapping(self) -> Dict[str, Any]:
        """
        Export field mapping configuration.
        
        Returns:
            Dictionary suitable for saving as YAML/JSON.
        """
        return {
            "fields": {
                name: {
                    "type": field.field_type.value,
                    "source": field.source_type,
                    "required": field.metadata.get("required", False),
                    "validation": [
                        {"type": rule.rule_type, "value": rule.value}
                        for rule in field.validation_rules
                    ],
                    "confidence": field.confidence,
                }
                for name, field in self.detected_fields.items()
            },
            "total_fields": len(self.detected_fields),
            "detected_at": datetime.now().isoformat(),
        }


# Convenience functions
def detect_pdf_fields(pdf_path: Union[str, Path]) -> Dict[str, DetectedField]:
    """Convenience function to detect PDF fields."""
    detector = FieldDetector()
    return detector.detect_pdf_fields(pdf_path)


def detect_docx_fields(
    docx_path: Union[str, Path],
    placeholder_style: str = "curly_braces"
) -> Dict[str, DetectedField]:
    """Convenience function to detect DOCX fields."""
    detector = FieldDetector()
    return detector.detect_docx_fields(docx_path, placeholder_style)


def get_field_schema(pdf_path: Union[str, Path]) -> Dict[str, Any]:
    """Convenience function to get field schema from PDF."""
    detector = FieldDetector()
    detector.detect_pdf_fields(pdf_path)
    return detector.get_field_schema()
