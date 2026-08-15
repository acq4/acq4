"""Tests for Autopatch.__init__: it opens the Camera module before building
the window, and refuses to open at all when no Camera module is configured."""
import importlib

import pytest

from acq4.modules.Autopatch.Autopatch import Autopatch
from acq4.util import Qt
from acq4.util.HelpfulException import HelpfulException

# Not `import acq4.modules.Autopatch.Autopatch as autopatch_module`: the
# package's own __init__.py does `from .Autopatch import Autopatch`, which
# rebinds the package's `Autopatch` attribute to the class -- so `import a.b.c
# as x` (attribute lookup through the package) would hand back the class, not
# the module namespace `AutopatchWindow` actually lives in.
autopatch_module = importlib.import_module("acq4.modules.Autopatch.Autopatch")


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeManager:
    """The minimum Module.__init__ needs (declareInterface) plus getModule,
    for exercising Autopatch.__init__ in isolation -- no real Manager, no
    AutopatchWindow, no config file on disk."""

    def __init__(self, cameraModule):
        self._cameraModule = cameraModule

    def declareInterface(self, name, interfaces, obj):
        pass

    def getModule(self, name):
        assert name == "Camera"
        return self._cameraModule


@pytest.fixture(autouse=True)
def _resetInstance():
    # Autopatch._instance is a class attribute shared across every instance;
    # a value left behind by one test's construction (successful or not)
    # would otherwise leak into the next.
    Autopatch._instance = None
    yield
    Autopatch._instance = None


def test_camera_is_opened_before_the_window_is_built(qapp, monkeypatch):
    order = []
    manager = _FakeManager(cameraModule=object())
    realGetModule = manager.getModule

    def getModule(name):
        order.append("getModule")
        return realGetModule(name)

    monkeypatch.setattr(manager, "getModule", getModule)

    class _FakeWindow:
        def __init__(self, module):
            order.append("window")

        def show(self):
            pass

    monkeypatch.setattr(autopatch_module, "AutopatchWindow", _FakeWindow)

    Autopatch(manager, "Autopatch", {})

    assert order == ["getModule", "window"]


def test_init_refuses_when_camera_is_not_configured(qapp):
    # Manager.loadDefinedModule (see Manager.py) only logs an error and
    # returns None, rather than raising, when "Camera" is not in the rig's
    # configuration at all -- the case that reaches here as
    # manager.getModule("Camera") answering None.
    manager = _FakeManager(cameraModule=None)

    with pytest.raises(HelpfulException, match="Camera"):
        Autopatch(manager, "Autopatch", {})

    # Set only once Camera is confirmed present: a refusal here must not
    # leave _instance pointing at a half-built module with no .ui, or every
    # later attempt to open Autopatch would hit
    # Autopatch._instance.ui.raise_() -> AttributeError, permanently.
    assert Autopatch._instance is None
