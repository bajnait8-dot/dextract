"""Dataclasses representing the structured output of the HTML extraction process.

This module defines the core data structures (`Element` and `Section`) used
to represent the parsed and organized content from HTML documents.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Element
# ---------------------------------------------------------------------------

ElementType = Literal[
    "prose", "table", "list", "image", "embedded", "code", "quote", "definition"
]


@dataclass
class Element:
    """A single parsed content unit within a Section.

    Attributes:
        type (ElementType): Structural type of this element.
        text (str): Plain-text representation, always populated.
        headers (list[str]): Column headers (meaningful only for `type == "table"`).
        rows (list[list[str]]): Data rows (meaningful only for `type == "table"`).
        meta (dict[str, Any]): Type-specific metadata. Keys vary by element type:
            - **table**: row_count, col_count, has_colspan, has_rowspan,
              has_explicit_header
            - **list**: item_count, ordered
            - **image**: src, alt, width, height, title, is_embedded
            - **embedded**: name, relationship_id, mime_type
            - **code**: language
            - **quote**: cite
            - **definition**: term, definitions
    """

    type: ElementType
    text: str
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Return a JSON-serializable dictionary representation.

        Returns:
            dict: A dictionary representation of the element.
        """
        return {
            "type": self.type,
            "text": self.text,
            "headers": self.headers,
            "rows": self.rows,
            "meta": self.meta,
        }


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------


@dataclass
class Section:
    """A logical document section delimited by a heading.

    Attributes:
        heading (str | None): Text of the heading that opens this section,
            or `None` for content appearing before the first heading.
        heading_level (int | None): Integer 1–6 corresponding to h1–h6, or `None`.
        heading_path (list[str]): Breadcrumb list from the document root down
            to and including this heading, e.g. `["Introduction", "Background"]`.
        elements (list[Element]): Ordered list of content elements under this heading.
    """

    heading: str | None
    heading_level: int | None
    heading_path: list[str] = field(default_factory=list)
    elements: list[Element] = field(default_factory=list)

    @property
    def has_content(self) -> bool:
        """True if this section contains at least one element.

        Returns:
            bool: Whether the section has content.
        """
        return bool(self.elements)

    @property
    def text_elements(self) -> list[Element]:
        """All prose elements in this section.

        Returns:
            list[Element]: A list of prose elements.
        """
        return [e for e in self.elements if e.type == "prose"]

    @property
    def tables(self) -> list[Element]:
        """All table elements in this section.

        Returns:
            list[Element]: A list of table elements.
        """
        return [e for e in self.elements if e.type == "table"]

    @property
    def images(self) -> list[Element]:
        """All image elements in this section.

        Returns:
            list[Element]: A list of image elements.
        """
        return [e for e in self.elements if e.type == "image"]

    @property
    def plain_text(self) -> str:
        """All prose text joined by newlines.

        Returns:
            str: The joined prose text.
        """
        prose_texts = [e.text for e in self.elements if e.type == "prose"]
        return "\n".join(prose_texts)

    def to_dict(self) -> dict:
        """Return a JSON-serializable dictionary representation.

        Returns:
            dict: A dictionary representation of the section.
        """
        return {
            "heading": self.heading,
            "heading_level": self.heading_level,
            "heading_path": self.heading_path,
            "elements": [e.to_dict() for e in self.elements],
        }
