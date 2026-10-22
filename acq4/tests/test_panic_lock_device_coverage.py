"""Panic Lock coverage for devices that sit outside the guarded class hierarchies.

Companion to ``test_panic_lock_guards.py``, which exercises the guards through the
base classes that carry them. This file covers the opposite hazard: a device that
*claims* a guarded role -- by declaring the interface, by reimplementing the role
in a parallel class, or by overriding the guarded chokepoint -- without inheriting
the behaviour that makes the role safe. A guard placed at a "single chokepoint"
does not reach such a device at all (see "Panic Lock Spec.md" §12 item 9).

``TestRoleCoverageContract`` is the general net. It reads the device source tree
rather than a list written down here, so a device added later with any of those
three shapes fails here by name. The remaining classes are the behavioural tests
for the devices that shape found.

No hardware. ``serial`` is an optional dependency (pyproject extras
``scientifica`` and ``thorlabs``), so the two serial devices skip where it is
absent; the source-level contract test needs no imports and always runs.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import numpy as np
import pytest

import acq4.devices
from acq4.devices.PressureControl import PressureControl
from acq4.panic import GlobalHalt, GlobalHaltException

TIMEOUT = 5.0


# ---------------------------------------------------------------------------
# §6.3 role coverage -- a source-level contract over acq4/devices
# ---------------------------------------------------------------------------

#: Base classes that carry a role's Panic Lock behaviour, by fully qualified name.
GUARDED_BASES = {
    "acq4.devices.Stage.Stage.Stage",
    "acq4.devices.PressureControl.device.PressureControl",
    "acq4.devices.FilterWheel.filterwheel.FilterWheel",
    "acq4.devices.Laser.Laser.Laser",
    "acq4.devices.Scanner.Scanner.Scanner",
}

#: declareInterface() roles whose §6.1 table has at least one Raise row. A device
#: that advertises one of these is promising the rig it behaves like that class.
GUARDED_INTERFACE_ROLES = {
    "stage": "acq4.devices.Stage.Stage.Stage",
    "laser": "acq4.devices.Laser.Laser.Laser",
    "scanner": "acq4.devices.Scanner.Scanner.Scanner",
}

#: The guarded chokepoints of each base (§6.2). A subclass that redefines one of
#: these takes the guard with it and must put it back.
GUARDED_CHOKEPOINTS = {
    "acq4.devices.Stage.Stage.Stage": ("move", "setVelocity"),
    "acq4.devices.PressureControl.device.PressureControl": ("setPressure", "rampPressure"),
    "acq4.devices.FilterWheel.filterwheel.FilterWheel": ("setPosition",),
    "acq4.devices.Laser.Laser.Laser": ("setChanHolding",),
    "acq4.devices.Scanner.Scanner.Scanner": ("setShutterOpen", "_setVoltage"),
}

_DEVICES_ROOT = Path(acq4.devices.__file__).parent
_PACKAGE_ROOT = _DEVICES_ROOT.parent.parent


class _ClassInfo:
    """One class definition found in the device tree, with the text of its body."""

    def __init__(self, module, name, bases, source, methods, roles):
        self.module = module
        self.name = name
        self.bases = bases  # [(localName, moduleItWasImportedFrom or None), ...]
        self.source = source
        self.methods = methods  # {name: source}
        self.roles = roles  # set of declareInterface role strings

    @property
    def qualname(self):
        return f"{self.module}.{self.name}"

    def __repr__(self):
        return f"<{self.qualname}>"


def _absoluteImport(module, node):
    """Resolve the module an ImportFrom node names, relative imports included."""
    if not node.level:
        return node.module
    parts = module.split(".")[:-node.level]
    return ".".join(parts + ([node.module] if node.module else []))


def _declaredRoles(node):
    """The declareInterface() role strings appearing anywhere inside *node*."""
    roles = set()
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name != "declareInterface":
            continue
        for arg in sub.args:
            if isinstance(arg, (ast.List, ast.Tuple)):
                roles.update(e.value for e in arg.elts if isinstance(e, ast.Constant))
    return roles


def _scanDeviceClasses():
    """Every top-level class defined under acq4/devices, indexed two ways.

    Static analysis, deliberately: most device modules import a hardware driver
    at module scope and cannot be imported on a machine without that hardware's
    library. Reading the source is the only way this contract can cover the whole
    tree rather than the handful of devices a test rig can build.
    """
    index = {}
    byName = {}
    for path in sorted(_DEVICES_ROOT.rglob("*.py")):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:  # a module for a Python we are not running
            continue
        module = ".".join(path.relative_to(_PACKAGE_ROOT).with_suffix("").parts)
        imports = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                src = _absoluteImport(module, node)
                for alias in node.names:
                    imports[alias.asname or alias.name] = src
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            bases = []
            for base in node.bases:
                localName = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", None)
                if localName is not None:
                    bases.append((localName, imports.get(localName)))
            methods = {
                b.name: ast.get_source_segment(text, b)
                for b in node.body
                if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            info = _ClassInfo(
                module=module,
                name=node.name,
                bases=bases,
                source=ast.get_source_segment(text, node) or "",
                methods=methods,
                roles=_declaredRoles(node),
            )
            index[info.qualname] = info
            byName.setdefault(info.name, []).append(info)
    return index, byName


def _resolveBase(base, byName):
    """Find the _ClassInfo a (localName, importedFrom) base refers to, if any."""
    localName, importedFrom = base
    candidates = byName.get(localName, [])
    if importedFrom is not None:
        # A package re-export ("from acq4.devices.Stage import Stage") names the
        # package, not the defining module, so match on prefix.
        narrowed = [c for c in candidates if c.module == importedFrom or c.module.startswith(importedFrom + ".")]
        if len(narrowed) == 1:
            return narrowed[0]
    return candidates[0] if len(candidates) == 1 else None


def _chain(info, byName):
    """*info* followed by every ancestor of it that lives in the device tree."""
    seen = {info.qualname: info}
    queue = [info]
    while queue:
        cls = queue.pop()
        for base in cls.bases:
            parent = _resolveBase(base, byName)
            if parent is not None and parent.qualname not in seen:
                seen[parent.qualname] = parent
                queue.append(parent)
    return list(seen.values())


def _participation(info, byName):
    """(registersAnAbortCallback, callsGlobalHaltCheck) for *info* or an ancestor."""
    chain = _chain(info, byName)
    return (
        any("add_abort_callback" in c.source for c in chain),
        any("globalHalt.check" in c.source for c in chain),
    )


@pytest.fixture(scope="module")
def deviceClasses():
    return _scanDeviceClasses()


class TestRoleCoverageContract:
    """Every device that claims a guarded role must be inside the interlock.

    All three checks below describe the same defect: a class takes on a role's
    responsibilities without taking on the base class that carries the role's
    safety behaviour, so the guard at the role's single chokepoint never runs for
    it. The checks differ only in how the claim is made -- by declaring the
    interface, by duplicating the class, or by overriding the chokepoint.
    """

    def test_the_scan_found_the_guarded_bases(self, deviceClasses):
        """A typo in a path would otherwise make every check below vacuous."""
        index, _ = deviceClasses
        missing = GUARDED_BASES - set(index)
        assert not missing, f"guarded base classes not found by the scan: {sorted(missing)}"

    def test_devices_declaring_a_guarded_role_participate(self, deviceClasses):
        """A device that says ``declareInterface(name, ['stage'], self)`` is telling
        the rest of ACQ4 it can be driven like a stage. It must then also stop like
        one: register an abort callback (§5.2) and guard its motion (§6.1).
        """
        index, byName = deviceClasses
        failures = {}
        for info in index.values():
            for role in info.roles & set(GUARDED_INTERFACE_ROLES):
                registers, guards = _participation(info, byName)
                if not (registers and guards):
                    failures[info.qualname] = (role, registers, guards)
        assert not failures, (
            "devices declare a guarded interface role without joining the Panic Lock "
            f"(role, registersCallback, hasGuard): {failures}"
        )

    def test_no_parallel_class_reimplements_a_guarded_role(self, deviceClasses):
        """A second class with a guarded base's name is a role implemented twice.

        The duplicate does not inherit the guard, and imports of the two are easy
        to confuse. If one has to exist, it must carry its own registration and
        guard.
        """
        index, byName = deviceClasses
        guardedNames = {index[q].name: q for q in GUARDED_BASES if q in index}
        failures = {}
        for info in index.values():
            if info.qualname in GUARDED_BASES or info.name not in guardedNames:
                continue
            if guardedNames[info.name] in {c.qualname for c in _chain(info, byName)}:
                continue  # a subclass that merely shares the name: already covered
            registers, guards = _participation(info, byName)
            if not (registers and guards):
                failures[info.qualname] = (guardedNames[info.name], registers, guards)
        assert not failures, (
            "classes reimplement a guarded device role without joining the Panic Lock "
            f"(shadowed base, registersCallback, hasGuard): {failures}"
        )

    def test_no_subclass_overrides_a_guarded_chokepoint_bare(self, deviceClasses):
        """An override of a guarded method takes the guard away with it.

        The override must either check the latch itself or delegate to the base
        implementation that does.
        """
        index, byName = deviceClasses
        failures = {}
        for info in index.values():
            ancestors = {c.qualname for c in _chain(info, byName)} - {info.qualname}
            for base in ancestors & set(GUARDED_CHOKEPOINTS):
                for method in GUARDED_CHOKEPOINTS[base]:
                    src = info.methods.get(method)
                    if src is None:
                        continue
                    delegates = f"super().{method}" in src or f"{index[base].name}.{method}" in src
                    if "globalHalt.check" not in src and not delegates:
                        failures[f"{info.qualname}.{method}"] = base
        assert not failures, (
            f"overrides of a guarded chokepoint that neither guard nor delegate: {failures}"
        )


# ---------------------------------------------------------------------------
# Shared stand-ins for the behavioural tests
# ---------------------------------------------------------------------------


class _HaltManager:
    """The slice of the device manager these devices touch, plus a GlobalHalt."""

    def __init__(self):
        self.globalHalt = GlobalHalt()
        self.config = {}
        self.interfaces = []

    def declareInterface(self, name, interfaces, obj):
        self.interfaces.append((name, tuple(interfaces)))

    def listInterfaces(self, typ):
        return []

    def getDevice(self, name):
        raise KeyError(name)

    def readConfigFile(self, filename):
        return {}

    def writeConfigFile(self, data, filename):
        return None

    def appendConfigFile(self, data, filename):
        return None

    def configFileName(self, filename):
        return filename


@pytest.fixture
def manager(qtbot):
    (qtbot,)  # a QApplication must exist for the devices' Qt mutexes and signals
    return _HaltManager()


def registeredNames(manager):
    return {name for name, _ in manager.globalHalt._abortCallbacks}


# ---------------------------------------------------------------------------
# SutterMP285 -- declares itself a stage without being one
# ---------------------------------------------------------------------------


class _FakeMP285Driver:
    """Records the commands that would have gone down the serial port."""

    def __init__(self, port, baud):
        self.port = port
        self.baud = baud
        self.calls = []
        self.pos = np.zeros(3)

    def setSpeed(self, speed, fine=True, timeout=10.0):
        self.calls.append(("setSpeed", speed, fine))

    def setPos(self, pos, block=True, timeout=10.0):
        self.calls.append(("setPos", tuple(pos)))

    def moveBy(self, pos, block=True, timeout=10.0):
        self.calls.append(("moveBy", tuple(pos)))

    def stop(self):
        self.calls.append(("stop",))

    def setLimits(self, limits):
        self.calls.append(("setLimits", tuple(limits)))

    def getPos(self):
        return self.pos

    def getImmediatePos(self):
        return self.pos

    def close(self):
        self.calls.append(("close",))


@pytest.fixture
def sutter(manager, monkeypatch):
    pytest.importorskip("serial", reason="pyserial is an optional dependency (extras: scientifica)")
    # import_module, not "import ... as": the package re-exports the class under the
    # same name as the module, so the attribute lookup lands on the class.
    module = importlib.import_module("acq4.devices.SutterMP285.SutterMP285")

    monkeypatch.setattr(module, "SutterMP285Driver", _FakeMP285Driver)
    dev = module.SutterMP285(manager, {"port": "COM3", "baud": 9600}, "Sutter")
    yield dev
    dev.quit()


class TestSutterMP285Guards:
    """§6.1 Stage rows, applied to the class that declares itself a stage."""

    def test_it_registers_an_abort_callback(self, sutter, manager):
        assert "Sutter.abort" in registeredNames(manager)

    def test_quit_unregisters(self, sutter, manager):
        sutter.quit()
        assert "Sutter.abort" not in registeredNames(manager)

    def test_moveTo_raises_before_touching_the_driver(self, sutter, manager):
        manager.globalHalt.halt("test panic")
        sutter.mp285.calls.clear()
        with pytest.raises(GlobalHaltException):
            sutter.moveTo([1e-3, 0, 0])
        assert sutter.mp285.calls == []

    def test_moveBy_raises_before_touching_the_driver(self, sutter, manager):
        manager.globalHalt.halt("test panic")
        sutter.mp285.calls.clear()
        with pytest.raises(GlobalHaltException):
            sutter.moveBy([1e-3, 0, 0])
        assert sutter.mp285.calls == []

    def test_setVelocity_raises_and_leaves_the_request_at_rest(self, sutter, manager):
        manager.globalHalt.halt("test panic")
        with pytest.raises(GlobalHaltException):
            sutter.setVelocity([1e-3, 0, 0])
        assert list(sutter.mThread.velocity) == [0, 0, 0]

    def test_the_joystick_goes_through_the_guard(self, sutter, manager):
        """The velocity controller is the one entry point with no ``move`` in its
        name; the device interface must not reach past the guard to the thread.
        """
        module = importlib.import_module("acq4.devices.SutterMP285.SutterMP285")
        source = inspect.getsource(module.SMP285Interface.joyStateChanged)
        assert "self.dev.setVelocity(" in source

    def test_motion_is_allowed_again_after_resume(self, sutter, manager):
        manager.globalHalt.halt("test panic")
        with pytest.raises(GlobalHaltException):
            sutter.moveTo([1e-3, 0, 0])
        manager.globalHalt.resume()
        sutter.moveTo([1e-3, 0, 0])
        assert ("setPos", (1e-3, 0, 0)) in sutter.mp285.calls

    def test_abortForHalt_stops_the_hardware_and_clears_the_velocity_request(self, sutter):
        sutter.setVelocity([1e-3, 0, 0])
        assert list(sutter.mThread.velocity) == [1e-3, 0, 0]
        sutter.mp285.calls.clear()

        sutter.abortForHalt()

        assert ("stop",) in sutter.mp285.calls
        assert list(sutter.mThread.velocity) == [0, 0, 0]

    def test_abortForHalt_completes_while_halted(self, sutter, manager):
        """§6.3: the halt path may only use operations §6.1 lists as Allowed."""
        sutter.setVelocity([1e-3, 0, 0])
        manager.globalHalt.halt("test panic")
        sutter.abortForHalt()  # must not raise
        assert ("stop",) in sutter.mp285.calls



# ---------------------------------------------------------------------------
# ThorlabsFilterWheel -- a parallel FilterWheel class
# ---------------------------------------------------------------------------


class _FakeThorlabsDriver:
    """Stand-in for FilterWheelDriver; the FW102C has no stop command."""

    def __init__(self, port, baud=115200):
        self.port = port
        self.baud = baud
        self.pos = 1
        self.calls = []

    def getPos(self):
        return self.pos

    def setPos(self, newPos):
        self.calls.append(("setPos", int(newPos)))
        self.pos = int(newPos)

    def getPosCount(self):
        return 3

    def getSpeed(self):
        return 1

    def setSpeed(self, speed):
        self.calls.append(("setSpeed", speed))

    def getTriggerMode(self):
        return 0

    def getSensorMode(self):
        return 0

    def close(self):
        self.calls.append(("close",))


@pytest.fixture
def thorlabsWheel(manager, monkeypatch):
    pytest.importorskip("serial", reason="pyserial is an optional dependency (extras: thorlabs)")
    module = importlib.import_module("acq4.devices.ThorlabsFilterWheel.FilterWheel")

    monkeypatch.setattr(module, "FilterWheelDriver", _FakeThorlabsDriver)
    # The poll thread only reads position; leave it out so the test drives the device.
    monkeypatch.setattr(module.FilterWheelThread, "start", lambda self: None)
    config = {
        "port": "COM4",
        "filters": {"0": {"name": "green", "description": "ET535/70m"}},
    }
    dev = module.FilterWheel(manager, config, "ThorWheel")
    yield dev
    dev.quit()


class TestThorlabsFilterWheelGuards:
    """§6.1 FilterWheel rows, applied to the Thorlabs class."""

    def test_it_registers_an_abort_callback(self, thorlabsWheel, manager):
        assert "ThorWheel.abort" in registeredNames(manager)

    def test_quit_unregisters(self, thorlabsWheel, manager):
        thorlabsWheel.quit()
        assert "ThorWheel.abort" not in registeredNames(manager)

    def test_starting_a_filter_move_raises_before_touching_the_driver(self, thorlabsWheel, manager):
        manager.globalHalt.halt("test panic")
        thorlabsWheel.driver.calls.clear()
        with pytest.raises(GlobalHaltException):
            thorlabsWheel.setPosition(2)
        assert thorlabsWheel.driver.calls == []
        assert thorlabsWheel.getPosition() == 1

    def test_a_filter_move_is_allowed_again_after_resume(self, thorlabsWheel, manager):
        manager.globalHalt.halt("test panic")
        with pytest.raises(GlobalHaltException):
            thorlabsWheel.setPosition(2)
        manager.globalHalt.resume()
        thorlabsWheel.setPosition(2)
        assert thorlabsWheel.getPosition() == 2

    def test_abort_completes_while_halted(self, thorlabsWheel, manager):
        """§6.3: stop() is Allowed, so the callback cannot trip its own guard."""
        manager.globalHalt.halt("test panic")
        thorlabsWheel.abort()  # must not raise


# ---------------------------------------------------------------------------
# PressureControl -- the guard must survive being subclassed
# ---------------------------------------------------------------------------


class _SingleCallPressureControl(PressureControl):
    """A PressureControl whose hardware sets source and pressure in one call.

    This is the shape of ``MIESPressureControl``: the bridge sets both at once, so
    the base class's ``_setSource()``/``_setPressure()`` split does not fit and the
    subclass overrides ``_applyPressure()`` instead. Everything ``setPressure()``
    owns -- validation, the directional guard, the change signal -- must still
    apply, which is the whole point of the seam being below the guard.
    """

    def __init__(self, manager, config, name):
        self.applied = []
        PressureControl.__init__(self, manager, config, name)
        self.source = 'atmosphere'
        self.pressure = 0

    def _applyPressure(self, source, pressure):
        self.applied.append((source, pressure))
        if source is not None:
            self.source = source
        if pressure is not None:
            self.pressure = pressure

    def getPressure(self):
        return self.pressure

    def getSource(self):
        return self.source


@pytest.fixture
def singleCallPressure(manager):
    dev = _SingleCallPressureControl(manager, {}, "Pressure")
    yield dev
    dev.quit()


class TestPressureControlSubclassGuard:
    def test_pressurising_raises_and_never_reaches_the_subclass(self, singleCallPressure, manager):
        manager.globalHalt.halt("test panic")
        singleCallPressure.applied.clear()
        with pytest.raises(GlobalHaltException):
            singleCallPressure.setPressure(source="regulator", pressure=20e3)
        assert singleCallPressure.applied == []
        assert singleCallPressure.source == "atmosphere"

    def test_venting_stays_allowed(self, singleCallPressure, manager):
        singleCallPressure.setPressure(source="regulator", pressure=20e3)
        manager.globalHalt.halt("test panic")
        singleCallPressure.setPressure(source="atmosphere", pressure=0)
        assert singleCallPressure.source == "atmosphere"

    def test_an_invalid_source_is_still_rejected(self, singleCallPressure):
        with pytest.raises(ValueError):
            singleCallPressure.setPressure(source="nonsense")
        assert singleCallPressure.applied == []

    def test_the_change_signal_still_fires(self, singleCallPressure, qtbot):
        with qtbot.waitSignal(singleCallPressure.sigPressureChanged, timeout=int(TIMEOUT * 1000)):
            singleCallPressure.setPressure(source="regulator", pressure=10e3)
