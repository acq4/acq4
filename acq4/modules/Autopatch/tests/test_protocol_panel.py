"""Tests for ProtocolPanel: listing/loading Protocol JSON files from a directory."""
import json
import os

import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def _write_protocol(path, name):
    # A minimal valid Protocol: one GoToNext flow node as entry, no edges needed.
    data = {
        "version": 1,
        "entry": "n1",
        "nodes": {"n1": {"type": "GoToNext", "params": {}}},
        "edges": [],
        "publicParams": [],
        "exceptionHandlers": {},
    }
    with open(os.path.join(path, name), "w") as fh:
        json.dump(data, fh)


def test_refresh_lists_json_files_in_dir(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write_protocol(tmp_path, "demo.json")
    _write_protocol(tmp_path, "other.json")
    (tmp_path / "not_a_protocol.txt").write_text("ignore me")

    panel = ProtocolPanel(protocolDir=str(tmp_path))

    items = {panel.fileCombo.itemText(i) for i in range(panel.fileCombo.count())}
    assert items == {"demo.json", "other.json"}


def test_load_selected_emits_protocol(qapp, tmp_path):
    from acq4.experiment.protocol import Protocol
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write_protocol(tmp_path, "demo.json")
    panel = ProtocolPanel(protocolDir=str(tmp_path))
    panel.fileCombo.setCurrentText("demo.json")

    received = []
    panel.sigProtocolLoaded.connect(received.append)
    result = panel.loadSelected()

    assert isinstance(result, Protocol)
    assert result.entry == "n1"
    assert len(received) == 1 and received[0] is result
    assert panel.protocol is result


def test_missing_dir_starts_empty_not_crashing(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    missing = str(tmp_path / "does_not_exist_yet")
    panel = ProtocolPanel(protocolDir=missing)

    assert panel.fileCombo.count() == 0
    assert os.path.isdir(missing)  # created for future drops
