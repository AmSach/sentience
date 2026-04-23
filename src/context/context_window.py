"""
Context Window - LLM context window management

Features:
- Token counting for multiple models
- Context prioritization
- Context compression
- Smart truncation strategies
"""

import os
import re
import math
import json
import hashlib
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from collections import Counter
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModelType(Enum):
    """Supported LLM model types."""
    GPT_4 = "gpt-4"
    GPT_4_TURBO = "gpt-4-turbo"
    GPT_4O = "gpt-4o"
    GPT_35_TURBO = "gpt-3.5-turbo"
    CLAUDE_3_OPUS = "claude-3-opus"
    CLAUPE_3_SONNET = "claude-3-sonnet"
    CLAUDE_3_HAIKU = "claude-3-haiku"
    CLAUDE_3_5_SONNET = "claude-3.5-sonnet"
    GEMINI_PRO = "gemini-pro"
    GEMINI_ULTRA = "gemini-ultra"
    LLAMA_2 = "llama-2"
    LLAMA_3 = "llama-3"
    MISTRAL = "mistral"
    MIXTRAL = "mixtral"
    CODELLAMA = "codellama"
    UNKNOWN = "unknown"


@dataclass
class ModelConfig:
    """Configuration for an LLM model's context window."""
    name: str
    model_type: ModelType
    max_context_tokens: int
    max_output_tokens: int
    supports_system_prompt: bool = True
    supports_vision: bool = False
    tokenizer_name: Optional[str] = None


# Model configurations
MODEL_CONFIGS: Dict[str, ModelConfig] = {
    "gpt-4": ModelConfig(
        name="gpt-4",
        model_type=ModelType.GPT_4,
        max_context_tokens=8192,
        max_output_tokens=4096
    ),
    "gpt-4-turbo": ModelConfig(
        name="gpt-4-turbo",
        model_type=ModelType.GPT_4_TURBO,
        max_context_tokens=128000,
        max_output_tokens=4096
    ),
    "gpt-4o": ModelConfig(
        name="gpt-4o",
        model_type=ModelType.GPT_4O,
        max_context_tokens=128000,
        max_output_tokens=4096,
        supports_vision=True
    ),
    "gpt-3.5-turbo": ModelConfig(
        name="gpt-3.5-turbo",
        model_type=ModelType.GPT_35_TURBO,
        max_context_tokens=16385,
        max_output_tokens=4096
    ),
    "claude-3-opus": ModelConfig(
        name="claude-3-opus",
        model_type=ModelType.CLAUDE_3_OPUS,
        max_context_tokens=200000,
        max_output_tokens=4096,
        supports_vision=True
    ),
    "claude-3-sonnet": ModelConfig(
        name="claude-3-sonnet",
        model_type=ModelType.CLAUPE_3_SONNET,
        max_context_tokens=200000,
        max_output_tokens=4096,
        supports_vision=True
    ),
    "claude-3-haiku": ModelConfig(
        name="claude-3-haiku",
        model_type=ModelType.CLAUDE_3_HAIKU,
        max_context_tokens=200000,
        max_output_tokens=4096
    ),
    "claude-3.5-sonnet": ModelConfig(
        name="claude-3.5-sonnet",
        model_type=ModelType.CLAUDE_3_5_SONNET,
        max_context_tokens=200000,
        max_output_tokens=8192,
        supports_vision=True
    ),
    "gemini-pro": ModelConfig(
        name="gemini-pro",
        model_type=ModelType.GEMINI_PRO,
        max_context_tokens=32760,
        max_output_tokens=2048
    ),
    "gemini-ultra": ModelConfig(
        name="gemini-ultra",
        model_type=ModelType.GEMINI_ULTRA,
        max_context_tokens=32760,
        max_output_tokens=2048,
        supports_vision=True
    ),
    "llama-2": ModelConfig(
        name="llama-2",
        model_type=ModelType.LLAMA_2,
        max_context_tokens=4096,
        max_output_tokens=2048
    ),
    "llama-3": ModelConfig(
        name="llama-3",
        model_type=ModelType.LLAMA_3,
        max_context_tokens=8192,
        max_output_tokens=2048
    ),
    "mistral": ModelConfig(
        name="mistral",
        model_type=ModelType.MISTRAL,
        max_context_tokens=32768,
        max_output_tokens=4096
    ),
    "mixtral": ModelConfig(
        name="mixtral",
        model_type=ModelType.MIXTRAL,
        max_context_tokens=32768,
        max_output_tokens=4096
    ),
}


