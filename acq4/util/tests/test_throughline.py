"""Tests for acq4.util.throughline: gentletask throughline propagation across the
teleprox process boundary, plus the LogSender record tagging used in child processes."""
import contextlib

import pytest

import gentletask
import teleprox.client as tc
import teleprox.server as ts
from gentletask import ThroughlineNameFilter
from teleprox.log import remote as log_remote

from acq4.util import throughline as tl


@pytest.fixture(autouse=True)
def restore_globals():
    """Save/restore the process-global provider/hook + LogSender so tests don't leak state."""
    prev_provider = tc._call_opts_provider
    prev_hook = ts._call_context_hook
    prev_sender = log_remote.sender
    yield
    tc.set_call_opts_provider(prev_provider)
    ts.set_call_context_hook(prev_hook)
    log_remote.sender = prev_sender


def test_opts_provider_empty_without_frames():
    """Outside any throughline frame the provider contributes nothing."""
    assert tl._opts_provider() == {}


def test_opts_provider_emits_frames():
    """The provider serializes the caller's current throughline frames."""
    with gentletask.throughline(name="op"), gentletask.throughline(name="step"):
        assert tl._opts_provider() == {tl.OPTS_KEY: ({"name": "op"}, {"name": "step"})}


def test_context_hook_restores_frames():
    """The hook installs transferred frames for the call, then tears them down."""
    with tl._context_hook({tl.OPTS_KEY: ({"name": "a"}, {"name": "b"})}):
        assert gentletask.task_chain() == ("a", "b")
    assert gentletask.task_chain() == ()


def test_context_hook_without_frames_is_noop():
    """Opts lacking the throughline key leave the throughline untouched."""
    with tl._context_hook({"obj": object()}):
        assert gentletask.task_chain() == ()


def test_enable_installs_and_disable_clears():
    """enable_ claims the provider/hook slots; disable_ releases them."""
    tl.enable_throughline_propagation()
    assert tc._call_opts_provider is tl._opts_provider
    assert ts._call_context_hook is tl._context_hook
    tl.disable_throughline_propagation()
    assert tc._call_opts_provider is None
    assert ts._call_context_hook is None


def test_disable_leaves_foreign_hooks_untouched():
    """disable_ clears only the hooks we installed, not another user's."""
    other_provider = lambda: {}

    @contextlib.contextmanager
    def other_hook(opts):
        yield

    tc.set_call_opts_provider(other_provider)
    ts.set_call_context_hook(other_hook)
    tl.disable_throughline_propagation()
    assert tc._call_opts_provider is other_provider
    assert ts._call_context_hook is other_hook


class _FakeSender:
    """Stand-in for teleprox LogSender: records the filters added to it."""

    def __init__(self):
        self.filters = []

    def addFilter(self, f):
        self.filters.append(f)


def test_tag_log_sender_attaches_filter_once():
    """_tag_log_sender attaches a ThroughlineNameFilter to the LogSender, idempotently."""
    fake = _FakeSender()
    log_remote.sender = fake
    tl._tag_log_sender()
    assert sum(isinstance(f, ThroughlineNameFilter) for f in fake.filters) == 1
    # Calling again does not stack a second filter.
    tl._tag_log_sender()
    assert sum(isinstance(f, ThroughlineNameFilter) for f in fake.filters) == 1


def test_tag_log_sender_noop_without_sender():
    """With no LogSender in this process (e.g. the parent), tagging is a no-op."""
    log_remote.sender = None
    tl._tag_log_sender()  # must not raise
