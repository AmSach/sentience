"""
Form Filler for Sentience v3.0
Auto-fills PDF and DOCX forms from data with field mapping and value transformation.
"""

import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal

from .pdf_engine import PDFEngine, PDFField, FieldType, fill_pdf_form
from .docx_engine import DOCXEngine, DOCXField, fill_docx_template
from .field_detector import (
    FieldDetector,
    DetectedField,
    DetectedFieldType,
    ValidationRule,
)

logger = logging.getLogger(__name__)


@dataclass
class FieldMapping:
    """Represents a mapping between data key and form field."""
    data_key: str
    field_name: str
    transformer: Optional[Callable[[Any], Any]] = None
    default_value: Optional[Any] = None
    required: bool = False
    description: str = ""


@dataclass
class TransformRule:
    """Rule for transforming values during fill."""
    source_type: str  # e.g., "date", "number", "currency"
    target_format: str  # e.g., "%Y-%m-%d", "{:.2f}"
    transformer: Optional[Callable[[Any], Any]] = None


class ValueTransformer:
    """
    Transforms values between different formats.
    
    Handles:
    - Date formatting
    - Number formatting
    - Currency formatting
    - Boolean conversion
    - String normalization
    """
    
    # Common date formats
    DATE_FORMATS = {
        "iso": "%Y-%m-%d",
        "us": "%m/%d/%Y",
        "eu": "%d/%m/%Y",
        "long": "%B %d, %Y",
        "short": "%b %d, %Y",
        "ymd": "%Y%m%d",
        "dmy": "%d%m%Y",
        "mdy": "%m%d%Y",
    }
    
    # Currency symbols
    CURRENCY_SYMBOLS = {
        "usd": "$",
        "eur": "€",
        "gbp": "£",
        "jpy": "¥",
        "inr": "₹",
        "cny": "¥",
    }
    
    @classmethod
    def transform(
        cls,
        value: Any,
        target_type: Optional[DetectedFieldType] = None,
        format_spec: Optional[str] = None
    ) -> Any:
        """
        Transform value to appropriate format.
        
        Args:
            value: Input value to transform.
            target_type: Target field type.
            format_spec: Format specification string.
            
        Returns:
            Transformed value.
        """
        if value is None:
            return ""
        
        # Handle different target types
        if target_type == DetectedFieldType.DATE:
            return cls._transform_date(value, format_spec)
        elif target_type == DetectedFieldType.CURRENCY:
            return cls._transform_currency(value, format_spec)
        elif target_type == DetectedFieldType.PERCENTAGE:
            return cls._transform_percentage(value, format_spec)
        elif target_type == DetectedFieldType.NUMBER:
            return cls._transform_number(value, format_spec)
        elif target_type == DetectedFieldType.PHONE:
            return cls._transform_phone(value)
        elif target_type == DetectedFieldType.CHECKBOX:
            return cls._transform_boolean(value)
        elif target_type == DetectedFieldType.EMAIL:
            return cls._transform_email(value)
        elif target_type == DetectedFieldType.SSN:
            return cls._transform_ssn(value)
        elif target_type == DetectedFieldType.TAX_ID:
            return cls._transform_tax_id(value)
        
        # Default: convert to string
        return str(value)
    
    @classmethod
    def _transform_date(cls, value: Any, format_spec: Optional[str] = None) -> str:
        """Transform value to date string."""
        if isinstance(value, (datetime, date)):
            fmt = cls.DATE_FORMATS.get(format_spec, "%Y-%m-%d")
            return value.strftime(fmt)
        
        if isinstance(value, str):
            # Try to parse and reformat
            for pattern in cls.DATE_FORMATS.values():
                try:
                    parsed = datetime.strptime(value, pattern)
                    fmt = cls.DATE_FORMATS.get(format_spec, pattern)
                    return parsed.strftime(fmt)
                except ValueError:
                    continue
            return value
        
        return str(value)
    
    @classmethod
    def _transform_currency(
        cls,
        value: Any,
        format_spec: Optional[str] = None
    ) -> str:
        """Transform value to currency string."""
        try:
            amount = float(value)
            currency = format_spec.lower() if format_spec else "usd"
            symbol = cls.CURRENCY_SYMBOLS.get(currency, "$")
            
            # Format with 2 decimal places
            if amount >= 0:
                return f"{symbol}{amount:,.2f}"
            else:
                return f"-{symbol}{abs(amount):,.2f}"
        except (ValueError, TypeError):
            return str(value)
    
    @classmethod
    def _transform_percentage(
        cls,
        value: Any,
        format_spec: Optional[str] = None
    ) -> str:
        """Transform value to percentage string."""
        try:
            num = float(value)
            
            # If value looks like decimal (0-1), convert to percentage
            if 0 <= num <= 1 and format_spec != "raw":
                return f"{num * 100:.1f}%"
            else:
                return f"{num:.1f}%"
        except (ValueError, TypeError):
            return str(value)
    
    @classmethod
    def _transform_number(
        cls,
        value: Any,
        format_spec: Optional[str] = None
    ) -> str:
        """Transform value to formatted number string."""
        try:
            num = float(value)
            
            if format_spec:
                return format_spec.format(num)
            elif num == int(num):
                return str(int(num))
            else:
                return f"{num:.2f}"
        except (ValueError, TypeError):
            return str(value)
    
    @classmethod
    def _transform_phone(cls, value: Any) -> str:
        """Transform value to formatted phone number."""
        # Extract digits
        digits = re.sub(r"\D", "", str(value))
        
        # Format based on length
        if len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        elif len(digits) == 11 and digits[0] == "1":
            return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        else:
            return str(value)
    
    @classmethod
    def _transform_boolean(cls, value: Any) -> bool:
        """Transform value to boolean."""
        if isinstance(value, bool):
            return value
        
        if isinstance(value, str):
            return value.lower() in ("true", "yes", "1", "on", "checked")
        
        if isinstance(value, (int, float)):
            return bool(value)
        
        return False
    
    @classmethod
    def _transform_email(cls, value: Any) -> str:
        """Transform value to lowercase email."""
        return str(value).lower().strip()
    
    @classmethod
    def _transform_ssn(cls, value: Any) -> str:
        """Transform value to formatted SSN."""
        digits = re.sub(r"\D", "", str(value))
        
        if len(digits) == 9:
            return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
        
        return str(value)
    
    @classmethod
    def _transform_tax_id(cls, value: Any) -> str:
        """Transform value to formatted tax ID."""
        digits = re.sub(r"\D", "", str(value))
        
        # EIN format: XX-XXXXXXX
        if len(digits) == 9:
            return f"{digits[:2]}-{digits[2:]}"
        
        return str(value)


