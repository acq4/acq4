import pytest
from pyqtgraph.dockarea import Dock, DockArea

from acq4.util import Qt
from acq4.util.ui_state import UiState


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


FILE = "modules/Win_ui.cfg"


class FakeManager:
    """Dict-backed stand-in for Manager's config-file pair."""

    def __init__(self, files=None):
        self.files = {} if files is None else files

    def readConfigFile(self, fileName, missingOk=True):
        return self.files.get(fileName, {})

    def writeConfigFile(self, data, fileName):
        self.files[fileName] = data


@pytest.fixture
def useManager(monkeypatch):
    """Return a function that installs a new FakeManager (optionally holding `files`) as getManager()."""

    def install(files=None):
        manager = FakeManager(files)
        monkeypatch.setattr("acq4.Manager.Manager.single", manager, raising=False)
        return manager

    return install


def avail(qapp):
    return qapp.primaryScreen().availableGeometry()


def test_geometry_round_trips(qapp, useManager):
    a = avail(qapp)
    manager = useManager()
    first = Qt.QWidget()
    first.setGeometry(a.x() + 20, a.y() + 30, 410, 320)
    UiState(first, FILE).save()
    state = manager.files[FILE]
    assert state["geometry"] == [a.x() + 20, a.y() + 30, 410, 320]
    assert state["maximized"] is False

    useManager({FILE: state})
    second = Qt.QWidget()
    UiState(second, FILE)
    assert second.geometry() == first.geometry()


def test_maximized_state_keeps_the_normal_geometry(qapp, useManager):
    a = avail(qapp)
    manager = useManager()
    win = Qt.QWidget()
    win.setGeometry(a.x() + 20, a.y() + 30, 410, 320)
    win.setWindowState(Qt.Qt.WindowMaximized)
    UiState(win, FILE).save()
    state = manager.files[FILE]
    assert state["maximized"] is True
    assert state["geometry"] == [a.x() + 20, a.y() + 30, 410, 320]

    useManager({FILE: state})
    restored = Qt.QWidget()
    UiState(restored, FILE)
    assert restored.windowState() & Qt.Qt.WindowMaximized
    assert restored.normalGeometry().size() == Qt.QSize(410, 320)


def test_maximized_window_without_a_normal_geometry_saves_its_current_one(qapp, useManager):
    class NeverNormal(Qt.QWidget):
        def normalGeometry(self):
            return Qt.QRect(0, 0, -1, -1)

    a = avail(qapp)
    manager = useManager()
    win = NeverNormal()
    win.setGeometry(a.x() + 20, a.y() + 30, 410, 320)
    win.setWindowState(Qt.Qt.WindowMaximized)
    UiState(win, FILE).save()
    state = manager.files[FILE]
    assert state["geometry"] == [win.geometry().x(), win.geometry().y(), win.geometry().width(), win.geometry().height()]
    assert state["geometry"][2] > 0
    assert state["maximized"] is True


def test_minimized_window_saves_its_normal_geometry(qapp, useManager):
    a = avail(qapp)
    manager = useManager()
    win = Qt.QWidget()
    win.setGeometry(a.x() + 20, a.y() + 30, 410, 320)
    win.setWindowState(Qt.Qt.WindowMinimized)
    UiState(win, FILE).save()
    assert manager.files[FILE]["geometry"] == [a.x() + 20, a.y() + 30, 410, 320]
    assert manager.files[FILE]["maximized"] is False


def test_main_window_state_is_kept_only_for_main_windows(qapp, useManager):
    manager = useManager()
    main = Qt.QMainWindow()
    UiState(main, FILE).save()
    assert isinstance(manager.files[FILE]["window"], str)
    useManager(manager.files)
    restored = Qt.QMainWindow()
    UiState(restored, FILE)  # must not raise

    other = useManager()
    plain = Qt.QWidget()
    UiState(plain, FILE).save()
    assert "window" not in other.files[FILE]


def test_window_saved_on_a_detached_monitor_is_moved_onto_a_screen(qapp, useManager):
    a = avail(qapp)
    useManager({FILE: {"geometry": [a.right() + 5000, a.bottom() + 5000, 400, 300]}})
    win = Qt.QWidget()
    UiState(win, FILE)
    assert a.contains(win.geometry().topLeft())
    assert win.size() == Qt.QSize(400, 300)


