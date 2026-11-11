"""Tests for loading and listing the bundled example Autopatch protocols.

Each bundled .py file must load through ProtocolFile and run through the
Orchestrator. The picker lists them in place from the package, never copied into
a rig's config directory, and an operator's own file of the same name shadows one.

Do not test what an example *does*. The examples are templates an operator copies
and rewrites; which actions one calls, in what order, and with which params is an
illustration, not a contract, and pinning it only means every edit to an example
also edits a test that asserts the example is what it is. Test the actions those
examples call, where the behavior actually lives."""
from __future__ import annotations

import importlib
import os
from unittest.mock import MagicMock

import pytest

import acq4.modules.Autopatch.example_protocols as example_protocols_pkg
import acq4.modules.Autopatch.example_protocols.example_patch_seq as example_patch_seq_mod
from acq4.devices.InteractionSiteArray import InteractionSiteArray
from acq4.devices.MockStage import MockStage
from acq4.devices.Pipette.pipette import Pipette
from acq4.experiment.actions import fsm as fsm_mod
from acq4.experiment.actions import sites as sites_mod
from acq4.experiment.actions.sites import build_tube_report
from acq4.experiment.exceptions import AbortExperiment
from acq4.experiment.tube_ids import generate_tube_ids, write_tube_count
from acq4.experiment.context import ExecutionContext
from acq4.experiment.orchestrator import Orchestrator
from acq4.experiment.protocol_directory import ProtocolDirectory
from acq4.experiment.protocol_file import ProtocolFile
from acq4.modules.Autopatch.example_protocols import EXAMPLE_PROTOCOLS_DIR
import acq4.util.DataManager as dm
from acq4.util import Qt

from .fakes import fakeModule

_EXAMPLES_DIR = os.path.dirname(example_protocols_pkg.__file__)

# The `actions` package re-exports `prompt` (the function) under the same name
# as the `prompt` submodule, so `acq4.experiment.actions.prompt` no longer
# resolves to the module via attribute access; go through sys.modules (via
# import_module) to reach the real submodule for monkeypatching.
_prompt_mod = importlib.import_module("acq4.experiment.actions.prompt")


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


@pytest.mark.parametrize(
    "filename",
    [
        "example_prompt.py",
        "example_patch.py",
        "example_patch_seq.py",
        "example_adaptive_seal.py",
    ],
)
def test_bundled_example_loads_through_protocol_file(filename):
    pf = ProtocolFile(os.path.join(_EXAMPLES_DIR, filename))
    pf.load()
    assert pf.is_loaded is True
    assert pf.load_error is None
    assert callable(pf.run)
    # PARAMS builds a param_tree without raising, for either bundled example's
    # single declared param.
    assert pf.param_tree is not None


def test_example_prompt_exposes_message_param_with_a_default():
    pf = ProtocolFile(os.path.join(_EXAMPLES_DIR, "example_prompt.py"))
    pf.load()
    assert pf.param_values() == {"message": "Ready to patch this cell?"}


@pytest.mark.parametrize(
    "filename",
    [
        "example_prompt.py",
        "example_patch.py",
        "example_patch_seq.py",
        "example_adaptive_seal.py",
    ],
)
def test_bundled_example_declares_a_tip_on_every_param(filename):
    """Bundled examples are the templates operators copy, so every param they
    expose must demonstrate an operator-facing tip -- not just the name."""
    pf = ProtocolFile(os.path.join(_EXAMPLES_DIR, filename))
    pf.load()
    for child in pf.param_tree.children():
        assert child.opts.get("tip"), f"{filename}: {child.name()!r} has no tip"


def test_example_prompt_description_is_populated_from_its_module_docstring():
    """The operator's protocol picker shows ProtocolFile.description, so it
    must actually describe the single-acknowledgement prompt this protocol
    runs -- not some other behavior."""
    pf = ProtocolFile(os.path.join(_EXAMPLES_DIR, "example_prompt.py"))
    pf.load()
    assert pf.description == (
        "Ask the operator to confirm they're ready.\n"
        "Hardware-free demo protocol."
    )


