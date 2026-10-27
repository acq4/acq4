"""Tests for the bundled example Autopatch protocols: each bundled .py file
must load cleanly through ProtocolFile and run through the Orchestrator, and
the picker must list them in place out of the package -- never copied into a
rig's config directory, where a second copy would drift -- while still letting
an operator shadow one by name with their own file."""
from __future__ import annotations

import importlib
import os

import pytest

import acq4.modules.Autopatch.example_protocols as example_protocols_pkg
import acq4.modules.Autopatch.example_protocols.example_patch as example_patch_mod
from acq4.experiment.actions.storage import mark_important
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


@pytest.mark.parametrize("filename", ["example_prompt.py", "example_patch.py"])
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


@pytest.mark.parametrize("filename", ["example_prompt.py", "example_patch.py"])
def test_bundled_example_declares_a_tip_on_every_param(filename):
    """Bundled examples are the templates operators copy, so every param they
    expose must demonstrate an operator-facing tip -- not just the name."""
    pf = ProtocolFile(os.path.join(_EXAMPLES_DIR, filename))
    pf.load()
    for child in pf.param_tree.children():
        assert child.opts.get("tip"), f"{filename}: {child.name()!r} has no tip"


def test_example_patch_exposes_preset_params_with_empty_defaults():
    pf = ProtocolFile(os.path.join(_EXAMPLES_DIR, "example_patch.py"))
    pf.load()
    # Empty defaults mean both load_preset() calls are no-ops out of the box,
    # so the bundled example runs on config/mock, which defines no presets.
    # force_clean defaults off for the same out-of-the-box reason: the opening
    # clean asks the pipette first and skips the cycle on a tip that has not
    # been onto a cell since its last clean.
    #
    # quick_clean_protocol is the one param with a non-empty default: the
    # pre-approach sonication is the point of the step, and a default of ""
    # would silently skip it. A rig whose sonicator has no protocol by that
    # name clears the field (or renames it), and sonicate() reports the
    # configured names when it does not.
    #
    # check_cell_present is the other non-empty default: with the cell check
    # split out of the cellfie it runs under `patch_preset` -- the imaging the
    # approach tracks the cell in -- so the old reason to leave it off (a
    # fluorescence reference being no use in brightfield) no longer applies,
    # and patching a cell the tracker cannot find is not the safer default.
    assert pf.param_values() == {
        "cellfie_preset": "",
        "patch_preset": "",
        "check_cell_present": True,
        "force_clean": False,
        "quick_clean_protocol": "quick clean",
    }


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


def test_example_patch_description_is_populated_from_its_module_docstring():
    pf = ProtocolFile(os.path.join(_EXAMPLES_DIR, "example_patch.py"))
    pf.load()
    assert pf.description == (
        "Capture a cellfie, move to the approach position, then drive the patch FSM.\n"
        "On a successful patch (whole cell), marks the cell's data directory important\n"
        "and runs the sequence already loaded in an open TaskRunner module -- have one\n"
        "open, with a sequence loaded, before running this protocol. Any other outcome\n"
        "prompts the operator to intervene.\n"
        "\n"
        "`cellfie_preset` and `patch_preset` name configured microscope imaging\n"
        "presets (e.g. \"GFP\", \"brightfield\"): the cellfie one for the z-stack, the patch\n"
        "one for the tip finding and the patch attempt either side of it. Leave either\n"
        "empty to skip loading it.\n"
        "\n"
        "`check_cell_present` runs the cell-tracker check (verify_cell) up front: it\n"
        "confirms the cell is still findable where its tracker expects it, and seeds\n"
        "that reference on a cell that does not have one yet. The tracker acquires the\n"
        "reference itself, under whatever imaging preset is loaded when it runs, which\n"
        "is why the check sits under `patch_preset` -- the imaging the approach follows\n"
        "the cell in -- rather than under `cellfie_preset`.\n"
        "\n"
        "The run opens with a pipette clean, which is skipped when the pipette reports\n"
        "its tip is still clean; `force_clean` runs the cycle regardless.\n"
        "\n"
        "However the run ends -- patched, failed, or raising -- it closes by parking the\n"
        "tip clear of the slice. Nothing below the patch attempt retracts on its own, and\n"
        "a tip left down where cell detect stopped keeps leaking internal into the tissue\n"
        "and shadows the cells the next pass images.\n"
        "\n"
        "Between the clean and the cellfie the tip is parked at the search position and\n"
        "given a short sonication at positive pressure, to expel anything it picked up\n"
        "leaving the clean well. It then stays in the bath, finding its tip at the\n"
        "search position and again over the cell, and is still there for the cellfie.\n"
        "`quick_clean_protocol` names the sonicator protocol to use; leave it empty to\n"
        "skip the sonication on a rig that has no such protocol."
    )


