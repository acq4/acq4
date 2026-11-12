"""Apply AmplifierSettings to a PatchClamp device and restore them afterwards."""

from __future__ import annotations

import dataclasses
import itertools
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .core import AmplifierSettings, ClampMode, TestPulseSettings, siPerMiesUnit

logger = logging.getLogger(__name__)

# AmplifierSettings field -> (MCC parameter, SI per MIES unit). MCC parameters apply to the current mode.
_MCC_PARAMS = {
    'bridgeBalanceEnabled': ('BridgeBalEnable', None),
    'bridgeBalance': ('BridgeBalResist', 1e6),  # MOhm
    'capNeutralizationEnabled': ('NeutralizationEnable', None),
    'capNeutralization': ('NeutralizationCap', 1e-12),  # pF
    'besselFilter': ('PrimarySignalLPF', 1.0),  # Hz
}
_IC_ONLY = {'BridgeBalEnable', 'BridgeBalResist', 'NeutralizationEnable', 'NeutralizationCap'}


@dataclass
class _Entry:
    kind: str  # 'mcc' | 'holding' | 'autobiasEnabled' | 'autobiasTarget'
    name: str  # MCC parameter, or the kind
    mode: Optional[str]  # clamp mode the value belongs to; None if mode-independent
    value: Any  # original value, SI
    order: int = field(default_factory=lambda: next(_order))


_order = itertools.count()  # orders scope entries against auto calibrations


class AmplifierScope:
    """Original values of the settings changed within one scope (a set or a run).

    The first change of a setting records its original; later changes of the same setting do not.
    """

    def __init__(self, label: str):
        self.label = label
        self.entries: list[_Entry] = []
        self.changes: list[dict] = []  # applied changes, for storage

    def remember(self, kind: str, name: str, mode: Optional[str], value: Any) -> None:
        if not any(e.kind == kind and e.name == name and e.mode == mode for e in self.entries):
            self.entries.append(_Entry(kind, name, mode, value))

    def __bool__(self) -> bool:
        return bool(self.entries)


