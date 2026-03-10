"""Human-readable diagnostics and introspection helpers for the extraction process.

These functions provide tools for summarizing, serializing, and analyzing
the output of the HTML extraction process, making it easier to debug
and verify the results.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import IO

from dextract.models import Element, Section

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


def summarise(sections: list[Section], file: IO[str] = sys.stdout) -> None:
    """Print a compact tree representation of parsed sections.

    Example output:
        [Section 0] (pre-heading)  — 2 element(s)
          PROSE   : The quick brown fox…
          IMAGE   : src='embedded:image1.png' alt='chart'

        [Section 1] L1 | Introduction  — 3 element(s)
          PROSE   : This paper presents…
          TABLE   : (4 rows × 3 cols) Header A | Header B | …
          LIST    : (5 items, unordered) - First item…

    Args:
        sections (list[Section]): The list of sections to summarize.
        file (IO[str]): The output stream to print to. Defaults to `sys.stdout`.
    """
    logger.debug("Summarizing %d sections", len(sections))
    for i, section in enumerate(sections):
        path_str = (
            " > ".join(section.heading_path)
            if section.heading_path
            else "(pre-heading)"
        )
        level_str = f"L{section.heading_level}" if section.heading_level else "L?"

        print(
            f"\n[Section {i}] {level_str} | {path_str}  — {len(section.elements)} element(s)",
            file=file,
        )

        for element in section.elements:
            _print_element(element, file=file)


def _print_element(element: Element, file: IO[str] = sys.stdout) -> None:
    """Print a single-line summary of an Element.

    Args:
        element (Element): The element to summarize.
        file (IO[str]): The output stream to print to. Defaults to `sys.stdout`.
    """
    preview = element.text[:90].replace("\n", "↵")
    tag = element.type.upper().ljust(8)

    if element.type == "table":
        rows = element.meta.get("row_count", "?")
        cols = element.meta.get("col_count", "?")
        print(f"  {tag}: ({rows} rows × {cols} cols) {preview}", file=file)

    elif element.type == "list":
        count = element.meta.get("item_count", "?")
        order_label = "ordered" if element.meta.get("ordered") else "unordered"
        print(f"  {tag}: ({count} items, {order_label}) {preview}", file=file)

    elif element.type == "image":
        src = element.meta.get("src", "")
        alt = element.meta.get("alt", "")
        print(f"  {tag}: src={src!r} alt={alt!r}", file=file)

    elif element.type == "embedded":
        name = element.meta.get("name", "")
        rid = element.meta.get("relationship_id", "")
        mime = element.meta.get("mime_type", "")
        print(f"  {tag}: name={name!r} rId={rid!r} mime={mime!r}", file=file)

    elif element.type == "code":
        lang = element.meta.get("language") or "unknown"
        print(f"  {tag}: ({lang}) {preview}", file=file)

    elif element.type == "quote":
        cite = element.meta.get("cite") or ""
        print(f"  {tag}: {preview}  cite={cite!r}", file=file)

    elif element.type == "definition":
        term = element.meta.get("term", "")
        print(f"  {tag}: term={term!r} → {preview}", file=file)

    else:
        print(f"  {tag}: {preview}", file=file)


def to_json(sections: list[Section], indent: int = 2) -> str:
    """Serialize sections to a JSON string.

    Args:
        sections (list[Section]): The list of sections to serialize.
        indent (int): The JSON indentation level. Defaults to 2.

    Returns:
        str: A pretty-printed JSON representation of the sections.
    """
    logger.debug("Serializing %d sections to JSON", len(sections))
    return json.dumps(
        [s.to_dict() for s in sections], indent=indent, ensure_ascii=False
    )


def stats(sections: list[Section]) -> dict:
    """Return summary statistics for a list of sections.

    Args:
        sections (list[Section]): The list of sections to analyze.

    Returns:
        dict: A dictionary containing various statistics about the sections
            and elements.
    """
    logger.debug("Calculating statistics for %d sections", len(sections))
    element_counts: dict[str, int] = {}
    max_depth = 0

    for section in sections:
        depth = len(section.heading_path)
        if depth > max_depth:
            max_depth = depth

        for element in section.elements:
            element_counts[element.type] = element_counts.get(element.type, 0) + 1

    return {
        "total_sections": len(sections),
        "sections_with_content": sum(1 for s in sections if s.has_content),
        "total_elements": sum(element_counts.values()),
        "elements_by_type": element_counts,
        "max_heading_depth": max_depth,
        "embedded_objects": element_counts.get("embedded", 0),
        "images": element_counts.get("image", 0),
        "tables": element_counts.get("table", 0),
        "lists": element_counts.get("list", 0),
        "code_blocks": element_counts.get("code", 0),
        "quotes": element_counts.get("quote", 0),
        "definitions": element_counts.get("definition", 0),
    }
