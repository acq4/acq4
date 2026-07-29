"""Tests for the bundled example Autopatch protocols: each bundled .py file
must load cleanly through ProtocolFile and run through the Orchestrator, and
the first-run install step must seed a fresh config dir with them without
ever overwriting an operator's existing file."""
from __future__ import annotations

import importlib
import os

import pytest

import acq4.modules.Autopatch.example_protocols as example_protocols_pkg
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
    # PARAMS builds a tree without raising, even for the empty-list case.
    assert pf.param_tree is not None


def test_example_prompt_exposes_message_param_with_a_default():
    pf = ProtocolFile(os.path.join(_EXAMPLES_DIR, "example_prompt.py"))
    pf.load()
    assert pf.param_values() == {"message": "Ready to patch this cell?"}


def test_example_patch_exposes_speed_param_with_a_default():
    pf = ProtocolFile(os.path.join(_EXAMPLES_DIR, "example_patch.py"))
    pf.load()
    assert pf.param_values() == {"speed": "fast"}


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


def test_example_prompt_runs_end_to_end_and_finishes_the_cell_as_skipped(tmp_path, monkeypatch):
    """End-to-end demo with the operator simulated: prompt_user is patched to
    return a choice immediately (standing in for the human click) since a
    stray QApplication left behind by another test would otherwise make
    prompt() block forever waiting for a real one. Everything else is real:
    ProtocolFile loading, the orchestrator running the protocol, next_cell()
    raising AdvanceToNextCell, and the cell finishing as "skipped"."""
    monkeypatch.setattr(_prompt_mod, "prompt_user", lambda title, message, choices: choices[0])

    dest = tmp_path / "autopatch_protocols"
    install_example_protocols(str(dest))
    pf = ProtocolFile(str(dest / "example_prompt.py"))
    pf.load()

    orch = Orchestrator(pf, contextFactory=lambda cell: ExecutionContext(cell=cell))
    finished = []
    orch.sigCellFinished.connect(lambda cell, status: finished.append((cell, status)))
    orch.run_sync_cell("cell-1")

    assert finished == [("cell-1", "skipped")]


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