# -- branching on patch()'s returned outcome ---------------------------------
#
# patch() declares "broken"/"fouled" as terminals (see actions/fsm.py), so it
# can never raise an OrchestrationError for them -- an `except
# OrchestrationError` around it is dead code. The protocol must instead
# branch on the returned outcome string itself. These monkeypatch the plain
# functions example_patch.py imported by name, so the branching logic is
# exercised without needing real pipette hardware.


def _patch_actions(monkeypatch, ctx, *, patch_outcome, calls):
    monkeypatch.setattr(
        example_patch_mod,
        "clean",
        lambda ctx, only_if_needed=True: calls.append(("clean", only_if_needed)),
    )
    monkeypatch.setattr(
        example_patch_mod,
        "load_preset",
        lambda ctx, preset: calls.append(("load_preset", preset)),
    )
    monkeypatch.setattr(
        example_patch_mod, "cellfie", lambda ctx: calls.append("cellfie")
    )
    monkeypatch.setattr(
        example_patch_mod, "verify_cell", lambda ctx: calls.append("verify_cell")
    )
    monkeypatch.setattr(example_patch_mod, "go_search", lambda ctx: calls.append("go_search"))
    monkeypatch.setattr(
        example_patch_mod,
        "sonicate",
        lambda ctx, protocol, pressure=None, settle=0.0: calls.append(
            ("sonicate", protocol, pressure, settle)
        ),
    )
    monkeypatch.setattr(
        example_patch_mod, "go_above_target", lambda ctx: calls.append("go_above_target")
    )
    monkeypatch.setattr(example_patch_mod, "find_tip", lambda ctx: calls.append("find_tip"))
    monkeypatch.setattr(example_patch_mod, "go_approach", lambda ctx: calls.append("go_approach"))
    monkeypatch.setattr(example_patch_mod, "patch", lambda ctx: patch_outcome)
    monkeypatch.setattr(
        example_patch_mod, "prompt", lambda ctx, message: calls.append(("prompt", message))
    )
    monkeypatch.setattr(example_patch_mod, "run_task", lambda ctx: calls.append("run_task"))
    monkeypatch.setattr(
        example_patch_mod, "mark_important", lambda ctx: calls.append("mark_important")
    )
    monkeypatch.setattr(example_patch_mod, "go_park", lambda ctx: calls.append("go_park"))


# "bath" and "fouled" are routine, anticipated terminals an operator does not
# need interrupted for; "broken" is the one exceptional outcome (see
# example_patch.run's docstring and the "only prompt for exceptional
# outcomes" commit that put this branch in).
@pytest.mark.parametrize(
    "outcome,expects_prompt", [("bath", False), ("broken", True), ("fouled", False)]
)
def test_example_patch_prompts_only_for_the_broken_outcome(monkeypatch, outcome, expects_prompt):
    calls = []
    ctx = ExecutionContext()
    _patch_actions(monkeypatch, ctx, patch_outcome=outcome, calls=calls)

    example_patch_mod.run(
        ctx, cellfie_preset="GFP", patch_preset="brightfield", check_cell_present=True
    )

    assert calls[:12] == [
        ("clean", True),
        # The patch preset first: it is the imaging both tip finds need, and the
        # imaging the cell check has to take its tracker reference under.
        ("load_preset", "brightfield"),
        # The cell check, while the pipette is still parked at home and clear of
        # the light path the tracker's own z-stack needs.
        "verify_cell",
        # The quick clean, at the search position.
        "go_search",
        ("sonicate", "quick clean", 50e3, 4.0),
        # Then the tip stays in the bath: find it here, move down over the
        # target, find it again, and take the cellfie from there.
        "find_tip",
        "go_above_target",
        "find_tip",
        ("load_preset", "GFP"),
        "cellfie",
        ("load_preset", "brightfield"),
        "go_approach",
    ]
    if expects_prompt:
        # After the park, not before it: an unanswered prompt on an unattended
        # rig would otherwise hold the tip down in the tissue for as long as it
        # went unanswered.
        assert calls[12] == "go_park"
        assert calls[13][0] == "prompt"
        assert outcome in calls[13][1]  # the prompt names which outcome occurred
    else:
        assert "prompt" not in calls
    # Only a whole cell is worth coming back to; nothing else gets flagged.
    assert "mark_important" not in calls
    assert "run_task" not in calls


