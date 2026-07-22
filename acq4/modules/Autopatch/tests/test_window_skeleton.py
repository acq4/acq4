"""Tests that AutopatchWindow constructs and exposes the five design-doc areas
as labeled placeholder group boxes."""
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    """A QApplication is required to instantiate any QWidget."""
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeDeviceSelector(Qt.QWidget):
    """Stands in for InterfaceCombo so these skeleton tests never trigger its
    internal getManager() call."""

    def getSelectedObj(self):
        return None


def _makeWindow(tmp_path):
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    return AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakeDeviceSelector(),
        cameraSelector=_FakeDeviceSelector(),
    )


def test_window_constructs_with_five_area_boxes(qapp, tmp_path):
    win = _makeWindow(tmp_path)

    assert isinstance(win.area1Box, Qt.QGroupBox)
    assert isinstance(win.area2Box, Qt.QGroupBox)
    assert isinstance(win.area3Box, Qt.QGroupBox)
    assert isinstance(win.area4Box, Qt.QGroupBox)
    assert isinstance(win.area5Box, Qt.QGroupBox)


def test_area_titles_name_their_design_doc_role(qapp, tmp_path):
    win = _makeWindow(tmp_path)

    assert "slice" in win.area1Box.title().lower()
    assert "cell" in win.area2Box.title().lower() and "find" in win.area2Box.title().lower()
    assert "status" in win.area3Box.title().lower() or "action" in win.area3Box.title().lower()
    assert "protocol" in win.area4Box.title().lower()
    assert "cell" in win.area5Box.title().lower()


def test_window_has_a_title(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    assert win.windowTitle() == "Autopatch"
