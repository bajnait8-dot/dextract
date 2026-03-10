"""Integration with Apache Tika for parsing binary files.

This module provides utilities for extracting content and metadata from various
file formats (PDF, DOCX, etc.) using Apache Tika, and optionally converting
the resulting HTML into Markdown.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from markdownify import markdownify as md
from tika import parser, unpack

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File Parsing
# ---------------------------------------------------------------------------


def parse_file(
    file_path: str | Path, extract_media: bool = False, include_md: bool = False
) -> dict[str, Any]:
    """Parse a file using Apache Tika and return its contents.

    Args:
        file_path (str | Path): Path to the file to be parsed.
        extract_media (bool): Whether to extract attachments/media from the
            file. Defaults to False.
        include_md (bool): Whether to include a Markdown-formatted version of
            the content. Defaults to False.

    Returns:
        dict[str, Any]: A dictionary containing:
            - **html_content**: Raw XHTML content from Tika.
            - **md_content**: (Optional) Markdown representation of the content.
            - **attachments**: (Optional) Dictionary of extracted attachments.
            - **tika_metadata**: Dictionary of metadata returned by Tika.
    """
    logger.info("Parsing file: %s", file_path)
    file_path_str = str(file_path)

    result: dict[str, Any] = {}

    # Extract HTML and metadata
    parsed = parser.from_file(file_path_str, xmlContent=True)
    html_raw = parsed.get("content")
    result["html_content"] = html_raw
    result["tika_metadata"] = parsed.get("metadata")

    # Optional Markdown conversion
    if include_md and html_raw:
        logger.debug("Converting HTML to Markdown")
        result["md_content"] = md(html_raw)

    # Optional media extraction
    if extract_media:
        logger.info("Extracting media from: %s", file_path)
        unpacked = unpack.from_file(file_path_str)
        result["attachments"] = unpacked.get("attachments")

    return result
