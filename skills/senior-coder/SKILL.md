---
name: senior-coder
description: Enforces senior-level coding practices: proper error handling, edge cases, validation, clean code principles, SOLID, DRY, KISS, testing, documentation, and defensive programming. Invoke when writing, reviewing, or debugging code to ensure production-quality output.
license: MIT
metadata:
  author: man44.zo.computer
  version: "1.0.0"
  domain: quality
  triggers: code, coding, write code, debug, refactor, review code
---

# Senior Coder - Production-Quality Code Practices

## When to Apply This Skill

- Writing new code
- Debugging existing code
- Reviewing code
- Refactoring
- Building features

## Core Principles

### 1. Error Handling - ALWAYS

```python
# BAD - No error handling
def read_file(path):
    return open(path).read()

# GOOD - Defensive error handling
def read_file(path: str) -> dict:
    \"\"\"Read file with proper error handling.
    
    Args:
        path: File path to read
        
    Returns:
        dict with 'success' (bool), 'content' (str) or 'error' (str)
    \"\"\"
    try:
        if not path:
            return {"success": False, "error": "Path is required"}
        
        path_obj = Path(path)
        if not path_obj.exists():
            return {"success": False, "error": f"File not found: {path}"}
        
        if not path_obj.is_file():
            return {"success": False, "error": f"Not a file: {path}"}
        
        if path_obj.stat().st_size > 10_000_000:  # 10MB limit
            return {"success": False, "error": "File too large (max 10MB)"}
        
        content = path_obj.read_text(encoding='utf-8', errors='replace')
        return {"success": True, "content": content}
    
    except PermissionError:
        return {"success": False, "error": f"Permission denied: {path}"}
    except UnicodeDecodeError:
        return {"success": False, "error": f"Cannot decode file (not text?): {path}"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {type(e).__name__}: {e}"}
```

### 2. Input Validation - ALWAYS

```python
# BAD - No validation
def process_user(user_id, email):
    save_to_db(user_id, email)

# GOOD - Validate all inputs
def process_user(user_id: str, email: str) -> dict:
    \"\"\"Process user with validation.\"\"\"
    
    # Validate user_id
    if not user_id or not isinstance(user_id, str):
        return {"success": False, "error": "user_id must be a non-empty string"}
    
    if len(user_id) > 36:
        return {"success": False, "error": "user_id too long (max 36 chars)"}
    
    # Validate email
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return {"success": False, "error": "Invalid email format"}
    
    return save_to_db(user_id, email)
```

### 3. Edge Cases - ALWAYS CONSIDER

```python
def get_first_item(items: list) -> any:
    \"\"\"Get first item safely.\"\"\"
    
    # Edge case: None input
    if items is None:
        return None
    
    # Edge case: Not a list
    if not isinstance(items, (list, tuple)):
        raise TypeError(f"Expected list, got {type(items).__name__}")
    
    # Edge case: Empty list
    if len(items) == 0:
        return None
    
    return items[0]
```

### 4. Type Hints - ALWAYS

```python
from typing import Optional, List, Dict, Any, Union, Callable

def process_data(
    items: List[Dict[str, Any]],
    processor: Callable[[Dict], Optional[Dict]],
    max_items: int = 100
) -> Dict[str, Union[List[Dict], str, int]]:
    \"\"\"Process list of items with a processor function.\"\"\"
    ...
```

### 5. Documentation - ALWAYS

```python
def calculate_total(
    items: List[Dict[str, float]],
    tax_rate: float = 0.0,
    discount: float = 0.0
) -> Dict[str, float]:
    \"\"\"Calculate total price for items.
    
    Args:
        items: List of item dicts with 'price' and 'quantity' keys
        tax_rate: Tax rate as decimal (0.1 = 10%), default 0
        discount: Discount amount to subtract, default 0
        
    Returns:
        Dict containing:
            - subtotal: Sum of price * quantity
            - tax: Tax amount
            - discount: Discount applied
            - total: Final amount
            
    Raises:
        ValueError: If items is empty or has invalid structure
        TypeError: If tax_rate or discount are not numeric
        
    Examples:
        >>> calculate_total([{'price': 10, 'quantity': 2}], tax_rate=0.1)
        {'subtotal': 20.0, 'tax': 2.0, 'discount': 0.0, 'total': 22.0}
    \"\"\"
    ...
```

### 6. SOLID Principles

- **S**ingle Responsibility: One class/function = one job
- **O**pen/Closed: Open for extension, closed for modification
- **L**iskov Substitution: Subclasses must be substitutable
- **I**nterface Segregation: Many specific interfaces > one general
- **D**ependency Inversion: Depend on abstractions, not concretions

### 7. DRY (Don't Repeat Yourself)

```python
# BAD - Repeated logic
def process_csv(file): ...
def process_json(file): ...
def process_xml(file): ...

# GOOD - Abstracted
def read_file(path, parser):
    content = Path(path).read_text()
    return parser(content)

def process_csv(content): ...
def process_json(content): ...

# Usage
data = read_file('data.csv', process_csv)
```

### 8. KISS (Keep It Simple, Stupid)

```python
# BAD - Over-engineered
class DataProcessorFactory:
    def create_processor(self, type):
        if type == 'csv':
            return CSVProcessorBuilder().with_validation().build()
        ...

# GOOD - Simple
def process_data(data, type):
    if type == 'csv':
        return process_csv(data)
    elif type == 'json':
        return process_json(data)
    raise ValueError(f"Unknown type: {type}")
```

### 9. Testing - REQUIRED FOR CRITICAL PATHS

```python
import pytest

def test_read_file():
    # Test success
    result = read_file('test.txt')
    assert result['success'] == True
    
    # Test file not found
    result = read_file('nonexistent.txt')
    assert result['success'] == False
    assert 'not found' in result['error'].lower()
    
    # Test empty path
    result = read_file('')
    assert result['success'] == False
    
    # Test None path
    result = read_file(None)
    assert result['success'] == False
```

### 10. Logging - FOR PRODUCTION

```python
import logging

logger = logging.getLogger(__name__)

def risky_operation(data):
    logger.debug(f"Starting operation with {len(data)} items")
    try:
        result = process(data)
        logger.info(f"Operation completed: {result}")
        return result
    except Exception as e:
        logger.error(f"Operation failed: {e}", exc_info=True)
        raise
```

## Checklist Before Committing Code

- [ ] All functions have error handling (try/except or return error dict)
- [ ] All inputs validated (type, range, null, empty)
- [ ] Edge cases handled (empty lists, None, invalid types, overflow)
- [ ] Type hints on all function signatures
- [ ] Docstrings on all public functions/classes
- [ ] No hardcoded values (use constants/config)
- [ ] No repeated code (DRY)
- [ ] No over-engineering (KISS)
- [ ] Critical paths have tests
- [ ] Logging for debugging/production

## Common Mistakes to Avoid

1. **Assuming inputs are valid** - NEVER trust input
2. **Silent failures** - ALWAYS report errors
3. **Over-catching exceptions** - Catch specific exceptions
4. **Missing None checks** - ALWAYS check for None
5. **Hardcoded paths/configs** - USE configuration
6. **Ignoring return values** - CHECK return values
7. **Deep nesting** - MAX 3 levels of nesting
8. **Long functions** - MAX 50 lines per function
9. **Magic numbers** - USE named constants
10. **Missing cleanup** - USE context managers (with)
