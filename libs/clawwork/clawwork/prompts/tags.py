"""XML tag vocabulary for LLM message markup.

Defines the tag names used to structure content within messages sent to
the LLM (e.g. ``<system-reminder>``, ``<error>``).  Each tag is a
callable :class:`Tag` instance — use it as a string for matching and
call it to wrap content::

    SYSTEM_REMINDER_TAG("Warning: file is empty")
    # → "<system-reminder>Warning: file is empty</system-reminder>"
"""

from __future__ import annotations


class Tag(str):
    """An XML tag name that can wrap content.

    Subclasses ``str`` so it works as a plain string (comparisons,
    f-strings, regex matching) while also being callable as a wrapper.
    """

    __slots__ = ()

    def __call__(self, content: str) -> str:
        """Wrap *content* in an opening/closing XML tag pair."""
        return f"<{self}>{content}</{self}>"


SYSTEM_REMINDER_TAG = Tag("system-reminder")
"""Tag used to inject system-level reminders into messages."""
