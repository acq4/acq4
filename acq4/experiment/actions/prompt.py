"""Prompt action: ask the operator to choose from labeled buttons and route the
protocol graph on whichever button they click."""
from __future__ import annotations

from acq4.util.PromptUser import prompt as prompt_user

from ..action import Action
from ..registry import register_action


@register_action(name="Prompt")
class PromptAction(Action):
    """Present the operator a message with one or more labeled buttons; the clicked
    label is the outcome the protocol graph routes on.

    `choices` is a comma-separated list of button labels (default "OK"). The
    prompt is non-modal and stop-aware, so stopping the run cancels it.
    """

    outcomes = ("OK",)
    paramSpec = (
        {"name": "title", "type": "str", "default": "Prompt"},
        {"name": "message", "type": "str", "default": ""},
        {"name": "choices", "type": "str", "default": "OK"},
    )

    def choices(self) -> list[str]:
        labels = [c.strip() for c in self.paramValue("choices").split(",") if c.strip()]
        return labels or ["OK"]

    def run(self, ctx):
        choices = self.choices()
        # Adopt the choices as outcomes so the orchestrator validates and routes
        # on whichever button the operator clicks.
        self.outcomes = tuple(choices)
        message = self.paramValue("message")
        self.setState(message)
        ctx.log(message)
        return prompt_user(self.paramValue("title"), message, choices)
