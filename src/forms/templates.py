"""
Template Management for Sentience v3.0
Manages form templates with storage, CRUD, versioning, and variable extraction.
"""

import os
import json
import shutil
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

from .pdf_engine import PDFEngine, get_pdf_fields
from .docx_engine import DOCXEngine, get_docx_fields
from .field_detector import FieldDetector, DetectedField

logger = logging.getLogger(__name__)


class TemplateType(Enum):
    """Template file types."""
    PDF = "pdf"
    DOCX = "docx"
    UNKNOWN = "unknown"


@dataclass
class TemplateVariable:
    """Represents a template variable/field."""
    name: str
    field_type: str
    required: bool = False
    default_value: Optional[Any] = None
    description: str = ""
    validation_pattern: Optional[str] = None
    options: List[str] = field(default_factory=list)
    position: Optional[Dict[str, Any]] = None  # Page, rect info


@dataclass
class TemplateVersion:
    """Represents a template version."""
    version_id: str
    version_number: int
    created_at: str
    created_by: str = "system"
    notes: str = ""
    file_hash: str = ""
    changes: List[str] = field(default_factory=list)


@dataclass
class Template:
    """Represents a form template."""
    template_id: str
    name: str
    description: str = ""
    template_type: TemplateType = TemplateType.UNKNOWN
    file_path: str = ""
    variables: List[TemplateVariable] = field(default_factory=list)
    versions: List[TemplateVersion] = field(default_factory=list)
    current_version: int = 1
    tags: List[str] = field(default_factory=list)
    category: str = "general"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["template_type"] = self.template_type.value
        data["variables"] = [asdict(v) for v in self.variables]
        data["versions"] = [asdict(v) for v in self.versions]
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Template":
        """Create from dictionary."""
        data = data.copy()
        data["template_type"] = TemplateType(data.get("template_type", "unknown"))
        
        # Convert variables
        variables = [
            TemplateVariable(**v) for v in data.pop("variables", [])
        ]
        
        # Convert versions
        versions = [
            TemplateVersion(**v) for v in data.pop("versions", [])
        ]
        
        return cls(
            variables=variables,
            versions=versions,
            **data
        )


class TemplateStorage:
    """
    Template storage backend.
    
    Manages:
    - Template file storage
    - Metadata persistence
    - Version history
    """
    
    def __init__(self, storage_dir: Union[str, Path] = None):
        """
        Initialize template storage.
        
        Args:
            storage_dir: Directory for storing templates.
        """
        if storage_dir is None:
            storage_dir = Path.home() / ".sentience" / "templates"
        
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.templates_file = self.storage_dir / "templates.json"
        self._templates: Dict[str, Template] = {}
        
        self._load_templates()
    
    def _load_templates(self) -> None:
        """Load templates from storage."""
        if self.templates_file.exists():
            try:
                with open(self.templates_file, "r") as f:
                    data = json.load(f)
                    self._templates = {
                        tid: Template.from_dict(tdata)
                        for tid, tdata in data.items()
                    }
                logger.info(f"Loaded {len(self._templates)} templates")
            except Exception as e:
                logger.error(f"Failed to load templates: {e}")
                self._templates = {}
    
    def _save_templates(self) -> None:
        """Save templates to storage."""
        with open(self.templates_file, "w") as f:
            json.dump({
                tid: template.to_dict()
                for tid, template in self._templates.items()
            }, f, indent=2)
        logger.debug("Saved templates to storage")
    
    def _get_template_dir(self, template_id: str) -> Path:
        """Get directory for a template."""
        template_dir = self.storage_dir / template_id
        template_dir.mkdir(parents=True, exist_ok=True)
        return template_dir
    
    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()


