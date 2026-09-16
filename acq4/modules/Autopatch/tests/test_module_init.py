"""Tests for Autopatch.__init__: it opens the Camera module before building
the window, refuses to open at all when no Camera module is configured, and
passes the rig's optional `protocolDir` config through to the window."""
import importlib
import os

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

    def __init__(self, cameraModule, configDir="/rig/config"):
        self._cameraModule = cameraModule
        # Only read when a `protocolDir` config is present, which is what a
        # relative one is resolved against.
        self.configDir = configDir

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
        def __init__(self, module, protocolDir=None):
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


# --- `protocolDir` config: which directory this rig's own protocols live in --
#
# None means "the default", which AutopatchWindow resolves to
# <configDir>/autopatch_protocols. The bundled example protocols are listed
# alongside whatever this names, out of the package, rather than copied into
# it -- see acq4.modules.Autopatch.example_protocols.


class _RecordingWindow:
    """Captures the protocolDir the module hands the window."""

    lastProtocolDir = "not set"

    def __init__(self, module, protocolDir=None):
        type(self).lastProtocolDir = protocolDir

    def show(self):
        pass


def _protocolDirFor(monkeypatch, config, configDir="/rig/config"):
    manager = _FakeManager(cameraModule=object(), configDir=configDir)
    monkeypatch.setattr(autopatch_module, "AutopatchWindow", _RecordingWindow)
    Autopatch(manager, "Autopatch", config)
    return _RecordingWindow.lastProtocolDir


def test_no_protocol_dir_config_leaves_the_window_to_use_its_default(qapp, monkeypatch):
    """The window's own default is <configDir>/autopatch_protocols; the module
    passes None rather than duplicating that path here."""
    assert _protocolDirFor(monkeypatch, {}) is None


def test_an_absolute_protocol_dir_config_is_used_as_given(qapp, monkeypatch):
    absolute = os.path.abspath(os.sep + os.path.join("protocols", "shared"))

    assert _protocolDirFor(monkeypatch, {"protocolDir": absolute}) == absolute


def test_a_relative_protocol_dir_config_resolves_against_the_config_dir(qapp, monkeypatch):
    """Relative is relative to the config directory -- where the default sits
    too -- so a rig can name a sibling of it without spelling out a full path."""
    result = _protocolDirFor(
        monkeypatch, {"protocolDir": "my_protocols"}, configDir=os.path.join("/rig", "config")
    )

    assert result == os.path.join("/rig", "config", "my_protocols")
