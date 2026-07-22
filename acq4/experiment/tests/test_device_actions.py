"""Registration/outcome tests for device-wrapping Actions.

Every device action drives real pipette/scope/task-runner hardware, so only their
registration and declared outcomes/positions are checked here; their behavior is
verified by live testing.
"""
from acq4.experiment.actions.device import (
    GoHomeAction,
    GoSearchAction,
    GoApproachAction,
    GoTargetAction,
    GoAboveTargetAction,
    FocusTipAction,
    FocusTargetAction,
    NewPipetteAction,
    FindTipAction,
    FindSurfaceAction,
    CellfieAction,
    TaskAction,
)
from acq4.experiment.registry import get_action_class


def test_named_moves_registered_with_positions():
    cases = {
        "GoHome": (GoHomeAction, "home"),
        "GoSearch": (GoSearchAction, "search"),
        "GoApproach": (GoApproachAction, "approach"),
        "GoTarget": (GoTargetAction, "target"),
        "GoAboveTarget": (GoAboveTargetAction, "aboveTarget"),
    }
    for name, (cls, position) in cases.items():
        assert get_action_class(name) is cls
        assert cls.position == position
        assert cls.outcomes == ("moved",)


def test_focus_actions_registered():
    assert get_action_class("FocusTip") is FocusTipAction
    assert FocusTipAction.focus_on == "tip"
    assert get_action_class("FocusTarget") is FocusTargetAction
    assert FocusTargetAction.focus_on == "target"
    assert FocusTipAction.outcomes == ("focused",)


def test_other_device_actions_registered():
    assert get_action_class("NewPipette") is NewPipetteAction
    assert NewPipetteAction.outcomes == ("ready",)
    assert get_action_class("FindTip") is FindTipAction
    assert FindTipAction.outcomes == ("found",)
    assert get_action_class("FindSurface") is FindSurfaceAction
    assert FindSurfaceAction.outcomes == ("found",)
    assert get_action_class("Cellfie") is CellfieAction
    assert CellfieAction.outcomes == ("captured",)
    assert get_action_class("Task") is TaskAction
    assert TaskAction.outcomes == ("done",)
