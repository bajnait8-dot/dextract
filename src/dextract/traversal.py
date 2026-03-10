"""Tree-walking logic that visits BeautifulSoup nodes and dispatches to parsers.

This module provides the core traversal logic for walking an HTML document's
tree structure, identifying key elements, and dispatching them to the
appropriate parsers.
"""

from __future__ import annotations

import logging
from typing import Iterator

from bs4 import BeautifulSoup, Tag

from .constants import (
    CODE_TAGS,
    DEFINITION_TAGS,
    EMBEDDED_DIV_CLASS,
    HEADING_TAGS,
    LIST_TAGS,
    QUOTE_TAGS,
    SKIP_TAGS,
    TIKA_META_CLASSES,
)
from .element_parsers import (
    parse_code,
    parse_definition_list,
    parse_embedded,
    parse_image,
    parse_list,
    parse_prose,
    parse_quote,
    parse_table,
)
from .heading import heading_level
from .models import Section
from .section_builder import SectionBuilder

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# Tags that own their subtree and are dispatched as a whole unit.
# Their children must not be yielded separately by the walker.
_SELF_CONTAINED_TAGS: frozenset[str] = (
    HEADING_TAGS
    | {"table", "img", "p"}
    | LIST_TAGS
    | CODE_TAGS
    | QUOTE_TAGS
    | DEFINITION_TAGS
)


def traverse(html: str) -> list[Section]:
    """Walk a Tika HTML document and return an ordered list of Sections.

    Args:
        html (str): Raw HTML string as produced by Apache Tika.

    Returns:
        list[Section]: An ordered list of Sections. Returns an empty list
            for blank input.
    """
    if not html or not html.strip():
        logger.warning("traverse() received empty or whitespace-only input.")
        return []

    logger.info("Starting HTML traversal")
    soup = BeautifulSoup(html, "lxml")
    body: Tag = soup.find("body") or soup  # type: ignore[assignment]

    builder = SectionBuilder()

    for tag in _walk(body):
        _dispatch(tag, builder)

    sections = builder.finalise()
    logger.info("Finished HTML traversal, generated %d sections", len(sections))
    return sections


def _walk(node: Tag) -> Iterator[Tag]:
    """Yield every Tag that the dispatcher should handle, in document order.

    When a self-contained tag is yielded, its children are not walked — the
    corresponding parser handles the subtree in full. Generic containers
    (div, section, article, etc.) are recursed into instead.

    Args:
        node (Tag): The root Tag to walk.

    Yields:
        Iterator[Tag]: Tags ready for dispatching.
    """
    for child in node.children:
        if not isinstance(child, Tag):
            continue

        name = (child.name or "").lower()

        if name in SKIP_TAGS:
            logger.debug("Skipping tag: <%s>", name)
            continue

        if _is_tika_meta(child):
            logger.debug("Skipping Tika metadata tag: <%s>", name)
            continue

        # Embedded sub-document divs are dispatched as a single unit.
        if name == "div" and EMBEDDED_DIV_CLASS in (child.get("class") or []):
            logger.debug("Found embedded sub-document div")
            yield child
            continue

        # Self-contained structural tags: yield and stop descent.
        if name in _SELF_CONTAINED_TAGS:
            logger.debug("Found self-contained tag: <%s>", name)
            yield child
            continue

        # Generic container: recurse into children.
        logger.debug("Recursing into container tag: <%s>", name)
        yield from _walk(child)


def _dispatch(tag: Tag, builder: SectionBuilder) -> None:
    """Route a Tag to its parser and hand the result to the SectionBuilder.

    Args:
        tag (Tag): A Tag previously yielded by `_walk`.
        builder (SectionBuilder): The active SectionBuilder instance.
    """
    name = (tag.name or "").lower()
    logger.debug("Dispatching tag: <%s>", name)

    if name in HEADING_TAGS:
        text = tag.get_text(separator=" ", strip=True)
        if not text:
            logger.debug("Skipping empty <%s> heading.", name)
            return
        builder.open_section(heading_text=text, level=heading_level(tag))
        return

    if name == "div" and EMBEDDED_DIV_CLASS in (tag.get("class") or []):
        element = parse_embedded(tag)
        if element:
            builder.add_element(element)
        return

    if name == "table":
        builder.add_element(parse_table(tag))
        return

    if name in LIST_TAGS:
        element = parse_list(tag)
        if element:
            builder.add_element(element)
        return

    if name in DEFINITION_TAGS:
        builder.add_elements(parse_definition_list(tag))
        return

    if name in CODE_TAGS:
        element = parse_code(tag)
        if element:
            builder.add_element(element)
        return

    if name in QUOTE_TAGS:
        element = parse_quote(tag)
        if element:
            builder.add_element(element)
        return

    if name == "img":
        element = parse_image(tag)
        if element:
            builder.add_element(element)
        return

    element = parse_prose(tag)
    if element:
        builder.add_element(element)


def _is_tika_meta(tag: Tag) -> bool:
    """Return True if the tag is a Tika internal metadata marker.

    Args:
        tag (Tag): A BeautifulSoup Tag to inspect.

    Returns:
        bool: True if the tag's classes overlap with known Tika metadata classes.
    """
    classes: list[str] = tag.get("class") or []
    return bool(set(classes) & TIKA_META_CLASSES)