def test_example_protocols_dir_points_at_the_bundled_package_files():
    """The constant names the package directory itself, not a copy of it: the
    picker lists these files where they are, so this path is what "Open in
    editor" opens and what an edit has to land in."""
    assert os.path.isdir(EXAMPLE_PROTOCOLS_DIR)
    assert os.path.samefile(EXAMPLE_PROTOCOLS_DIR, _EXAMPLES_DIR)
    # Every bundled example must itself be a loadable ProtocolFile.
    for name in ("example_prompt.py", "example_patch.py", "example_patch_seq.py"):
        pf = ProtocolFile(os.path.join(EXAMPLE_PROTOCOLS_DIR, name))
        pf.load()
        assert pf.is_loaded is True


def test_examples_are_never_copied_into_the_operators_protocol_dir(tmp_path):
    """The bug this whole arrangement exists to prevent: a second copy of every
    example seeded into a rig's config directory and then left to drift."""
    dest = tmp_path / "autopatch_protocols"
    directory = ProtocolDirectory(str(dest), extra_paths=[EXAMPLE_PROTOCOLS_DIR])
    directory.scan()

    assert set(directory.protocols.keys()) == {
        "example_prompt",
        "example_patch",
        "example_patch_seq",
        "example_adaptive_seal",
    }
    assert not (dest / "example_prompt.py").exists()
    assert not (dest / "example_patch.py").exists()


def test_the_packages_own_init_is_not_listed_as_a_protocol(tmp_path):
    directory = ProtocolDirectory(str(tmp_path), extra_paths=[EXAMPLE_PROTOCOLS_DIR])
    directory.scan()

    assert "__init__" not in directory.protocols


def test_protocol_directory_over_the_examples_dir_lists_exactly_the_two_examples(tmp_path):
    directory = ProtocolDirectory(str(tmp_path), extra_paths=[EXAMPLE_PROTOCOLS_DIR])
    directory.scan()

    assert set(directory.protocols.keys()) == {
        "example_prompt",
        "example_patch",
        "example_patch_seq",
        "example_adaptive_seal",
    }
    assert directory.protocols["example_prompt"].is_loaded is True
    assert directory.protocols["example_patch"].is_loaded is True
    assert directory.protocols["example_patch_seq"].is_loaded is True


def test_an_operators_own_file_shadows_the_bundled_example_of_the_same_name(tmp_path):
    """The escape hatch that replaces "seed once and never overwrite": a file
    of the same name in the operator's own directory wins, and deleting it
    falls back to the bundled example on the next scan."""
    (tmp_path / "example_prompt.py").write_text(
        "PARAMS = []\n\n\ndef run(ctx, **params):\n    return \"mine\"\n"
    )
    directory = ProtocolDirectory(str(tmp_path), extra_paths=[EXAMPLE_PROTOCOLS_DIR])
    directory.scan()

    assert set(directory.protocols.keys()) == {
        "example_prompt",
        "example_patch",
        "example_patch_seq",
        "example_adaptive_seal",
    }
    assert directory.get("example_prompt").path == str(tmp_path / "example_prompt.py")
    # The unshadowed one still comes from the package.
    assert os.path.dirname(directory.get("example_patch").path) == EXAMPLE_PROTOCOLS_DIR

    (tmp_path / "example_prompt.py").unlink()
    directory.scan()

    assert os.path.dirname(directory.get("example_prompt").path) == EXAMPLE_PROTOCOLS_DIR
    assert directory.get("example_prompt").is_loaded is True


def test_example_prompt_runs_end_to_end_and_finishes_the_cell_as_done(tmp_path, monkeypatch):
    """End-to-end demo with the operator simulated: prompt_user is patched to
    return a choice immediately (standing in for the human click) since a
    stray QApplication left behind by another test would otherwise make
    prompt() block forever waiting for a real one. Everything else is real:
    ProtocolFile loading and the orchestrator running the protocol. The
    protocol never advances the queue itself -- run() returning normally is
    what the orchestrator's success path (Orchestrator._processCell's `else`
    branch) reports as "done"."""
    monkeypatch.setattr(_prompt_mod, "prompt_user", lambda title, message, choices: choices[0])

    pf = ProtocolFile(os.path.join(EXAMPLE_PROTOCOLS_DIR, "example_prompt.py"))
    pf.load()

    orch = Orchestrator(pf, contextFactory=lambda cell: ExecutionContext(cell=cell))
    finished = []
    orch.sigCellFinished.connect(lambda cell, status: finished.append((cell, status)))
    orch.run_sync_cell("cell-1")

    assert finished == [("cell-1", "done")]


