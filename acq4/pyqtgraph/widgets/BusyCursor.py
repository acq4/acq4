from ..Qt import QtGui, QtCore

__all__ = ['BusyCursor']

class BusyCursor(object):
    """Class for displaying a busy mouse cursor during long operations.
    Usage::

        with pyqtgraph.BusyCursor():
            doLongOperation()

    May be nested.
    """
    active = []

    def __enter__(self):
        if QtGui.QApplication.instance() is not None:
            QtGui.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
            BusyCursor.active.append(self)
            self._active = True
        else:
            self._active = False

    def __exit__(self, *args):
        if self._active:
            BusyCursor.active.pop(-1)
            if len(BusyCursor.active) == 0:
                QtGui.QApplication.restoreOverrideCursor()
        