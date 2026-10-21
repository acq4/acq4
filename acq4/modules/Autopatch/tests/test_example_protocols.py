"""Tests for the machinery that loads and lists the bundled example Autopatch
protocols: each bundled .py file must load cleanly through ProtocolFile and run
through the Orchestrator, and the picker must list them in place out of the
package -- never copied into a rig's config directory, where a second copy would
drift -- while still letting an operator shadow one by name with their own file.

What an example *does* is deliberately not pinned here. The examples are
suggestions to copy and edit, not interfaces: asserting their call sequences
makes every edit to one a test failure, and leaves the example looking like a
contract it was never meant to be."""
from __future__ import annotations

import importlib
import os

import pytest

import acq4.modules.Autopatch.example_protocols as example_protocols_pkg
from acq4.experiment.context import ExecutionContext
from acq4.experiment.orchestrator import Orchestrator
from acq4.experiment.protocol_directory import ProtocolDirectory
from acq4.experiment.protocol_file import ProtocolFile
from acq4.modules.Autopatch.example_protocols import EXAMPLE_PROTOCOLS_DIR
import acq4.util.DataManager as dm
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


@pytest.mark.parametrize("filename", ["example_prompt.py", "example_patch.py"])
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





# "bath" and "fouled" are routine, anticipated terminals an operator does not
# need interrupted for; "broken" is the one exceptional outcome (see
# example_patch.run's docstring and the "only prompt for exceptional
# outcomes" commit that put this branch in).




























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
        module=None,
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
