# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'LogWidgetTemplate.ui'
#
# Created: Fri Sep  9 11:01:51 2011
#      by: PyQt4 UI code generator 4.8.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    _fromUtf8 = lambda s: s

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName(_fromUtf8("Form"))
        Form.resize(535, 419)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.storageDirLabel = QtGui.QLabel(Form)
        self.storageDirLabel.setObjectName(_fromUtf8("storageDirLabel"))
        self.gridLayout.addWidget(self.storageDirLabel, 0, 1, 1, 1)
        spacerItem = QtGui.QSpacerItem(214, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem, 0, 2, 1, 1)
        self.makeErrorBtn = QtGui.QPushButton(Form)
        self.makeErrorBtn.setObjectName(_fromUtf8("makeErrorBtn"))
        self.gridLayout.addWidget(self.makeErrorBtn, 0, 3, 1, 1)
        self.output = QtGui.QPlainTextEdit(Form)
        self.output.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.output.setUndoRedoEnabled(False)
        self.output.setReadOnly(True)
        self.output.setObjectName(_fromUtf8("output"))
        self.gridLayout.addWidget(self.output, 1, 0, 1, 4)
        self.input = QtGui.QLineEdit(Form)
        self.input.setObjectName(_fromUtf8("input"))
        self.gridLayout.addWidget(self.input, 2, 0, 1, 4)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Current Storage Dir: ", None, QtGui.QApplication.UnicodeUTF8))
        self.storageDirLabel.setText(QtGui.QApplication.translate("Form", "None", None, QtGui.QApplication.UnicodeUTF8))
        self.makeErrorBtn.setText(QtGui.QApplication.translate("Form", "make error", None, QtGui.QApplication.UnicodeUTF8))

