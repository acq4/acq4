"""Tests that ProtocolPanel installs a protocol's own ProtocolFile.param_tree
directly into its ParameterTree, with no mirror layer: editing the installed
tree changes what ProtocolFile.param_values() returns."""
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


def _write_protocol_with_params(dir_path, name):
    _write(
        dir_path,
        name,
        """
        PARAMS = [dict(name="Approach speed", type="str", default="slow")]

        def run(ctx, **params):
            return "done"
        """,
    )


def test_param_tree_installed_is_the_protocol_files_own_tree(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write_protocol_with_params(tmp_path, "demo.py")
    panel = ProtocolPanel(protocolDir=str(tmp_path))  # auto-selects/loads "demo"
    pf = panel.protocolFile

    names = [c.name() for c in pf.param_tree.children()]
    assert names == ["Approach speed"]
    assert pf.param_tree.child("Approach speed").value() == "slow"

    root = panel.paramTree.invisibleRootItem()
    assert root.child(0).param is pf.param_tree


def test_editing_installed_tree_changes_param_values(qapp, tmp_path):
    """The whole point of dropping the mirror layer: there is no separate
    mirror parameter to edit and no write-back wiring -- editing the tree
    ProtocolPanel installed IS editing the ProtocolFile's own tree, so
    param_values() (what the orchestrator passes to run()) reflects it
    immediately."""
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write_protocol_with_params(tmp_path, "demo.py")
    panel = ProtocolPanel(protocolDir=str(tmp_path))  # auto-selects/loads "demo"
    pf = panel.protocolFile

    pf.param_tree.child("Approach speed").setValue("fast")

    assert pf.param_values() == {"Approach speed": "fast"}


def test_selecting_a_loaded_protocol_shows_its_param_tree(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write_protocol_with_params(tmp_path, "demo.py")
    panel = ProtocolPanel(protocolDir=str(tmp_path))

    idx = panel.fileCombo.findData("demo")
    panel.fileCombo.setCurrentIndex(idx)

    root = panel.paramTree.invisibleRootItem()
    assert root.childCount() == 1
    assert root.child(0).childCount() == 1  # "Approach speed"
    assert not panel.errorLabel.text()
