# Dextract

Dextract is a Python package designed for extracting content from any document type (PDF, DOCX, PPTX, etc.) into structured HTML and logical sections. By leveraging Apache Tika, it converts binary files into XHTML and logically oorganizes the content into a hierarchical model of headings, paragraphs, tables, and images.

## Features

- **Hierarchical Extraction:** Groups content into sections based on `h1`-`h6` tags.
- **Breadcrumb Tracking:** Maintains the full heading path for each section.
- **Rich Element Parsing:**
    - **Prose:** Cleaned and normalized text from block-level tags.
    - **Tables:** Parsed into pipe-delimited Markdown-style text, including headers and metadata.
    - **Lists:** Ordered and unordered lists with appropriate prefixes.
    - **Images:** Extraction of `src`, `alt`, `title`, and dimensions.
    - **Embedded Objects:** Identification of Tika-embedded sub-documents and OLE objects.
    - **Code Blocks:** Preservation of formatting and language detection.
    - **Quotes & Definitions:** Structured extraction of blockquotes and definition lists.
- **Confluence Formatting:** Includes a specialized formatter to convert Tika XHTML directly into Confluence Storage Format.

## Installation

```bash
pip install dextract
```

## Quick Start

### File Parsing with Apache Tika

Dextract includes a utility to wrap Apache Tika for parsing binary files (like PDFs or Word documents) into XHTML, which can then be processed.

```python
from dextract import parse_file, process_html

# Parse a binary file into HTML and metadata
# Use extract_media=True to pull out attachments/images
parsed = parse_file("report.pdf", extract_media=True)

# Process the resulting HTML into structured sections
sections = process_html(parsed["html_content"])
```

### Basic Extraction (from HTML)

```python
from dextract import process_html, summarise

# Raw HTML from Tika (or any other source)
html_content = """
<html>
    <body>
        <h1>Project Overview</h1>
        <p>This is a sample document.</p>
        <h2>Key Features</h2>
        <ul>
            <li>Fast extraction</li>
            <li>Structured output</li>
        </ul>
    </body>
</html>
"""

# Process the HTML into sections
sections = process_html(html_content)

# Print a summary of the extracted sections
summarise(sections)
```

### Confluence Formatting

```python
from dextract.formatter import ConfluenceFormatter

tika_html = "..." # Raw XHTML from Tika
attachments = {"image1.png": b"..."} # Optional attachment data

formatter = ConfluenceFormatter(tika_html, attachments)
confluence_xhtml = formatter.convert()
```

## Package Structure

- `dextract.processor`: The primary entry point (`process_html`).
- `dextract.parser`: File parsing utilities using Apache Tika (`parse_file`).
- `dextract.models`: Core data structures (`Section`, `Element`).
- `dextract.traversal`: The engine that walks the HTML tree.
- `dextract.element_parsers`: Specialized parsers for different HTML tags.
- `dextract.formatter`: Confluence Storage Format conversion utilities.
- `dextract.debug`: Helpers for inspection and statistics.


## License

MIT
