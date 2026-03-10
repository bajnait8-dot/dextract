"""Dextract: A tool for extracting content from any document type to HTML.

This package provides utilities for parsing various file formats (via Apache Tika)
and traversing the resulting HTML to extract structured data into logical
sections and elements.
"""

from dextract.debug import stats, summarise, to_json
from dextract.models import Element, ElementType, Section
from dextract.parser import parse_file
from dextract.processor import process_html

__all__ = [
    "process_html",
    "parse_file",
    "Section",
    "Element",
    "ElementType",
    "summarise",
    "to_json",
    "stats",
]
