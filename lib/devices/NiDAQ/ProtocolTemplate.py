# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ProtocolTemplate.ui'
#
# Created: Tue May  5 22:26:42 2009
#      by: PyQt4 UI code generator 4.4.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(202, 125)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName("gridLayout")
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.rateSpin = QtGui.QDoubleSpinBox(Form)
        self.rateSpin.setMinimum(0.01)
        self.rateSpin.setMaximum(2000.0)
        self.rateSpin.setProperty("value", QtCore.QVariant(40.0))
        self.rateSpin.setObjectName("rateSpin")
        self.gridLayout.addWidget(self.rateSpin, 0, 1, 1, 1)
        self.label_5 = QtGui.QLabel(Form)
        self.label_5.setObjectName("label_5")
        self.gridLayout.addWidget(self.label_5, 0, 2, 1, 1)
        self.label_4 = QtGui.QLabel(Form)
        self.label_4.setObjectName("label_4")
        self.gridLayout.addWidget(self.label_4, 1, 0, 1, 1)
        self.periodSpin = QtGui.QDoubleSpinBox(Form)
        self.periodSpin.setMinimum(1.0)
        self.periodSpin.setMaximum(10000.0)
        self.periodSpin.setProperty("value", QtCore.QVariant(25.0))
        self.periodSpin.setObjectName("periodSpin")
        self.gridLayout.addWidget(self.periodSpin, 1, 1, 1, 1)
        self.label_6 = QtGui.QLabel(Form)
        self.label_6.setObjectName("label_6")
        self.gridLayout.addWidget(self.label_6, 1, 2, 1, 1)
        self.label_3 = QtGui.QLabel(Form)
        self.label_3.setObjectName("label_3")
        self.gridLayout.addWidget(self.label_3, 2, 0, 1, 1)
        self.numPtsLabel = QtGui.QLabel(Form)
        self.numPtsLabel.setObjectName("numPtsLabel")
        self.gridLayout.addWidget(self.numPtsLabel, 2, 1, 1, 2)
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 3, 0, 1, 1)
        self.triggerDevList = QtGui.QComboBox(Form)
        self.triggerDevList.setObjectName("triggerDevList")
        self.triggerDevList.addItem(QtCore.QString())
        self.gridLayout.addWidget(self.triggerDevList, 3, 1, 1, 2)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 4, 1, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Rate", None, QtGui.QApplication.UnicodeUTF8))
        self.label_5.setText(QtGui.QApplication.translate("Form", "kHz", None, QtGui.QApplication.UnicodeUTF8))
        self.label_4.setText(QtGui.QApplication.translate("Form", "Period", None, QtGui.QApplication.UnicodeUTF8))
        self.label_6.setText(QtGui.QApplication.translate("Form", "μs", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("Form", "Points", None, QtGui.QApplication.UnicodeUTF8))
        self.numPtsLabel.setText(QtGui.QApplication.translate("Form", "0", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "Trigger", None, QtGui.QApplication.UnicodeUTF8))
        self.triggerDevList.setItemText(0, QtGui.QApplication.translate("Form", "No Trigger", None, QtGui.QApplication.UnicodeUTF8))