def test_autopatch_window_init_lists_the_examples_without_copying_them(qapp, tmp_path):
    """AutopatchWindow's own init creates a not-yet-existing protocol dir and
    lists both bundled examples in the picker -- out of the package, leaving
    the rig's own directory empty rather than seeding copies into it."""
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    class _FakeDeviceSelector(Qt.QWidget):
        def getSelectedObj(self):
            return None

    protocolDir = tmp_path / "does_not_exist_yet" / "autopatch_protocols"
    win = AutopatchWindow(
        module=fakeModule(),
        protocolDir=str(protocolDir),
        pipetteSelector=_FakeDeviceSelector(),
        cameraSelector=_FakeDeviceSelector(),
    )

    items = {win.protocolPanel.fileCombo.itemText(i) for i in range(win.protocolPanel.fileCombo.count())}
    assert items == {"example_prompt", "example_patch", "example_patch_seq", "example_adaptive_seal"}
    # The operator's directory was created, but nothing was written into it.
    assert protocolDir.is_dir()
    assert list(protocolDir.iterdir()) == []
    # ...because the listed protocols are the package's own files.
    for name in ("example_prompt", "example_patch", "example_patch_seq"):
        protocol = win.protocolPanel.directory.get(name)
        assert os.path.dirname(protocol.path) == EXAMPLE_PROTOCOLS_DIR


# -- example_patch_seq -------------------------------------------------------


class _SeqPipette(Qt.QObject):
    """The least PatchPipette _drive_fsm needs: it reaches the requested entry
    state and then 'out', which is the only terminal collect declares."""

    sigStateChanged = Qt.Signal(object, object, object)
    sigNewEvent = Qt.Signal(object, object)

    def __init__(self, pipetteDevice):
        super().__init__()
        self.pipetteDevice = pipetteDevice
        self.clampDevice = None
        self.cell = None
        self._current = "out"

    def name(self):
        return "Pipette1"

    def setCell(self, cell, target=True):
        self.cell = cell

    def setState(self, state, **config):
        self._changeState(state)
        self._changeState("out")

    def _changeState(self, state):
        old, self._current = self._current, state
        self.sigStateChanged.emit(self, state, old)

    def getState(self):
        return None


def _rack_pipette(rows=1, cols=4):
    """A real InteractionSiteArray behind a Pipette stub carrying the real
    site-assignment methods, wrapped in the minimal PatchPipette above."""
    storage = {}
    # Populated as devices are built; the array resolves its parentDevice during
    # construction, so getDevice has to be live before that call -- hence a dict
    # the closure reads rather than a side_effect set afterwards.
    devices = {}
    device_manager = MagicMock()
    device_manager.readConfigFile.side_effect = lambda path: storage.get(path, {})
    device_manager.writeConfigFile.side_effect = lambda data, path: storage.update(
        {path: dict(data)}
    )
    device_manager.configFileName.side_effect = lambda path: path
    device_manager.listDevices.return_value = []
    device_manager.listInterfaces.return_value = []
    device_manager.getDevice.side_effect = devices.get

    devices["TestStage"] = stage = MockStage(device_manager, {"nAxes": 3}, "TestStage")
    devices["Rack"] = array = InteractionSiteArray(
        device_manager,
        {
            "rows": rows,
            "cols": cols,
            "siteRadius": 1e-3,
            "siteHeight": 5e-3,
            "parentDevice": "TestStage",
            "role": "nucleus",
        },
        "Rack",
    )

    class _StubPipette:
        def name(self_):
            return "TestPip"

        def configPath(self_):
            return os.path.join("devices", f"{self_.name()}_config")

        def readConfigFile(self_, filename):
            return self_.dm.readConfigFile(os.path.join(self_.configPath(), filename))

        def writeConfigFile(self_, data, filename):
            self_.dm.writeConfigFile(data, os.path.join(self_.configPath(), filename))

    _StubPipette._loadSiteAssignments = Pipette._loadSiteAssignments
    _StubPipette.getSiteFor = Pipette.getSiteFor
    _StubPipette.getSiteDeviceFor = Pipette.getSiteDeviceFor
    _StubPipette.setSiteFor = Pipette.setSiteFor

    pipette_device = _StubPipette()
    pipette_device.dm = device_manager
    pipette_device.config = {}
    pipette_device._site_assignments = {}
    pipette_device._loadSiteAssignments()
    pipette_device.setSiteFor("nucleus", array)

    # The first rack is labelled the way the operator would label it, so the
    # day's tube numbering and the ids on the sites start out consistent.
    ids = generate_tube_ids("T{tube_count}_{well}", rows, cols, 0)
    for index, site in enumerate(array.sites):
        site.tube_id = ids[index]
    write_tube_count(array, len(array.sites))

    return _SeqPipette(pipette_device), array, stage


