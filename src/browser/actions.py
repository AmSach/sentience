"""
Browser Actions for Sentience v3.0
Comprehensive browser interaction actions including click, type, scroll, form filling, drag and drop, and keyboard shortcuts.
"""

import asyncio
import base64
import logging
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

from playwright.async_api import (
    Page,
    Locator,
    Keyboard,
    Mouse,
    FileChooser,
    Download,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)

logger = logging.getLogger(__name__)


@dataclass
class ActionResult:
    """Result of a browser action."""
    success: bool
    value: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    screenshot: Optional[bytes] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionOptions:
    """Options for browser actions."""
    timeout: int = 30000
    delay: float = 0.0
    force: bool = False
    trial: bool = False
    no_wait_after: bool = False
    position: Optional[Dict[str, float]] = None
    modifiers: Optional[List[str]] = None
    button: str = "left"
    click_count: int = 1
    scroll_into_view: bool = True


class HumanBehavior:
    """Simulate human-like behavior for actions."""
    
    def __init__(
        self,
        min_delay: float = 0.05,
        max_delay: float = 0.3,
        typing_speed_range: Tuple[float, float] = (0.05, 0.15),
        mouse_move_steps: int = 20
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.typing_speed_range = typing_speed_range
        self.mouse_move_steps = mouse_move_steps
        
    def random_delay(self) -> float:
        """Generate random delay."""
        return random.uniform(self.min_delay, self.max_delay)
        
    def random_typing_delay(self) -> float:
        """Generate random typing delay."""
        return random.uniform(*self.typing_speed_range)
        
    async def human_like_delay(self) -> None:
        """Wait for a human-like random delay."""
        await asyncio.sleep(self.random_delay())


class BrowserActions:
    """
    Comprehensive browser action toolkit.
    Provides methods for all common browser interactions.
    """
    
    def __init__(
        self,
        page: Page,
        human_behavior: Optional[HumanBehavior] = None,
        default_timeout: int = 30000
    ):
        self.page = page
        self.keyboard = page.keyboard
        self.mouse = page.mouse
        self.human = human_behavior or HumanBehavior()
        self.default_timeout = default_timeout
        
    # ==================== Element Selection ====================
    
    def locate(
        self,
        selector: str,
        has_text: Optional[str] = None,
        has: Optional[str] = None
    ) -> Locator:
        """
        Create a locator for an element.
        
        Args:
            selector: CSS selector or XPath
            has_text: Filter by text content
            has: Filter by child element
        """
        locator = self.page.locator(selector)
        
        if has_text:
            locator = locator.filter(has_text=has_text)
            
        if has:
            locator = locator.filter(has=self.page.locator(has))
            
        return locator
        
    async def wait_for_element(
        self,
        selector: str,
        state: str = "visible",
        timeout: Optional[int] = None
    ) -> Locator:
        """
        Wait for element to reach a state.
        
        Args:
            selector: Element selector
            state: State to wait for (visible, hidden, attached, detached)
            timeout: Timeout in ms
        """
        locator = self.page.locator(selector)
        await locator.wait_for(state=state, timeout=timeout or self.default_timeout)
        return locator
        
    async def find_by_text(
        self,
        text: str,
        exact: bool = False
    ) -> Locator:
        """Find element by text content."""
        return self.page.get_by_text(text, exact=exact)
        
    async def find_by_role(
        self,
        role: str,
        name: Optional[str] = None
    ) -> Locator:
        """Find element by ARIA role."""
        if name:
            return self.page.get_by_role(role, name=name)
        return self.page.get_by_role(role)
        
    async def find_by_label(
        self,
        text: str,
        exact: bool = False
    ) -> Locator:
        """Find element by label text."""
        return self.page.get_by_label(text, exact=exact)
        
    async def find_by_placeholder(
        self,
        text: str,
        exact: bool = False
    ) -> Locator:
        """Find element by placeholder text."""
        return self.page.get_by_placeholder(text, exact=exact)
        
    async def find_by_test_id(
        self,
        test_id: str
    ) -> Locator:
        """Find element by test ID."""
        return self.page.get_by_test_id(test_id)
        
    # ==================== Click Actions ====================
    
    async def click(
        self,
        selector: str,
        options: Optional[ActionOptions] = None,
        human_like: bool = True
    ) -> ActionResult:
        """
        Click on an element.
        
        Args:
            selector: Element selector
            options: Action options
            human_like: Simulate human behavior
        """
        start_time = time.time()
        options = options or ActionOptions()
        
        try:
            locator = self.page.locator(selector)
            
            # Scroll into view if needed
            if options.scroll_into_view:
                await locator.scroll_into_view_if_needed(timeout=options.timeout)
                
            # Human-like behavior
            if human_like:
                await self.human.human_like_delay()
                
            # Perform click
            await locator.click(
                timeout=options.timeout,
                force=options.force,
                trial=options.trial,
                no_wait_after=options.no_wait_after,
                position=options.position,
                modifiers=options.modifiers,
                button=options.button,
                click_count=options.click_count,
            )
            
            if human_like:
                await self.human.human_like_delay()
                
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                error=str(e),
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
    async def double_click(
        self,
        selector: str,
        options: Optional[ActionOptions] = None
    ) -> ActionResult:
        """Double-click on an element."""
        options = options or ActionOptions()
        options.click_count = 2
        return await self.click(selector, options)
        
    async def right_click(
        self,
        selector: str,
        options: Optional[ActionOptions] = None
    ) -> ActionResult:
        """Right-click on an element."""
        options = options or ActionOptions()
        options.button = "right"
        return await self.click(selector, options)
        
    async def click_at_coordinates(
        self,
        x: float,
        y: float,
        delay: float = 0.0
    ) -> ActionResult:
        """Click at specific coordinates."""
        start_time = time.time()
        
        try:
            await self.mouse.click(x, y, delay=delay)
            
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=True,
                duration_ms=duration,
                metadata={"x": x, "y": y}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=False, error=str(e), duration_ms=duration)
            
    async def click_text(
        self,
        text: str,
        exact: bool = False,
        options: Optional[ActionOptions] = None
    ) -> ActionResult:
        """Click on element containing text."""
        locator = self.page.get_by_text(text, exact=exact)
        selector = f"text={text}"
        
        start_time = time.time()
        options = options or ActionOptions()
        
        try:
            await locator.click(timeout=options.timeout)
            
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=True,
                duration_ms=duration,
                metadata={"text": text}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=False, error=str(e), duration_ms=duration)
            
    # ==================== Type Actions ====================
    
    async def type_text(
        self,
        selector: str,
        text: str,
        delay: float = 50,
        clear_first: bool = True,
        human_like: bool = True
    ) -> ActionResult:
        """
        Type text into an input field.
        
        Args:
            selector: Input element selector
            text: Text to type
            delay: Delay between keystrokes in ms
            clear_first: Clear existing text first
            human_like: Use human-like typing speeds
        """
        start_time = time.time()
        
        try:
            locator = self.page.locator(selector)
            
            # Clear existing content
            if clear_first:
                await locator.fill("", timeout=self.default_timeout)
                
            # Human-like typing
            if human_like:
                for char in text:
                    actual_delay = self.human.random_typing_delay() * 1000
                    await locator.press_sequentially(
                        char,
                        delay=actual_delay
                    )
            else:
                await locator.type(text, delay=delay)
                
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                value=text,
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                error=str(e),
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
    async def fill(
        self,
        selector: str,
        value: str,
        timeout: Optional[int] = None
    ) -> ActionResult:
        """
        Fill an input field (faster, no typing simulation).
        
        Args:
            selector: Input element selector
            value: Value to fill
            timeout: Timeout in ms
        """
        start_time = time.time()
        
        try:
            locator = self.page.locator(selector)
            await locator.fill(value, timeout=timeout or self.default_timeout)
            
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                value=value,
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                error=str(e),
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
    async def clear(
        self,
        selector: str
    ) -> ActionResult:
        """Clear an input field."""
        return await self.fill(selector, "")
        
    async def press_key(
        self,
        key: str,
        modifiers: Optional[List[str]] = None
    ) -> ActionResult:
        """
        Press a keyboard key.
        
        Args:
            key: Key to press (e.g., 'Enter', 'Tab', 'Escape', 'ArrowDown')
            modifiers: Modifier keys (e.g., ['Control', 'Shift'])
        """
        start_time = time.time()
        
        try:
            if modifiers:
                # Press modifiers, then key, then release
                for mod in modifiers:
                    await self.keyboard.down(mod)
                    
                await self.keyboard.press(key)
                
                for mod in reversed(modifiers):
                    await self.keyboard.up(mod)
            else:
                await self.keyboard.press(key)
                
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                value=key,
                duration_ms=duration,
                metadata={"key": key, "modifiers": modifiers}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=False, error=str(e), duration_ms=duration)
            
    async def type_slowly(
        self,
        text: str,
        min_delay: float = 0.1,
        max_delay: float = 0.3
    ) -> ActionResult:
        """
        Type text slowly with random delays (human-like).
        
        Args:
            text: Text to type
            min_delay: Minimum delay between characters
            max_delay: Maximum delay between characters
        """
        start_time = time.time()
        
        try:
            for char in text:
                delay = random.uniform(min_delay, max_delay)
                await self.keyboard.type(char)
                await asyncio.sleep(delay)
                
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                value=text,
                duration_ms=duration
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=False, error=str(e), duration_ms=duration)
            
    # ==================== Scroll Actions ====================
    
    async def scroll(
        self,
        direction: str = "down",
        amount: int = 300,
        smooth: bool = True
    ) -> ActionResult:
        """
        Scroll the page.
        
        Args:
            direction: Scroll direction (up, down, left, right)
            amount: Scroll amount in pixels
            smooth: Use smooth scrolling
        """
        start_time = time.time()
        
        try:
            scroll_map = {
                "up": f"window.scrollBy(0, -{amount}, {{behavior: 'smooth'}})" if smooth else f"window.scrollBy(0, -{amount})",
                "down": f"window.scrollBy(0, {amount}, {{behavior: 'smooth'}})" if smooth else f"window.scrollBy(0, {amount})",
                "left": f"window.scrollBy(-{amount}, 0, {{behavior: 'smooth'}})" if smooth else f"window.scrollBy(-{amount}, 0)",
                "right": f"window.scrollBy({amount}, 0, {{behavior: 'smooth'}})" if smooth else f"window.scrollBy({amount}, 0)",
            }
            
            await self.page.evaluate(scroll_map[direction])
            
            if smooth:
                await asyncio.sleep(0.5)
                
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                duration_ms=duration,
                metadata={"direction": direction, "amount": amount}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=False, error=str(e), duration_ms=duration)
            
    async def scroll_to_element(
        self,
        selector: str,
        align: str = "center"
    ) -> ActionResult:
        """
        Scroll to make element visible.
        
        Args:
            selector: Element selector
            align: Alignment (top, center, bottom)
        """
        start_time = time.time()
        
        try:
            locator = self.page.locator(selector)
            await locator.scroll_into_view_if_needed(timeout=self.default_timeout)
            
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                error=str(e),
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
    async def scroll_to_top(self) -> ActionResult:
        """Scroll to top of page."""
        start_time = time.time()
        
        try:
            await self.page.evaluate("window.scrollTo(0, 0)")
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=True, duration_ms=duration)
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=False, error=str(e), duration_ms=duration)
            
    async def scroll_to_bottom(self) -> ActionResult:
        """Scroll to bottom of page."""
        start_time = time.time()
        
        try:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=True, duration_ms=duration)
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=False, error=str(e), duration_ms=duration)
            
    async def scroll_page_by_percentage(
        self,
        percentage: float
    ) -> ActionResult:
        """
        Scroll to a percentage of the page.
        
        Args:
            percentage: Percentage (0-100)
        """
        start_time = time.time()
        
        try:
            script = f"""
                const scrollHeight = document.body.scrollHeight - window.innerHeight;
                window.scrollTo(0, scrollHeight * {percentage / 100});
            """
            await self.page.evaluate(script)
            
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=True,
                duration_ms=duration,
                metadata={"percentage": percentage}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=False, error=str(e), duration_ms=duration)
            
    # ==================== Form Actions ====================
    
    async def fill_form(
        self,
        fields: Dict[str, str],
        submit_selector: Optional[str] = None
    ) -> ActionResult:
        """
        Fill multiple form fields.
        
        Args:
            fields: Dict of selector -> value
            submit_selector: Optional submit button selector
        """
        start_time = time.time()
        results = {}
        
        try:
            for selector, value in fields.items():
                result = await self.fill(selector, value)
                results[selector] = result.success
                
                if not result.success:
                    duration = (time.time() - start_time) * 1000
                    return ActionResult(
                        success=False,
                        error=f"Failed to fill {selector}: {result.error}",
                        duration_ms=duration,
                        metadata={"results": results}
                    )
                    
            # Submit form if selector provided
            if submit_selector:
                await self.click(submit_selector)
                
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                duration_ms=duration,
                metadata={"results": results, "fields_count": len(fields)}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                error=str(e),
                duration_ms=duration,
                metadata={"results": results}
            )
            
    async def select_option(
        self,
        selector: str,
        value: Optional[str] = None,
        label: Optional[str] = None,
        index: Optional[int] = None
    ) -> ActionResult:
        """
        Select an option from a dropdown.
        
        Args:
            selector: Select element selector
            value: Option value
            label: Option label text
            index: Option index
        """
        start_time = time.time()
        
        try:
            locator = self.page.locator(selector)
            
            if value is not None:
                await locator.select_option(value=value)
            elif label is not None:
                await locator.select_option(label=label)
            elif index is not None:
                await locator.select_option(index=index)
            else:
                raise ValueError("Must provide value, label, or index")
                
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                duration_ms=duration,
                metadata={"selector": selector, "value": value, "label": label, "index": index}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                error=str(e),
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
    async def check(
        self,
        selector: str
    ) -> ActionResult:
        """Check a checkbox or radio button."""
        start_time = time.time()
        
        try:
            locator = self.page.locator(selector)
            await locator.check(timeout=self.default_timeout)
            
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                error=str(e),
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
    async def uncheck(
        self,
        selector: str
    ) -> ActionResult:
        """Uncheck a checkbox."""
        start_time = time.time()
        
        try:
            locator = self.page.locator(selector)
            await locator.uncheck(timeout=self.default_timeout)
            
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                error=str(e),
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
    async def set_input_files(
        self,
        selector: str,
        files: Union[str, List[str]]
    ) -> ActionResult:
        """
        Upload files to an input[type=file].
        
        Args:
            selector: File input selector
            files: File path(s) to upload
        """
        start_time = time.time()
        
        try:
            locator = self.page.locator(selector)
            
            if isinstance(files, str):
                files = [files]
                
            await locator.set_input_files(files)
            
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                value=files,
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                error=str(e),
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
    # ==================== Drag and Drop ====================
    
    async def drag_and_drop(
        self,
        source_selector: str,
        target_selector: str,
        steps: int = 20
    ) -> ActionResult:
        """
        Drag element from source to target.
        
        Args:
            source_selector: Source element selector
            target_selector: Target element selector
            steps: Number of steps for mouse movement
        """
        start_time = time.time()
        
        try:
            source = self.page.locator(source_selector)
            target = self.page.locator(target_selector)
            
            await source.drag_to(target, steps=steps)
            
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                duration_ms=duration,
                metadata={"source": source_selector, "target": target_selector}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                error=str(e),
                duration_ms=duration,
                metadata={"source": source_selector, "target": target_selector}
            )
            
    async def drag_to_coordinates(
        self,
        source_selector: str,
        target_x: float,
        target_y: float
    ) -> ActionResult:
        """Drag element to specific coordinates."""
        start_time = time.time()
        
        try:
            source = self.page.locator(source_selector)
            source_box = await source.bounding_box()
            
            if not source_box:
                raise ValueError("Source element not visible")
                
            # Calculate source center
            source_x = source_box["x"] + source_box["width"] / 2
            source_y = source_box["y"] + source_box["height"] / 2
            
            # Move to source, press, move to target, release
            await self.mouse.move(source_x, source_y)
            await self.mouse.down()
            
            # Move gradually
            steps = 20
            for i in range(1, steps + 1):
                x = source_x + (target_x - source_x) * i / steps
                y = source_y + (target_y - source_y) * i / steps
                await self.mouse.move(x, y)
                await asyncio.sleep(0.01)
                
            await self.mouse.up()
            
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                duration_ms=duration,
                metadata={"source": source_selector, "target_x": target_x, "target_y": target_y}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                error=str(e),
                duration_ms=duration,
                metadata={"source": source_selector}
            )
            
    # ==================== Mouse Actions ====================
    
    async def hover(
        self,
        selector: str,
        options: Optional[ActionOptions] = None
    ) -> ActionResult:
        """Hover over an element."""
        start_time = time.time()
        options = options or ActionOptions()
        
        try:
            locator = self.page.locator(selector)
            
            if options.scroll_into_view:
                await locator.scroll_into_view_if_needed()
                
            await locator.hover(
                timeout=options.timeout,
                position=options.position,
                modifiers=options.modifiers
            )
            
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                error=str(e),
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
    async def mouse_move(
        self,
        x: float,
        y: float,
        steps: int = 1
    ) -> ActionResult:
        """Move mouse to coordinates."""
        start_time = time.time()
        
        try:
            await self.mouse.move(x, y, steps=steps)
            
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                duration_ms=duration,
                metadata={"x": x, "y": y}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=False, error=str(e), duration_ms=duration)
            
    # ==================== Keyboard Shortcuts ====================
    
    async def keyboard_shortcut(
        self,
        shortcut: str
    ) -> ActionResult:
        """
        Execute a keyboard shortcut.
        
        Args:
            shortcut: Shortcut string (e.g., 'Ctrl+C', 'Cmd+Shift+P')
        """
        start_time = time.time()
        
        try:
            # Parse shortcut
            parts = shortcut.split("+")
            key = parts[-1]
            modifiers = [m.strip() for m in parts[:-1]]
            
            # Map common modifier names
            modifier_map = {
                "Ctrl": "Control",
                "Cmd": "Meta",
                "Command": "Meta",
                "Opt": "Alt",
                "Option": "Alt",
            }
            
            mapped_modifiers = [modifier_map.get(m, m) for m in modifiers]
            
            result = await self.press_key(key, mapped_modifiers)
            
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                duration_ms=duration,
                metadata={"shortcut": shortcut}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                error=str(e),
                duration_ms=duration,
                metadata={"shortcut": shortcut}
            )
            
    async def copy(self) -> ActionResult:
        """Copy selection to clipboard."""
        return await self.keyboard_shortcut("Ctrl+C")
        
    async def cut(self) -> ActionResult:
        """Cut selection to clipboard."""
        return await self.keyboard_shortcut("Ctrl+X")
        
    async def paste(self) -> ActionResult:
        """Paste from clipboard."""
        return await self.keyboard_shortcut("Ctrl+V")
        
    async def select_all(self) -> ActionResult:
        """Select all content."""
        return await self.keyboard_shortcut("Ctrl+A")
        
    async def undo(self) -> ActionResult:
        """Undo last action."""
        return await self.keyboard_shortcut("Ctrl+Z")
        
    async def redo(self) -> ActionResult:
        """Redo last undone action."""
        return await self.keyboard_shortcut("Ctrl+Y")
        
    async def save(self) -> ActionResult:
        """Save (common shortcut)."""
        return await self.keyboard_shortcut("Ctrl+S")
        
    async def find(self) -> ActionResult:
        """Open find dialog."""
        return await self.keyboard_shortcut("Ctrl+F")
        
    # ==================== Navigation Actions ====================
    
    async def go_back(self) -> ActionResult:
        """Navigate back."""
        start_time = time.time()
        
        try:
            await self.page.go_back()
            
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=True, duration_ms=duration)
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=False, error=str(e), duration_ms=duration)
            
    async def go_forward(self) -> ActionResult:
        """Navigate forward."""
        start_time = time.time()
        
        try:
            await self.page.go_forward()
            
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=True, duration_ms=duration)
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=False, error=str(e), duration_ms=duration)
            
    async def reload(self, ignore_cache: bool = False) -> ActionResult:
        """Reload the page."""
        start_time = time.time()
        
        try:
            await self.page.reload(ignore_cache=ignore_cache)
            
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=True, duration_ms=duration)
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=False, error=str(e), duration_ms=duration)
            
    # ==================== Focus Actions ====================
    
    async def focus(
        self,
        selector: str
    ) -> ActionResult:
        """Focus an element."""
        start_time = time.time()
        
        try:
            locator = self.page.locator(selector)
            await locator.focus(timeout=self.default_timeout)
            
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                error=str(e),
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
    async def blur(
        self,
        selector: str
    ) -> ActionResult:
        """Remove focus from element."""
        start_time = time.time()
        
        try:
            await self.page.evaluate(
                f"document.querySelector('{selector}').blur()"
            )
            
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                error=str(e),
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
    # ==================== Wait Actions ====================
    
    async def wait_for_selector(
        self,
        selector: str,
        state: str = "visible",
        timeout: Optional[int] = None
    ) -> ActionResult:
        """Wait for element to appear."""
        start_time = time.time()
        
        try:
            await self.page.wait_for_selector(
                selector,
                state=state,
                timeout=timeout or self.default_timeout
            )
            
            duration = (time.time() - start_time) * 1000
            
            return ActionResult(
                success=True,
                duration_ms=duration,
                metadata={"selector": selector, "state": state}
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                error=str(e),
                duration_ms=duration,
                metadata={"selector": selector}
            )
            
    async def wait_for_load_state(
        self,
        state: str = "load"
    ) -> ActionResult:
        """Wait for page load state."""
        start_time = time.time()
        
        try:
            await self.page.wait_for_load_state(state)
            
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=True, duration_ms=duration)
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ActionResult(success=False, error=str(e), duration_ms=duration)
            
    async def wait_for_timeout(
        self,
        ms: int
    ) -> ActionResult:
        """Wait for specified duration."""
        start_time = time.time()
        
        await self.page.wait_for_timeout(ms)
        
        duration = (time.time() - start_time) * 1000
        return ActionResult(success=True, duration_ms=duration)
