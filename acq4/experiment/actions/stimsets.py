"""Stimset actions: run one MIES stimset, or a chain of them, on this pipette's clamp
through StimsetRunner, storing into the current data directory and the cell's notebook."""

from __future__ import annotations

import contextlib
import threading
from pathlib import Path

from acq4.util.allen_stimsets.notebook import Notebook
from acq4.util.task import check_stop

from ..exceptions import OrchestrationError

NOTEBOOK_FILENAME = "notebook.json"

# Time allowed for a stopped runner to finish its sweep teardown before the action re-raises.
_STOP_TIMEOUT = 30.0


def cell_notebook(ctx):
    """Return this cell's stimset Notebook, creating it on first use.

    Kept on ``ctx.stimset_notebook``. Created in the current data directory (the cell's,
    at the start of a protocol) as ``notebook.json``, loading the file if it exists, so a
    retried cell continues the same notebook.
    """
    if ctx.stimset_notebook is None:
        cellDir = Path(ctx.manager.getCurrentDir().name())
        ctx.stimset_notebook = Notebook(cellDir / NOTEBOOK_FILENAME)
    return ctx.stimset_notebook


def _loadStimsets(source):
    """Stimset definitions from *source* (a MIES NWB path), or the production set if None."""
    from acq4.util.allen_stimsets import stimset

    if source is None:
        return stimset.loadProductionStimsets()
    return stimset.loadStimsets(source)


def _newRunner(ctx, source, test_pulse, param_overrides, functions=None):
    """Build a StimsetRunner on this pipette's clamp, storing in the current data directory."""
    # Deferred: the runner imports device and Qt code that acq4.experiment does not need.
    from acq4.util.allen_stimsets.runner import StimsetRunner

    return StimsetRunner(
        ctx.pipette.clampDevice,
        _loadStimsets(source),
        cell_notebook(ctx),
        ctx.manager.getCurrentDir(),
        testPulse=test_pulse,
        paramOverrides=param_overrides,
        manager=ctx.manager,
        functions=functions,
    )


def _runUntilDone(ctx, runner, fn, poll_interval=0.1):
    """Call *fn* on a worker thread and return its result, polling for stop and next cell.

    On Stopped or a flow signal, calls ``runner.stop()``, waits up to _STOP_TIMEOUT for
    *fn* to return, then re-raises. Re-raises any exception *fn* raised.
    """
    done = threading.Event()
    outcome = {}

    def target():
        try:
            outcome["result"] = fn()
        except BaseException as exc:
            outcome["error"] = exc
        finally:
            done.set()

    threading.Thread(target=target, name="StimsetRunner", daemon=True).start()
    try:
        while not done.wait(poll_interval):
            check_stop()
            if ctx.next_cell_requested():
                ctx.next_cell()
    except BaseException:
        runner.stop()
        if not done.wait(_STOP_TIMEOUT):
            ctx.log(f"stimset runner still running {_STOP_TIMEOUT:.0f} s after stop")
        raise
    if "error" in outcome:
        raise outcome["error"]
    return outcome["result"]


@contextlib.contextmanager
def _heldPressure(ctx, pressure):
    """Hold *pressure* (Pa) from the regulator, then restore the previous source and value.

    No-op for None. Raises OrchestrationError if the pipette has no pressure device.
    """
    if pressure is None:
        yield
        return
    dev = ctx.pipette.pressureDevice
    if dev is None:
        raise OrchestrationError(
            f"pressure was requested but {ctx.pipette.name()} has no pressureDevice"
        )
    source, previous = dev.getSource(), dev.getPressure()
    dev.setPressure(source="regulator", pressure=pressure)
    try:
        yield
    finally:
        dev.setPressure(source=source, pressure=previous)


def _resultLines(name, result) -> list[str]:
    lines = [f"{name}: {'passed' if result.passed else 'FAILED'}"]
    lines += [f"  {key}: {value}" for key, value in result.values.items()]
    return lines


def _saveNotebook(ctx) -> None:
    cell_notebook(ctx).save()


def run_stimset(
    ctx,
    name: str,
    source=None,
    test_pulse=None,
    param_overrides: dict | None = None,
    pressure: float | None = None,
    pausable: bool = False,
    clamp_mode: str | None = None,
):
    """Run one stimset with its analysis function and return its SetResult.

    Blocks until the set ends. A failed set is returned, not raised; the caller decides.
    Stopping the run or requesting the next cell stops the runner first.

    Parameters
    ----------
    name : str
        Stimset name, e.g. ``'EXTPBREAKN180424_DA_0'``.
    source : str or Path, optional
        MIES NWB to read stimsets from; default the production stimsets.
    test_pulse : TestPulseSettings, optional
        Inserted test pulse; default the runner's.
    param_overrides : dict, optional
        ``{stimset name: {analysis parameter: value}}``.
    pressure : float, optional
        Pressure (Pa) held from the regulator during the set, then restored.
    pausable : bool
        Honor a pause request before starting. Default False: most stimsets run with the
        tip on a cell.
    clamp_mode : str, optional
        'VC' or 'IC': play the stimset as a plain recording in this mode instead of with an
        analysis function. Required for stimsets without one (e.g. EXTPEXPEND).
    """
    with ctx.log_action(f"Stimset {name}", pausable=pausable) as action_entry:
        action_entry.set_status(f"running {name}")
        functions = None
        if clamp_mode is not None:
            from acq4.util.allen_stimsets.functions.plain import plainRecording

            functions = {name: plainRecording(clamp_mode)}
        runner = _newRunner(ctx, source, test_pulse, param_overrides, functions)
        try:
            with _heldPressure(ctx, pressure):
                result = _runUntilDone(ctx, runner, lambda: runner.runSet(name))
        finally:
            _saveNotebook(ctx)
        lines = _resultLines(name, result)
        action_entry.set_status(lines[0])
        action_entry.set_details("text", {"lines": lines})
        ctx.log(lines[0])
        return result


def run_stimset_chain(
    ctx,
    start: str,
    end: str | None = None,
    source=None,
    test_pulse=None,
    param_overrides: dict | None = None,
    pausable: bool = False,
    then: list[tuple[str, str | None]] = (),
):
    """Run stimsets from *start* through *end* and return ``[(name, SetResult), ...]``.

    Chaining and where the chain stops are StimsetRunner.runChain's; results are in run
    order. *then* lists further ``(start, end)`` chains run afterwards in the same run, so
    run-scope amplifier settings (VM's autobias target) carry into them; a failed chain does not
    skip them. Other behavior and parameters as for run_stimset(), without `pressure`.
    """
    chains = [(start, end), *then]
    title = " ; ".join(f"{s} -> {e}" if e is not None else f"from {s}" for s, e in chains)
    title = f"Stimsets {title}"
    with ctx.log_action(title, pausable=pausable) as action_entry:
        action_entry.set_status(f"running from {start}")
        runner = _newRunner(ctx, source, test_pulse, param_overrides)
        try:
            results = _runUntilDone(ctx, runner, lambda: runner.runChains(chains))
        finally:
            _saveNotebook(ctx)
        lines = []
        for setName, result in results:
            lines += _resultLines(setName, result)
        passed = sum(1 for _, r in results if r.passed)
        summary = f"{passed}/{len(results)} sets passed"
        action_entry.set_status(summary)
        action_entry.set_details("text", {"lines": [summary] + lines})
        ctx.log(f"{title}: {summary}")
        return results