def _seq_actions(monkeypatch, calls):
    """Stub everything that touches hardware or the FSM, leaving the three
    nucleus actions -- the gate, the swap, and collect -- real."""
    # collect drives the FSM for real, and _drive_fsm would otherwise start a
    # MultiPatchLogWriter against the cell directory. The event log is not what
    # this test is about, and a real one would write files into the tree the
    # report is read back out of.
    monkeypatch.setattr(fsm_mod, "_openWriter", lambda ctx, full: None)
    monkeypatch.setattr(
        example_patch_seq_mod,
        "clean",
        lambda ctx, only_if_needed=True: calls.append("clean"),
    )
    for name in (
        "verify_cell",
        "go_search",
        "find_tip",
        "go_above_target",
        "cellfie",
        "go_approach",
        "go_park",
        "run_task",
        "mark_important",
        "home_with_nucleus",
    ):
        monkeypatch.setattr(
            example_patch_seq_mod, name, lambda ctx, _n=name: calls.append(_n)
        )
    monkeypatch.setattr(
        example_patch_seq_mod, "load_preset", lambda ctx, preset: calls.append("preset")
    )
    monkeypatch.setattr(
        example_patch_seq_mod,
        "sonicate",
        lambda ctx, protocol, pressure=None, settle=0.0: calls.append("sonicate"),
    )
    monkeypatch.setattr(
        example_patch_seq_mod, "snap", lambda ctx, name="image": calls.append(("snap", name))
    )
    monkeypatch.setattr(
        example_patch_seq_mod, "prompt", lambda ctx, message: calls.append("prompt")
    )
    monkeypatch.setattr(example_patch_seq_mod, "patch", lambda ctx: "whole cell")
    monkeypatch.setattr(example_patch_seq_mod, "reseal", lambda ctx: "outside out")


@pytest.fixture
def seq_day(tmp_path):
    day = dm.getDirHandle(str(tmp_path / "2026.11.02_000"), create=True)
    day.setInfo({"dirType": "Day"})
    slice_dir = day.getDir("Slice_000", create=True)
    slice_dir.setInfo({"dirType": "Slice"})
    return day, slice_dir


def _info_off_disk(cell_dir):
    """The cell's info as a fresh handle reads it, bypassing the handle cache."""
    return dm.getDirHandle(cell_dir.name()).info()


class _SeqManager:
    """Hands out one fresh cell directory per cell, the way the orchestrator
    makes a cell's directory current before the protocol runs."""

    def __init__(self, slice_dir):
        self.slice_dir = slice_dir
        self.current = None
        self.made = 0

    def next_cell(self):
        name = f"Cell_{self.made:03d}"
        self.made += 1
        self.current = self.slice_dir.getDir(name, create=True)
        self.current.setInfo({"dirType": "Cell"})
        return self.current

    def getCurrentDir(self):
        return self.current


