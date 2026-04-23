"""
Content Extractor for Sentience v3.0
Comprehensive content extraction including text, links, images, tables, and structured data.
"""

import asyncio
import base64
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import urljoin, urlparse, urlunparse

from playwright.async_api import (
    Page,
    Locator,
    ElementHandle,
    Response,
    TimeoutError as PlaywrightTimeoutError,
)

logger = logging.getLogger(__name__)


@dataclass
class ExtractedText:
    """Extracted text content."""
    content: str
    word_count: int
    character_count: int
    headings: Dict[str, List[str]]
    paragraphs: List[str]
    lists: List[List[str]]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedLink:
    """Extracted link information."""
    url: str
    text: str
    title: Optional[str] = None
    rel: Optional[str] = None
    target: Optional[str] = None
    is_external: bool = False
    is_navigation: bool = False
    is_download: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedImage:
    """Extracted image information."""
    url: str
    alt: str
    title: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    srcset: Optional[str] = None
    is_lazy: bool = False
    is_svg: bool = False
    is_background: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedTable:
    """Extracted table data."""
    headers: List[str]
    rows: List[List[str]]
    row_count: int
    column_count: int
    caption: Optional[str] = None
    has_merged_cells: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedMetadata:
    """Extracted page metadata."""
    title: str
    description: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    author: Optional[str] = None
    og_image: Optional[str] = None
    og_type: Optional[str] = None
    canonical_url: Optional[str] = None
    published_date: Optional[str] = None
    modified_date: Optional[str] = None
    language: Optional[str] = None
    favicon: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedForm:
    """Extracted form information."""
    action: str
    method: str
    inputs: List[Dict[str, Any]]
    textareas: List[Dict[str, Any]]
    selects: List[Dict[str, Any]]
    buttons: List[Dict[str, Any]]
    has_file_upload: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StructuredData:
    """Extracted structured data (JSON-LD, Microdata, RDFa)."""
    schema_type: str
    data: Dict[str, Any]
    format: str  # json-ld, microdata, rdfa
    metadata: Dict[str, Any] = field(default_factory=dict)


