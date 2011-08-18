# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'LogWindowTemplate.ui'
#
# Created: Thu Aug 18 15:14:47 2011
#      by: PyQt4 UI code generator 4.8.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    _fromUtf8 = lambda s: s

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName(_fromUtf8("MainWindow"))
        MainWindow.resize(578, 458)
        self.centralwidget = QtGui.QWidget(MainWindow)
        self.centralwidget.setObjectName(_fromUtf8("centralwidget"))
        self.gridLayout = QtGui.QGridLayout(self.centralwidget)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.output = QtGui.QPlainTextEdit(self.centralwidget)
        self.output.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.output.setUndoRedoEnabled(False)
        self.output.setReadOnly(True)
        self.output.setObjectName(_fromUtf8("output"))
        self.gridLayout.addWidget(self.output, 1, 0, 1, 4)
        self.input = QtGui.QLineEdit(self.centralwidget)
        self.input.setObjectName(_fromUtf8("input"))
        self.gridLayout.addWidget(self.input, 2, 0, 1, 4)
        self.label = QtGui.QLabel(self.centralwidget)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.storageDirLabel = QtGui.QLabel(self.centralwidget)
        self.storageDirLabel.setObjectName(_fromUtf8("storageDirLabel"))
        self.gridLayout.addWidget(self.storageDirLabel, 0, 1, 1, 1)
        spacerItem = QtGui.QSpacerItem(229, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem, 0, 2, 1, 1)
        self.setStorageDirBtn = QtGui.QPushButton(self.centralwidget)
        self.setStorageDirBtn.setObjectName(_fromUtf8("setStorageDirBtn"))
        self.gridLayout.addWidget(self.setStorageDirBtn, 0, 3, 1, 1)
        MainWindow.setCentralWidget(self.centralwidget)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QtGui.QApplication.translate("MainWindow", "Log", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("MainWindow", "Current Storage Dir: ", None, QtGui.QApplication.UnicodeUTF8))
        self.storageDirLabel.setText(QtGui.QApplication.translate("MainWindow", "None", None, QtGui.QApplication.UnicodeUTF8))
        self.setStorageDirBtn.setText(QtGui.QApplication.translate("MainWindow", "Set Storage Dir", None, QtGui.QApplication.UnicodeUTF8))