@pytest.mark.parametrize(
    "state",
    [
        {},
        {"geometry": "nonsense"},
        {"geometry": [1, 2, 3]},
        {"geometry": [0, 0, 0, 0]},
        {"window": "not-a-state"},
        {"window": 7},
        {"splitter": "not-a-state"},
    ],
)
def test_missing_or_invalid_state_is_ignored(qapp, useManager, state):
    useManager({FILE: state})
    win = Qt.QMainWindow()
    splitter = Qt.QSplitter()
    win.setGeometry(10, 20, 300, 200)
    UiState(win, FILE, widgets={"splitter": splitter})
    assert win.geometry() == Qt.QRect(10, 20, 300, 200)


def test_saves_when_the_window_is_closed(qapp, useManager):
    manager = useManager()
    win = Qt.QWidget()
    UiState(win, FILE)
    win.show()
    win.resize(630, 420)
    win.close()
    assert manager.files[FILE]["geometry"][2:] == [630, 420]


def test_splitter_state_round_trips(qapp, useManager):
    def makeSplitter():
        s = Qt.QSplitter()
        s.addWidget(Qt.QWidget())
        s.addWidget(Qt.QWidget())
        return s

    manager = useManager()
    first = Qt.QWidget()
    s1 = makeSplitter()
    s1.setSizes([100, 300])
    UiState(first, FILE, widgets={"split": s1}).save()
    assert isinstance(manager.files[FILE]["split"], str)

    useManager(manager.files)
    second = Qt.QWidget()
    s2 = makeSplitter()
    UiState(second, FILE, widgets={"split": s2})
    assert s2.sizes() == s1.sizes()


def test_dock_area_state_round_trips(qapp, useManager):
    def makeArea():
        area = DockArea()
        a, b = Dock("a"), Dock("b")
        area.addDock(a)
        area.addDock(b, "right", a)
        return area, a, b

    manager = useManager()
    area1, a1, b1 = makeArea()
    area1.moveDock(b1, "bottom", a1)
    win1 = Qt.QWidget()
    UiState(win1, FILE, widgets={"docks": area1}).save()

    useManager(manager.files)
    area2, _, _ = makeArea()
    win2 = Qt.QWidget()
    UiState(win2, FILE, widgets={"docks": area2})
    assert area2.saveState() == area1.saveState()


def test_widget_names_may_not_shadow_window_keys(qapp, useManager):
    useManager()
    with pytest.raises(ValueError):
        UiState(Qt.QWidget(), FILE, widgets={"geometry": Qt.QSplitter()})


def test_simultaneous_windows_get_separate_files(qapp, useManager):
    useManager()
    first = Qt.QWidget()
    second = Qt.QWidget()
    s1 = UiState(first, FILE)
    s2 = UiState(second, FILE)
    assert s1.configFile == FILE
    assert s2.configFile == "modules/Win_ui_1.cfg"

    # a window opened after the first one closes takes over its file
    first.show()
    first.close()
    third = Qt.QWidget()
    assert UiState(third, FILE).configFile == FILE

    # reopening the first window moves it to a file nobody else holds
    first.show()
    assert s1.configFile == "modules/Win_ui_2.cfg"
    first.close()


def test_a_deleted_window_frees_its_file(qapp, useManager):
    useManager()
    win = Qt.QWidget()
    UiState(win, FILE)
    win.deleteLater()
    Qt.QCoreApplication.sendPostedEvents(None, Qt.QEvent.DeferredDelete)
    other = Qt.QWidget()
    assert UiState(other, FILE).configFile == FILE


def test_other_managers_do_not_share_the_registry(qapp, useManager):
    useManager()
    first = Qt.QWidget()
    UiState(first, FILE)
    useManager()
    second = Qt.QWidget()
    assert UiState(second, FILE).configFile == FILE


def test_a_write_failure_is_logged_not_raised(qapp, useManager, caplog):
    manager = useManager()

    def unwritable(data, fileName):
        raise OSError("read-only config directory")

    manager.writeConfigFile = unwritable
    win = Qt.QWidget()
    with caplog.at_level("ERROR", logger="acq4.util.ui_state"):
        UiState(win, FILE).save()
    assert "read-only config directory" in caplog.text
