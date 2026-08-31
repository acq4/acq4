"""Tests for ProtocolPanel: listing/loading .py protocol files from a
ProtocolDirectory, error display for broken files, and Reload/Open-in-editor."""
import os
import textwrap

import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def _write(dir_path, name, body):
    path = dir_path / name
    path.write_text(textwrap.dedent(body))
    return str(path)


def _good_protocol_body(default=3):
    return f"""
        \"\"\"A good protocol.\"\"\"
        PARAMS = [dict(name="count", type="int", default={default})]

        def run(ctx, **params):
            return "done"
    """


def test_refresh_lists_py_files_sorted(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write(tmp_path, "zzz.py", _good_protocol_body())
    _write(tmp_path, "aaa.py", _good_protocol_body())
    (tmp_path / "not_a_protocol.txt").write_text("ignore me")

    panel = ProtocolPanel(protocolDir=str(tmp_path))

    names = [panel.fileCombo.itemData(i) for i in range(panel.fileCombo.count())]
    assert names == ["aaa", "zzz"]


def test_missing_dir_starts_empty_not_crashing(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    missing = str(tmp_path / "does_not_exist_yet")
    panel = ProtocolPanel(protocolDir=missing)

    assert panel.fileCombo.count() == 0
    assert os.path.isdir(missing)  # created for future drops


def test_broken_file_is_listed_with_error_indicator(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write(tmp_path, "bad.py", "this is not valid python !!!")

    panel = ProtocolPanel(protocolDir=str(tmp_path))

    idx = panel.fileCombo.findData("bad")
    assert idx >= 0
    assert panel.fileCombo.itemText(idx) != "bad"  # some error indicator decorates the label


def test_selecting_broken_file_shows_load_error_and_does_not_emit(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write(tmp_path, "bad.py", "this is not valid python !!!")

    panel = ProtocolPanel(protocolDir=str(tmp_path))
    received = []
    panel.sigProtocolLoaded.connect(received.append)

    idx = panel.fileCombo.findData("bad")
    panel.fileCombo.setCurrentIndex(idx)

    assert panel.errorLabel.text()  # shows the load_error text
    assert panel.paramTree.topLevelItemCount() == 0
    assert received == []


def test_selecting_broken_file_does_not_set_protocol_file(qapp, tmp_path):
    """A broken protocol's error is shown (see the test above), but it must
    never become panel.protocolFile or reach sigProtocolLoaded -- there is no
    ProtocolFile fit to hand an Orchestrator."""
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write(tmp_path, "bad.py", "this is not valid python !!!")

    panel = ProtocolPanel(protocolDir=str(tmp_path))
    received = []
    panel.sigProtocolLoaded.connect(received.append)

    assert panel.protocolFile is None
    assert received == []
    assert panel.errorLabel.text()


def test_selecting_a_protocol_emits_its_protocol_file(qapp, tmp_path):
    """Selection alone is the load -- no button click reaches sigProtocolLoaded."""
    from acq4.experiment.protocol_file import ProtocolFile
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write(tmp_path, "aaa.py", _good_protocol_body())
    _write(tmp_path, "demo.py", _good_protocol_body())
    panel = ProtocolPanel(protocolDir=str(tmp_path))  # auto-selects "aaa" (sorted first)

    received = []
    panel.sigProtocolLoaded.connect(received.append)
    panel.fileCombo.setCurrentIndex(panel.fileCombo.findData("demo"))

    assert isinstance(panel.protocolFile, ProtocolFile)
    assert panel.protocolFile.name == "demo"
    assert len(received) == 1 and received[0] is panel.protocolFile


def test_param_edit_survives_switching_away_and_back(qapp, tmp_path):
    """Selecting a different protocol and back must not reload the first --
    reloading rebuilds param_tree from PARAMS defaults, which would silently
    discard this edit."""
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write(tmp_path, "aaa.py", _good_protocol_body(default=3))
    _write(tmp_path, "zzz.py", _good_protocol_body(default=5))
    panel = ProtocolPanel(protocolDir=str(tmp_path))  # auto-selects/loads "aaa"

    pf = panel.protocolFile
    assert pf.name == "aaa"
    pf.param_tree.child("count").setValue(42)
    assert pf.param_values() == {"count": 42}

    panel.fileCombo.setCurrentIndex(panel.fileCombo.findData("zzz"))
    assert panel.protocolFile is not pf

    panel.fileCombo.setCurrentIndex(panel.fileCombo.findData("aaa"))
    assert panel.protocolFile is pf
    assert pf.param_values() == {"count": 42}


def test_rescanning_without_changing_selection_does_not_re_emit(qapp, tmp_path):
    """_rebuildCombo() re-runs the selection handler on every rescan (including
    the one _RescanningComboBox triggers just by opening the popup), so it
    must not re-emit for a selection that hasn't actually changed -- otherwise
    just browsing the dropdown would rebuild the orchestrator and re-enqueue
    every held cell."""
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write(tmp_path, "demo.py", _good_protocol_body())
    panel = ProtocolPanel(protocolDir=str(tmp_path))

    received = []
    panel.sigProtocolLoaded.connect(received.append)

    _write(tmp_path, "extra.py", _good_protocol_body())
    panel.fileCombo.showPopup()  # rescans and repopulates; "demo" stays selected

    assert panel.fileCombo.findData("extra") >= 0
    assert received == []


def test_reload_button_picks_up_new_default_and_new_file(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write(tmp_path, "demo.py", _good_protocol_body(default=3))
    panel = ProtocolPanel(protocolDir=str(tmp_path))  # auto-selects/loads "demo"
    pf = panel.protocolFile
    assert pf.param_values() == {"count": 3}

    _write(tmp_path, "demo.py", _good_protocol_body(default=9))
    _write(tmp_path, "extra.py", _good_protocol_body())
    panel.reloadBtn.click()

    assert panel.fileCombo.findData("extra") >= 0
    # Same ProtocolFile object -- Reload re-imports it in place, so the
    # already-held reference reflects the new default without reselecting.
    assert panel.protocolFile is pf
    assert pf.param_values() == {"count": 9}


def test_open_in_editor_disabled_with_no_selection(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    panel = ProtocolPanel(protocolDir=str(tmp_path))

    assert panel.fileCombo.count() == 0
    assert not panel.editorBtn.isEnabled()


def test_open_in_editor_invokes_the_shared_code_editor_launcher(qapp, tmp_path, monkeypatch):
    # openInEditor delegates to acq4.util.codeEditor.invokeCodeEditor rather than
    # picking $EDITOR/xdg-open itself: xdg-open doesn't exist on Windows, and
    # invokeCodeEditor already handles cross-platform editor detection. See
    # "fix: use invokeCodeEditor in ProtocolPanel.openInEditor".
    from acq4.modules.Autopatch import protocol_panel as protocol_panel_module
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write(tmp_path, "demo.py", _good_protocol_body())

    captured = {}

    def _fake_invoke(fileName, lineNum, command=None):
        captured["args"] = (fileName, lineNum)

    monkeypatch.setattr(protocol_panel_module, "invokeCodeEditor", _fake_invoke)

    panel = ProtocolPanel(protocolDir=str(tmp_path))
    panel.fileCombo.setCurrentIndex(panel.fileCombo.findData("demo"))
    assert panel.editorBtn.isEnabled()
    panel.editorBtn.click()

    demo_path = str(tmp_path / "demo.py")
    assert captured["args"] == (demo_path, 1)


def test_opening_the_picker_rescans_for_a_newly_dropped_file(qapp, tmp_path):
    """Reload-on-interact: the operator shouldn't need to remember to click
    Reload just to see a file that appeared on disk -- opening the combo box
    itself rescans."""
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    panel = ProtocolPanel(protocolDir=str(tmp_path))
    assert panel.fileCombo.count() == 0

    _write(tmp_path, "demo.py", _good_protocol_body())
    panel.fileCombo.showPopup()

    assert panel.fileCombo.findData("demo") >= 0


def test_opening_the_picker_does_not_reset_the_loaded_protocols_params(qapp, tmp_path):
    """Reproduces the operator-facing bug: an operator's param edit must
    survive opening the dropdown -- the live Orchestrator holds this exact
    ProtocolFile and re-reads its param_values() every cell, so a silent
    reset mid-run would revert parameters without any indication."""
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write(tmp_path, "demo.py", _good_protocol_body(default=3))
    panel = ProtocolPanel(protocolDir=str(tmp_path))  # auto-selects/loads "demo"
    pf = panel.protocolFile
    assert pf.param_values() == {"count": 3}

    pf.param_tree.child("count").setValue(9)
    assert pf.param_values() == {"count": 9}

    panel.fileCombo.showPopup()  # discovery-only rescan, not a reload

    assert panel.protocolFile is pf
    assert pf.param_values() == {"count": 9}


def test_reload_button_renamed_from_refresh(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    panel = ProtocolPanel(protocolDir=str(tmp_path))
    assert panel.reloadBtn.text() == "Reload"