def test_example_patch_runs_the_task_runner_sequence_on_whole_cell(monkeypatch):
    calls = []
    ctx = ExecutionContext()
    _patch_actions(monkeypatch, ctx, patch_outcome="whole cell", calls=calls)

    example_patch_mod.run(
        ctx, cellfie_preset="GFP", patch_preset="brightfield", check_cell_present=True
    )

    assert calls == [
        ("clean", True),
        ("load_preset", "brightfield"),
        "verify_cell",
        "go_search",
        ("sonicate", "quick clean", 50e3, 4.0),
        "find_tip",
        "go_above_target",
        "find_tip",
        ("load_preset", "GFP"),
        "cellfie",
        ("load_preset", "brightfield"),
        "go_approach",
        "mark_important",
        "run_task",
        # The recording is over, so the tip comes out of the slice here rather
        # than waiting for the next cell's clean cycle to pull it off.
        "go_park",
    ]
    assert "prompt" not in calls


@pytest.mark.parametrize("outcome", ["whole cell", "bath", "broken", "fouled"])
def test_example_patch_parks_the_pipette_however_the_attempt_ends(monkeypatch, outcome):
    """The tip must come out of the slice on every route out of the patch block.

    This is the defect the park exists for: a failed cell detect returns from
    run() the moment patch() reports "bath", leaving the tip down where detection
    stopped -- leaking internal into the tissue, and shadowing the next cell for
    the tracker z-stack that immediately follows. The prompting outcomes return
    by their own route and the whole-cell one runs on past the branch, so "parks
    on every outcome" is the property, not "parks after the bath case".
    """
    calls = []
    ctx = ExecutionContext()
    _patch_actions(monkeypatch, ctx, patch_outcome=outcome, calls=calls)

    example_patch_mod.run(ctx)

    # After the approach, not instead of it: a park that ran before the attempt
    # would satisfy "go_park in calls" while patching nothing. And last of
    # everything that touches the rig -- only the operator prompt, which the
    # "broken" outcome raises, is allowed after it.
    assert calls.index("go_approach") < calls.index("go_park")
    after = calls[calls.index("go_park") + 1:]
    assert all(isinstance(c, tuple) and c[0] == "prompt" for c in after), after


def test_example_patch_parks_the_pipette_when_the_attempt_raises(monkeypatch):
    """A park written as the last statement of run() would be skipped by exactly
    the failures that most need it -- an action raising mid-attempt leaves the
    tip at the target. It is a finally, and this is what says so."""
    calls = []
    ctx = ExecutionContext()
    _patch_actions(monkeypatch, ctx, patch_outcome="whole cell", calls=calls)

    def _boom(ctx):
        raise RuntimeError("task runner exploded")

    monkeypatch.setattr(example_patch_mod, "run_task", _boom)

    with pytest.raises(RuntimeError):
        example_patch_mod.run(ctx)

    assert calls[-1] == "go_park"


def test_example_patch_skips_the_cell_check_when_it_is_turned_off(monkeypatch):
    """The param is only worth exposing if it reaches the action: a run that
    checked the cell anyway would leave the operator's choice with no effect."""
    calls = []
    ctx = ExecutionContext()
    _patch_actions(monkeypatch, ctx, patch_outcome="bath", calls=calls)

    example_patch_mod.run(ctx, check_cell_present=False)

    assert "verify_cell" not in calls
    # The cellfie is not conditional on it: the two are separate actions now,
    # and the z-stack is worth saving whether or not the cell was checked.
    assert "cellfie" in calls


def test_example_patch_checks_the_cell_under_the_patch_preset_before_moving(monkeypatch):
    """Placement is the whole point of splitting the check out of the cellfie.
    verify_cell has the tracker acquire its reference under whatever preset is
    loaded, and the approach follows the cell under `patch_preset` -- so the
    check must run after that preset is loaded (not under a fluorescence
    `cellfie_preset`), and before the pipette leaves home, since the tracker
    runs its own z-stack over the cell and wants nothing in the light path."""
    calls = []
    ctx = ExecutionContext()
    _patch_actions(monkeypatch, ctx, patch_outcome="bath", calls=calls)

    example_patch_mod.run(ctx, cellfie_preset="GFP", patch_preset="brightfield")

    check = calls.index("verify_cell")
    assert calls[check - 1] == ("load_preset", "brightfield")
    # Ahead of every pipette move out of home, and so ahead of both tip finds.
    for moved in ("go_search", "go_above_target", "go_approach", "find_tip"):
        assert check < calls.index(moved)
    # And ahead of the cellfie's own preset, so it never runs under that one.
    assert check < calls.index(("load_preset", "GFP"))


