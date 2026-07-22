"""Prompt action: surfaces operator instructions via the log/status and returns
once acknowledged. It does not itself block on a GUI dialog."""
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
