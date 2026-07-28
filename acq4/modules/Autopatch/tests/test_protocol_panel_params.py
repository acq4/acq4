"""Tests that ProtocolPanel renders a protocol's publicParams as an editable
ParameterTree mirror, two-way bound onto the underlying Action params."""
import json
import os

import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def _write_protocol_with_public_param(path, name):
    data = {
        "version": 1,
        "entry": "n1",
        "nodes": {"n1": {"type": "GoHome", "params": {"speed": "slow"}}},
        "edges": [],
        "publicParams": [{"node": "n1", "param": "speed", "public": "Approach speed"}],
        "exceptionHandlers": {},
    }
    with open(os.path.join(path, name), "w") as fh:
        json.dump(data, fh)


def test_param_tree_has_one_child_per_public_param(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write_protocol_with_public_param(tmp_path, "demo.json")
    panel = ProtocolPanel(protocolDir=str(tmp_path))
    panel.fileCombo.setCurrentText("demo.json")
    panel.loadSelected()

    names = [c.name() for c in panel.paramsRoot.children()]
    assert names == ["Approach speed"]
    assert panel.paramsRoot.child("Approach speed").value() == "slow"


def test_editing_mirror_pushes_value_to_underlying_action_param(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write_protocol_with_public_param(tmp_path, "demo.json")
    panel = ProtocolPanel(protocolDir=str(tmp_path))
    panel.fileCombo.setCurrentText("demo.json")
    panel.loadSelected()

    panel.paramsRoot.child("Approach speed").setValue("fast")

    assert panel.protocol.nodes["n1"].paramValue("speed") == "fast"
