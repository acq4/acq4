"""Prompt action: surfaces operator instructions via the log/status. In this
device-free phase it does not block on a dialog; the UI phase adds an operator-blocking widget."""
from __future__ import annotations

from ..action import Action
from ..registry import register_action


@register_action(name="Prompt")
class PromptAction(Action):
    outcomes = ("acknowledged",)
    paramSpec = ({"name": "message", "type": "str", "default": ""},)

    def run(self, ctx):
        message = self.paramValue("message")
        self.setState(message)
        ctx.log(message)
        return "acknowledged"
