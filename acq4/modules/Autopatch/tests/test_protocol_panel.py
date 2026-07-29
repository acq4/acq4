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


def test_load_selected_on_broken_file_does_not_emit(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write(tmp_path, "bad.py", "this is not valid python !!!")

    panel = ProtocolPanel(protocolDir=str(tmp_path))
    received = []
    panel.sigProtocolLoaded.connect(received.append)

    panel.fileCombo.setCurrentIndex(panel.fileCombo.findData("bad"))
    result = panel.loadSelected()

    assert result is None
    assert received == []
    assert panel.errorLabel.text()


def test_load_selected_emits_protocol_file(qapp, tmp_path):
    from acq4.experiment.protocol_file import ProtocolFile
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write(tmp_path, "demo.py", _good_protocol_body())
    panel = ProtocolPanel(protocolDir=str(tmp_path))
    panel.fileCombo.setCurrentIndex(panel.fileCombo.findData("demo"))

    received = []
    panel.sigProtocolLoaded.connect(received.append)
    result = panel.loadSelected()

    assert isinstance(result, ProtocolFile)
    assert result.name == "demo"
    assert len(received) == 1 and received[0] is result
    assert panel.protocolFile is result


def test_reload_button_picks_up_new_default_and_new_file(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write(tmp_path, "demo.py", _good_protocol_body(default=3))
    panel = ProtocolPanel(protocolDir=str(tmp_path))
    panel.fileCombo.setCurrentIndex(panel.fileCombo.findData("demo"))
    pf = panel.loadSelected()
    assert pf.param_values() == {"count": 3}

    _write(tmp_path, "demo.py", _good_protocol_body(default=9))
    _write(tmp_path, "extra.py", _good_protocol_body())
    panel.reloadBtn.click()

    assert panel.fileCombo.findData("extra") >= 0
    panel.fileCombo.setCurrentIndex(panel.fileCombo.findData("demo"))
    pf = panel.loadSelected()
    assert pf.param_values() == {"count": 9}


def test_open_in_editor_disabled_with_no_selection(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    panel = ProtocolPanel(protocolDir=str(tmp_path))

    assert panel.fileCombo.count() == 0
    assert not panel.editorBtn.isEnabled()


def test_open_in_editor_uses_env_editor(qapp, tmp_path, monkeypatch):
    from acq4.modules.Autopatch import protocol_panel as protocol_panel_module
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write(tmp_path, "demo.py", _good_protocol_body())
    monkeypatch.setenv("EDITOR", "myeditor")

    captured = {}

    def _fake_popen(args, **kwargs):
        captured["args"] = args

        class _FakeProc:
            pass

        return _FakeProc()

    monkeypatch.setattr(protocol_panel_module.subprocess, "Popen", _fake_popen)

    panel = ProtocolPanel(protocolDir=str(tmp_path))
    panel.fileCombo.setCurrentIndex(panel.fileCombo.findData("demo"))
    assert panel.editorBtn.isEnabled()
    panel.editorBtn.click()

    demo_path = str(tmp_path / "demo.py")
    assert captured["args"] == ["myeditor", demo_path]


def test_open_in_editor_falls_back_to_xdg_open(qapp, tmp_path, monkeypatch):
    from acq4.modules.Autopatch import protocol_panel as protocol_panel_module
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write(tmp_path, "demo.py", _good_protocol_body())
    monkeypatch.delenv("EDITOR", raising=False)

    captured = {}

    def _fake_popen(args, **kwargs):
        captured["args"] = args

        class _FakeProc:
            pass

        return _FakeProc()

    monkeypatch.setattr(protocol_panel_module.subprocess, "Popen", _fake_popen)

    panel = ProtocolPanel(protocolDir=str(tmp_path))
    panel.fileCombo.setCurrentIndex(panel.fileCombo.findData("demo"))
    panel.editorBtn.click()

    demo_path = str(tmp_path / "demo.py")
    assert captured["args"] == ["xdg-open", demo_path]


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
    """Reproduces the operator-facing bug: after Load, an operator's param
    edit must survive opening the dropdown -- the live Orchestrator holds
    this exact ProtocolFile and re-reads its param_values() every cell, so a
    silent reset mid-run would revert parameters without any indication."""
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write(tmp_path, "demo.py", _good_protocol_body(default=3))
    panel = ProtocolPanel(protocolDir=str(tmp_path))
    panel.fileCombo.setCurrentIndex(panel.fileCombo.findData("demo"))
    pf = panel.loadSelected()
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
