"""Tests for the bundled example Autopatch protocols: each bundled .py file
must load cleanly through ProtocolFile and run through the Orchestrator, and
the first-run install step must seed a fresh config dir with them without
ever overwriting an operator's existing file."""
from __future__ import annotations

import importlib
import os

import pytest

import acq4.modules.Autopatch.example_protocols as example_protocols_pkg
import acq4.modules.Autopatch.example_protocols.example_patch as example_patch_mod
from acq4.experiment.context import ExecutionContext
from acq4.experiment.orchestrator import Orchestrator
from acq4.experiment.protocol_directory import ProtocolDirectory
from acq4.experiment.protocol_file import ProtocolFile
from acq4.modules.Autopatch.example_protocols import install_example_protocols
from acq4.util import Qt

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


def test_example_patch_exposes_preset_params_with_empty_defaults():
    pf = ProtocolFile(os.path.join(_EXAMPLES_DIR, "example_patch.py"))
    pf.load()
    # Empty defaults mean both load_preset() calls are no-ops out of the box,
    # so the bundled example runs on config/mock, which defines no presets.
    assert pf.param_values() == {"cellfie_preset": "", "patch_preset": ""}


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
        "On a successful patch (whole cell), runs the sequence already loaded in an\n"
        "open TaskRunner module -- have one open, with a sequence loaded, before\n"
        "running this protocol. Any other outcome prompts the operator to intervene."
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
        "load_preset",
        lambda ctx, preset: calls.append(("load_preset", preset)),
    )
    monkeypatch.setattr(example_patch_mod, "cellfie", lambda ctx: calls.append("cellfie"))
    monkeypatch.setattr(example_patch_mod, "go_approach", lambda ctx: calls.append("go_approach"))
    monkeypatch.setattr(example_patch_mod, "patch", lambda ctx: patch_outcome)
    monkeypatch.setattr(
        example_patch_mod, "prompt", lambda ctx, message: calls.append(("prompt", message))
    )
    monkeypatch.setattr(example_patch_mod, "run_task", lambda ctx: calls.append("run_task"))


@pytest.mark.parametrize("outcome", ["bath", "broken", "fouled"])
def test_example_patch_prompts_the_operator_on_a_non_success_outcome(monkeypatch, outcome):
    calls = []
    ctx = ExecutionContext()
    _patch_actions(monkeypatch, ctx, patch_outcome=outcome, calls=calls)

    example_patch_mod.run(ctx, cellfie_preset="GFP", patch_preset="brightfield")

    assert calls[:4] == [
        ("load_preset", "GFP"),
        "cellfie",
        ("load_preset", "brightfield"),
        "go_approach",
    ]
    assert calls[4][0] == "prompt"
    assert outcome in calls[4][1]  # the prompt names which outcome occurred
    assert "run_task" not in calls


def test_example_patch_runs_the_task_runner_sequence_on_whole_cell(monkeypatch):
    calls = []
    ctx = ExecutionContext()
    _patch_actions(monkeypatch, ctx, patch_outcome="whole cell", calls=calls)

    example_patch_mod.run(ctx, cellfie_preset="GFP", patch_preset="brightfield")

    assert calls == [
        ("load_preset", "GFP"),
        "cellfie",
        ("load_preset", "brightfield"),
        "go_approach",
        "run_task",
    ]
    assert "prompt" not in calls


def test_install_example_protocols_copies_into_a_fresh_config_dir(tmp_path):
    dest = tmp_path / "autopatch_protocols"
    install_example_protocols(str(dest))

    assert (dest / "example_prompt.py").exists()
    assert (dest / "example_patch.py").exists()
    # Every installed file must itself be a loadable ProtocolFile.
    for name in ("example_prompt.py", "example_patch.py"):
        pf = ProtocolFile(str(dest / name))
        pf.load()
        assert pf.is_loaded is True


def test_install_example_protocols_skips_its_own_init_file(tmp_path):
    dest = tmp_path / "autopatch_protocols"
    install_example_protocols(str(dest))

    assert not (dest / "__init__.py").exists()


def test_install_example_protocols_never_overwrites_an_existing_file(tmp_path):
    dest = tmp_path / "autopatch_protocols"
    dest.mkdir()
    (dest / "example_prompt.py").write_text("operator's own edits, not valid python !!!")

    install_example_protocols(str(dest))

    assert (dest / "example_prompt.py").read_text() == "operator's own edits, not valid python !!!"
    # The other example is still installed since only the existing name was skipped.
    assert (dest / "example_patch.py").exists()


def test_protocol_directory_over_installed_dir_lists_exactly_the_two_examples(tmp_path):
    dest = tmp_path / "autopatch_protocols"
    install_example_protocols(str(dest))

    directory = ProtocolDirectory(str(dest))
    directory.scan()

    assert set(directory.protocols.keys()) == {"example_prompt", "example_patch"}
    assert directory.protocols["example_prompt"].is_loaded is True
    assert directory.protocols["example_patch"].is_loaded is True


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

    dest = tmp_path / "autopatch_protocols"
    install_example_protocols(str(dest))
    pf = ProtocolFile(str(dest / "example_prompt.py"))
    pf.load()

    orch = Orchestrator(pf, contextFactory=lambda cell: ExecutionContext(cell=cell))
    finished = []
    orch.sigCellFinished.connect(lambda cell, status: finished.append((cell, status)))
    orch.run_sync_cell("cell-1")

    assert finished == [("cell-1", "done")]


def test_autopatch_window_init_seeds_a_missing_protocol_dir_with_examples(qapp, tmp_path):
    """AutopatchWindow's own init -- not just install_example_protocols() called
    directly -- creates a not-yet-existing protocol dir and seeds it with both
    bundled examples before the picker lists its contents."""
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    class _FakeDeviceSelector(Qt.QWidget):
        def getSelectedObj(self):
            return None

    protocolDir = tmp_path / "does_not_exist_yet" / "autopatch_protocols"
    win = AutopatchWindow(
        module=None,
        protocolDir=str(protocolDir),
        pipetteSelector=_FakeDeviceSelector(),
        cameraSelector=_FakeDeviceSelector(),
    )

    assert (protocolDir / "example_prompt.py").exists()
    assert (protocolDir / "example_patch.py").exists()
    items = {win.protocolPanel.fileCombo.itemText(i) for i in range(win.protocolPanel.fileCombo.count())}
    assert items == {"example_prompt", "example_patch"}
