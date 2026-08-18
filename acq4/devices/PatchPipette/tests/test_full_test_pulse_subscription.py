"""Tests for PatchPipette's full-test-pulse subscription: independent recorders
must each be able to request the full test-pulse object without one's release
silencing the other's."""
import pytest

from acq4.devices.PatchPipette.patchpipette import PatchPipette


class _Pip:
    """Exercises the subscription methods against a bare instance, without
    standing up a real PatchPipette (which needs a Manager and devices)."""

    requestFullTestPulseData = PatchPipette.requestFullTestPulseData
    releaseFullTestPulseData = PatchPipette.releaseFullTestPulseData
    emitsFullTestPulseData = PatchPipette.emitsFullTestPulseData

    def __init__(self):
        self._fullTestPulseSubscribers = set()


def test_no_subscribers_means_no_full_data():
    assert _Pip().emitsFullTestPulseData() is False


def test_one_subscriber_turns_it_on():
    pip = _Pip()
    pip.requestFullTestPulseData("recorder-a")
    assert pip.emitsFullTestPulseData() is True


def test_releasing_the_only_subscriber_turns_it_off():
    pip = _Pip()
    token = object()
    pip.requestFullTestPulseData(token)
    pip.releaseFullTestPulseData(token)
    assert pip.emitsFullTestPulseData() is False


def test_one_recorder_releasing_does_not_silence_another():
    # The whole reason this is a set and not a bool: Autopatch stopping its
    # recorder must not switch off MultiPatch's full-test-pulse capture.
    pip = _Pip()
    autopatch, multipatch = object(), object()
    pip.requestFullTestPulseData(autopatch)
    pip.requestFullTestPulseData(multipatch)

    pip.releaseFullTestPulseData(autopatch)

    assert pip.emitsFullTestPulseData() is True


def test_requesting_twice_with_one_token_is_idempotent():
    pip = _Pip()
    token = object()
    pip.requestFullTestPulseData(token)
    pip.requestFullTestPulseData(token)
    pip.releaseFullTestPulseData(token)
    assert pip.emitsFullTestPulseData() is False


def test_releasing_an_unknown_token_is_harmless():
    # stop() is idempotent, so it may release a token it already released.
    pip = _Pip()
    pip.releaseFullTestPulseData(object())
    assert pip.emitsFullTestPulseData() is False


def test_the_old_boolean_setter_is_gone():
    # A bare setter is what let the last caller to stop win; leaving it in place
    # would leave that footgun loaded.
    assert not hasattr(PatchPipette, "emitFullTestPulseData")
