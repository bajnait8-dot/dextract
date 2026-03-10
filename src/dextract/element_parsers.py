"""One focused parser per HTML element type.

Each parser receives a BeautifulSoup Tag and returns either an Element or
None when the tag has no meaningful content to contribute. All parsers are
pure functions and never mutate the soup tree.
"""

from __future__ import annotations

import logging
import mimetypes
import re
from typing import Callable

from bs4 import NavigableString, Tag

from .constants import (
    EMBEDDED_DIV_CLASS,
    HEADING_TAGS,
    LIST_TAGS,
    ORDERED_PREFIX,
    UNORDERED_PREFIX,
)
from .models import Element

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

ParserFn = Callable[[Tag], Element | None]


# ---------------------------------------------------------------------------
# Prose
# ---------------------------------------------------------------------------


def parse_prose(tag: Tag) -> Element | None:
    """Extract plain text from a block-level tag.

    Collapses internal whitespace so downstream consumers receive clean text.

    Args:
        tag (Tag): Any block-level BeautifulSoup Tag.

    Returns:
        Element | None: An Element with type "prose", or None if the tag is empty.
    """
    raw = tag.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", raw).strip()

    if not text:
        logger.debug("Skipping empty prose element")
        return None

    return Element(type="prose", text=text)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def parse_table(tag: Tag) -> Element:
    """Parse a `<table>` into a pipe-delimited text representation.

    Handles explicit `<thead>`/`<tbody>`/`<tfoot>` sections as well as
    tables with only bare `<tr>` rows. When no `<thead>` is present, the
    first row is promoted to headers if it consists entirely of `<th>` cells.

    Note:
        `colspan` and `rowspan` are detected and recorded in meta but not
        expanded — full grid reconstruction is out of scope for text extraction.

    Args:
        tag (Tag): A `<table>` BeautifulSoup Tag.

    Returns:
        Element: An Element with type "table". Always returned, even for empty tables.
    """
    headers: list[str] = []
    rows: list[list[str]] = []
    has_colspan = False
    has_rowspan = False

    logger.debug("Parsing table element")

    # 1. Pull headers from <thead> if present.
    thead = tag.find("thead")
    if thead and isinstance(thead, Tag):
        logger.debug("Found <thead> in table")
        for tr in thead.find_all("tr"):
            cells = _extract_cells(tr)
            if cells:
                headers = cells
                break

    # 2. Pull data rows from <tbody>, or fall back to the table itself.
    tbody = tag.find("tbody")
    body_scope: Tag = tbody if isinstance(tbody, Tag) else tag

    recursive = not isinstance(tbody, Tag)
    for tr in body_scope.find_all("tr", recursive=recursive):
        # Check for spans while traversing
        for cell in tr.find_all(["td", "th"]):
            if cell.get("colspan"):
                has_colspan = True
            if cell.get("rowspan"):
                has_rowspan = True

        cells = _extract_cells(tr)
        if any(c.strip() for c in cells):
            rows.append(cells)

    # 3. Append <tfoot> rows as data rows.
    tfoot = tag.find("tfoot")
    if tfoot and isinstance(tfoot, Tag):
        logger.debug("Found <tfoot> in table")
        for tr in tfoot.find_all("tr"):
            cells = _extract_cells(tr)
            if any(c.strip() for c in cells):
                rows.append(cells)

    # 4. Auto-promote the first row to headers if it is all <th> cells.
    if not headers and rows:
        first_row_tag = tag.find("tr")
        if first_row_tag and isinstance(first_row_tag, Tag):
            cell_tags = first_row_tag.find_all(["td", "th"])
            all_th = all(cell.name == "th" for cell in cell_tags)
            if all_th:
                logger.debug("Auto-promoting first row to headers (all <th>)")
                headers = rows.pop(0)

    # 5. Determine column count and pad short rows.
    col_count = len(headers) if headers else max((len(r) for r in rows), default=0)

    if headers:
        for i, row in enumerate(rows):
            if len(row) < len(headers):
                rows[i] = row + [""] * (len(headers) - len(row))

    # 6. Render as pipe-delimited markdown text.
    text = _render_table_text(headers, rows)

    logger.debug("Table parsed: %d rows, %d columns", len(rows), col_count)

    return Element(
        type="table",
        text=text,
        headers=headers,
        rows=rows,
        meta={
            "row_count": len(rows),
            "col_count": col_count,
            "has_colspan": has_colspan,
            "has_rowspan": has_rowspan,
            "has_explicit_header": thead is not None,
        },
    )


