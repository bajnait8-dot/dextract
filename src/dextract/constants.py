"""All tag sets, class names, and tunable defaults used across the package.

This module contains constants that define how HTML tags are grouped,
handled, and filtered during the extraction process.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# HTML tag groups
# ---------------------------------------------------------------------------

HEADING_TAGS: frozenset[str] = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

LIST_TAGS: frozenset[str] = frozenset({"ul", "ol"})

SKIP_TAGS: frozenset[str] = frozenset(
    {"script", "style", "head", "noscript", "template"}
)

PROSE_TAGS: frozenset[str] = frozenset(
    {
        "p",
        "div",
        "article",
        "section",
        "main",
        "aside",
        "header",
        "footer",
        "nav",
        "address",
        "details",
        "summary",
    }
)

CODE_TAGS: frozenset[str] = frozenset({"pre", "code"})

QUOTE_TAGS: frozenset[str] = frozenset({"blockquote", "q"})

DEFINITION_TAGS: frozenset[str] = frozenset({"dl"})

# ---------------------------------------------------------------------------
# Tika-specific markers
# ---------------------------------------------------------------------------

# Class Tika applies to embedded sub-document wrapper divs.
EMBEDDED_DIV_CLASS: str = "package-entry"

# Tika metadata div classes to skip entirely.
TIKA_META_CLASSES: frozenset[str] = frozenset({"tika-metadata"})

# ---------------------------------------------------------------------------
# Traversal: tags whose children are handled by their own parser, not the
# top-level walker.
# ---------------------------------------------------------------------------

CONTAINER_TAGS: frozenset[str] = frozenset({"table", "ul", "ol", "dl"})

# ---------------------------------------------------------------------------
# Prose filtering
# ---------------------------------------------------------------------------

# Minimum characters for a prose element to be kept.
MIN_PROSE_LENGTH: int = 1

# ---------------------------------------------------------------------------
# Table parsing
# ---------------------------------------------------------------------------

# Maximum header rows to auto-detect when no explicit <thead> is present.
MAX_HEADER_ROWS_AUTO: int = 1

# ---------------------------------------------------------------------------
# List formatting
# ---------------------------------------------------------------------------

UNORDERED_PREFIX: str = "- "
ORDERED_PREFIX: str = "{n}. "