class TemplateManager(TemplateStorage):
    """
    Template management with CRUD operations and versioning.
    
    Extends TemplateStorage with:
    - Template creation and import
    - Variable extraction
    - Version control
    - Search and filtering
    """
    
    def __init__(self, storage_dir: Union[str, Path] = None):
        """Initialize template manager."""
        super().__init__(storage_dir)
        self.detector = FieldDetector()
    
    def create_template(
        self,
        name: str,
        source_file: Union[str, Path],
        description: str = "",
        category: str = "general",
        tags: List[str] = None,
        extract_variables: bool = True
    ) -> Template:
        """
        Create a new template from a file.
        
        Args:
            name: Template name.
            source_file: Source PDF or DOCX file.
            description: Template description.
            category: Template category.
            tags: List of tags.
            extract_variables: Whether to auto-extract variables.
            
        Returns:
            Created Template object.
        """
        source_file = Path(source_file)
        if not source_file.exists():
            raise FileNotFoundError(f"Source file not found: {source_file}")
        
        # Generate template ID
        template_id = self._generate_id(name)
        template_dir = self._get_template_dir(template_id)
        
        # Determine type
        suffix = source_file.suffix.lower()
        if suffix == ".pdf":
            template_type = TemplateType.PDF
        elif suffix in (".docx", ".doc"):
            template_type = TemplateType.DOCX
        else:
            template_type = TemplateType.UNKNOWN
        
        # Copy file to storage
        dest_file = template_dir / source_file.name
        shutil.copy2(source_file, dest_file)
        
        # Create template
        template = Template(
            template_id=template_id,
            name=name,
            description=description,
            template_type=template_type,
            file_path=str(dest_file),
            category=category,
            tags=tags or [],
        )
        
        # Extract variables if requested
        if extract_variables:
            template.variables = self._extract_variables(dest_file)
        
        # Create initial version
        initial_version = TemplateVersion(
            version_id=self._generate_id("v1"),
            version_number=1,
            created_at=datetime.now().isoformat(),
            file_hash=self._compute_file_hash(dest_file),
            notes="Initial version",
        )
        template.versions.append(initial_version)
        
        # Save to storage
        self._templates[template_id] = template
        self._save_templates()
        
        logger.info(f"Created template: {name} ({template_id})")
        return template
    
    def _generate_id(self, prefix: str) -> str:
        """Generate unique ID."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        hash_part = hashlib.md5(f"{prefix}{timestamp}".encode()).hexdigest()[:8]
        return f"{prefix.lower().replace(' ', '-')}_{timestamp}_{hash_part}"
    
    def _extract_variables(
        self,
        file_path: Path
    ) -> List[TemplateVariable]:
        """Extract variables from template file."""
        variables = []
        
        try:
            if file_path.suffix.lower() == ".pdf":
                detected_fields = self.detector.detect_pdf_fields(file_path)
            else:
                detected_fields = self.detector.detect_docx_fields(file_path)
            
            for name, detected in detected_fields.items():
                var = TemplateVariable(
                    name=name,
                    field_type=detected.field_type.value,
                    required=detected.metadata.get("required", False),
                    description=detected.metadata.get("tooltip", ""),
                    options=detected.metadata.get("options", []),
                    position={
                        "page": detected.metadata.get("page_number"),
                        "rect": detected.metadata.get("rect"),
                    } if detected.metadata.get("page_number") is not None else None,
                )
                variables.append(var)
                
        except Exception as e:
            logger.warning(f"Failed to extract variables: {e}")
        
        return variables
    
    def get_template(self, template_id: str) -> Optional[Template]:
        """
        Get a template by ID.
        
        Args:
            template_id: Template ID.
            
        Returns:
            Template object or None if not found.
        """
        return self._templates.get(template_id)
    
    def get_template_by_name(self, name: str) -> Optional[Template]:
        """Get template by name (first match)."""
        for template in self._templates.values():
            if template.name == name:
                return template
        return None
    
    def update_template(
        self,
        template_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Template]:
        """
        Update template metadata.
        
        Args:
            template_id: Template ID.
            name: New name.
            description: New description.
            category: New category.
            tags: New tags.
            metadata: Additional metadata.
            
        Returns:
            Updated Template or None if not found.
        """
        template = self._templates.get(template_id)
        if not template:
            return None
        
        if name is not None:
            template.name = name
        if description is not None:
            template.description = description
        if category is not None:
            template.category = category
        if tags is not None:
            template.tags = tags
        if metadata is not None:
            template.metadata.update(metadata)
        
        template.updated_at = datetime.now().isoformat()
        
        self._save_templates()
        logger.info(f"Updated template: {template_id}")
        
        return template
    
    def update_template_file(
        self,
        template_id: str,
        new_file: Union[str, Path],
        notes: str = ""
    ) -> Optional[Template]:
        """
        Update template file with new version.
        
        Args:
            template_id: Template ID.
            new_file: New template file.
            notes: Version notes.
            
        Returns:
            Updated Template or None if not found.
        """
        template = self._templates.get(template_id)
        if not template:
            return None
        
        new_file = Path(new_file)
        if not new_file.exists():
            raise FileNotFoundError(f"New file not found: {new_file}")
        
        template_dir = self._get_template_dir(template_id)
        
        # Store old file as version
        old_file = Path(template.file_path)
        version_number = template.current_version + 1
        
        # Rename old file to version
        if old_file.exists():
            version_file = template_dir / f"v{version_number - 1}_{old_file.name}"
            shutil.move(old_file, version_file)
        
        # Copy new file
        dest_file = template_dir / new_file.name
        shutil.copy2(new_file, dest_file)
        template.file_path = str(dest_file)
        
        # Create version record
        new_version = TemplateVersion(
            version_id=self._generate_id(f"v{version_number}"),
            version_number=version_number,
            created_at=datetime.now().isoformat(),
            notes=notes,
            file_hash=self._compute_file_hash(dest_file),
        )
        template.versions.append(new_version)
        template.current_version = version_number
        
        # Re-extract variables
        template.variables = self._extract_variables(dest_file)
        template.updated_at = datetime.now().isoformat()
        
        self._save_templates()
        logger.info(f"Updated template file: {template_id} (v{version_number})")
        
        return template
    
    def delete_template(
        self,
        template_id: str,
        keep_files: bool = False
    ) -> bool:
        """
        Delete a template.
        
        Args:
            template_id: Template ID.
            keep_files: Whether to keep stored files.
            
        Returns:
            True if deleted, False if not found.
        """
        template = self._templates.get(template_id)
        if not template:
            return False
        
        # Remove files
        if not keep_files:
            template_dir = self._get_template_dir(template_id)
            if template_dir.exists():
                shutil.rmtree(template_dir)
        
        # Remove from registry
        del self._templates[template_id]
        self._save_templates()
        
        logger.info(f"Deleted template: {template_id}")
        return True
    
    def list_templates(
        self,
        category: Optional[str] = None,
        template_type: Optional[TemplateType] = None,
        tags: Optional[List[str]] = None,
        search: Optional[str] = None
    ) -> List[Template]:
        """
        List templates with optional filtering.
        
        Args:
            category: Filter by category.
            template_type: Filter by type.
            tags: Filter by tags (any match).
            search: Search in name and description.
            
        Returns:
            List of matching templates.
        """
        templates = list(self._templates.values())
        
        if category:
            templates = [t for t in templates if t.category == category]
        
        if template_type:
            templates = [t for t in templates if t.template_type == template_type]
        
        if tags:
            templates = [
                t for t in templates
                if any(tag in t.tags for tag in tags)
            ]
        
        if search:
            search_lower = search.lower()
            templates = [
                t for t in templates
                if search_lower in t.name.lower()
                or search_lower in t.description.lower()
            ]
        
        return templates
    
    def get_template_file(
        self,
        template_id: str,
        version: Optional[int] = None
    ) -> Optional[Path]:
        """
        Get template file path.
        
        Args:
            template_id: Template ID.
            version: Version number (None for current).
            
        Returns:
            Path to template file or None.
        """
        template = self._templates.get(template_id)
        if not template:
            return None
        
        if version is None or version == template.current_version:
            file_path = Path(template.file_path)
            if file_path.exists():
                return file_path
            return None
        
        # Get specific version
        template_dir = self._get_template_dir(template_id)
        file_name = Path(template.file_path).name
        version_file = template_dir / f"v{version}_{file_name}"
        
        if version_file.exists():
            return version_file
        
        return None
    
    def get_version_history(
        self,
        template_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get version history for a template.
        
        Args:
            template_id: Template ID.
            
        Returns:
            List of version information.
        """
        template = self._templates.get(template_id)
        if not template:
            return []
        
        return [asdict(v) for v in template.versions]
    
    def restore_version(
        self,
        template_id: str,
        version_number: int
    ) -> Optional[Template]:
        """
        Restore a previous version as current.
        
        Args:
            template_id: Template ID.
            version_number: Version to restore.
            
        Returns:
            Updated Template or None.
        """
        template = self._templates.get(template_id)
        if not template:
            return None
        
        # Find the version
        version_file = self.get_template_file(template_id, version_number)
        if not version_file:
            logger.error(f"Version {version_number} file not found")
            return None
        
        # Get version info
        version_info = next(
            (v for v in template.versions if v.version_number == version_number),
            None
        )
        
        if not version_info:
            return None
        
        # Create new version from restore
        return self.update_template_file(
            template_id,
            version_file,
            notes=f"Restored from version {version_number}"
        )
    
    def add_variable(
        self,
        template_id: str,
        variable: TemplateVariable
    ) -> Optional[Template]:
        """Add a variable to template."""
        template = self._templates.get(template_id)
        if not template:
            return None
        
        # Remove existing with same name
        template.variables = [
            v for v in template.variables if v.name != variable.name
        ]
        template.variables.append(variable)
        template.updated_at = datetime.now().isoformat()
        
        self._save_templates()
        return template
    
    def remove_variable(
        self,
        template_id: str,
        variable_name: str
    ) -> Optional[Template]:
        """Remove a variable from template."""
        template = self._templates.get(template_id)
        if not template:
            return None
        
        template.variables = [
            v for v in template.variables if v.name != variable_name
        ]
        template.updated_at = datetime.now().isoformat()
        
        self._save_templates()
        return template
    
    def export_template(
        self,
        template_id: str,
        output_dir: Union[str, Path],
        include_versions: bool = False
    ) -> Optional[Path]:
        """
        Export template to directory.
        
        Args:
            template_id: Template ID.
            output_dir: Output directory.
            include_versions: Include all version files.
            
        Returns:
            Path to export directory.
        """
        template = self._templates.get(template_id)
        if not template:
            return None
        
        output_dir = Path(output_dir) / template_id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy current file
        current_file = Path(template.file_path)
        if current_file.exists():
            shutil.copy2(current_file, output_dir / current_file.name)
        
        # Export metadata
        metadata_path = output_dir / "template.json"
        with open(metadata_path, "w") as f:
            json.dump(template.to_dict(), f, indent=2)
        
        # Export versions if requested
        if include_versions:
            versions_dir = output_dir / "versions"
            versions_dir.mkdir(exist_ok=True)
            
            for version in template.versions:
                version_file = self.get_template_file(
                    template_id, version.version_number
                )
                if version_file and version_file.exists():
                    shutil.copy2(version_file, versions_dir / version_file.name)
        
        logger.info(f"Exported template: {template_id}")
        return output_dir
    
    def import_template(
        self,
        source_dir: Union[str, Path],
        new_name: Optional[str] = None
    ) -> Optional[Template]:
        """
        Import template from exported directory.
        
        Args:
            source_dir: Source directory with template.json.
            new_name: Optional new name.
            
        Returns:
            Imported Template.
        """
        source_dir = Path(source_dir)
        metadata_file = source_dir / "template.json"
        
        if not metadata_file.exists():
            raise FileNotFoundError(f"No template.json in {source_dir}")
        
        with open(metadata_file, "r") as f:
            data = json.load(f)
        
        # Find template file
        template_files = [
            f for f in source_dir.iterdir()
            if f.suffix.lower() in (".pdf", ".docx", ".doc")
            and f.name != "template.json"
        ]
        
        if not template_files:
            raise FileNotFoundError(f"No template file in {source_dir}")
        
        # Create from file
        template_file = template_files[0]
        name = new_name or data.get("name", template_file.stem)
        
        template = self.create_template(
            name=name,
            source_file=template_file,
            description=data.get("description", ""),
            category=data.get("category", "general"),
            tags=data.get("tags", []),
        )
        
        # Apply saved variables if present
        if "variables" in data:
            template.variables = [
                TemplateVariable(**v) for v in data["variables"]
            ]
            self._save_templates()
        
        logger.info(f"Imported template: {template.template_id}")
        return template
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get template storage statistics."""
        return {
            "total_templates": len(self._templates),
            "by_type": {
                t.value: sum(
                    1 for t2 in self._templates.values()
                    if t2.template_type == t
                )
                for t in TemplateType
            },
            "by_category": self._count_by_field("category"),
            "total_versions": sum(
                len(t.versions) for t in self._templates.values()
            ),
            "storage_size": self._get_storage_size(),
        }
    
    def _count_by_field(self, field: str) -> Dict[str, int]:
        """Count templates by a field value."""
        counts = {}
        for template in self._templates.values():
            value = getattr(template, field, "unknown")
            counts[value] = counts.get(value, 0) + 1
        return counts
    
    def _get_storage_size(self) -> int:
        """Get total storage size in bytes."""
        total = 0
        for path in self.storage_dir.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return total


# Convenience functions
def create_template(
    name: str,
    source_file: Union[str, Path],
    storage_dir: Optional[Union[str, Path]] = None
) -> Template:
    """Convenience function to create a template."""
    manager = TemplateManager(storage_dir)
    return manager.create_template(name, source_file)


def get_template(
    template_id: str,
    storage_dir: Optional[Union[str, Path]] = None
) -> Optional[Template]:
    """Convenience function to get a template."""
    manager = TemplateManager(storage_dir)
    return manager.get_template(template_id)


def list_templates(
    storage_dir: Optional[Union[str, Path]] = None,
    **filters
) -> List[Template]:
    """Convenience function to list templates."""
    manager = TemplateManager(storage_dir)
    return manager.list_templates(**filters)
