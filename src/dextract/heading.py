"""Utilities for extracting heading levels and tracking the breadcrumb path.

This module provides functions and classes to handle HTML heading tags and
maintain the hierarchical path (breadcrumb) during document traversal.
"""

from __future__ import annotations

import logging

from bs4 import Tag

from dextract.constants import HEADING_TAGS

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


def heading_level(tag: Tag) -> int:
    """Return the integer level (1–6) for a heading tag.

    Args:
        tag (Tag): A BeautifulSoup Tag whose name is one of h1–h6.

    Returns:
        int: The heading level as an integer between 1 and 6 inclusive.

    Raises:
        ValueError: If the tag is not a recognized heading tag.
    """
    name = (tag.name or "").lower()
    if name not in HEADING_TAGS:
        logger.error("Attempted to get level of non-heading tag: %s", name)
        raise ValueError(f"Not a heading tag: {name!r}")
    level = int(name[1:])
    logger.debug("Detected heading level %d for tag <%s>", level, name)
    return level


class HeadingPath:
    """Tracks the active heading breadcrumb as a document is traversed.

    The breadcrumb is a list of heading texts indexed by level:
    index 0 holds the active h1 text, index 1 the active h2 text, and so on.
    Encountering a heading clears all deeper levels automatically.

    Example:
        >>> hp = HeadingPath()
        >>> hp.update("Introduction", 1)
        ['Introduction']
        >>> hp.update("Background", 2)
        ['Introduction', 'Background']
        >>> hp.update("Other Background", 2)
        ['Introduction', 'Other Background']
        >>> hp.update("Deep Dive", 1)
        ['Deep Dive']
    """

    def __init__(self) -> None:
        """Initialize an empty HeadingPath."""
        # Slot 0 is unused; slots 1–6 map to h1–h6.
        self._slots: list[str | None] = [None] * 7

    def update(self, text: str, level: int) -> list[str]:
        """Record a new heading and return the updated breadcrumb.

        Args:
            text (str): Heading text (already stripped of whitespace).
            level (int): Heading level between 1 and 6.

        Returns:
            list[str]: The current breadcrumb list, shallowest heading first.

        Raises:
            ValueError: If level is outside the range 1–6.
        """
        if not 1 <= level <= 6:
            logger.error("Invalid heading level provided to update: %d", level)
            raise ValueError(f"Heading level must be 1–6, got {level}")

        logger.debug("Updating heading path at level %d with text: %s", level, text)
        self._slots[level] = text

        for deeper_level in range(level + 1, 7):
            self._slots[deeper_level] = None

        return self.current

    @property
    def current(self) -> list[str]:
        """The current breadcrumb with no None entries, shallowest first.

        Returns:
            list[str]: The active heading path.
        """
        return [slot for slot in self._slots[1:] if slot is not None]

    def reset(self) -> None:
        """Clear the entire breadcrumb."""
        logger.debug("Resetting heading path")
        self._slots = [None] * 7