class FormFiller:
    """
    Form filling engine with auto-mapping and transformation.
    
    Handles:
    - Auto-fill from data dictionary
    - Field mapping configuration
    - Value transformation
    - Multi-format support (PDF, DOCX)
    """
    
    def __init__(self):
        """Initialize form filler."""
        self.field_mappings: Dict[str, FieldMapping] = {}
        self.transformer = ValueTransformer()
        self.detector = FieldDetector()
        self._detected_fields: Dict[str, DetectedField] = {}
    
    def load_mapping_config(self, config_path: Union[str, Path]) -> None:
        """
        Load field mapping configuration from file.
        
        Args:
            config_path: Path to JSON or YAML mapping file.
        """
        config_path = Path(config_path)
        
        if not config_path.exists():
            raise FileNotFoundError(f"Mapping config not found: {config_path}")
        
        content = config_path.read_text()
        
        # Parse based on extension
        if config_path.suffix == ".json":
            config = json.loads(content)
        elif config_path.suffix in (".yaml", ".yml"):
            try:
                import yaml
                config = yaml.safe_load(content)
            except ImportError:
                # Fallback to simple YAML parsing
                config = self._parse_simple_yaml(content)
        else:
            raise ValueError(f"Unsupported config format: {config_path.suffix}")
        
        # Build mappings
        self.field_mappings.clear()
        
        for mapping in config.get("mappings", []):
            field_mapping = FieldMapping(
                data_key=mapping.get("data_key", ""),
                field_name=mapping.get("field_name", ""),
                default_value=mapping.get("default"),
                required=mapping.get("required", False),
                description=mapping.get("description", ""),
            )
            self.field_mappings[field_mapping.field_name] = field_mapping
        
        logger.info(f"Loaded {len(self.field_mappings)} field mappings")
    
    def _parse_simple_yaml(self, content: str) -> Dict[str, Any]:
        """Simple YAML parser for basic configs."""
        result = {"mappings": []}
        current_mapping = None
        
        for line in content.split("\n"):
            line = line.rstrip()
            
            if line.startswith("- "):
                if current_mapping:
                    result["mappings"].append(current_mapping)
                current_mapping = {}
                line = line[2:]
            
            if current_mapping is not None and ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                
                current_mapping[key] = value
        
        if current_mapping:
            result["mappings"].append(current_mapping)
        
        return result
    
    def save_mapping_config(self, config_path: Union[str, Path]) -> None:
        """
        Save current field mappings to file.
        
        Args:
            config_path: Path to save configuration.
        """
        config_path = Path(config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        config = {
            "version": "1.0",
            "mappings": [
                {
                    "data_key": m.data_key,
                    "field_name": m.field_name,
                    "default": m.default_value,
                    "required": m.required,
                    "description": m.description,
                }
                for m in self.field_mappings.values()
            ]
        }
        
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        
        logger.info(f"Saved mapping config to: {config_path}")
    
    def auto_map_fields(
        self,
        template_path: Union[str, Path],
        data_keys: List[str],
        threshold: float = 0.7
    ) -> Dict[str, str]:
        """
        Automatically map data keys to form fields.
        
        Args:
            template_path: Path to PDF or DOCX template.
            data_keys: Available data keys.
            threshold: Confidence threshold for auto-mapping.
            
        Returns:
            Dictionary mapping field names to data keys.
        """
        template_path = Path(template_path)
        
        # Detect fields in template
        if template_path.suffix.lower() == ".pdf":
            self._detected_fields = self.detector.detect_pdf_fields(template_path)
        else:
            self._detected_fields = self.detector.detect_docx_fields(template_path)
        
        # Get suggestions from detector
        suggestions = self.detector.suggest_mappings(data_keys)
        
        # Build mappings based on threshold
        auto_mappings = {}
        
        for field_name, suggested_keys in suggestions.items():
            if suggested_keys:
                # Use first suggestion if confidence is high enough
                field = self._detected_fields.get(field_name)
                if field and field.confidence >= threshold:
                    auto_mappings[field_name] = suggested_keys[0]
                    self.field_mappings[field_name] = FieldMapping(
                        data_key=suggested_keys[0],
                        field_name=field_name,
                        required=field.metadata.get("required", False),
                    )
        
        logger.info(f"Auto-mapped {len(auto_mappings)} fields")
        return auto_mappings
    
    def add_mapping(
        self,
        field_name: str,
        data_key: str,
        transformer: Optional[Callable] = None,
        default_value: Optional[Any] = None,
        required: bool = False
    ) -> None:
        """Add a field mapping."""
        self.field_mappings[field_name] = FieldMapping(
            data_key=data_key,
            field_name=field_name,
            transformer=transformer,
            default_value=default_value,
            required=required,
        )
    
    def remove_mapping(self, field_name: str) -> None:
        """Remove a field mapping."""
        self.field_mappings.pop(field_name, None)
    
    def fill_pdf(
        self,
        pdf_path: Union[str, Path],
        data: Dict[str, Any],
        output_path: Union[str, Path],
        validate: bool = True
    ) -> Dict[str, Any]:
        """
        Fill a PDF form with data.
        
        Args:
            pdf_path: Path to source PDF.
            data: Data dictionary to fill.
            output_path: Path to save filled PDF.
            validate: Whether to validate before filling.
            
        Returns:
            Dictionary with fill results and status.
        """
        pdf_path = Path(pdf_path)
        output_path = Path(output_path)
        
        # Detect fields if not already done
        if not self._detected_fields:
            self._detected_fields = self.detector.detect_pdf_fields(pdf_path)
        
        # Transform and map data
        field_values = self._prepare_field_values(data)
        
        # Validate if requested
        validation_errors = {}
        if validate:
            validation_errors = self.detector.validate_values(field_values)
            
            # Check for missing required fields
            for name, mapping in self.field_mappings.items():
                if mapping.required and name not in field_values:
                    if name not in validation_errors:
                        validation_errors[name] = []
                    validation_errors[name].append("Required field is missing")
        
        # Fill the PDF
        result = fill_pdf_form(pdf_path, field_values, output_path)
        
        result["validation_errors"] = validation_errors if validation_errors else None
        result["mappings_used"] = {
            name: mapping.data_key 
            for name, mapping in self.field_mappings.items()
            if name in field_values
        }
        
        return result
    
    def fill_docx(
        self,
        docx_path: Union[str, Path],
        data: Dict[str, Any],
        output_path: Union[str, Path],
        validate: bool = True,
        preserve_style: bool = True
    ) -> Dict[str, Any]:
        """
        Fill a DOCX template with data.
        
        Args:
            docx_path: Path to source DOCX.
            data: Data dictionary to fill.
            output_path: Path to save filled DOCX.
            validate: Whether to validate before filling.
            preserve_style: Whether to preserve text formatting.
            
        Returns:
            Dictionary with fill results and status.
        """
        docx_path = Path(docx_path)
        output_path = Path(output_path)
        
        # Detect fields if not already done
        if not self._detected_fields:
            self._detected_fields = self.detector.detect_docx_fields(docx_path)
        
        # Transform and map data
        field_values = self._prepare_field_values(data)
        
        # Validate if requested
        validation_errors = {}
        if validate:
            validation_errors = self.detector.validate_values(field_values)
        
        # Fill the DOCX
        result = fill_docx_template(docx_path, field_values, output_path, preserve_style)
        
        result["validation_errors"] = validation_errors if validation_errors else None
        result["mappings_used"] = {
            name: mapping.data_key
            for name, mapping in self.field_mappings.items()
            if name in field_values
        }
        
        return result
    
    def fill_auto(
        self,
        template_path: Union[str, Path],
        data: Dict[str, Any],
        output_path: Union[str, Path],
        **kwargs
    ) -> Dict[str, Any]:
        """
        Automatically detect template type and fill.
        
        Args:
            template_path: Path to template file.
            data: Data dictionary to fill.
            output_path: Path to save output.
            **kwargs: Additional arguments passed to specific filler.
            
        Returns:
            Dictionary with fill results.
        """
        template_path = Path(template_path)
        suffix = template_path.suffix.lower()
        
        if suffix == ".pdf":
            return self.fill_pdf(template_path, data, output_path, **kwargs)
        elif suffix in (".docx", ".doc"):
            return self.fill_docx(template_path, data, output_path, **kwargs)
        else:
            raise ValueError(f"Unsupported template format: {suffix}")
    
    def _prepare_field_values(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare field values from data using mappings.
        
        Applies:
        - Field mapping
        - Value transformation
        - Default values
        """
        field_values = {}
        
        # Apply mappings
        for field_name, mapping in self.field_mappings.items():
            # Get value from data
            value = data.get(mapping.data_key)
            
            # Use default if missing
            if value is None and mapping.default_value is not None:
                value = mapping.default_value
            
            # Apply custom transformer
            if mapping.transformer is not None:
                value = mapping.transformer(value)
            else:
                # Auto-transform based on field type
                detected = self._detected_fields.get(field_name)
                if detected:
                    value = self.transformer.transform(
                        value,
                        detected.field_type,
                        detected.metadata.get("format")
                    )
            
            if value is not None:
                field_values[field_name] = value
        
        # Also include unmapped data that matches field names
        for field_name in self._detected_fields:
            if field_name not in field_values and field_name in data:
                field_values[field_name] = data[field_name]
        
        return field_values
    
    def bulk_fill(
        self,
        template_path: Union[str, Path],
        data_rows: List[Dict[str, Any]],
        output_dir: Union[str, Path],
        filename_template: str = "filled_{index}.{ext}",
        continue_on_error: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Fill multiple forms from a list of data.
        
        Args:
            template_path: Path to template.
            data_rows: List of data dictionaries.
            output_dir: Directory for output files.
            filename_template: Template for output filenames.
            continue_on_error: Continue if one fill fails.
            
        Returns:
            List of fill results for each data row.
        """
        template_path = Path(template_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        ext = template_path.suffix.lower()
        
        for idx, data in enumerate(data_rows, 1):
            try:
                filename = filename_template.format(
                    index=idx,
                    ext=ext.lstrip("."),
                    **data
                )
                output_path = output_dir / filename
                
                result = self.fill_auto(template_path, data, output_path)
                result["index"] = idx
                results.append(result)
                
            except Exception as e:
                error_result = {
                    "index": idx,
                    "success": False,
                    "error": str(e),
                }
                results.append(error_result)
                
                if not continue_on_error:
                    logger.error(f"Bulk fill failed at index {idx}: {e}")
                    break
        
        successful = sum(1 for r in results if r.get("success", False))
        logger.info(f"Bulk fill completed: {successful}/{len(data_rows)} successful")
        
        return results
    
    def get_missing_fields(
        self,
        data: Dict[str, Any]
    ) -> List[str]:
        """
        Get list of required fields missing from data.
        
        Args:
            data: Data dictionary to check.
            
        Returns:
            List of missing required field names.
        """
        missing = []
        
        for field_name, detected in self._detected_fields.items():
            if detected.metadata.get("required", False):
                # Check if field has a value or a mapping with data
                if field_name not in data:
                    mapping = self.field_mappings.get(field_name)
                    if mapping:
                        if mapping.data_key not in data and mapping.default_value is None:
                            missing.append(field_name)
                    else:
                        missing.append(field_name)
        
        return missing
    
    def get_fill_preview(
        self,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Preview how data will fill the form without saving.
        
        Args:
            data: Data dictionary to preview.
            
        Returns:
            Dictionary showing mapped and transformed values.
        """
        field_values = self._prepare_field_values(data)
        
        return {
            "field_values": field_values,
            "unmapped_data": {
                k: v for k, v in data.items()
                if k not in field_values and k not in self.field_mappings
            },
            "missing_required": self.get_missing_fields(data),
            "total_fields": len(self._detected_fields),
            "fields_to_fill": len(field_values),
        }


# Convenience functions
def fill_form(
    template_path: Union[str, Path],
    data: Dict[str, Any],
    output_path: Union[str, Path],
    mapping_config: Optional[Union[str, Path]] = None
) -> Dict[str, Any]:
    """
    Convenience function to fill a form with optional mapping config.
    
    Args:
        template_path: Path to template.
        data: Data dictionary.
        output_path: Output path.
        mapping_config: Optional path to mapping config.
        
    Returns:
        Fill result dictionary.
    """
    filler = FormFiller()
    
    if mapping_config:
        filler.load_mapping_config(mapping_config)
    else:
        filler.auto_map_fields(template_path, list(data.keys()))
    
    return filler.fill_auto(template_path, data, output_path)


def bulk_fill_forms(
    template_path: Union[str, Path],
    data_rows: List[Dict[str, Any]],
    output_dir: Union[str, Path]
) -> List[Dict[str, Any]]:
    """
    Convenience function for bulk form filling.
    
    Args:
        template_path: Path to template.
        data_rows: List of data dictionaries.
        output_dir: Output directory.
        
    Returns:
        List of fill results.
    """
    filler = FormFiller()
    
    # Auto-map from first row
    if data_rows:
        filler.auto_map_fields(template_path, list(data_rows[0].keys()))
    
    return filler.bulk_fill(template_path, data_rows, output_dir)
