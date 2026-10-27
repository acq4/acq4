import os
import weakref

from pyqtgraph.dockarea import DockArea

from acq4.Manager import getManager
from acq4.logging_config import get_logger
from acq4.util import Qt

logger = get_logger(__name__)

# Smallest part of a restored window that must overlap a screen for it to count as reachable.
_MIN_VISIBLE = Qt.QSize(100, 50)


class UiState(Qt.QObject):
    """Saves and restores a top-level window's layout in a config file.

    Create one per window, after its contents exist and before it is shown, and keep it for the
    window's life; it becomes a child of the window. State is restored on construction and saved
    whenever the window receives a Close event. Call save() from teardown paths that do not close
    the window.

    File contents::

        geometry   [x, y, width, height] in the normal (not maximized) state
        maximized  True if the window was maximized
        window     percent-encoded QMainWindow.saveState() (QMainWindow only)
        <name>     state of each entry in `widgets`

    Parameters
    ----------
    win : QWidget
        The top-level window.
    configFile : str
        Config-directory-relative path, e.g. "modules/Camera_ui.cfg". If another open window is
        using it, the first free numbered variant ("modules/Camera_ui_1.cfg", ...) is used instead;
        the file actually used is `configFile` on this object.
    widgets : dict, optional
        {name: widget} of QSplitter, QHeaderView, QMainWindow or pyqtgraph DockArea widgets whose
        state is also kept.
    """

    _reservedKeys = ("geometry", "maximized", "window")
    _instances = weakref.WeakSet()

    def __init__(self, win: Qt.QWidget, configFile: str, widgets: dict = None):
        super().__init__(win)
        self._widgets = dict(widgets or {})
        clash = set(self._widgets) & set(self._reservedKeys)
        if clash:
            raise ValueError(f"Widget names {sorted(clash)} are reserved")
        self._manager = getManager()
        self._baseFile = configFile
        self._closeSeen = False
        self.configFile = self._unusedFile()
        UiState._instances.add(self)
        win.installEventFilter(self)
        self._restore()

    def save(self) -> None:
        """Write the window's current state to `configFile`. Errors are logged, not raised."""
        try:
            win = self.parent()
            if win is None:
                return
            state = _captureWindow(win)
            for name, widget in self._widgets.items():
                state[name] = _captureWidget(widget)
        except RuntimeError:
            return  # the window is already deleted
        try:
            self._manager.writeConfigFile(state, self.configFile)
        except Exception:
            logger.exception(f"Could not save window state to {self.configFile}")

    def eventFilter(self, obj, ev):
        if ev.type() == Qt.QEvent.Close:
            self._closeSeen = True
            self.save()
        elif ev.type() == Qt.QEvent.Show and self._closeSeen:
            # reopened: the file may have been taken by another window meanwhile
            self._closeSeen = False
            self.configFile = self._unusedFile()
        return False

    def _restore(self) -> None:
        win = self.parent()
        try:
            state = self._manager.readConfigFile(self.configFile)
        except Exception:
            logger.exception(f"Could not read window state from {self.configFile}")
            return
        _applyGeometry(win, state.get("geometry"))
        if "window" in state and isinstance(win, Qt.QMainWindow):
            self._restoreWidget("window", win, state["window"])
        for name, widget in self._widgets.items():
            if name in state:
                self._restoreWidget(name, widget, state[name])
        if state.get("maximized"):
            win.setWindowState(win.windowState() | Qt.Qt.WindowMaximized)

    def _restoreWidget(self, name, widget, state) -> None:
        try:
            if isinstance(widget, DockArea):
                widget.restoreState(state, missing="ignore")
            elif not widget.restoreState(Qt.QByteArray.fromPercentEncoding(state.encode())):
                logger.warning(f"Saved state for '{name}' in {self.configFile} was rejected")
        except Exception:
            logger.warning(f"Could not restore '{name}' from {self.configFile}", exc_info=True)

    def _isOpen(self) -> bool:
        try:
            win = self.parent()
            return win is not None and not (self._closeSeen and not win.isVisible())
        except RuntimeError:
            return False  # the window is already deleted

    def _unusedFile(self) -> str:
        """Return the first variant of the requested file not held by another open window."""
        taken = {
            _normPath(s.configFile)
            for s in list(UiState._instances)
            if s is not self and s._manager is self._manager and s._isOpen()
        }
        root, ext = os.path.splitext(self._baseFile)
        name, n = self._baseFile, 0
        while _normPath(name) in taken:
            n += 1
            name = f"{root}_{n}{ext}"
        return name


def _normPath(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _captureWindow(win: Qt.QWidget) -> dict:
    special = win.windowState() & (Qt.Qt.WindowMaximized | Qt.Qt.WindowFullScreen | Qt.Qt.WindowMinimized)
    # geometry() is the maximized or off-screen placeholder rect in these states
    geom = win.normalGeometry() if special else win.geometry()
    if not geom.isValid():
        # never had a normal geometry (e.g. maximized since creation); the current
        # rect still records which screen the window is on
        geom = win.geometry()
    state = {
        "geometry": [geom.x(), geom.y(), geom.width(), geom.height()],
        "maximized": bool(win.windowState() & Qt.Qt.WindowMaximized),
    }
    if isinstance(win, Qt.QMainWindow):
        state["window"] = _captureWidget(win)
    return state


def _captureWidget(widget):
    if isinstance(widget, DockArea):
        return widget.saveState()
    return bytes(widget.saveState().toPercentEncoding()).decode()


def _applyGeometry(win: Qt.QWidget, geometry) -> None:
    if geometry is None:
        return
    try:
        rect = Qt.QRect(*[int(v) for v in geometry])
    except (TypeError, ValueError):
        logger.warning(f"Ignoring invalid window geometry {geometry!r}")
        return
    if rect.width() > 0 and rect.height() > 0:
        win.setGeometry(_onScreen(rect))


def _onScreen(rect: Qt.QRect) -> Qt.QRect:
    """Return `rect`, moved onto the primary screen if too little of it is on any current screen."""
    screens = Qt.QApplication.screens()
    if not screens:
        return rect
    for screen in screens:
        overlap = rect.intersected(screen.availableGeometry())
        if overlap.width() >= _MIN_VISIBLE.width() and overlap.height() >= _MIN_VISIBLE.height():
            return rect
    avail = Qt.QApplication.primaryScreen().availableGeometry()
    moved = Qt.QRect(rect)
    moved.setSize(rect.size().boundedTo(avail.size()))
    moved.moveTopLeft(avail.topLeft())
    return moved