def test_example_patch_forwards_the_quick_clean_protocol_name_to_sonicate(monkeypatch):
    """Same reason as the cell-check flag: a param the action never sees leaves
    the operator editing a field with no effect."""
    calls = []
    ctx = ExecutionContext()
    _patch_actions(monkeypatch, ctx, patch_outcome="bath", calls=calls)

    example_patch_mod.run(ctx, quick_clean_protocol="expel")

    assert ("sonicate", "expel", 50e3, 4.0) in calls


def test_example_patch_empty_quick_clean_protocol_still_reaches_sonicate(monkeypatch):
    """The skip lives in sonicate(), not in the protocol: an empty name is
    forwarded and the action no-ops on it, so there is one place that decides
    what an unconfigured sonication does."""
    calls = []
    ctx = ExecutionContext()
    _patch_actions(monkeypatch, ctx, patch_outcome="bath", calls=calls)

    example_patch_mod.run(ctx, quick_clean_protocol="")

    assert ("sonicate", "", 50e3, 4.0) in calls
    # The search move is not conditional on it: the tip find that follows wants
    # the wide, tip-centered field the search sets up whether or not anything
    # was sonicated there.
    assert "go_search" in calls


def test_example_patch_sonicates_after_parking_at_the_search_position(monkeypatch):
    """Order matters for safety, not just tidiness: Sonicator.safeToSonicate
    prompts on a tip that still looks like it is in a recording chamber, which
    would stall an unattended run, and debris expelled near the target lands on
    the cell about to be patched."""
    calls = []
    ctx = ExecutionContext()
    _patch_actions(monkeypatch, ctx, patch_outcome="bath", calls=calls)

    example_patch_mod.run(ctx)

    search = calls.index("go_search")
    sonication = next(i for i, c in enumerate(calls) if c[0] == "sonicate")
    assert search < sonication


def test_example_patch_never_retracts_the_pipette_after_the_sonication(monkeypatch):
    """The tip must not cross the meniscus once it is clean: it collects debris
    on the way out of the solution and again on the way back in. So no go_home
    (nor any other retraction) between the sonication and the approach -- which
    is also why the cellfie is taken with the pipette parked in frame."""
    calls = []
    ctx = ExecutionContext()
    _patch_actions(monkeypatch, ctx, patch_outcome="bath", calls=calls)

    example_patch_mod.run(ctx)

    assert "go_home" not in calls
    sonication = next(i for i, c in enumerate(calls) if c[0] == "sonicate")
    # Everything after the sonication keeps the pipette in the bath: the only
    # pipette moves left are the two that descend toward the cell.
    after = calls[sonication + 1 :]
    assert [c for c in after if c in ("go_home", "go_search")] == []
    assert "go_above_target" in after
    assert "go_approach" in after


def test_example_patch_finds_the_tip_at_the_search_position_and_again_over_the_cell(
    monkeypatch,
):
    """Once in the wide, tip-centered field the search sets up, and again at the
    position the approach starts from -- the move between the two is long enough
    that the first offset does not survive it."""
    calls = []
    ctx = ExecutionContext()
    _patch_actions(monkeypatch, ctx, patch_outcome="bath", calls=calls)

    example_patch_mod.run(ctx)

    finds = [i for i, c in enumerate(calls) if c == "find_tip"]
    assert len(finds) == 2
    search = calls.index("go_search")
    above = calls.index("go_above_target")
    sonication = next(i for i, c in enumerate(calls) if c[0] == "sonicate")
    # search -> sonicate -> find -> above target -> find
    assert search < sonication < finds[0] < above < finds[1]


def test_example_patch_takes_the_cellfie_after_both_tip_finds(monkeypatch):
    """The cellfie comes last before the approach, so the stack is as fresh as
    it can be against tissue that drifts, and it is taken from the position the
    approach starts from."""
    calls = []
    ctx = ExecutionContext()
    _patch_actions(monkeypatch, ctx, patch_outcome="bath", calls=calls)

    example_patch_mod.run(ctx, cellfie_preset="GFP", patch_preset="brightfield")

    cellfie_at = calls.index("cellfie")
    assert calls[cellfie_at - 1] == ("load_preset", "GFP")
    # Nothing between the cellfie and the approach but the preset the approach
    # images under.
    assert calls[cellfie_at + 1 :][:2] == [("load_preset", "brightfield"), "go_approach"]