def test_example_patch_seq_fills_a_rack_cell_by_cell(qapp, monkeypatch, seq_day):
    """The defect the whole feature exists for: nothing used to set used_up, so
    every nucleus went into tube 0 forever."""
    _, slice_dir = seq_day
    pip, array, stage = _rack_pipette(cols=4)
    try:
        calls = []
        _seq_actions(monkeypatch, calls)
        monkeypatch.setattr(
            sites_mod,
            "prompt_tube_rack",
            lambda title, text, rows, cols, make_ids, start_n, extra_text=None: (
                make_ids(start_n, False),
                start_n,
            ),
        )
        manager = _SeqManager(slice_dir)

        cells = []
        for _ in range(4):
            cell_dir = manager.next_cell()
            cells.append(cell_dir)
            example_patch_seq_mod.run(
                ExecutionContext(pipette=pip, manager=manager),
                tube_id_format="T{tube_count}_{well}",
            )

        assert [c.info()["nucleus_tube_position"] for c in cells] == [
            "A01",
            "A02",
            "A03",
            "A04",
        ]
        assert [c.info()["nucleus_tube_id"] for c in cells] == [
            "T0_A01",
            "T1_A02",
            "T2_A03",
            "T3_A04",
        ]
        # Off disk, not through the handle's cache: what survives the session.
        for index, cell_dir in enumerate(cells):
            on_disk = _info_off_disk(cell_dir)
            assert on_disk["nucleus_tube_position"] == f"A0{index + 1}"
            assert on_disk["nucleus_tube_id"] == f"T{index}_A0{index + 1}"
    finally:
        stage.quit()


def test_example_patch_seq_swaps_the_rack_and_keeps_going(qapp, monkeypatch, seq_day):
    _, slice_dir = seq_day
    pip, array, stage = _rack_pipette(cols=4)
    try:
        calls = []
        _seq_actions(monkeypatch, calls)
        swaps = []

        def fake_prompt(title, text, rows, cols, make_ids, start_n, extra_text=None):
            swaps.append(extra_text)
            return make_ids(start_n, False), start_n

        monkeypatch.setattr(sites_mod, "prompt_tube_rack", fake_prompt)
        manager = _SeqManager(slice_dir)

        cells = []
        for _ in range(5):
            cells.append(manager.next_cell())
            example_patch_seq_mod.run(
                ExecutionContext(pipette=pip, manager=manager),
                tube_id_format="T{tube_count}_{well}",
            )

        # One swap, at the fifth cell -- the gate sits at the top of the
        # protocol, so the operator is called over at the START of the cell that
        # has nowhere to go rather than after the deposit that exhausted the rack.
        assert len(swaps) == 1
        # The fifth cell reuses position A01 of a NEW rack, whose id continues
        # the day's numbering rather than restarting it.
        on_disk = _info_off_disk(cells[4])
        assert on_disk["nucleus_tube_position"] == "A01"
        assert on_disk["nucleus_tube_id"] == "T4_A01"
        # And the report the operator was shown at the swap named the old rack's
        # tubes and the cells in them.
        assert "T0_A01" in swaps[0]
        assert "Slice_000/Cell_000" in swaps[0]
    finally:
        stage.quit()


def test_example_patch_seq_aborts_when_the_operator_cancels_the_swap(
    qapp, monkeypatch, seq_day
):
    """Carrying on would patch a cell with nowhere to put its nucleus."""
    _, slice_dir = seq_day
    pip, array, stage = _rack_pipette(cols=1)
    try:
        calls = []
        _seq_actions(monkeypatch, calls)
        monkeypatch.setattr(
            sites_mod,
            "prompt_tube_rack",
            lambda *a, **k: None,
        )
        manager = _SeqManager(slice_dir)
        for site in array.sites:
            site.used_up = True

        manager.next_cell()
        with pytest.raises(AbortExperiment):
            example_patch_seq_mod.run(ExecutionContext(pipette=pip, manager=manager))

        # Nothing was patched: the gate is ahead of the clean for exactly this.
        assert calls == []
    finally:
        stage.quit()


