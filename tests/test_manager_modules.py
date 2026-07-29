# Tests for Manager's module lookup/loading accessors.
# Covers the contract that getOrLoadModule and loadDefinedModule hand back the module
# instance, whether it was already loaded, defined in the config, or neither.

import pytest
from pyqtgraph.util.mutex import Mutex

from acq4 import modules as module_registry
from acq4.Manager import Manager
from acq4.util import Qt


class FakeModule:
    """Stand-in for a modules.Module; only needs a name and a window()."""

    def __init__(self, name):
        self.name = name
        self._window = object()

    def window(self):
        return self._window


@pytest.fixture
def manager():
    """A Manager with only the state the module accessors touch.

    Manager.__init__ builds a whole application (singleton guard, devices, log
    window), so bypass it and populate just the module bookkeeping. loadModule is
    replaced with a stub so no real GUI module is instantiated.
    """
    man = Manager.__new__(Manager)
    man.modules = {}
    man.definedModules = {}
    man.moduleLock = Mutex(recursive=True)
    man.loadModule = lambda moduleClassName, name=None, config=None, **kwds: (
        man.modules.setdefault(name or moduleClassName, FakeModule(name or moduleClassName))
    )
    return man


def test_loadDefinedModule_returns_the_module(manager):
    manager.definedModules['Visualize3D'] = {'module': 'Visualize3D'}

    mod = manager.loadDefinedModule('Visualize3D')

    assert isinstance(mod, FakeModule)
    assert mod is manager.modules['Visualize3D']


def test_getOrLoadModule_returns_defined_module_on_first_load(manager):
    """The first getOrLoadModule of a *defined* module goes down the
    loadDefinedModule path; callers immediately dereference the result
    (e.g. ``.window()``), so it must be the module, not None."""
    manager.definedModules['Visualize3D'] = {'module': 'Visualize3D'}

    mod = manager.getOrLoadModule('Visualize3D')

    assert mod is not None
    assert mod is manager.modules['Visualize3D']


def test_getOrLoadModule_is_idempotent(manager):
    manager.definedModules['Visualize3D'] = {'module': 'Visualize3D'}

    first = manager.getOrLoadModule('Visualize3D')
    second = manager.getOrLoadModule('Visualize3D')

    assert first is second


def test_getOrLoadModule_returns_already_loaded_module(manager):
    existing = FakeModule('Visualize3D')
    manager.modules['Visualize3D'] = existing

    assert manager.getOrLoadModule('Visualize3D') is existing


def test_getOrLoadModule_falls_back_to_undefined_module_class(manager):
    """A module that is neither loaded nor defined in the config is loaded by
    class name."""
    mod = manager.getOrLoadModule('Visualize3D')

    assert isinstance(mod, FakeModule)
    assert mod is manager.modules['Visualize3D']


@pytest.fixture
def loading_manager():
    """A Manager that runs the real loadModule(). QObject.__init__ is needed so
    sigModulesChanged can be emitted; interfaceDir and the module class registry
    are the only other things loadModule touches."""
    man = Manager.__new__(Manager)
    Qt.QObject.__init__(man)
    man.modules = {}
    man.definedModules = {}
    man.moduleLock = Mutex(recursive=True)
    man.listInterfaces = lambda *args, **kwds: {}
    return man


class ModuleShaped:
    """Matches the modclass(manager, name, config) constructor signature."""

    def __init__(self, manager, name, config):
        self.name = name

    def window(self):
        return None


def test_loadModule_drops_its_reservation_when_construction_fails(loading_manager, monkeypatch):
    """loadModule reserves self.modules[name] = None before constructing. If the
    constructor raises, that None must not be left behind: every later
    getOrLoadModule() would hand it out as if the module were loaded, turning one
    failed load into a permanent, silent None."""

    class FailingModule:
        def __init__(self, manager, name, config):
            raise RuntimeError("constructor exploded")

    monkeypatch.setattr(module_registry, "getModuleClass", lambda name: FailingModule)

    with pytest.raises(RuntimeError, match="constructor exploded"):
        loading_manager.loadModule('Visualize3D')

    assert 'Visualize3D' not in loading_manager.modules


def test_loadModule_reservation_drop_allows_a_later_retry(loading_manager, monkeypatch):
    """After a failed load the name must be free for a later successful load,
    rather than raising NameError('already in use')."""

    class FailingModule:
        def __init__(self, manager, name, config):
            raise RuntimeError("constructor exploded")

    monkeypatch.setattr(module_registry, "getModuleClass", lambda name: FailingModule)
    with pytest.raises(RuntimeError):
        loading_manager.loadModule('Visualize3D')

    monkeypatch.setattr(module_registry, "getModuleClass", lambda name: ModuleShaped)
    mod = loading_manager.loadModule('Visualize3D')

    assert mod is loading_manager.modules['Visualize3D']


def test_getModule_returns_freshly_loaded_defined_module(manager):
    manager.definedModules['Visualize3D'] = {'module': 'Visualize3D'}

    assert manager.getModule('Visualize3D') is manager.modules['Visualize3D']


def test_getModule_survives_a_renamed_module(manager):
    """loadModule() picks a different name when the requested one collides, so
    the loaded module is not necessarily filed under the name asked for. Return
    what was loaded rather than indexing by the requested name."""
    manager.definedModules['Visualize3D'] = {'module': 'Visualize3D'}
    manager.loadModule = lambda moduleClassName, name=None, config=None, **kwds: (
        manager.modules.setdefault('Visualize3D_0', FakeModule('Visualize3D_0'))
    )

    mod = manager.getModule('Visualize3D')

    assert mod is manager.modules['Visualize3D_0']
