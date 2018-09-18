# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\FilterWheelTaskTemplate.ui'
#
# Created by: PyQt4 UI code generator 4.11.4
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
        Form.resize(400, 300)
        self.gridLayout_2 = QtGui.QGridLayout(Form)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout_2.addWidget(self.label_2, 1, 0, 1, 1)
        self.sequenceCombo = QtGui.QComboBox(Form)
        self.sequenceCombo.setObjectName(_fromUtf8("sequenceCombo"))
        self.gridLayout_2.addWidget(self.sequenceCombo, 1, 1, 1, 1)
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout_2.addWidget(self.label, 0, 0, 1, 1)
        self.filterCombo = QtGui.QComboBox(Form)
        self.filterCombo.setObjectName(_fromUtf8("filterCombo"))
        self.gridLayout_2.addWidget(self.filterCombo, 0, 1, 1, 1)
        self.sequenceListEdit = QtGui.QLineEdit(Form)
        self.sequenceListEdit.setObjectName(_fromUtf8("sequenceListEdit"))
        self.gridLayout_2.addWidget(self.sequenceListEdit, 2, 1, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.label_2.setText(_translate("Form", "Sequence", None))
        self.label.setText(_translate("Form", "Filter Wheel position", None))

