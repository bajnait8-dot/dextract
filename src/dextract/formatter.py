"""Converts Apache Tika XHTML output to Confluence storage-format XHTML.

This module provides the `ConfluenceFormatter` class, which handles the
conversion of Tika-generated HTML into the specialized XHTML format used
by Confluence for page storage.

It handles:
    - Headings, paragraphs, and lists (pass-through or minor adjustment)
    - Tables (promoting the first row to headers)
    - Inline images (mapping to Confluence attachment or URL tags)
    - Embedded OLE objects (mapping to links or specialized macros)
    - Basic text formatting (strong, em, underline, strike-through)
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_class(tag: Tag, cls: str) -> bool:
    """Check if a BeautifulSoup Tag has a specific CSS class.

    Args:
        tag (Tag): The Tag to check.
        cls (str): The class name to look for.

    Returns:
        bool: True if the class is present, False otherwise.
    """
    return cls in (tag.get("class") or [])


def _inner_text(tag: Tag) -> str:
    """Get the stripped text content of a Tag.

    Args:
        tag (Tag): The Tag to extract text from.

    Returns:
        str: The stripped text content.
    """
    return tag.get_text(strip=True)


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------


class ConfluenceFormatter:
    """Converts Tika XHTML to Confluence page storage format.

    Attributes:
        tika_html (str): Raw Tika output. May contain multiple concatenated
            <html> documents.
        attachments (dict[str, bytes]): Mapping of {filename: bytes} for
            embedded files Tika also extracted.
        first_row_as_header (bool): When True, the first <tr> of every table
            becomes <th> cells.
        rid_to_filename (dict[str, str]): Mapping of rId to attachment filename.
    """

    # Tika wraps some bullet characters as literal middot / bullet chars
    _BULLET_CHARS = {"·", "•", "‣", "◦"}

    def __init__(
        self,
        tika_html: str,
        attachments: Optional[Dict[str, bytes]] = None,
        rid_map_override: Optional[Dict[str, str]] = None,
        first_row_as_header: bool = True,
    ):
        """Initialize the ConfluenceFormatter.

        Args:
            tika_html (str): Raw Tika output.
            attachments (dict[str, bytes], optional): Mapping of {filename: bytes}.
            rid_map_override (dict[str, str], optional): Manual {rId: filename}
                mapping.
            first_row_as_header (bool): Whether to treat the first table row
                as a header. Defaults to True.
        """
        self.tika_html = tika_html
        self.attachments: Dict[str, bytes] = attachments or {}
        self.first_row_as_header = first_row_as_header

        # rId  →  attachment filename  (e.g. "rId3" → "oleObject1.odg")
        self.rid_to_filename: Dict[str, str] = {}
        self._scan_embedded_metadata()
        if rid_map_override:
            logger.debug("Applying rId map override: %s", rid_map_override)
            self.rid_to_filename.update(rid_map_override)

    # ── metadata scan ─────────────────────────────────────────────────────────

    def _scan_embedded_metadata(self) -> None:
        """Walk every <html> block in the Tika output.

        For each block that has embeddedRelationshipId + resourceName meta tags,
        record the rId → filename mapping.
        """
        logger.debug("Scanning Tika output for embedded metadata")
        soup = BeautifulSoup(self.tika_html, "html.parser")
        for html_node in soup.find_all("html"):
            meta: Dict[str, str] = {
                m["name"]: m.get("content", "")
                for m in html_node.find_all("meta", attrs={"name": True})
            }
            rid = meta.get("embeddedRelationshipId")
            name = meta.get("resourceName", "")
            if rid and name:
                # resourceName sometimes arrives as  b'foo.xlsx'  (bytes repr)
                name = re.sub(r"^b'(.+)'$", r"\1", name)
                logger.debug("Detected mapping: %s -> %s", rid, name)
                self.rid_to_filename[rid] = name

    # ── public entry point ────────────────────────────────────────────────────

    def convert(self) -> str:
        """Return a Confluence storage-format XHTML string for the page body.

        Only the *first* <html> document in the Tika output is treated as the
        main document body; the rest are embedded resources.

        Returns:
            str: The converted Confluence storage format XHTML.
        """
        logger.info("Starting Confluence format conversion")
        soup = BeautifulSoup(self.tika_html, "html.parser")
        main_html = soup.find("html")
        if not main_html:
            logger.warning("No <html> tag found in Tika output")
            return ""
        body = main_html.find("body")
        if not body:
            logger.warning("No <body> tag found in main <html> document")
            return ""

        parts: List[str] = []
        for child in body.children:
            if isinstance(child, Tag):
                chunk = self._convert_element(child)
                if chunk:
                    parts.append(chunk)

        result = "\n".join(parts)
        logger.info("Confluence conversion complete (%d characters)", len(result))
        return result

    # ── element dispatcher ────────────────────────────────────────────────────

    def _convert_element(self, el: Tag) -> str:
        """Route a BeautifulSoup Tag to its specialized converter.

        Args:
            el (Tag): The Tag to convert.

        Returns:
            str: The converted XHTML string.
        """
        tag = el.name
        logger.debug("Converting element: <%s>", tag)

        # ── Tika metadata artefacts – skip ────────────────────────────────────
        if _has_class(el, "package-entry"):
            logger.debug("Skipping package-entry div")
            return ""

        # ── Headings (h1–h6) ──────────────────────────────────────────────────
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            inner = self._process_children(el)
            return f"<{tag}>{inner}</{tag}>" if inner.strip() else ""

        # ── Paragraphs ────────────────────────────────────────────────────────
        if tag == "p":
            inner = self._process_children(el)
            stripped = inner.strip()
            if not stripped:
                return "<p />"
            # Tika sometimes emits leading bullet chars for un-parsed lists
            if stripped and stripped[0] in self._BULLET_CHARS:
                logger.debug("Detected pseudo-list item in paragraph")
                return f"<ul><li><p>{stripped[1:].strip()}</p></li></ul>"
            return f"<p>{inner}</p>"

        # ── Tables ────────────────────────────────────────────────────────────
        if tag == "table":
            return self._convert_table(el)

        # ── Lists ─────────────────────────────────────────────────────────────
        if tag in ("ul", "ol"):
            return self._convert_list(el)

        # ── Divs (may be embedded OLE objects or generic wrappers) ────────────
        if tag == "div":
            return self._convert_div(el)

        # ── Inline images ─────────────────────────────────────────────────────
        if tag == "img":
            return self._convert_img(el)

        # ── Anything else: recurse children ───────────────────────────────────
        inner = self._process_children(el)
        return f"<{tag}>{inner}</{tag}>" if inner else ""

    # ── child walker ──────────────────────────────────────────────────────────

    def _process_children(self, el: Tag) -> str:
        """Recursively convert children and concatenate results.

        Args:
            el (Tag): The parent Tag whose children should be processed.

        Returns:
            str: The concatenated string of processed children.
        """
        parts: List[str] = []
        for child in el.children:
            if isinstance(child, NavigableString):
                parts.append(str(child))
            elif isinstance(child, Tag):
                if child.name == "img":
                    parts.append(self._convert_img(child))
                elif child.name == "div" and _has_class(child, "embedded"):
                    parts.append(self._convert_embedded_div(child))
                elif child.name in ("b", "strong"):
                    parts.append(f"<strong>{self._process_children(child)}</strong>")
                elif child.name in ("i", "em"):
                    parts.append(f"<em>{self._process_children(child)}</em>")
                elif child.name == "u":
                    parts.append(
                        f'<span style="text-decoration: underline;">'
                        f"{self._process_children(child)}</span>"
                    )
                elif child.name in ("s", "strike"):
                    parts.append(
                        f'<span style="text-decoration: line-through;">'
                        f"{self._process_children(child)}</span>"
                    )
                elif child.name == "code":
                    parts.append(f"<code>{self._process_children(child)}</code>")
                elif child.name == "br":
                    parts.append("<br />")
                elif child.name == "a":
                    parts.append(self._convert_anchor(child))
                else:
                    parts.append(self._process_children(child))
        return "".join(parts)

    # ── converters ────────────────────────────────────────────────────────────

    def _convert_img(self, img: Tag) -> str:
        """Convert an <img> tag to Confluence storage format.

        <img src="embedded:foo.gif" alt="...">
            → <ac:image ac:alt="..."><ri:attachment ri:filename="foo.gif"/></ac:image>

        <img src="https://...">
            → <ac:image><ri:url ri:value="https://..."/></ac:image>

        Args:
            img (Tag): The <img> Tag.

        Returns:
            str: Confluence XHTML for the image.
        """
        src = img.get("src", "")
        alt = img.get("alt", "")
        alt_attr = f' ac:alt="{alt}"' if alt else ""

        if src.startswith("embedded:"):
            filename = src[len("embedded:") :]
            logger.debug("Converting embedded image: %s", filename)
            return (
                f"<ac:image{alt_attr}>"
                f'<ri:attachment ri:filename="{filename}"/>'
                f"</ac:image>"
            )
        if src:
            logger.debug("Converting external image URL: %s", src)
            return f'<ac:image{alt_attr}><ri:url ri:value="{src}"/></ac:image>'
        return ""

    def _convert_embedded_div(self, div: Tag) -> str:
        """Convert a Tika embedded div to a Confluence link or macro.

        <div class="embedded" id="rId5"/>
            looks up rid_to_filename → "oleObject2.xlsx"
            → <ac:link>
                  <ri:attachment ri:filename="oleObject2.xlsx"/>
                  <ac:plain-text-link-body><![CDATA[oleObject2.xlsx]]></ac:plain-text-link-body>
               </ac:link>

        Args:
            div (Tag): The <div class="embedded"> Tag.

        Returns:
            str: Confluence XHTML for the embedded resource.
        """
        rid = div.get("id", "")
        filename = self.rid_to_filename.get(rid, "")
        if not filename:
            logger.debug("Attachment not resolved for rId: %s", rid)
            return f"<!-- embedded {rid}: attachment not resolved -->"

        display = filename.rsplit("/", 1)[-1]  # strip any path prefix
        ext = display.rsplit(".", 1)[-1].lower() if "." in display else ""

        # ── xlsx: render with the Confluence viewxls / viewfile macro ─────────
        if ext == "xlsx":
            logger.debug("Converting embedded Excel file: %s", display)
            return self._macro_view_file(display)

        # ── images that ended up as OLE (e.g. .emf, .wmf) ────────────────────
        if ext in ("emf", "wmf", "png", "gif", "jpg", "jpeg", "svg"):
            logger.debug("Converting embedded image (OLE): %s", display)
            return f'<ac:image><ri:attachment ri:filename="{display}"/></ac:image>'

        # ── generic attachment link ───────────────────────────────────────────
        logger.debug("Converting generic attachment link: %s", display)
        return (
            f"<ac:link>"
            f'<ri:attachment ri:filename="{display}"/>'
            f"<ac:plain-text-link-body>"
            f"<![CDATA[{display}]]>"
            f"</ac:plain-text-link-body>"
            f"</ac:link>"
        )

    def _macro_view_file(self, filename: str) -> str:
        """Confluence 'viewfile' macro – renders an embedded spreadsheet inline.

        Falls back gracefully if the macro isn't available.

        Args:
            filename (str): The filename of the attachment to view.

        Returns:
            str: Confluence macro XHTML.
        """
        return (
            f'<ac:structured-macro ac:name="viewfile">'
            f'<ac:parameter ac:name="name">'
            f'<ri:attachment ri:filename="{filename}"/>'
            f"</ac:parameter>"
            f"</ac:structured-macro>"
        )

    def _convert_anchor(self, a: Tag) -> str:
        """Convert an HTML <a> tag to Confluence storage format.

        Args:
            a (Tag): The <a> Tag.

        Returns:
            str: Confluence XHTML for the link.
        """
        href = a.get("href", "")
        inner = self._process_children(a)
        if not href:
            return inner
        return f'<a href="{href}">{inner}</a>'

    def _convert_table(self, table: Tag) -> str:
        """Convert an HTML table to Confluence storage format.

        First row → <th> cells (Confluence header row), remainder → <td>.
        Empty trailing rows (all cells empty) are dropped.

        Args:
            table (Tag): The <table> Tag.

        Returns:
            str: Confluence XHTML for the table.
        """
        rows = [r for r in table.find_all("tr")]
        if not rows:
            return ""

        # Drop rows where every cell is blank
        def row_has_content(tr: Tag) -> bool:
            return any(_inner_text(c).strip() for c in tr.find_all(["td", "th"]))

        rows = [r for r in rows if row_has_content(r)]
        if not rows:
            return ""

        logger.debug("Converting table with %d content rows", len(rows))
        lines = ["<table><tbody>"]
        for row_idx, row in enumerate(rows):
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            lines.append("<tr>")
            for cell in cells:
                use_header = self.first_row_as_header and row_idx == 0
                cell_tag = "th" if use_header else "td"
                inner = self._process_children(cell)
                colspan = cell.get("colspan")
                rowspan = cell.get("rowspan")
                attrs = ""
                if colspan and colspan != "1":
                    attrs += f' colspan="{colspan}"'
                if rowspan and rowspan != "1":
                    attrs += f' rowspan="{rowspan}"'
                content = f"<p>{inner}</p>" if inner.strip() else "<p />"
                lines.append(f"<{cell_tag}{attrs}>{content}</{cell_tag}>")
            lines.append("</tr>")

        lines.append("</tbody></table>")
        return "\n".join(lines)

    def _convert_list(self, list_el: Tag) -> str:
        """Convert an HTML <ul> or <ol> to Confluence storage format.

        Args:
            list_el (Tag): The list Tag.

        Returns:
            str: Confluence XHTML for the list.
        """
        tag = list_el.name  # ul or ol
        items = list_el.find_all("li", recursive=False)
        if not items:
            return ""

        logger.debug("Converting %s list with %d items", tag, len(items))
        lines = [f"<{tag}>"]
        for item in items:
            inner = self._process_children(item)
            lines.append(f"<li>{inner}</li>")
        lines.append(f"</{tag}>")
        return "\n".join(lines)

    def _convert_div(self, div: Tag) -> str:
        """Convert a generic HTML <div> by recursing into its children.

        Args:
            div (Tag): The <div> Tag.

        Returns:
            str: Confluence XHTML for the div content.
        """
        if _has_class(div, "embedded"):
            return self._convert_embedded_div(div)
        if _has_class(div, "package-entry"):
            return ""

        # Generic div: just recurse into children
        parts = []
        for child in div.children:
            if isinstance(child, Tag):
                chunk = self._convert_element(child)
                if chunk:
                    parts.append(chunk)
            elif isinstance(child, NavigableString) and str(child).strip():
                parts.append(str(child))
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def convert(
    tika_html: str,
    attachments: Optional[Dict[str, bytes]] = None,
    rid_map_override: Optional[Dict[str, str]] = None,
    first_row_as_header: bool = True,
) -> str:
    """One-shot conversion. Returns Confluence storage-format XHTML body string.

    Example:
        from tika import parser as tika_parser
        raw   = tika_parser.from_file("report.docx", xmlContent=True)
        html  = raw["content"]
        files = raw["attachments"]
        from tika_to_confluence import convert
        body = convert(html, files)

    Args:
        tika_html (str): Raw Tika output.
        attachments (dict, optional): Mapping of {filename: bytes}.
        rid_map_override (dict, optional): Manual {rId: filename} mapping.
        first_row_as_header (bool): Whether to treat the first table row
            as a header. Defaults to True.

    Returns:
        str: The converted Confluence storage format XHTML.
    """
    return ConfluenceFormatter(
        tika_html=tika_html,
        attachments=attachments,
        rid_map_override=rid_map_override,
        first_row_as_header=first_row_as_header,
    ).convert()


def format_file(html_content: str, attachments: Optional[Dict[str, bytes]]) -> str:
    """Convenience function to convert Tika HTML + attachments to Confluence format.

    Args:
        html_content (str): Raw Tika output.
        attachments (dict, optional): Mapping of {filename: bytes}.

    Returns:
        str: The converted Confluence storage format XHTML.
    """
    converter = ConfluenceFormatter(html_content, attachments)
    return converter.convert()
