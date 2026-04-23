"""
CSV Processor Skill
Process and manipulate CSV files.
"""

import os
import csv
import io
from typing import Dict, List, Any, Optional, Iterator
from dataclasses import dataclass
from collections import Counter

METADATA = {
    "name": "csv-processor",
    "description": "Process, transform, and analyze CSV files",
    "category": "data",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["process csv", "csv file", "parse csv", "csv data"],
    "dependencies": [],
    "tags": ["csv", "data", "processing", "pandas"]
}

SKILL_NAME = "csv-processor"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "data"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


@dataclass
class CSVStats:
    rows: int
    columns: int
    headers: List[str]
    column_types: Dict[str, str]
    null_counts: Dict[str, int]
    unique_counts: Dict[str, int]


class CSVProcessor:
    """Process and manipulate CSV files."""
    
    def __init__(self, delimiter: str = ',', quotechar: str = '"'):
        self.delimiter = delimiter
        self.quotechar = quotechar
        self.data: List[Dict[str, Any]] = []
        self.headers: List[str] = []
    
    def read_file(self, filepath: str, has_header: bool = True) -> List[Dict[str, Any]]:
        """Read CSV file into list of dicts."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
        
        self.data = []
        
        with open(filepath, 'r', encoding='utf-8', newline='') as f:
            reader = csv.reader(f, delimiter=self.delimiter, quotechar=self.quotechar)
            
            if has_header:
                self.headers = next(reader)
            else:
                first_row = next(reader)
                self.headers = [f"col_{i}" for i in range(len(first_row))]
                self.data.append(dict(zip(self.headers, first_row)))
            
            for row in reader:
                self.data.append(dict(zip(self.headers, row)))
        
        return self.data
    
    def read_string(self, csv_string: str, has_header: bool = True) -> List[Dict[str, Any]]:
        """Read CSV string into list of dicts."""
        self.data = []
        
        reader = csv.reader(io.StringIO(csv_string), delimiter=self.delimiter, quotechar=self.quotechar)
        
        if has_header:
            self.headers = next(reader)
        else:
            first_row = next(reader)
            self.headers = [f"col_{i}" for i in range(len(first_row))]
            self.data.append(dict(zip(self.headers, first_row)))
        
        for row in reader:
            if row:  # Skip empty rows
                self.data.append(dict(zip(self.headers, row)))
        
        return self.data
    
    def write_file(self, filepath: str, data: List[Dict] = None) -> str:
        """Write data to CSV file."""
        data = data or self.data
        
        if not data:
            raise ValueError("No data to write")
        
        with open(filepath, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.headers, delimiter=self.delimiter, quotechar=self.quotechar)
            writer.writeheader()
            writer.writerows(data)
        
        return filepath
    
    def to_string(self, data: List[Dict] = None) -> str:
        """Convert data to CSV string."""
        data = data or self.data
        
        if not data:
            return ""
        
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=self.headers, delimiter=self.delimiter, quotechar=self.quotechar)
        writer.writeheader()
        writer.writerows(data)
        
        return output.getvalue()
    
    def get_stats(self) -> CSVStats:
        """Get statistics about the CSV data."""
        if not self.data:
            return CSVStats(0, 0, [], {}, {}, {})
        
        column_types = {}
        null_counts = {}
        unique_counts = {}
        
        for header in self.headers:
            values = [row.get(header, '') for row in self.data]
            non_null = [v for v in values if v and v.strip()]
            
            # Determine type
            column_types[header] = self._infer_column_type(non_null)
            
            # Count nulls
            null_counts[header] = len(values) - len(non_null)
            
            # Count unique
            unique_counts[header] = len(set(non_null))
        
        return CSVStats(
            rows=len(self.data),
            columns=len(self.headers),
            headers=self.headers,
            column_types=column_types,
            null_counts=null_counts,
            unique_counts=unique_counts
        )
    
    def _infer_column_type(self, values: List[str]) -> str:
        """Infer the type of a column from its values."""
        if not values:
            return "empty"
        
        # Check if all values are integers
        try:
            [int(v) for v in values]
            return "integer"
        except ValueError:
            pass
        
        # Check if all values are floats
        try:
            [float(v) for v in values]
            return "float"
        except ValueError:
            pass
        
        # Check if all values are booleans
        bool_values = {'true', 'false', 'yes', 'no', '1', '0'}
        if all(v.lower() in bool_values for v in values):
            return "boolean"
        
        return "string"
    
    def filter_rows(self, condition: callable) -> List[Dict[str, Any]]:
        """Filter rows based on condition function."""
        return [row for row in self.data if condition(row)]
    
    def filter_by_value(self, column: str, value: Any, operator: str = "==") -> List[Dict[str, Any]]:
        """Filter rows by column value."""
        result = []
        
        for row in self.data:
            row_val = row.get(column, '')
            
            # Convert value types for comparison
            if operator in ('==', '!=', '>', '<', '>=', '<='):
                try:
                    row_val = float(row_val) if '.' in str(row_val) else int(row_val)
                    value = float(value) if '.' in str(value) else int(value)
                except (ValueError, TypeError):
                    pass
            
            if operator == "==" and row_val == value:
                result.append(row)
            elif operator == "!=" and row_val != value:
                result.append(row)
            elif operator == ">" and row_val > value:
                result.append(row)
            elif operator == "<" and row_val < value:
                result.append(row)
            elif operator == ">=" and row_val >= value:
                result.append(row)
            elif operator == "<=" and row_val <= value:
                result.append(row)
            elif operator == "contains" and str(value).lower() in str(row_val).lower():
                result.append(row)
            elif operator == "startswith" and str(row_val).lower().startswith(str(value).lower()):
                result.append(row)
        
        return result
    
    def sort_rows(self, column: str, reverse: bool = False) -> List[Dict[str, Any]]:
        """Sort rows by column value."""
        return sorted(self.data, key=lambda x: x.get(column, ''), reverse=reverse)
    
    def select_columns(self, columns: List[str]) -> List[Dict[str, Any]]:
        """Select only specific columns."""
        return [{k: row.get(k, '') for k in columns} for row in self.data]
    
    def rename_column(self, old_name: str, new_name: str) -> None:
        """Rename a column."""
        if old_name not in self.headers:
            raise ValueError(f"Column '{old_name}' not found")
        
        self.headers[self.headers.index(old_name)] = new_name
        
        for row in self.data:
            if old_name in row:
                row[new_name] = row.pop(old_name)
    
    def add_column(self, name: str, value: Any = '', transform: callable = None) -> None:
        """Add a new column."""
        self.headers.append(name)
        
        for row in self.data:
            if transform:
                row[name] = transform(row)
            else:
                row[name] = value
    
    def transform_column(self, column: str, transform: callable) -> None:
        """Transform values in a column."""
        for row in self.data:
            if column in row:
                row[column] = transform(row[column])
    
    def group_by(self, column: str, agg: str = "count") -> Dict[str, Any]:
        """Group rows by column and aggregate."""
        groups = {}
        
        for row in self.data:
            key = row.get(column, '')
            if key not in groups:
                groups[key] = []
            groups[key].append(row)
        
        if agg == "count":
            return {k: len(v) for k, v in groups.items()}
        elif agg == "sum":
            return {k: sum(float(r.get(column, 0) for r in v if r.get(column, '').replace('.', '').isdigit()) for k, v in groups.items()}
        elif agg == "mean":
            sums = {}
            counts = {}
            for key, rows in groups.items():
                numeric = [float(r.get(column, 0)) for r in rows if r.get(column, '').replace('.', '').isdigit()]
                if numeric:
                    sums[key] = sum(numeric)
                    counts[key] = len(numeric)
            return {k: sums[k] / counts[k] for k in sums}
        elif agg == "list":
            return groups
        
        return groups
    
    def merge(self, other: 'CSVProcessor', on: str, how: str = "inner") -> 'CSVProcessor':
        """Merge with another CSV on a common column."""
        result = CSVProcessor()
        result.headers = self.headers + [h for h in other.headers if h not in self.headers]
        
        # Build index for other
        other_index = {}
        for row in other.data:
            key = row.get(on, '')
            if key not in other_index:
                other_index[key] = []
            other_index[key].append(row)
        
        # Merge
        for row in self.data:
            key = row.get(on, '')
            
            if key in other_index:
                for other_row in other_index[key]:
                    merged = {**row, **other_row}
                    result.data.append(merged)
            elif how == "left":
                result.data.append({**row, **{h: '' for h in other.headers}})
        
        return result
    
    def deduplicate(self, subset: List[str] = None) -> List[Dict[str, Any]]:
        """Remove duplicate rows."""
        seen = set()
        unique = []
        
        for row in self.data:
            if subset:
                key = tuple(row.get(c, '') for c in subset)
            else:
                key = tuple(sorted(row.items()))
            
            if key not in seen:
                seen.add(key)
                unique.append(row)
        
        self.data = unique
        return unique
    
    def sample(self, n: int = None, fraction: float = None) -> List[Dict[str, Any]]:
        """Get a sample of the data."""
        import random
        
        if n is not None:
            return random.sample(self.data, min(n, len(self.data)))
        elif fraction is not None:
            n = int(len(self.data) * fraction)
            return random.sample(self.data, n)
        
        return self.data[:10]


def execute(
    filepath: str = None,
    csv_string: str = None,
    operation: str = "read",
    output_file: str = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Process CSV files.
    
    Args:
        filepath: Path to CSV file
        csv_string: CSV data as string
        operation: Operation (read/stats/filter/sort/select/transform/group/merge/sample)
        output_file: Output file path for write operations
    
    Returns:
        Processing results
    """
    processor = CSVProcessor(
        delimiter=kwargs.get('delimiter', ','),
        quotechar=kwargs.get('quotechar', '"')
    )
    
    # Read data first
    if filepath:
        processor.read_file(filepath, has_header=kwargs.get('has_header', True))
    elif csv_string:
        processor.read_string(csv_string, has_header=kwargs.get('has_header', True))
    
    if operation == "read":
        return {
            "success": True,
            "data": processor.data,
            "rows": len(processor.data),
            "headers": processor.headers
        }
    
    elif operation == "stats":
        stats = processor.get_stats()
        return {
            "success": True,
            "stats": {
                "rows": stats.rows,
                "columns": stats.columns,
                "headers": stats.headers,
                "column_types": stats.column_types,
                "null_counts": stats.null_counts,
                "unique_counts": stats.unique_counts
            }
        }
    
    elif operation == "filter":
        column = kwargs.get('column')
        value = kwargs.get('value')
        operator = kwargs.get('operator', '==')
        
        if not column:
            return {"success": False, "error": "column required for filter"}
        
        filtered = processor.filter_by_value(column, value, operator)
        return {
            "success": True,
            "data": filtered,
            "original_rows": len(processor.data),
            "filtered_rows": len(filtered)
        }
    
    elif operation == "sort":
        column = kwargs.get('column')
        reverse = kwargs.get('reverse', False)
        
        if not column:
            return {"success": False, "error": "column required for sort"}
        
        sorted_data = processor.sort_rows(column, reverse)
        return {
            "success": True,
            "data": sorted_data
        }
    
    elif operation == "select":
        columns = kwargs.get('columns', [])
        
        if not columns:
            return {"success": False, "error": "columns required for select"}
        
        selected = processor.select_columns(columns)
        return {
            "success": True,
            "data": selected,
            "selected_columns": columns
        }
    
    elif operation == "transform":
        column = kwargs.get('column')
        transforms = kwargs.get('transforms', {})
        
        if not column:
            return {"success": False, "error": "column required for transform"}
        
        for col, transform in transforms.items():
            processor.transform_column(col, transform)
        
        return {
            "success": True,
            "data": processor.data
        }
    
    elif operation == "group":
        column = kwargs.get('column')
        agg = kwargs.get('agg', 'count')
        
        if not column:
            return {"success": False, "error": "column required for group"}
        
        grouped = processor.group_by(column, agg)
        return {
            "success": True,
            "groups": grouped,
            "aggregation": agg
        }
    
    elif operation == "merge":
        other_file = kwargs.get('other_file')
        on = kwargs.get('on')
        how = kwargs.get('how', 'inner')
        
        if not other_file or not on:
            return {"success": False, "error": "other_file and 'on' column required for merge"}
        
        other = CSVProcessor()
        other.read_file(other_file)
        
        merged = processor.merge(other, on, how)
        return {
            "success": True,
            "data": merged.data,
            "rows": len(merged.data)
        }
    
    elif operation == "sample":
        n = kwargs.get('n')
        fraction = kwargs.get('fraction')
        
        sample = processor.sample(n, fraction)
        return {
            "success": True,
            "data": sample,
            "sample_size": len(sample)
        }
    
    elif operation == "write":
        if not output_file:
            return {"success": False, "error": "output_file required for write"}
        
        processor.write_file(output_file)
        return {
            "success": True,
            "output_file": output_file,
            "rows_written": len(processor.data)
        }
    
    return {"success": False, "error": f"Unknown operation: {operation}"}