class ContentExtractor:
    """
    Comprehensive content extraction toolkit.
    Extracts text, links, images, tables, and structured data from pages.
    """
    
    def __init__(
        self,
        page: Page,
        base_url: Optional[str] = None,
        timeout: int = 30000
    ):
        self.page = page
        self.base_url = base_url or page.url
        self.timeout = timeout
        
    # ==================== Text Extraction ====================
    
    async def extract_text(
        self,
        selector: Optional[str] = None,
        include_hidden: bool = False,
        normalize_whitespace: bool = True
    ) -> ExtractedText:
        """
        Extract text content from page or element.
        
        Args:
            selector: Optional CSS selector to limit extraction
            include_hidden: Include hidden elements
            normalize_whitespace: Normalize whitespace in text
        """
        # Get all text
        if selector:
            locator = self.page.locator(selector)
            content = await locator.inner_text()
        else:
            content = await self.page.inner_text("body")
            
        if normalize_whitespace:
            content = self._normalize_whitespace(content)
            
        # Extract headings
        headings = {}
        for level in range(1, 7):
            h_selector = f"h{level}"
            if selector:
                h_selector = f"{selector} {h_selector}"
                
            heading_texts = await self.page.locator(h_selector).all_inner_texts()
            if heading_texts:
                headings[f"h{level}"] = heading_texts
                
        # Extract paragraphs
        p_selector = "p"
        if selector:
            p_selector = f"{selector} p"
        paragraphs = await self.page.locator(p_selector).all_inner_texts()
        
        # Extract lists
        lists = []
        for list_type in ["ul", "ol"]:
            list_selector = list_type
            if selector:
                list_selector = f"{selector} {list_type}"
                
            list_count = await self.page.locator(list_selector).count()
            for i in range(list_count):
                items = await self.page.locator(f"{list_selector} >> nth={i} li").all_inner_texts()
                if items:
                    lists.append(items)
                    
        # Count words and characters
        word_count = len(content.split())
        character_count = len(content)
        
        return ExtractedText(
            content=content,
            word_count=word_count,
            character_count=character_count,
            headings=headings,
            paragraphs=paragraphs,
            lists=lists,
            metadata={
                "url": self.page.url,
                "extracted_at": datetime.now().isoformat(),
            }
        )
        
    async def extract_text_by_selector(
        self,
        selector: str
    ) -> List[str]:
        """Extract text from all matching elements."""
        return await self.page.locator(selector).all_inner_texts()
        
    async def extract_readable_text(self) -> ExtractedText:
        """
        Extract main readable content (article-like).
        Uses heuristics to find main content area.
        """
        # Try common article selectors
        article_selectors = [
            "article",
            "[role='main']",
            "main",
            ".post-content",
            ".article-content",
            ".entry-content",
            ".content",
            "#content",
        ]
        
        for selector in article_selectors:
            count = await self.page.locator(selector).count()
            if count > 0:
                return await self.extract_text(selector)
                
        # Fallback to body
        return await self.extract_text("body")
        
    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace in text."""
        # Replace multiple spaces/tabs with single space
        text = re.sub(r'[ \t]+', ' ', text)
        # Replace multiple newlines with double newline
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Strip leading/trailing whitespace from lines
        lines = [line.strip() for line in text.split('\n')]
        return '\n'.join(lines)
        
    # ==================== Link Extraction ====================
    
    async def extract_links(
        self,
        selector: Optional[str] = None,
        filter_duplicates: bool = True,
        resolve_urls: bool = True
    ) -> List[ExtractedLink]:
        """
        Extract all links from page.
        
        Args:
            selector: Optional CSS selector to limit extraction
            filter_duplicates: Remove duplicate URLs
            resolve_urls: Resolve relative URLs to absolute
        """
        links = []
        seen_urls: Set[str] = set()
        
        # Get all anchor elements
        a_selector = "a"
        if selector:
            a_selector = f"{selector} a"
            
        anchors = await self.page.locator(a_selector).element_handles()
        
        for anchor in anchors:
            try:
                href = await anchor.get_attribute("href")
                
                if not href or href in ["#", "javascript:void(0)", "javascript:;"]:
                    continue
                    
                # Resolve URL
                if resolve_urls:
                    href = urljoin(self.base_url, href)
                    
                # Filter duplicates
                if filter_duplicates and href in seen_urls:
                    continue
                    
                seen_urls.add(href)
                
                # Get link attributes
                text = await anchor.inner_text()
                title = await anchor.get_attribute("title")
                rel = await anchor.get_attribute("rel")
                target = await anchor.get_attribute("target")
                
                # Determine link type
                parsed = urlparse(href)
                base_parsed = urlparse(self.base_url)
                is_external = parsed.netloc != base_parsed.netloc
                
                is_navigation = any(
                    nav_word in text.lower()
                    for nav_word in ["home", "about", "contact", "menu", "nav"]
                ) if text else False
                
                is_download = href.endswith((".pdf", ".zip", ".doc", ".xls", ".exe"))
                
                link = ExtractedLink(
                    url=href,
                    text=text.strip() if text else "",
                    title=title,
                    rel=rel,
                    target=target,
                    is_external=is_external,
                    is_navigation=is_navigation,
                    is_download=is_download,
                )
                
                links.append(link)
                
            except Exception as e:
                logger.debug(f"Error extracting link: {e}")
                continue
                
        return links
        
    async def extract_internal_links(self) -> List[ExtractedLink]:
        """Extract only internal links."""
        links = await self.extract_links()
        return [link for link in links if not link.is_external]
        
    async def extract_external_links(self) -> List[ExtractedLink]:
        """Extract only external links."""
        links = await self.extract_links()
        return [link for link in links if link.is_external]
        
    async def extract_download_links(self) -> List[ExtractedLink]:
        """Extract download links."""
        links = await self.extract_links()
        return [link for link in links if link.is_download]
        
    # ==================== Image Extraction ====================
    
    async def extract_images(
        self,
        selector: Optional[str] = None,
        include_data_urls: bool = False,
        include_background_images: bool = False
    ) -> List[ExtractedImage]:
        """
        Extract all images from page.
        
        Args:
            selector: Optional CSS selector to limit extraction
            include_data_urls: Include base64 data URLs
            include_background_images: Include CSS background images
        """
        images = []
        seen_urls: Set[str] = set()
        
        # Get all img elements
        img_selector = "img"
        if selector:
            img_selector = f"{selector} img"
            
        img_elements = await self.page.locator(img_selector).element_handles()
        
        for img in img_elements:
            try:
                src = await img.get_attribute("src")
                
                if not src:
                    continue
                    
                # Skip data URLs unless requested
                if src.startswith("data:") and not include_data_urls:
                    continue
                    
                # Skip duplicates
                if src in seen_urls:
                    continue
                    
                seen_urls.add(src)
                
                # Get attributes
                alt = await img.get_attribute("alt") or ""
                title = await img.get_attribute("title")
                width = await img.get_attribute("width")
                height = await img.get_attribute("height")
                srcset = await img.get_attribute("srcset")
                loading = await img.get_attribute("loading")
                
                # Determine image type
                is_svg = src.endswith(".svg") or "image/svg" in src
                is_lazy = loading == "lazy" or "lazy" in (srcset or "")
                
                image = ExtractedImage(
                    url=src,
                    alt=alt,
                    title=title,
                    width=int(width) if width and width.isdigit() else None,
                    height=int(height) if height and height.isdigit() else None,
                    srcset=srcset,
                    is_lazy=is_lazy,
                    is_svg=is_svg,
                )
                
                images.append(image)
                
            except Exception as e:
                logger.debug(f"Error extracting image: {e}")
                continue
                
        # Extract background images if requested
        if include_background_images:
            bg_images = await self._extract_background_images(selector)
            images.extend(bg_images)
            
        return images
        
    async def _extract_background_images(
        self,
        selector: Optional[str] = None
    ) -> List[ExtractedImage]:
        """Extract CSS background images."""
        images = []
        
        script = """
            (selector) => {
                const elements = selector ? 
                    document.querySelectorAll(selector) : 
                    document.querySelectorAll('*');
                    
                const bgImages = [];
                
                elements.forEach((el, index) => {
                    const style = window.getComputedStyle(el);
                    const bgImage = style.backgroundImage;
                    
                    if (bgImage && bgImage !== 'none') {
                        const urlMatch = bgImage.match(/url\\(['"]?([^'")]+)['"]?\\)/);
                        if (urlMatch) {
                            bgImages.push({
                                url: urlMatch[1],
                                tagName: el.tagName,
                                className: el.className,
                            });
                        }
                    }
                });
                
                return bgImages;
            }
        """
        
        try:
            bg_data = await self.page.evaluate(script, selector)
            
            for bg in bg_data:
                image = ExtractedImage(
                    url=bg["url"],
                    alt="",
                    is_background=True,
                    metadata={
                        "tag_name": bg.get("tagName"),
                        "class_name": bg.get("className"),
                    }
                )
                images.append(image)
                
        except Exception as e:
            logger.debug(f"Error extracting background images: {e}")
            
        return images
        
    async def download_image(
        self,
        image_url: str,
        save_path: str
    ) -> bool:
        """Download an image to disk."""
        try:
            # Handle data URLs
            if image_url.startswith("data:"):
                match = re.match(r'data:image/\w+;base64,(.+)', image_url)
                if match:
                    data = base64.b64decode(match.group(1))
                    Path(save_path).write_bytes(data)
                    return True
                    
            # Download regular URL
            response = await self.page.request.get(image_url)
            
            if response.ok:
                content = await response.body()
                Path(save_path).write_bytes(content)
                return True
                
        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            
        return False
        
    # ==================== Table Extraction ====================
    
    async def extract_tables(
        self,
        selector: Optional[str] = None,
        include_hidden: bool = False
    ) -> List[ExtractedTable]:
        """
        Extract all tables from page.
        
        Args:
            selector: Optional CSS selector to limit extraction
            include_hidden: Include hidden tables
        """
        tables = []
        
        table_selector = "table"
        if selector:
            table_selector = f"{selector} table"
            
        table_elements = await self.page.locator(table_selector).element_handles()
        
        for table in table_elements:
            try:
                # Check if visible
                if not include_hidden:
                    is_visible = await table.is_visible()
                    if not is_visible:
                        continue
                        
                # Get caption
                caption = None
                caption_el = await table.query_selector("caption")
                if caption_el:
                    caption = await caption_el.inner_text()
                    
                # Get headers
                headers = []
                th_elements = await table.query_selector_all("thead th, tr:first-child th")
                for th in th_elements:
                    header_text = await th.inner_text()
                    headers.append(header_text.strip())
                    
                # If no thead, check first row for headers
                if not headers:
                    first_row = await table.query_selector("tr:first-child")
                    if first_row:
                        first_row_cells = await first_row.query_selector_all("td, th")
                        for cell in first_row_cells:
                            text = await cell.inner_text()
                            headers.append(text.strip())
                            
                # Get rows
                rows = []
                row_elements = await table.query_selector_all("tbody tr, tr")
                
                for row in row_elements:
                    # Skip header row
                    first_cell = await row.query_selector("td:first-child, th:first-child")
                    if first_cell:
                        is_th = await first_cell.evaluate("el => el.tagName === 'TH'")
                        if is_th:
                            continue
                            
                    cells = await row.query_selector_all("td, th")
                    row_data = []
                    
                    for cell in cells:
                        text = await cell.inner_text()
                        row_data.append(text.strip())
                        
                    if row_data:
                        rows.append(row_data)
                        
                # Check for merged cells
                has_merged = await table.evaluate("""
                    (table) => {
                        const cells = table.querySelectorAll('td[rowspan], td[colspan], th[rowspan], th[colspan]');
                        return cells.length > 0;
                    }
                """)
                
                # Determine column count
                column_count = max(len(headers), max((len(row) for row in rows), default=0))
                
                table = ExtractedTable(
                    headers=headers,
                    rows=rows,
                    row_count=len(rows),
                    column_count=column_count,
                    caption=caption,
                    has_merged_cells=has_merged,
                )
                
                tables.append(table)
                
            except Exception as e:
                logger.debug(f"Error extracting table: {e}")
                continue
                
        return tables
        
    async def table_to_dataframe(
        self,
        table: ExtractedTable
    ) -> Dict[str, Any]:
        """Convert extracted table to dataframe-like structure."""
        data = {
            "columns": table.headers or [f"col_{i}" for i in range(table.column_count)],
            "data": table.rows,
            "index": list(range(len(table.rows))),
        }
        return data
        
    async def table_to_csv(
        self,
        table: ExtractedTable
    ) -> str:
        """Convert extracted table to CSV string."""
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        if table.headers:
            writer.writerow(table.headers)
            
        for row in table.rows:
            writer.writerow(row)
            
        return output.getvalue()
        
    # ==================== Metadata Extraction ====================
    
    async def extract_metadata(self) -> ExtractedMetadata:
        """Extract page metadata."""
        # Title
        title = await self.page.title()
        
        # Meta tags
        meta_tags = await self.page.locator("meta").all()
        meta_dict = {}
        
        for meta in meta_tags:
            name = await meta.get_attribute("name")
            prop = await meta.get_attribute("property")
            content = await meta.get_attribute("content")
            
            key = name or prop
            if key and content:
                meta_dict[key] = content
                
        # Extract specific metadata
        description = meta_dict.get("description")
        keywords = meta_dict.get("keywords", "").split(", ")
        author = meta_dict.get("author")
        og_image = meta_dict.get("og:image")
        og_type = meta_dict.get("og:type")
        canonical = meta_dict.get("canonical")
        
        # Get canonical URL from link element
        canonical_link = await self.page.locator("link[rel='canonical']").first()
        if canonical_link:
            href = await canonical_link.get_attribute("href")
            if href:
                canonical = href
                
        # Dates
        published = meta_dict.get("article:published_time") or meta_dict.get("datePublished")
        modified = meta_dict.get("article:modified_time") or meta_dict.get("dateModified")
        
        # Language
        lang = await self.page.evaluate("document.documentElement.lang")
        
        # Favicon
        favicon = None
        favicon_link = await self.page.locator("link[rel*='icon']").first()
        if favicon_link:
            favicon = await favicon_link.get_attribute("href")
            
        return ExtractedMetadata(
            title=title,
            description=description,
            keywords=keywords if keywords != [""] else [],
            author=author,
            og_image=og_image,
            og_type=og_type,
            canonical_url=canonical,
            published_date=published,
            modified_date=modified,
            language=lang,
            favicon=favicon,
            metadata={"all_meta": meta_dict}
        )
        
    # ==================== Form Extraction ====================
    
    async def extract_forms(
        self,
        selector: Optional[str] = None
    ) -> List[ExtractedForm]:
        """Extract all forms from page."""
        forms = []
        
        form_selector = "form"
        if selector:
            form_selector = f"{selector} form"
            
        form_elements = await self.page.locator(form_selector).element_handles()
        
        for form in form_elements:
            try:
                action = await form.get_attribute("action") or ""
                method = await form.get_attribute("method") or "GET"
                
                # Extract inputs
                inputs = []
                input_elements = await form.query_selector_all("input")
                
                for inp in input_elements:
                    input_type = await inp.get_attribute("type") or "text"
                    input_name = await inp.get_attribute("name")
                    input_value = await inp.get_attribute("value")
                    input_placeholder = await inp.get_attribute("placeholder")
                    input_required = await inp.get_attribute("required")
                    
                    inputs.append({
                        "type": input_type,
                        "name": input_name,
                        "value": input_value,
                        "placeholder": input_placeholder,
                        "required": input_required is not None,
                    })
                    
                # Extract textareas
                textareas = []
                textarea_elements = await form.query_selector_all("textarea")
                
                for ta in textarea_elements:
                    textarea_name = await ta.get_attribute("name")
                    textarea_placeholder = await ta.get_attribute("placeholder")
                    textarea_value = await ta.inner_text()
                    
                    textareas.append({
                        "name": textarea_name,
                        "value": textarea_value,
                        "placeholder": textarea_placeholder,
                    })
                    
                # Extract selects
                selects = []
                select_elements = await form.query_selector_all("select")
                
                for sel in select_elements:
                    select_name = await sel.get_attribute("name")
                    options = []
                    
                    option_elements = await sel.query_selector_all("option")
                    for opt in option_elements:
                        opt_value = await opt.get_attribute("value")
                        opt_text = await opt.inner_text()
                        options.append({"value": opt_value, "text": opt_text})
                        
                    selects.append({
                        "name": select_name,
                        "options": options,
                    })
                    
                # Extract buttons
                buttons = []
                button_elements = await form.query_selector_all("button, input[type='submit'], input[type='button']")
                
                for btn in button_elements:
                    btn_type = await btn.get_attribute("type") or "submit"
                    btn_text = await btn.inner_text()
                    btn_name = await btn.get_attribute("name")
                    btn_value = await btn.get_attribute("value")
                    
                    buttons.append({
                        "type": btn_type,
                        "text": btn_text,
                        "name": btn_name,
                        "value": btn_value,
                    })
                    
                # Check for file upload
                has_file_upload = any(
                    inp["type"] == "file" for inp in inputs
                )
                
                form_data = ExtractedForm(
                    action=action,
                    method=method.upper(),
                    inputs=inputs,
                    textareas=textareas,
                    selects=selects,
                    buttons=buttons,
                    has_file_upload=has_file_upload,
                )
                
                forms.append(form_data)
                
            except Exception as e:
                logger.debug(f"Error extracting form: {e}")
                continue
                
        return forms
        
    # ==================== Structured Data Extraction ====================
    
    async def extract_structured_data(self) -> List[StructuredData]:
        """Extract JSON-LD, Microdata, and RDFa structured data."""
        structured = []
        
        # Extract JSON-LD
        json_ld_scripts = await self.page.locator('script[type="application/ld+json"]').all()
        
        for script in json_ld_scripts:
            try:
                content = await script.inner_text()
                data = json.loads(content)
                
                # Handle @graph format
                if "@graph" in data:
                    for item in data["@graph"]:
                        structured.append(StructuredData(
                            schema_type=item.get("@type", "Unknown"),
                            data=item,
                            format="json-ld",
                        ))
                else:
                    structured.append(StructuredData(
                        schema_type=data.get("@type", "Unknown"),
                        data=data,
                        format="json-ld",
                    ))
                    
            except Exception as e:
                logger.debug(f"Error parsing JSON-LD: {e}")
                continue
                
        # Extract Microdata
        microdata = await self._extract_microdata()
        structured.extend(microdata)
        
        # Extract RDFa
        rdfa = await self._extract_rdfa()
        structured.extend(rdfa)
        
        return structured
        
    async def _extract_microdata(self) -> List[StructuredData]:
        """Extract Microdata structured data."""
        structured = []
        
        script = """
            () => {
                const items = [];
                const elements = document.querySelectorAll('[itemscope]');
                
                elements.forEach(el => {
                    const item = {};
                    const type = el.getAttribute('itemtype');
                    if (type) item['@type'] = type.split('/').pop();
                    
                    const props = el.querySelectorAll('[itemprop]');
                    props.forEach(prop => {
                        const name = prop.getAttribute('itemprop');
                        let value = prop.getAttribute('content') || 
                                   prop.getAttribute('href') ||
                                   prop.getAttribute('src') ||
                                   prop.textContent;
                        item[name] = value;
                    });
                    
                    items.push(item);
                });
                
                return items;
            }
        """
        
        try:
            items = await self.page.evaluate(script)
            
            for item in items:
                structured.append(StructuredData(
                    schema_type=item.get("@type", "Unknown"),
                    data=item,
                    format="microdata",
                ))
                
        except Exception as e:
            logger.debug(f"Error extracting microdata: {e}")
            
        return structured
        
    async def _extract_rdfa(self) -> List[StructuredData]:
        """Extract RDFa structured data."""
        structured = []
        
        script = """
            () => {
                const items = [];
                const elements = document.querySelectorAll('[typeof]');
                
                elements.forEach(el => {
                    const item = {};
                    item['@type'] = el.getAttribute('typeof');
                    
                    const props = el.querySelectorAll('[property]');
                    props.forEach(prop => {
                        const name = prop.getAttribute('property');
                        const value = prop.getAttribute('content') || prop.textContent;
                        item[name] = value;
                    });
                    
                    items.push(item);
                });
                
                return items;
            }
        """
        
        try:
            items = await self.page.evaluate(script)
            
            for item in items:
                structured.append(StructuredData(
                    schema_type=item.get("@type", "Unknown"),
                    data=item,
                    format="rdfa",
                ))
                
        except Exception as e:
            logger.debug(f"Error extracting RDFa: {e}")
            
        return structured
        
    # ==================== Comprehensive Extraction ====================
    
    async def extract_all(
        self,
        include_images: bool = True,
        include_links: bool = True,
        include_tables: bool = True,
        include_forms: bool = True,
        include_metadata: bool = True,
        include_structured_data: bool = True
    ) -> Dict[str, Any]:
        """
        Perform comprehensive extraction of all content.
        
        Args:
            include_images: Include image extraction
            include_links: Include link extraction
            include_tables: Include table extraction
            include_forms: Include form extraction
            include_metadata: Include metadata extraction
            include_structured_data: Include structured data extraction
        """
        result = {
            "url": self.page.url,
            "extracted_at": datetime.now().isoformat(),
        }
        
        # Extract text (always)
        text = await self.extract_text()
        result["text"] = {
            "content": text.content,
            "word_count": text.word_count,
            "headings": text.headings,
        }
        
        # Extract links
        if include_links:
            links = await self.extract_links()
            result["links"] = {
                "count": len(links),
                "internal": [l.__dict__ for l in links if not l.is_external],
                "external": [l.__dict__ for l in links if l.is_external],
            }
            
        # Extract images
        if include_images:
            images = await self.extract_images()
            result["images"] = {
                "count": len(images),
                "items": [img.__dict__ for img in images],
            }
            
        # Extract tables
        if include_tables:
            tables = await self.extract_tables()
            result["tables"] = {
                "count": len(tables),
                "items": [t.__dict__ for t in tables],
            }
            
        # Extract forms
        if include_forms:
            forms = await self.extract_forms()
            result["forms"] = {
                "count": len(forms),
                "items": [f.__dict__ for f in forms],
            }
            
        # Extract metadata
        if include_metadata:
            metadata = await self.extract_metadata()
            result["metadata"] = metadata.__dict__
            
        # Extract structured data
        if include_structured_data:
            structured = await self.extract_structured_data()
            result["structured_data"] = {
                "count": len(structured),
                "items": [s.__dict__ for s in structured],
            }
            
        return result
        
    # ==================== Utility Methods ====================
    
    async def get_element_info(
        self,
        selector: str
    ) -> Dict[str, Any]:
        """Get detailed information about an element."""
        locator = self.page.locator(selector)
        
        if not await locator.count():
            return {"exists": False}
            
        element = await locator.first().element_handle()
        
        info = {
            "exists": True,
            "tag": await element.evaluate("el => el.tagName.toLowerCase()"),
            "text": await element.inner_text(),
            "html": await element.inner_html(),
            "attributes": {},
            "bounding_box": await element.bounding_box(),
            "is_visible": await element.is_visible(),
            "is_enabled": await element.is_enabled(),
        }
        
        # Get all attributes
        attrs = await element.evaluate("""
            (el) => {
                const attrs = {};
                for (const attr of el.attributes) {
                    attrs[attr.name] = attr.value;
                }
                return attrs;
            }
        """)
        info["attributes"] = attrs
        
        return info
        
    async def get_page_stats(self) -> Dict[str, Any]:
        """Get page statistics."""
        stats = await self.page.evaluate("""
            () => ({
                documentWidth: document.documentElement.scrollWidth,
                documentHeight: document.documentElement.scrollHeight,
                viewportWidth: window.innerWidth,
                viewportHeight: window.innerHeight,
                scrollX: window.scrollX,
                scrollY: window.scrollY,
                links: document.links.length,
                images: document.images.length,
                forms: document.forms.length,
                scripts: document.scripts.length,
                stylesheets: document.styleSheets.length,
            })
        """)
        
        return stats
