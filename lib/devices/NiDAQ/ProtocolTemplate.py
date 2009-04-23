# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ProtocolTemplate.ui'
#
# Created: Thu Apr 23 18:55:45 2009
#      by: PyQt4 UI code generator 4.4.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(204, 71)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName("gridLayout")
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.rateSpin = QtGui.QSpinBox(Form)
        self.rateSpin.setMaximum(2000000)
        self.rateSpin.setSingleStep(1000)
        self.rateSpin.setProperty("value", QtCore.QVariant(40000))
        self.rateSpin.setObjectName("rateSpin")
        self.gridLayout.addWidget(self.rateSpin, 0, 1, 1, 1)
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)
        self.triggerDevList = QtGui.QComboBox(Form)
        self.triggerDevList.setObjectName("triggerDevList")
        self.triggerDevList.addItem(QtCore.QString())
        self.gridLayout.addWidget(self.triggerDevList, 1, 1, 1, 2)
        self.numPtsLabel = QtGui.QLabel(Form)
        self.numPtsLabel.setObjectName("numPtsLabel")
        self.gridLayout.addWidget(self.numPtsLabel, 0, 2, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Rate", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "Trigger", None, QtGui.QApplication.UnicodeUTF8))
        self.triggerDevList.setItemText(0, QtGui.QApplication.translate("Form", "No Trigger", None, QtGui.QApplication.UnicodeUTF8))
        self.numPtsLabel.setText(QtGui.QApplication.translate("Form", "0 pts", None, QtGui.QApplication.UnicodeUTF8))

