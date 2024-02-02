"""
This stub file is to aid in the PyCharm auto-completion of the Qt imports.
"""

from typing import Union, Any

try:
    from PyQt5 import QtCore, QtGui, QtWidgets, QtTest
    from PyQt5.QtCore import *
    from PyQt5.QtGui import *
    from PyQt5.QtWidgets import *
    from PyQt5.QtTest import *

    QtCore = QtCore
    QtGui = QtGui
    QtWidgets = QtWidgets
except ImportError:
    try:
        from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
        from PyQt6.QtCore import *
        from PyQt6.QtGui import *
        from PyQt6.QtWidgets import *
        from PyQt6.QtTest import *

        QtCore = QtCore
        QtGui = QtGui
        QtWidgets = QtWidgets
    except ImportError:
        try:
            from PySide2 import QtCore, QtGui, QtWidgets, QtTest
            from PySide2.QtCore import *
            from PySide2.QtGui import *
            from PySide2.QtWidgets import *
            from PySide2.QtTest import *

            QtCore = QtCore
            QtGui = QtGui
            QtWidgets = QtWidgets
        except ImportError:
            try:
                from PySide6 import QtCore, QtGui, QtWidgets, QtTest
                from PySide6.QtCore import *
                from PySide6.QtGui import *
                from PySide6.QtWidgets import *
                from PySide6.QtTest import *

                QtCore = QtCore
                QtGui = QtGui
                QtWidgets = QtWidgets
            except ImportError as e:
                raise ImportError("No suitable qt binding found") from e

Signal = QtCore.pyqtSignal
App: QtWidgets.QApplication
VERSION_INFO: str
QT_LIB: str
QtVersion: str
def exec_() -> QtWidgets.QApplication: ...
def mkQApp(name: Union[str, None] = None) -> QtWidgets.QApplication: ...
def isQObjectAlive(obj: QtCore.QObject) -> bool: ...
def importTemplate(templateName: str) -> Any: ...