def test_example_patch_loads_the_patch_preset_before_the_tip_finds(monkeypatch):
    """The tip finds have to see the tip, so they run under the patch preset
    rather than whatever the previous cell happened to leave loaded."""
    calls = []
    ctx = ExecutionContext()
    _patch_actions(monkeypatch, ctx, patch_outcome="bath", calls=calls)

    example_patch_mod.run(ctx, cellfie_preset="GFP", patch_preset="brightfield")

    firstFind = calls.index("find_tip")
    assert calls.index(("load_preset", "brightfield")) < firstFind
    # And loaded back after the cellfie's own preset, for the approach.
    assert [c for c in calls if c[0] == "load_preset"] == [
        ("load_preset", "brightfield"),
        ("load_preset", "GFP"),
        ("load_preset", "brightfield"),
    ]


def test_example_patch_marks_the_cell_directory_important_on_whole_cell(
    monkeypatch, tmp_path
):
    """End-to-end over the real action and a real managed directory: the flag
    the Data Manager bolds (`important`, from Manager.suggestedDirFields) lands
    on the cell's own directory, which is the one the orchestrator makes current
    before the protocol runs."""
    cell_dir = dm.getDirHandle(str(tmp_path / "Cell_000"), create=True)
    cell_dir.setInfo({"dirType": "Cell"})

    class _Manager:
        def getCurrentDir(self):
            return cell_dir

    calls = []
    ctx = ExecutionContext(manager=_Manager())
    _patch_actions(monkeypatch, ctx, patch_outcome="whole cell", calls=calls)
    # Everything but the marking is stubbed; this is the action under test.
    monkeypatch.setattr(example_patch_mod, "mark_important", mark_important)

    example_patch_mod.run(ctx)

    assert cell_dir.info()["important"] is True
    assert cell_dir.info()["dirType"] == "Cell"


def test_example_protocols_dir_points_at_the_bundled_package_files():
    """The constant names the package directory itself, not a copy of it: the
    picker lists these files where they are, so this path is what "Open in
    editor" opens and what an edit has to land in."""
    assert os.path.isdir(EXAMPLE_PROTOCOLS_DIR)
    assert os.path.samefile(EXAMPLE_PROTOCOLS_DIR, _EXAMPLES_DIR)
    # Every bundled example must itself be a loadable ProtocolFile.
    for name in ("example_prompt.py", "example_patch.py"):
        pf = ProtocolFile(os.path.join(EXAMPLE_PROTOCOLS_DIR, name))
        pf.load()
        assert pf.is_loaded is True


def test_examples_are_never_copied_into_the_operators_protocol_dir(tmp_path):
    """The bug this whole arrangement exists to prevent: a second copy of every
    example seeded into a rig's config directory and then left to drift."""
    dest = tmp_path / "autopatch_protocols"
    directory = ProtocolDirectory(str(dest), extra_paths=[EXAMPLE_PROTOCOLS_DIR])
    directory.scan()

    assert set(directory.protocols.keys()) == {"example_prompt", "example_patch"}
    assert not (dest / "example_prompt.py").exists()
    assert not (dest / "example_patch.py").exists()


def test_the_packages_own_init_is_not_listed_as_a_protocol(tmp_path):
    directory = ProtocolDirectory(str(tmp_path), extra_paths=[EXAMPLE_PROTOCOLS_DIR])
    directory.scan()

    assert "__init__" not in directory.protocols


def test_protocol_directory_over_the_examples_dir_lists_exactly_the_two_examples(tmp_path):
    directory = ProtocolDirectory(str(tmp_path), extra_paths=[EXAMPLE_PROTOCOLS_DIR])
    directory.scan()

    assert set(directory.protocols.keys()) == {"example_prompt", "example_patch"}
    assert directory.protocols["example_prompt"].is_loaded is True
    assert directory.protocols["example_patch"].is_loaded is True


def test_an_operators_own_file_shadows_the_bundled_example_of_the_same_name(tmp_path):
    """The escape hatch that replaces "seed once and never overwrite": a file
    of the same name in the operator's own directory wins, and deleting it
    falls back to the bundled example on the next scan."""
    (tmp_path / "example_prompt.py").write_text(
        "PARAMS = []\n\n\ndef run(ctx, **params):\n    return \"mine\"\n"
    )
    directory = ProtocolDirectory(str(tmp_path), extra_paths=[EXAMPLE_PROTOCOLS_DIR])
    directory.scan()

    assert set(directory.protocols.keys()) == {"example_prompt", "example_patch"}
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
    assert items == {"example_prompt", "example_patch"}
    # The operator's directory was created, but nothing was written into it.
    assert protocolDir.is_dir()
    assert list(protocolDir.iterdir()) == []
    # ...because the listed protocols are the package's own files.
    for name in ("example_prompt", "example_patch"):
        protocol = win.protocolPanel.directory.get(name)
        assert os.path.dirname(protocol.path) == EXAMPLE_PROTOCOLS_DIR
