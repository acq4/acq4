"""Prompt action: ask the operator to choose from labeled buttons and return
whichever label they click."""
from __future__ import annotations

from acq4.util import Qt
from acq4.util.PromptUser import prompt as prompt_user


def _resolve_choices(choices) -> list[str]:
    """Normalize `choices` (a sequence, or the legacy comma-separated string) to
    a non-empty list of labels, defaulting to `["OK"]`."""
    if isinstance(choices, str):
        labels = [c.strip() for c in choices.split(",") if c.strip()]
    else:
        labels = list(choices)
    return labels or ["OK"]


def _is_headless() -> bool:
    return Qt.QApplication.instance() is None


def prompt(ctx, message: str = "", title: str = "Prompt", choices=("OK",)) -> str:
    """Ask the operator to choose from labeled buttons; returns the clicked label.
    Non-modal and stop-aware. Headless (no UI): logs and returns the first choice."""
    labels = _resolve_choices(choices)
    with ctx.log_action("Prompt") as entry:
        entry.set_status(message)
        ctx.log(message)
        if _is_headless():
            return labels[0]
        return prompt_user(title, message, labels)