def test_example_patch_seq_skips_the_nucleus_tail_when_reseal_falls_back(
    qapp, monkeypatch, seq_day
):
    """reseal returning 'whole cell' means it fell back and there is no nucleus
    to deposit."""
    _, slice_dir = seq_day
    pip, array, stage = _rack_pipette(cols=2)
    try:
        calls = []
        _seq_actions(monkeypatch, calls)
        monkeypatch.setattr(example_patch_seq_mod, "reseal", lambda ctx: "whole cell")
        manager = _SeqManager(slice_dir)
        cell_dir = manager.next_cell()

        example_patch_seq_mod.run(ExecutionContext(pipette=pip, manager=manager))

        assert "home_with_nucleus" not in calls
        assert "nucleus_tube_id" not in cell_dir.info()
        assert array.sites[0].used_up is False
        assert calls[-1] == "go_park"
    finally:
        stage.quit()


def test_example_patch_seq_images_the_nucleus_before_homing_it(
    qapp, monkeypatch, seq_day
):
    _, slice_dir = seq_day
    pip, array, stage = _rack_pipette(cols=2)
    try:
        calls = []
        _seq_actions(monkeypatch, calls)
        manager = _SeqManager(slice_dir)
        manager.next_cell()

        example_patch_seq_mod.run(ExecutionContext(pipette=pip, manager=manager))

        # reseal -> one image -> home with nucleus -> deposit.
        assert calls.count(("snap", "outside_out")) == 1
        assert calls.index(("snap", "outside_out")) < calls.index("home_with_nucleus")
    finally:
        stage.quit()


def test_example_patch_seq_parks_the_pipette_however_the_attempt_ends(
    qapp, monkeypatch, seq_day
):
    _, slice_dir = seq_day
    pip, array, stage = _rack_pipette(cols=2)
    try:
        calls = []
        _seq_actions(monkeypatch, calls)
        monkeypatch.setattr(example_patch_seq_mod, "patch", lambda ctx: "bath")
        manager = _SeqManager(slice_dir)
        manager.next_cell()

        example_patch_seq_mod.run(ExecutionContext(pipette=pip, manager=manager))

        assert calls.index("go_approach") < calls.index("go_park")
        assert "home_with_nucleus" not in calls
    finally:
        stage.quit()


def test_the_finished_day_reports_every_cell_against_its_tube(
    qapp, monkeypatch, seq_day
):
    _, slice_dir = seq_day
    pip, array, stage = _rack_pipette(cols=3)
    try:
        calls = []
        _seq_actions(monkeypatch, calls)
        monkeypatch.setattr(
            sites_mod,
            "prompt_tube_rack",
            lambda title, text, rows, cols, make_ids, start_n, extra_text=None: (
                make_ids(start_n, False),
                start_n,
            ),
        )
        manager = _SeqManager(slice_dir)
        for _ in range(2):
            manager.next_cell()
            example_patch_seq_mod.run(
                ExecutionContext(pipette=pip, manager=manager),
                tube_id_format="T{tube_count}_{well}",
            )

        report = build_tube_report(array, manager.getCurrentDir())

        lines = report.split("\n")
        assert lines[1].split() == ["0", "A01", "Slice_000/Cell_000", "T0_A01"]
        assert lines[2].split() == ["1", "A02", "Slice_000/Cell_001", "T1_A02"]
        assert lines[3].split() == ["2", "A03", "--", "T2_A03"]
    finally:
        stage.quit()


def test_an_unlabelled_rack_records_the_position_and_an_empty_tube_id(
    qapp, monkeypatch, seq_day
):
    """The operator labels the first rack through the array's own device GUI
    before a run. Until they do, a cell still lands in a tube; it just has no id
    to report."""
    _, slice_dir = seq_day
    pip, array, stage = _rack_pipette(cols=2)
    try:
        for site in array.sites:
            site.tube_id = None
        calls = []
        _seq_actions(monkeypatch, calls)
        manager = _SeqManager(slice_dir)
        cell_dir = manager.next_cell()

        example_patch_seq_mod.run(ExecutionContext(pipette=pip, manager=manager))

        on_disk = _info_off_disk(cell_dir)
        assert on_disk["nucleus_tube_position"] == "A01"
        assert on_disk["nucleus_tube_id"] == ""
        lines = build_tube_report(array, cell_dir).split("\n")
        assert lines[1].split() == ["0", "A01", "--"]
    finally:
        stage.quit()