class AmplifierControl:
    """Reads and changes the amplifier and clamp-device settings named in AmplifierSettings.

    MCC parameters go through ``clamp.getParam``/``setParam`` (MultiClamp); clamps without them raise
    NotImplementedError for those settings. Holding is ACQ4's holding command (``getHolding``/
    ``setHolding``), which ACQ4 autobias adjusts; changing autobias also records the IC holding for
    restore. Every method may block on MCC calls and device reservations; call from the runner thread.
    """

    def __init__(self, clamp, log: Optional[logging.Logger] = None):
        self.clamp = clamp
        self.log = log or logger
        self._calibrated: dict[tuple[str, str], int] = {}  # (MCC parameter, mode) -> order

    def holding(self, mode: ClampMode) -> float:
        """Return the holding command of *mode* in MIES units (mV VC, pA IC)."""
        return self.clamp.getHolding(mode) / siPerMiesUnit(mode, 'command')

    def autobiasTarget(self) -> Optional[float]:
        """Return the autobias target in mV, also while autobias is off (MIES reads the panel value)."""
        target = self.clamp.autoBiasTarget()
        return None if target is None else target * 1e3

    def apply(self, settings: AmplifierSettings, mode: ClampMode, scope: AmplifierScope) -> None:
        """Apply *settings* with the clamp in *mode*, recording originals in *scope* before each change.

        Auto calibrations (``'auto'`` pipette offset and bridge balance) are not recorded: they are kept.
        Raises RuntimeError if the clamp is not in *mode*, ValueError for settings that do not exist in
        *mode* or that conflict.
        """
        changes = settings.changes()
        if not changes:
            return
        current = self.clamp.getMode()
        if current != mode:
            raise RuntimeError(
                f"amplifier settings for {mode} requested while the clamp is in {current}"
            )
        if mode != 'IC':
            for name in changes:
                if name in _MCC_PARAMS and _MCC_PARAMS[name][0] in _IC_ONLY:
                    raise ValueError(f"{name} exists only in IC, not {mode}")

        if settings.holdingEnabled is False and settings.holding is not None:
            raise ValueError("holdingEnabled=False conflicts with a holding value")
        if settings.holdingEnabled is False:
            if self.clamp.getParam('HoldingEnable'):
                self._setMcc('HoldingEnable', False, mode, scope)
            self._setHolding(mode, 0.0, scope)
        elif settings.holdingEnabled is True:
            self.log.info("holdingEnabled=True: ACQ4 holding always applies; nothing to change")
        if settings.holding is not None:
            self._setHolding(mode, settings.holding * siPerMiesUnit(mode, 'command'), scope)

        for name, (param, scale) in _MCC_PARAMS.items():
            value = changes.get(name)
            if value is None or value == 'auto':
                continue
            self._setMcc(param, value if scale is None else value * scale, mode, scope)

        if settings.pipetteOffset == 'auto':
            self._runAuto('PipetteOffset', self.clamp.autoPipetteOffset, mode, scope)
        if settings.bridgeBalance == 'auto':
            self._runAuto('BridgeBalResist', self.clamp.autoBridgeBalance, mode, scope)

        if settings.autobiasTarget is not None or settings.autobiasEnabled is not None:
            # autobias moves the IC holding; restore it with the autobias settings
            scope.remember('holding', 'holding', 'IC', self.clamp.getHolding('IC'))
        if settings.autobiasTarget is not None:
            before = self.clamp.autoBiasTarget()
            scope.remember('autobiasTarget', 'autobiasTarget', None, before)
            self.clamp.setAutoBiasTarget(settings.autobiasTarget * 1e-3)
            self._logChange(scope, 'autobiasTarget', None, before, settings.autobiasTarget * 1e-3)
        if settings.autobiasEnabled is not None:
            before = self.clamp.autoBiasEnabled()
            scope.remember('autobiasEnabled', 'autobiasEnabled', None, before)
            self.clamp.enableAutoBias(settings.autobiasEnabled)
            self._logChange(scope, 'autobiasEnabled', None, before, settings.autobiasEnabled)

    def restore(self, scope: AmplifierScope) -> None:
        """Restore every setting in *scope* to its original, newest change first, then empty *scope*.

        A parameter auto-calibrated (pipette offset, bridge balance) after its entry was recorded keeps
        the calibrated value. MCC parameters of another mode are restored by switching to that mode and
        back. Each restore is logged; a failed restore is logged and the rest still run, then the first
        error is raised.
        """
        errors = []
        for entry in reversed(scope.entries):
            if self._calibrated.get((entry.name, entry.mode), -1) > entry.order:
                self.log.info(f"{scope.label}: kept auto-calibrated {entry.name} ({entry.mode})")
                continue
            try:
                self._restoreEntry(entry, scope.label)
            except Exception as exc:
                self.log.exception(
                    f"{scope.label}: failed to restore {entry.name} ({entry.mode}) to {entry.value!r}"
                )
                errors.append(exc)
        scope.entries.clear()
        if errors:
            raise errors[0]

    def _restoreEntry(self, entry: _Entry, label: str) -> None:
        if entry.kind == 'holding':
            before = self.clamp.getHolding(entry.mode)
            self.clamp.setHolding(entry.mode, entry.value)
        elif entry.kind == 'autobiasTarget':
            before = self.clamp.autoBiasTarget()
            self.clamp.setAutoBiasTarget(entry.value)
        elif entry.kind == 'autobiasEnabled':
            before = self.clamp.autoBiasEnabled()
            self.clamp.enableAutoBias(entry.value)
        else:
            current = self.clamp.getMode()
            if current != entry.mode:
                self.clamp.setMode(entry.mode)
            try:
                before = self.clamp.getParam(entry.name)
                self.clamp.setParam(entry.name, entry.value)
            finally:
                if current != entry.mode:
                    self.clamp.setMode(current)
        self.log.info(
            f"{label}: restored {entry.name} ({entry.mode}): {before!r} -> {entry.value!r}"
        )

    def _setMcc(self, param: str, value, mode: str, scope: AmplifierScope) -> None:
        before = self.clamp.getParam(param)
        scope.remember('mcc', param, mode, before)
        self.clamp.setParam(param, value)
        self._logChange(scope, param, mode, before, value)

    def _setHolding(self, mode: str, value: float, scope: AmplifierScope) -> None:
        before = self.clamp.getHolding(mode)
        scope.remember('holding', 'holding', mode, before)
        self.clamp.setHolding(mode, value)
        self._logChange(scope, 'holding', mode, before, value)

    def _runAuto(self, param: str, fn, mode: str, scope: AmplifierScope) -> None:
        before = self.clamp.getParam(param)
        fn()
        self._calibrated[(param, mode)] = next(_order)
        self._logChange(scope, param, mode, before, self.clamp.getParam(param), auto=True)

    def _logChange(self, scope: AmplifierScope, name, mode, before, after, auto=False) -> None:
        scope.changes.append(
            {'name': name, 'mode': mode, 'before': before, 'after': after, 'auto': auto}
        )
        how = 'auto-set' if auto else 'set'
        self.log.info(f"{scope.label}: {how} {name} ({mode}): {before!r} -> {after!r}")