def _render_table_text(headers: list[str], rows: list[list[str]]) -> str:
    """Render table headers and rows as a pipe-delimited string.

    Args:
        headers (list[str]): Column header strings.
        rows (list[list[str]]): Data row strings.

    Returns:
        str: A multi-line pipe-delimited string, or "[empty table]" if both
            headers and rows are empty.
    """
    if headers:
        separator = " | ".join(["---"] * len(headers))
        lines = [" | ".join(headers), separator]
        for row in rows:
            lines.append(" | ".join(row[: len(headers)]))
        return "\n".join(lines)

    if rows:
        lines = []
        for row in rows:
            lines.append(" | ".join(row))
        return "\n".join(lines)

    return "[empty table]"


def _extract_cells(tr: Tag) -> list[str]:
    """Return the cleaned text of every `<td>`/`<th>` in a row.

    Args:
        tr (Tag): A `<tr>` BeautifulSoup Tag.

    Returns:
        list[str]: A list of cell text strings with collapsed whitespace.
    """
    cells = []
    for td in tr.find_all(["td", "th"]):
        raw = td.get_text(separator=" ", strip=True)
        cells.append(re.sub(r"\s+", " ", raw).strip())
    return cells


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------


def parse_list(tag: Tag) -> Element | None:
    """Parse a `<ul>` or `<ol>` into a newline-delimited prefixed string.

    Each list item is prefixed with "- " for unordered lists or
    "N. " for ordered lists. Items with no text content are skipped.
    Text from nested `<ul>`/`<ol>` children is excluded to avoid
    duplication, as nested lists are emitted as separate elements.

    Args:
        tag (Tag): A `<ul>` or `<ol>` BeautifulSoup Tag.

    Returns:
        Element | None: An Element with type "list", or None if all items are empty.
    """
    is_ordered = tag.name == "ol"
    items: list[str] = []

    logger.debug("Parsing %s list", "ordered" if is_ordered else "unordered")

    for li in tag.find_all("li", recursive=False):
        text = _li_direct_text(li)
        if text:
            items.append(text)

    if not items:
        logger.debug("Skipping empty list")
        return None

    lines = []
    for i, item in enumerate(items):
        if is_ordered:
            lines.append(ORDERED_PREFIX.format(n=i + 1) + item)
        else:
            lines.append(UNORDERED_PREFIX + item)

    return Element(
        type="list",
        text="\n".join(lines),
        meta={"item_count": len(items), "ordered": is_ordered},
    )


def _li_direct_text(li: Tag) -> str:
    """Return the text of a `<li>` excluding any nested list children.

    Args:
        li (Tag): A `<li>` BeautifulSoup Tag.

    Returns:
        str: Cleaned text string with collapsed whitespace.
    """
    parts: list[str] = []

    for child in li.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag) and child.name not in LIST_TAGS:
            parts.append(child.get_text(separator=" ", strip=False))

    return re.sub(r"\s+", " ", " ".join(parts)).strip()


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------


def parse_image(tag: Tag) -> Element | None:
    """Extract metadata from an `<img>` tag without loading image bytes.

    Tika embedded image `src` values look like `"embedded:image2.jpeg"`
    and are preserved verbatim so callers can route them back to Tika.

    Args:
        tag (Tag): An `<img>` BeautifulSoup Tag.

    Returns:
        Element | None: An Element with type "image", or None if `src` is absent.
    """
    src = (tag.get("src") or "").strip()

    if not src:
        logger.debug("Skipping <img> with no src attribute.")
        return None

    alt = (tag.get("alt") or "").strip()
    title = (tag.get("title") or "").strip()
    width = tag.get("width")
    height = tag.get("height")

    label = alt or title or "no description"
    display_text = f"[Image: {label}]"

    if src.startswith("embedded:"):
        display_text += f" (embedded: {src})"

    logger.debug("Parsed image: src=%s", src)

    return Element(
        type="image",
        text=display_text,
        meta={
            "src": src,
            "alt": alt,
            "title": title,
            "width": int(width) if width and str(width).isdigit() else width,
            "height": int(height) if height and str(height).isdigit() else height,
            "is_embedded": src.startswith("embedded:"),
        },
    )


# ---------------------------------------------------------------------------
# Embedded sub-documents
# ---------------------------------------------------------------------------


def parse_embedded(tag: Tag) -> Element | None:
    """Parse a Tika-generated embedded sub-document marker.

    Tika renders embedded objects as `<div class="package-entry">`. The
    name is read from the first heading inside the div, with a fallback to
    all text. The `id` attribute, if present, is stored as the relationship
    id so callers can use it with Tika's `/unpack` endpoint.

    Args:
        tag (Tag): A `<div class="package-entry">` BeautifulSoup Tag.

    Returns:
        Element | None: An Element with type "embedded", or None if no name is found.
    """
    inner_heading = tag.find(HEADING_TAGS)

    if inner_heading and isinstance(inner_heading, Tag):
        name = inner_heading.get_text(strip=True)
    else:
        name = re.sub(r"\s+", " ", tag.get_text(strip=True)).strip()

    if not name:
        logger.debug("Skipping embedded object with no name")
        return None

    relationship_id: str | None = tag.get("id") or None
    mime_type = _mime_from_name(name)

    logger.debug("Parsed embedded object: %s (mime: %s)", name, mime_type)

    return Element(
        type="embedded",
        text=f"[Embedded object: {name}]",
        meta={
            "name": name,
            "relationship_id": relationship_id,
            "mime_type": mime_type,
        },
    )


