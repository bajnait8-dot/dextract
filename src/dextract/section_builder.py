"""SectionBuilder accumulates Elements into Sections during HTML traversal.

This module provides the `SectionBuilder` class, which manages the state of
the document being built, including the current section, heading path, and
accumulated elements.
"""

from __future__ import annotations

import logging

from dextract.heading import HeadingPath
from dextract.models import Element, Section

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


class SectionBuilder:
    """Accumulates Elements into Sections as a document is traversed.

    Separating this mutable state from the traversal logic keeps the
    traversal loop stateless and easy to reason about.

    Example:
        builder = SectionBuilder()
        builder.open_section(heading_text="Introduction", level=1)
        builder.add_element(some_element)
        sections = builder.finalise()
    """

    def __init__(self) -> None:
        """Initialize a new SectionBuilder."""
        self._heading_path = HeadingPath()
        self._sections: list[Section] = []
        self._current: Section = self._make_section(heading=None, level=None, path=[])
        logger.debug("Initialized SectionBuilder")

    def open_section(self, heading_text: str, level: int) -> None:
        """Seal the current section and open a new one.

        The current section is only kept if it has content or an explicit
        heading. The new section starts empty.

        Args:
            heading_text (str): Cleaned text of the heading tag.
            level (int): Heading level between 1 and 6.
        """
        logger.debug("Opening new section: '%s' (level %d)", heading_text, level)
        self._seal_current()
        path = self._heading_path.update(heading_text, level)
        self._current = self._make_section(heading=heading_text, level=level, path=path)

    def add_element(self, element: Element) -> None:
        """Append a single Element to the currently open section.

        Args:
            element (Element): The parsed Element to add.
        """
        logger.debug("Adding element of type '%s' to current section", element.type)
        self._current.elements.append(element)

    def add_elements(self, elements: list[Element]) -> None:
        """Append multiple Elements to the currently open section.

        Args:
            elements (list[Element]): The parsed Elements to add.
        """
        logger.debug("Adding %d elements to current section", len(elements))
        self._current.elements.extend(elements)

    def finalise(self) -> list[Section]:
        """Close the last open section and return all accumulated sections.

        After calling this method the builder is reset and safe to reuse,
        though creating a new builder per document is recommended.

        Returns:
            list[Section]: An ordered list of all accumulated sections.
        """
        self._seal_current()
        result = list(self._sections)

        logger.info(
            "Finalized %d sections (%d with content).",
            len(result),
            sum(1 for s in result if s.has_content),
        )

        self._sections = []
        self._heading_path.reset()
        self._current = self._make_section(heading=None, level=None, path=[])

        return result

    @staticmethod
    def _make_section(
        heading: str | None,
        level: int | None,
        path: list[str],
    ) -> Section:
        """Create a new Section instance.

        Args:
            heading (str | None): The heading text.
            level (int | None): The heading level.
            path (list[str]): The heading path.

        Returns:
            Section: A new Section instance.
        """
        return Section(
            heading=heading,
            heading_level=level,
            heading_path=list(path),
        )

    def _seal_current(self) -> None:
        """Move the current section to the completed list if worth keeping.

        A section is kept when it has at least one element or an explicit
        heading. Empty pre-heading sections are discarded.
        """
        if self._current.has_content or self._current.heading is not None:
            logger.debug(
                "Sealing section: '%s' with %d elements",
                self._current.heading,
                len(self._current.elements),
            )
            self._sections.append(self._current)
        else:
            logger.debug("Discarding empty pre-heading section")
