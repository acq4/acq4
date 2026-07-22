"""Tests for the Action type registry."""
import pytest

from acq4.experiment.action import Action
from acq4.experiment.registry import (
    register_action,
    get_action_class,
    action_type_name,
)


def test_register_and_lookup_by_class_name():
    @register_action
    class Alpha(Action):
        outcomes = ("ok",)

    assert get_action_class("Alpha") is Alpha
    assert action_type_name(Alpha()) == "Alpha"


def test_register_with_explicit_name():
    @register_action(name="custom-beta")
    class Beta(Action):
        outcomes = ("ok",)

    assert get_action_class("custom-beta") is Beta
    assert action_type_name(Beta()) == "custom-beta"


def test_unknown_type_raises():
    with pytest.raises(KeyError):
        get_action_class("does-not-exist")


def test_unregistered_subclass_not_misattributed():
    @register_action(name="BaseRegistered")
    class BaseRegistered(Action):
        outcomes = ("ok",)

    class DerivedUnregistered(BaseRegistered):
        outcomes = ("ok2",)

    # The unregistered subclass must report its own class name (not the parent's
    # registered name), so a round-trip fails loudly rather than silently
    # reconstructing the parent type.
    assert action_type_name(BaseRegistered()) == "BaseRegistered"
    assert action_type_name(DerivedUnregistered()) == "DerivedUnregistered"
    with pytest.raises(KeyError):
        get_action_class("DerivedUnregistered")


def test_duplicate_name_different_class_raises():
    @register_action(name="dupe")
    class Gamma(Action):
        outcomes = ("ok",)

    with pytest.raises(ValueError):
        @register_action(name="dupe")
        class Delta(Action):
            outcomes = ("ok",)