def _mime_from_name(name: str) -> str | None:
    """Infer a MIME type from a filename's extension.

    Args:
        name (str): A filename string, e.g. "report.xlsx".

    Returns:
        str | None: A MIME type string, or None if the extension is unknown.
    """
    if "." not in name:
        return None

    _, ext = name.rsplit(".", 1)
    mime, _ = mimetypes.guess_type(f"file.{ext}")
    return mime


# ---------------------------------------------------------------------------
# Code blocks
# ---------------------------------------------------------------------------


def parse_code(tag: Tag) -> Element | None:
    """Parse `<pre>` and `<code>` blocks, preserving internal formatting.

    For `<pre>` tags, text is read from an inner `<code>` child when
    present. Language is detected from the HTML5 `class="language-*"`
    convention.

    Args:
        tag (Tag): A `<pre>` or `<code>` BeautifulSoup Tag.

    Returns:
        Element | None: An Element with type "code", or None if the block is empty.
    """
    inner_code = tag.find("code") if tag.name == "pre" else tag
    target: Tag = inner_code if isinstance(inner_code, Tag) else tag

    text = target.get_text(separator="\n")
    stripped = text.strip("\n").rstrip()

    if not stripped:
        logger.debug("Skipping empty code block")
        return None

    language = _detect_language(target)
    logger.debug("Parsed code block (language: %s)", language or "unknown")

    return Element(
        type="code",
        text=stripped,
        meta={"language": language},
    )


def _detect_language(tag: Tag) -> str | None:
    """Detect a language hint from a tag's CSS class attribute.

    Recognizes the `language-*` and `lang-*` HTML5 conventions.

    Args:
        tag (Tag): A BeautifulSoup Tag to inspect.

    Returns:
        str | None: The language string (e.g. "python"), or None if not found.
    """
    classes: list[str] = tag.get("class") or []

    for cls in classes:
        if cls.startswith("language-"):
            return cls[len("language-") :]
        if cls.startswith("lang-"):
            return cls[len("lang-") :]

    return None


# ---------------------------------------------------------------------------
# Block quotes
# ---------------------------------------------------------------------------


def parse_quote(tag: Tag) -> Element | None:
    """Parse `<blockquote>` and `<q>` elements.

    Args:
        tag (Tag): A `<blockquote>` or `<q>` BeautifulSoup Tag.

    Returns:
        Element | None: An Element with type "quote", or None if the tag is empty.
    """
    text = re.sub(r"\s+", " ", tag.get_text(separator=" ", strip=True)).strip()

    if not text:
        logger.debug("Skipping empty quote element")
        return None

    cite: str | None = tag.get("cite") or None
    logger.debug("Parsed quote: %s...", text[:20])

    return Element(
        type="quote",
        text=f'"{text}"',
        meta={"cite": cite},
    )


# ---------------------------------------------------------------------------
# Definition lists
# ---------------------------------------------------------------------------


def parse_definition_list(tag: Tag) -> list[Element]:
    """Parse a `<dl>` into one Element per term/definition pair.

    A single `<dl>` may contain multiple `<dt>`/`<dd>` groups. Each
    group becomes its own Element to preserve the list structure.

    Args:
        tag (Tag): A `<dl>` BeautifulSoup Tag.

    Returns:
        list[Element]: A list of Elements with type "definition". May be empty.
    """
    elements: list[Element] = []
    current_term: str | None = None
    definitions: list[str] = []

    logger.debug("Parsing definition list")

    def flush_current_term() -> None:
        if current_term is None:
            return
        definition_text = "; ".join(definitions) if definitions else "(no definition)"
        elements.append(
            Element(
                type="definition",
                text=f"{current_term}: {definition_text}",
                meta={"term": current_term, "definitions": list(definitions)},
            )
        )

    for child in tag.find_all(["dt", "dd"], recursive=False):
        if not isinstance(child, Tag):
            continue

        if child.name == "dt":
            flush_current_term()
            current_term = re.sub(r"\s+", " ", child.get_text(strip=True)).strip()
            definitions = []

        elif child.name == "dd":
            dd_text = re.sub(
                r"\s+", " ", child.get_text(separator=" ", strip=True)
            ).strip()
            if dd_text:
                definitions.append(dd_text)

    flush_current_term()
    logger.debug("Definition list parsed into %d elements", len(elements))
    return elements
