"""Builds the bundled example Autopatch protocols from real, registered engine
Action classes and serializes them with Protocol.save_json, so the shipped
JSON in this directory is guaranteed to round-trip through Protocol.load_json.

Run as a script (`python -m acq4.modules.Autopatch.example_protocols.generate`)
to regenerate example_prompt.json and example_patch.json after changing either
build function below.
"""
from __future__ import annotations

import os

from acq4.experiment.actions.device import CellfieAction, GoApproachAction
from acq4.experiment.actions.flow import AbortAction, GoToNextAction
from acq4.experiment.actions.prompt import PromptAction
from acq4.experiment.fsm import PatchAction
from acq4.experiment.protocol import Protocol

_HERE = os.path.dirname(__file__)


def build_example_prompt() -> Protocol:
    """Minimal, hardware-free demo: ask the operator a yes/no question, then
    advance to the next cell. Exercises the picker, the params panel (via the
    prompt's message as a public param), and the run loop without touching any
    device."""
    ask = PromptAction(name="ask", params={"message": "Ready to patch this cell?"})
    goNext = GoToNextAction(name="next")
    return Protocol(
        nodes={"ask": ask, "next": goNext},
        edges={("ask", "OK"): "next"},
        entry="ask",
        publicParams=[{"node": "ask", "param": "message", "public": "message"}],
    )


def build_example_patch() -> Protocol:
    """Realistic patch template: capture a cellfie, move to the approach
    position, then drive the Patch FSM. All three non-broken/non-fouled
    outcomes advance to the next cell. A catch-all exception handler warns the
    operator and aborts the run."""
    cellfie = CellfieAction(name="cellfie")
    goto = GoApproachAction(name="goto")
    patch = PatchAction(name="patch")
    advance = GoToNextAction(name="advance")

    warn = PromptAction(name="warn", params={"message": "Pipette problem — intervene"})
    abort = AbortAction(name="abort")
    handler = Protocol(
        nodes={"warn": warn, "abort": abort},
        edges={("warn", "OK"): "abort"},
        entry="warn",
    )

    return Protocol(
        nodes={"cellfie": cellfie, "goto": goto, "patch": patch, "advance": advance},
        edges={
            ("cellfie", "captured"): "goto",
            ("goto", "moved"): "patch",
            ("patch", "whole cell"): "advance",
            ("patch", "cell attached"): "advance",
            ("patch", "bath"): "advance",
        },
        entry="cellfie",
        publicParams=[{"node": "goto", "param": "speed", "public": "speed"}],
        exceptionHandlers={"Exception": handler},
    )


def main() -> None:
    build_example_prompt().save_json(os.path.join(_HERE, "example_prompt.json"))
    build_example_patch().save_json(os.path.join(_HERE, "example_patch.json"))


if __name__ == "__main__":
    main()