def commandLimit(clamp, mode: ClampMode, manager) -> float:
    """Return the largest |command| the clamp's DA channel can output in *mode*, MIES units.

    Uses the DAQ's AO range and the MultiClamp external command sensitivity; inf for clamps that
    report no sensitivity.
    """
    if not hasattr(clamp, 'extCmdScale'):
        return float('inf')
    daq = manager.getDevice(clamp.getDAQName('command'))
    return (
        max(abs(v) for v in daq._defaultAORange)
        * clamp.extCmdScale(mode)
        / siPerMiesUnit(mode, 'command')
    )


# MIES DAEphys defaults: 10 ms pulse, 35 % baseline, 10 mV VC, -50 pA IC.
DEFAULT_TEST_PULSE = TestPulseSettings(
    pulseDuration=10.0, baselineFraction=0.35, amplitudeVC=10.0, amplitudeIC=-50.0
)


def testPulseFromClamp(clamp) -> tuple[TestPulseSettings, dict[str, str]]:
    """Return the inserted-TP settings taken from *clamp*'s test pulse, and each field's source.

    Durations come from the VC test pulse; the baseline fraction only when its pre and post durations
    are equal. A field the clamp cannot supply is taken from DEFAULT_TEST_PULSE. Sources are
    'clamp:<parameter>' or 'default'.
    """

    getter = getattr(clamp, 'getTestPulseParameter', None)  # None: clamp has no ACQ4 test pulse

    def param(name):
        if getter is None:
            return None
        try:
            return getter(name)
        except KeyError:
            return None

    values = dataclasses.asdict(DEFAULT_TEST_PULSE)
    sources = dict.fromkeys(values, 'default')
    pulse, pre, post = (param(f'vc{k}Duration') for k in ('Pulse', 'Pre', 'Post'))
    if pulse is not None:
        values['pulseDuration'], sources['pulseDuration'] = pulse * 1e3, 'clamp:vcPulseDuration'
        if pre is not None and post is not None and abs(pre - post) < 1e-9:
            values['baselineFraction'] = pre / (pre + pulse + post)
            sources['baselineFraction'] = 'clamp:vcPreDuration/vcPostDuration'
    for field_, name, scale in [
        ('amplitudeVC', 'vcAmplitude', 1e3),
        ('amplitudeIC', 'icAmplitude', 1e12),
    ]:
        v = param(name)
        if v is not None:
            values[field_], sources[field_] = v * scale, f'clamp:{name}'
    return TestPulseSettings(**values), sources