@dataclass
class ContextItem:
    """An item in the context window."""
    id: str
    content: str
    source: str  # file, symbol, description, etc.
    item_type: str  # code, documentation, config, chat
    priority: int  # 0-10, higher = more important
    tokens: int = 0
    is_required: bool = False
    can_compress: bool = True
    can_truncate: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        self.id = self.id or hashlib.sha256(self.content.encode()).hexdigest()[:16]


@dataclass
class ContextWindow:
    """A managed context window for LLM input."""
    model_config: ModelConfig
    items: List[ContextItem] = field(default_factory=list)
    total_tokens: int = 0
    reserved_output_tokens: int = 4096
    available_tokens: int = 0
    
    def __post_init__(self):
        self.available_tokens = self.model_config.max_context_tokens - self.reserved_output_tokens


@dataclass
class TruncationResult:
    """Result of a truncation operation."""
    original_tokens: int
    final_tokens: int
    removed_items: List[str]
    truncated_items: List[str]
    compression_ratio: float


class TokenCounter:
    """Count tokens for various LLM models."""
    
    def __init__(self):
        self._tiktoken_encoder = None
        self._cache: Dict[str, int] = {}
        self._max_cache_size = 10000
    
    def count(self, text: str, model: str = "gpt-4") -> int:
        """Count tokens in text for a specific model."""
        # Check cache
        cache_key = f"{model}:{hashlib.sha256(text.encode()).hexdigest()[:16]}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Try tiktoken for OpenAI models
        if model.startswith("gpt") or model.startswith("o1"):
            count = self._count_tiktoken(text, model)
        # Estimate for other models
        else:
            count = self._estimate_tokens(text, model)
        
        # Cache result
        if len(self._cache) >= self._max_cache_size:
            # Remove oldest entries
            keys_to_remove = list(self._cache.keys())[:1000]
            for k in keys_to_remove:
                del self._cache[k]
        
        self._cache[cache_key] = count
        return count
    
    def _count_tiktoken(self, text: str, model: str) -> int:
        """Count tokens using tiktoken."""
        try:
            import tiktoken
            
            if self._tiktoken_encoder is None:
                # Get appropriate encoding
                try:
                    self._tiktoken_encoder = tiktoken.encoding_for_model(model)
                except KeyError:
                    # Default to cl100k_base (GPT-4 encoding)
                    self._tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
            
            return len(self._tiktoken_encoder.encode(text))
        except ImportError:
            logger.warning("tiktoken not installed, using estimation")
            return self._estimate_tokens(text, model)
    
    def _estimate_tokens(self, text: str, model: str) -> int:
        """Estimate token count without tiktoken."""
        # Different models have different tokenization
        # This is a rough estimation
        
        # Count words
        words = len(text.split())
        
        # Count special characters that often become separate tokens
        special_chars = sum(1 for c in text if c in '{}[]()<>!@#$%^&*-+=|\\:;"\'`~,./?')
        
        # Count newlines
        newlines = text.count('\n')
        
        # Model-specific estimation
        model_lower = model.lower()
        
        if 'claude' in model_lower:
            # Claude tends to have fewer tokens per word
            # Roughly 1.3 tokens per word on average
            base_tokens = int(words * 1.3)
        elif 'gemini' in model_lower:
            # Gemini uses SentencePiece
            base_tokens = int(words * 1.4)
        elif 'llama' in model_lower or 'mistral' in model_lower:
            # LLaMA uses BPE with special handling
            base_tokens = int(words * 1.4)
        else:
            # GPT-style: roughly 1.3 tokens per word on average for English
            base_tokens = int(words * 1.3)
        
        # Add overhead for special characters and newlines
        total = base_tokens + (special_chars // 4) + (newlines // 2)
        
        return max(total, 1)
    
    def count_messages(self, messages: List[Dict[str, str]], model: str = "gpt-4") -> int:
        """Count tokens in a list of chat messages."""
        total = 0
        
        # Add message overhead tokens
        # This varies by model but ~4 tokens per message is common
        message_overhead = 4
        
        for message in messages:
            total += message_overhead
            
            for key, value in message.items():
                if isinstance(value, str):
                    total += self.count(value, model)
                # Add key tokens
                total += 1  # Role keys are typically single tokens
        
        # Add reply priming tokens
        total += 3
        
        return total
    
    def clear_cache(self) -> None:
        """Clear the token count cache."""
        self._cache.clear()


class ContextPrioritizer:
    """Prioritize context items for inclusion."""
    
    def __init__(self):
        self._priority_weights = {
            'active_file': 10,
            'recently_edited': 8,
            'referenced_symbol': 7,
            'imported_file': 6,
            'related_file': 5,
            'test_file': 4,
            'documentation': 3,
            'config': 2,
            'dependency': 1,
        }
    
    def prioritize(self, items: List[ContextItem], 
                   query: Optional[str] = None,
                   active_file: Optional[str] = None,
                   recent_files: Optional[List[str]] = None) -> List[ContextItem]:
        """Sort items by priority."""
        recent_set = set(recent_files or [])
        
        def get_priority(item: ContextItem) -> Tuple[int, int]:
            # Higher priority first, then more tokens (larger = more context)
            priority = item.priority
            
            # Boost active file
            if active_file and item.source == active_file:
                priority += self._priority_weights['active_file']
            
            # Boost recent files
            if item.source in recent_set:
                idx = list(recent_set).index(item.source)
                recency_boost = self._priority_weights['recently_edited'] - idx
                priority += max(0, recency_boost)
            
            # Boost if source is referenced in query
            if query and item.source.lower() in query.lower():
                priority += self._priority_weights['referenced_symbol']
            
            return (priority, item.tokens)
        
        return sorted(items, key=get_priority, reverse=True)
    
    def set_priority_weight(self, item_type: str, weight: int) -> None:
        """Set priority weight for an item type."""
        self._priority_weights[item_type] = weight


class ContextCompressor:
    """Compress context while preserving essential information."""
    
    def __init__(self, token_counter: Optional[TokenCounter] = None):
        self.token_counter = token_counter or TokenCounter()
        self._compression_patterns = self._build_compression_patterns()
    
    def _build_compression_patterns(self) -> Dict[str, str]:
        """Build patterns for compression."""
        return {
            # Remove excess whitespace
            r'\n{3,}': '\n\n',
            r' {2,}': ' ',
            r'\t{2,}': '\t',
            
            # Remove common boilerplate
            r'^\s*#\s*encoding:\s*[^\n]+\n': '',
            r'^\s*#!/usr/bin/env\s+[^\n]+\n': '',
            r'^\s*#\s*!.*\n': '',
            
            # Compress docstrings (keep first line only)
            r'("""[\s\S]*?""")|(\'\'\'[\s\S]*?\'\'\')': self._compress_docstring,
            
            # Remove type-only imports
            r'^\s*from\s+\S+\s+import\s+Type\[[^\]]+\]\s*$': '',
            
            # Remove redundant type annotations
            r':\s*Optional\[None\]': '',
            r':\s*Union\[([^\]]+)\]': r': \1',
        }
    
    def _compress_docstring(self, match) -> str:
        """Compress a docstring to its first line."""
        docstring = match.group(0)
        # Get first line
        lines = docstring.strip('\'"').strip().split('\n')
        if lines:
            first_line = lines[0].strip()
            return f'"""{first_line}"""'
        return '""""""'
    
    def compress(self, content: str, target_ratio: float = 0.5,
                 preserve_structure: bool = True) -> str:
        """Compress content to target ratio."""
        original_tokens = self.token_counter.count(content)
        target_tokens = int(original_tokens * target_ratio)
        
        # Apply compression patterns
        compressed = content
        for pattern, replacement in self._compression_patterns.items():
            if callable(replacement):
                compressed = re.sub(pattern, replacement, compressed)
            else:
                compressed = re.sub(pattern, replacement, compressed, flags=re.MULTILINE)
        
        # If still too long, apply structural compression
        current_tokens = self.token_counter.count(compressed)
        
        if current_tokens > target_tokens and preserve_structure:
            compressed = self._structural_compress(compressed, target_tokens)
        
        return compressed
    
    def _structural_compress(self, content: str, target_tokens: int) -> str:
        """Compress by removing less important structural elements."""
        lines = content.split('\n')
        
        # Identify line types
        line_types: List[Tuple[int, str]] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            if not stripped:
                line_types.append((i, 'empty'))
            elif stripped.startswith('#') or stripped.startswith('//'):
                line_types.append((i, 'comment'))
            elif stripped.startswith('"""') or stripped.startswith("'''"):
                line_types.append((i, 'docstring'))
            elif stripped in ('pass', '...', 'break', 'continue'):
                line_types.append((i, 'placeholder'))
            else:
                line_types.append((i, 'code'))
        
        # Build compressed content by removing low-priority lines
        current_tokens = self.token_counter.count(content)
        removed_indices: Set[int] = set()
        
        # Remove in order: empty, comments, placeholders
        for line_type in ['empty', 'comment', 'placeholder']:
            if current_tokens <= target_tokens:
                break
            
            for i, lt in line_types:
                if lt == line_type and i not in removed_indices:
                    removed_indices.add(i)
                    current_tokens -= self.token_counter.count(lines[i])
                    
                    if current_tokens <= target_tokens:
                        break
        
        # Rebuild content
        compressed_lines = [line for i, line in enumerate(lines) if i not in removed_indices]
        
        return '\n'.join(compressed_lines)
    
    def compress_item(self, item: ContextItem, target_ratio: float = 0.5) -> ContextItem:
        """Compress a context item."""
        if not item.can_compress:
            return item
        
        compressed_content = self.compress(item.content, target_ratio)
        compressed_tokens = self.token_counter.count(compressed_content)
        
        return ContextItem(
            id=item.id + "_compressed",
            content=compressed_content,
            source=item.source,
            item_type=item.item_type,
            priority=item.priority,
            tokens=compressed_tokens,
            is_required=item.is_required,
            can_compress=False,  # Don't compress again
            can_truncate=item.can_truncate,
            metadata={**item.metadata, 'original_tokens': item.tokens, 'compression_ratio': target_ratio}
        )


class SmartTruncator:
    """Smart truncation strategies for context window."""
    
    STRATEGY_PRESERVE_START = 'preserve_start'
    STRATEGY_PRESERVE_END = 'preserve_end'
    STRATEGY_PRESERVE_MIDDLE = 'preserve_middle'
    STRATEGY_PRESERVE_IMPORTS = 'preserve_imports'
    STRATEGY_SLIDING_WINDOW = 'sliding_window'
    STRATEGY_SEMANTIC = 'semantic'
    
    def __init__(self, token_counter: Optional[TokenCounter] = None):
        self.token_counter = token_counter or TokenCounter()
    
    def truncate(self, content: str, max_tokens: int,
                 strategy: str = STRATEGY_PRESERVE_IMPORTS,
                 cursor_position: Optional[int] = None) -> str:
        """Truncate content using specified strategy."""
        current_tokens = self.token_counter.count(content)
        
        if current_tokens <= max_tokens:
            return content
        
        if strategy == self.STRATEGY_PRESERVE_START:
            return self._truncate_preserve_start(content, max_tokens)
        elif strategy == self.STRATEGY_PRESERVE_END:
            return self._truncate_preserve_end(content, max_tokens)
        elif strategy == self.STRATEGY_PRESERVE_MIDDLE:
            return self._truncate_preserve_middle(content, max_tokens, cursor_position)
        elif strategy == self.STRATEGY_PRESERVE_IMPORTS:
            return self._truncate_preserve_imports(content, max_tokens)
        elif strategy == self.STRATEGY_SLIDING_WINDOW:
            return self._truncate_sliding_window(content, max_tokens, cursor_position)
        else:
            return self._truncate_preserve_start(content, max_tokens)
    
    def _truncate_preserve_start(self, content: str, max_tokens: int) -> str:
        """Truncate from the end, preserving start."""
        lines = content.split('\n')
        result_lines: List[str] = []
        current_tokens = 0
        
        for line in lines:
            line_tokens = self.token_counter.count(line + '\n')
            
            if current_tokens + line_tokens > max_tokens:
                break
            
            result_lines.append(line)
            current_tokens += line_tokens
        
        # Add truncation marker
        result_lines.append('\n... [truncated] ...\n')
        
        return '\n'.join(result_lines)
    
    def _truncate_preserve_end(self, content: str, max_tokens: int) -> str:
        """Truncate from the start, preserving end."""
        lines = content.split('\n')
        result_lines: List[str] = []
        current_tokens = 0
        
        # Work backwards
        for line in reversed(lines):
            line_tokens = self.token_counter.count(line + '\n')
            
            if current_tokens + line_tokens > max_tokens:
                break
            
            result_lines.insert(0, line)
            current_tokens += line_tokens
        
        # Add truncation marker at start
        result_lines.insert(0, '... [truncated] ...\n')
        
        return '\n'.join(result_lines)
    
    def _truncate_preserve_middle(self, content: str, max_tokens: int,
                                   cursor_position: Optional[int] = None) -> str:
        """Truncate start and end, preserving middle around cursor."""
        lines = content.split('\n')
        
        # Determine center line
        if cursor_position is not None:
            center_line = cursor_position
        else:
            center_line = len(lines) // 2
        
        # Calculate tokens per half
        tokens_per_half = max_tokens // 2
        
        # Get lines before cursor
        before_lines: List[str] = []
        before_tokens = 0
        
        for i in range(center_line - 1, -1, -1):
            line_tokens = self.token_counter.count(lines[i] + '\n')
            
            if before_tokens + line_tokens > tokens_per_half:
                break
            
            before_lines.insert(0, lines[i])
            before_tokens += line_tokens
        
        # Get lines after cursor
        after_lines: List[str] = []
        after_tokens = 0
        
        for i in range(center_line, len(lines)):
            line_tokens = self.token_counter.count(lines[i] + '\n')
            
            if after_tokens + line_tokens > tokens_per_half:
                break
            
            after_lines.append(lines[i])
            after_tokens += line_tokens
        
        # Combine
        result_lines = ['... [truncated] ...\n'] + before_lines + after_lines + ['... [truncated] ...\n']
        
        return '\n'.join(result_lines)
    
    def _truncate_preserve_imports(self, content: str, max_tokens: int) -> str:
        """Truncate while preserving imports and exports."""
        lines = content.split('\n')
        
        # Identify imports/exports
        import_lines: List[int] = []
        code_lines: List[int] = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            if stripped.startswith(('import ', 'from ', 'export ', 'require(')):
                import_lines.append(i)
            else:
                code_lines.append(i)
        
        # Calculate space for imports
        import_content = '\n'.join(lines[i] for i in import_lines)
        import_tokens = self.token_counter.count(import_content)
        
        remaining_tokens = max_tokens - import_tokens - 20  # 20 for markers
        
        # Add code lines within remaining space
        result_lines: List[str] = [lines[i] for i in import_lines]
        current_tokens = 0
        added_marker = False
        
        for i in code_lines:
            line_tokens = self.token_counter.count(lines[i] + '\n')
            
            if current_tokens + line_tokens > remaining_tokens:
                if not added_marker:
                    result_lines.append('\n... [code truncated] ...\n')
                    added_marker = True
                continue
            
            result_lines.append(lines[i])
            current_tokens += line_tokens
        
        return '\n'.join(result_lines)
    
    def _truncate_sliding_window(self, content: str, max_tokens: int,
                                  cursor_position: Optional[int] = None) -> str:
        """Use sliding window around cursor position."""
        lines = content.split('\n')
        
        # Determine center
        if cursor_position is not None:
            center = cursor_position
        else:
            center = len(lines) // 2
        
        # Calculate window size in lines
        avg_tokens_per_line = self.token_counter.count(content) / max(1, len(lines))
        window_lines = int(max_tokens / max(1, avg_tokens_per_line))
        
        # Calculate window bounds
        half_window = window_lines // 2
        start = max(0, center - half_window)
        end = min(len(lines), center + half_window)
        
        # Adjust if window is too small
        if end - start < window_lines:
            if start == 0:
                end = min(len(lines), window_lines)
            elif end == len(lines):
                start = max(0, len(lines) - window_lines)
        
        # Build result
        result_lines: List[str] = []
        
        if start > 0:
            result_lines.append('... [truncated] ...\n')
        
        result_lines.extend(lines[start:end])
        
        if end < len(lines):
            result_lines.append('\n... [truncated] ...')
        
        return '\n'.join(result_lines)


class ContextWindowManager:
    """Manage LLM context window with prioritization, compression, and truncation."""
    
    def __init__(self, model: str = "gpt-4", reserved_output_tokens: int = 4096):
        self.model = model
        self.config = MODEL_CONFIGS.get(model, ModelConfig(
            name=model,
            model_type=ModelType.UNKNOWN,
            max_context_tokens=128000,
            max_output_tokens=4096
        ))
        
        self.token_counter = TokenCounter()
        self.prioritizer = ContextPrioritizer()
        self.compressor = ContextCompressor(self.token_counter)
        self.truncator = SmartTruncator(self.token_counter)
        
        self.reserved_output_tokens = min(reserved_output_tokens, self.config.max_output_tokens)
        self.available_tokens = self.config.max_context_tokens - self.reserved_output_tokens
    
    def get_available_tokens(self) -> int:
        """Get available tokens for context."""
        return self.available_tokens
    
    def create_context_item(self, content: str, source: str,
                            item_type: str = "code",
                            priority: int = 5,
                            is_required: bool = False,
                            can_compress: bool = True,
                            can_truncate: bool = True,
                            metadata: Optional[Dict[str, Any]] = None) -> ContextItem:
        """Create a context item."""
        tokens = self.token_counter.count(content)
        
        return ContextItem(
            id=hashlib.sha256(f"{source}:{content}".encode()).hexdigest()[:16],
            content=content,
            source=source,
            item_type=item_type,
            priority=priority,
            tokens=tokens,
            is_required=is_required,
            can_compress=can_compress,
            can_truncate=can_truncate,
            metadata=metadata or {}
        )
    
    def fit_to_window(self, items: List[ContextItem],
                      query: Optional[str] = None,
                      active_file: Optional[str] = None,
                      recent_files: Optional[List[str]] = None,
                      compression_threshold: float = 0.8,
                      truncation_strategy: str = SmartTruncator.STRATEGY_PRESERVE_IMPORTS) -> Tuple[List[ContextItem], TruncationResult]:
        """Fit items to context window with compression and truncation."""
        # Calculate total tokens
        total_tokens = sum(item.tokens for item in items)
        original_tokens = total_tokens
        
        if total_tokens <= self.available_tokens:
            return items, TruncationResult(
                original_tokens=original_tokens,
                final_tokens=total_tokens,
                removed_items=[],
                truncated_items=[],
                compression_ratio=1.0
            )
        
        # Step 1: Prioritize items
        prioritized = self.prioritizer.prioritize(items, query, active_file, recent_files)
        
        # Step 2: Try to fit with compression
        if total_tokens > self.available_tokens * compression_threshold:
            compressed_items: List[ContextItem] = []
            compressed_tokens = 0
            
            for item in prioritized:
                if item.can_compress and compressed_tokens + item.tokens > self.available_tokens * 0.7:
                    # Compress this item
                    compressed = self.compressor.compress_item(item, target_ratio=0.5)
                    compressed_items.append(compressed)
                    compressed_tokens += compressed.tokens
                else:
                    compressed_items.append(item)
                    compressed_tokens += item.tokens
            
            if compressed_tokens <= self.available_tokens:
                return compressed_items, TruncationResult(
                    original_tokens=original_tokens,
                    final_tokens=compressed_tokens,
                    removed_items=[],
                    truncated_items=[item.id for item in compressed_items if item.can_compress],
                    compression_ratio=compressed_tokens / original_tokens
                )
            
            prioritized = compressed_items
            total_tokens = compressed_tokens
        
        # Step 3: Truncate items
        final_items: List[ContextItem] = []
        final_tokens = 0
        removed_items: List[str] = []
        truncated_items: List[str] = []
        
        for item in prioritized:
            remaining_space = self.available_tokens - final_tokens
            
            if remaining_space <= 0:
                removed_items.append(item.id)
                continue
            
            if item.tokens <= remaining_space:
                final_items.append(item)
                final_tokens += item.tokens
            elif item.is_required:
                # Truncate required items
                truncated_content = self.truncator.truncate(
                    item.content,
                    remaining_space - 10,  # Leave room for marker
                    truncation_strategy
                )
                truncated_tokens = self.token_counter.count(truncated_content)
                
                truncated_item = ContextItem(
                    id=item.id + "_truncated",
                    content=truncated_content,
                    source=item.source,
                    item_type=item.item_type,
                    priority=item.priority,
                    tokens=truncated_tokens,
                    is_required=True,
                    can_compress=False,
                    can_truncate=False,
                    metadata={**item.metadata, 'original_tokens': item.tokens, 'truncated': True}
                )
                
                final_items.append(truncated_item)
                final_tokens += truncated_tokens
                truncated_items.append(item.id)
            elif item.can_truncate:
                # Truncate non-required items
                truncated_content = self.truncator.truncate(
                    item.content,
                    remaining_space - 10,
                    truncation_strategy
                )
                truncated_tokens = self.token_counter.count(truncated_content)
                
                if truncated_tokens > 50:  # Only include if meaningful
                    truncated_item = ContextItem(
                        id=item.id + "_truncated",
                        content=truncated_content,
                        source=item.source,
                        item_type=item.item_type,
                        priority=item.priority,
                        tokens=truncated_tokens,
                        is_required=False,
                        can_compress=False,
                        can_truncate=False,
                        metadata={**item.metadata, 'original_tokens': item.tokens, 'truncated': True}
                    )
                    
                    final_items.append(truncated_item)
                    final_tokens += truncated_tokens
                    truncated_items.append(item.id)
                else:
                    removed_items.append(item.id)
            else:
                removed_items.append(item.id)
        
        return final_items, TruncationResult(
            original_tokens=original_tokens,
            final_tokens=final_tokens,
            removed_items=removed_items,
            truncated_items=truncated_items,
            compression_ratio=final_tokens / original_tokens if original_tokens > 0 else 1.0
        )
    
    def build_messages(self, items: List[ContextItem],
                       system_prompt: Optional[str] = None,
                       user_query: Optional[str] = None,
                       conversation_history: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
        """Build chat messages from context items."""
        messages: List[Dict[str, str]] = []
        
        # System prompt
        if system_prompt and self.config.supports_system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # Context items as system context
        if items:
            context_parts: List[str] = []
            current_section = None
            
            for item in items:
                # Group by type
                if item.item_type != current_section:
                    if current_section is not None:
                        context_parts.append("")
                    context_parts.append(f"=== {item.item_type.upper()}: {item.source} ===")
                    current_section = item.item_type
                
                context_parts.append(item.content)
            
            context_content = "\n".join(context_parts)
            
            # If model doesn't support system, prepend to user message
            if self.config.supports_system_prompt:
                messages.append({"role": "system", "content": f"Context:\n{context_content}"})
            else:
                # Will be prepended to user message
                if user_query:
                    user_query = f"Context:\n{context_content}\n\n{user_query}"
                else:
                    user_query = f"Context:\n{context_content}"
        
        # Conversation history
        if conversation_history:
            messages.extend(conversation_history)
        
        # User query
        if user_query:
            messages.append({"role": "user", "content": user_query})
        
        return messages
    
    def estimate_tokens_for_messages(self, messages: List[Dict[str, str]]) -> int:
        """Estimate total tokens for messages."""
        return self.token_counter.count_messages(messages, self.model)
    
    def get_model_config(self) -> ModelConfig:
        """Get current model configuration."""
        return self.config
    
    def set_model(self, model: str) -> None:
        """Change the model."""
        self.model = model
        self.config = MODEL_CONFIGS.get(model, ModelConfig(
            name=model,
            model_type=ModelType.UNKNOWN,
            max_context_tokens=128000,
            max_output_tokens=4096
        ))
        self.available_tokens = self.config.max_context_tokens - self.reserved_output_tokens


def create_context_window(model: str = "gpt-4", 
                          reserved_output_tokens: int = 4096) -> ContextWindowManager:
    """Create a context window manager."""
    return ContextWindowManager(model, reserved_output_tokens)


if __name__ == '__main__':
    import sys
    
    model = sys.argv[1] if len(sys.argv) > 1 else "gpt-4"
    manager = create_context_window(model)
    
    print(f"Model: {model}")
    print(f"Max context: {manager.config.max_context_tokens}")
    print(f"Max output: {manager.config.max_output_tokens}")
    print(f"Available: {manager.get_available_tokens()}")
    
    # Test with sample content
    sample_code = '''
import os
import sys
from typing import Dict, List

def process_data(data: Dict[str, Any]) -> List[str]:
    """Process the input data and return results."""
    results = []
    for key, value in data.items():
        results.append(f"{key}: {value}")
    return results

class DataProcessor:
    """A class to process data."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.results = []
    
    def run(self, data: Dict) -> List[str]:
        return process_data(data)
'''
    
    item = manager.create_context_item(sample_code, "example.py", "code", priority=5)
    print(f"\nSample code tokens: {item.tokens}")
    
    # Test fitting
    items = [item]
    final_items, result = manager.fit_to_window(items)
    
    print(f"\nFit result:")
    print(f"  Original tokens: {result.original_tokens}")
    print(f"  Final tokens: {result.final_tokens}")
    print(f"  Compression ratio: {result.compression_ratio:.2%}")
