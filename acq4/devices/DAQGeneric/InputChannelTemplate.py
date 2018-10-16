# -*- coding: utf-8 -*-
from __future__ import print_function

# Form implementation generated from reading ui file 'InputChannelTemplate.ui'
#
# Created: Sun Feb 22 13:29:16 2015
#      by: PyQt4 UI code generator 4.10.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    def _fromUtf8(s):
        return s

try:
    _encoding = QtGui.QApplication.UnicodeUTF8
    def _translate(context, text, disambig):
        return QtGui.QApplication.translate(context, text, disambig, _encoding)
except AttributeError:
    def _translate(context, text, disambig):
        return QtGui.QApplication.translate(context, text, disambig)

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName(_fromUtf8("Form"))
        Form.resize(427, 220)
        self.verticalLayout = QtGui.QVBoxLayout(Form)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.groupBox = GroupBox(Form)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.groupBox.setFont(font)
        self.groupBox.setCheckable(False)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout = QtGui.QGridLayout(self.groupBox)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setContentsMargins(5, 0, 0, 0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.recordCheck = QtGui.QCheckBox(self.groupBox)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.recordCheck.setFont(font)
        self.recordCheck.setChecked(True)
        self.recordCheck.setObjectName(_fromUtf8("recordCheck"))
        self.gridLayout.addWidget(self.recordCheck, 0, 0, 1, 1)
        self.displayCheck = QtGui.QCheckBox(self.groupBox)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.displayCheck.setFont(font)
        self.displayCheck.setChecked(True)
        self.displayCheck.setObjectName(_fromUtf8("displayCheck"))
        self.gridLayout.addWidget(self.displayCheck, 0, 1, 1, 1)
        self.recordInitCheck = QtGui.QCheckBox(self.groupBox)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.recordInitCheck.setFont(font)
        self.recordInitCheck.setObjectName(_fromUtf8("recordInitCheck"))
        self.gridLayout.addWidget(self.recordInitCheck, 1, 0, 1, 2)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 2, 0, 1, 1)
        self.verticalLayout.addWidget(self.groupBox)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.groupBox.setTitle(_translate("Form", "GroupBox", None))
        self.recordCheck.setText(_translate("Form", "Record Trace", None))
        self.displayCheck.setText(_translate("Form", "Display", None))
        self.recordInitCheck.setText(_translate("Form", "Record Initial State", None))

from acq4.pyqtgraph import GroupBox
