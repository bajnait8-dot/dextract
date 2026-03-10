"""Public entry point for the dextract package.

This module provides the primary function for processing Tika-generated HTML
and converting it into a structured list of sections and elements.
"""

from __future__ import annotations

import logging

from dextract.models import Section
from dextract.traversal import traverse

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


def process_html(html: str) -> list[Section]:
    """Parse Tika-generated HTML and return an ordered list of Sections.

    Each Section groups all content elements under their nearest preceding
    heading. Content appearing before the first heading is collected in a
    Section whose `heading` attribute is `None`.

    Args:
        html (str): Raw HTML string returned by `tika.parser.from_file(...)["content"]`.

    Returns:
        list[Section]: An ordered list of Sections. Returns an empty list
            for blank input.

    Example:
        from tika import parser
        from dextract import process_html

        parsed = parser.from_file("report.pdf", xmlContent=True)
        sections = process_html(parsed["content"])

        for section in sections:
            print(section.heading, "->", len(section.elements), "elements")
    """
    logger.info("Processing HTML document (%d characters)", len(html) if html else 0)
    sections = traverse(html)
    logger.info("Successfully processed HTML into %d sections", len(sections))
    return sections
