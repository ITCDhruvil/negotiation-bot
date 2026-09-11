"""Situation playbook and cross-desk lesson memory.

Deterministic — no LLM. Tactic math stays in the deal engine.
"""

from app.playbook.memory import format_lessons, record_lesson, retrieve_lessons
from app.playbook.situations import (
    PLAYBOOK,
    adapt_tactic,
    classify_situation,
    render_playbook_block,
)

__all__ = [
    "PLAYBOOK",
    "adapt_tactic",
    "classify_situation",
    "format_lessons",
    "record_lesson",
    "render_playbook_block",
    "retrieve_lessons",
]
