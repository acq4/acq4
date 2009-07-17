# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'deviceTemplate.ui'
#
# Created: Wed Jul 15 14:06:46 2009
#      by: PyQt4 UI code generator 4.4.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(206, 64)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(3)
        self.gridLayout.setHorizontalSpacing(8)
        self.gridLayout.setVerticalSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.positionLabel = QtGui.QLabel(Form)
        self.positionLabel.setObjectName("positionLabel")
        self.gridLayout.addWidget(self.positionLabel, 0, 1, 1, 2)
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)
        self.objRadioLayout = QtGui.QVBoxLayout()
        self.objRadioLayout.setSpacing(0)
        self.objRadioLayout.setObjectName("objRadioLayout")
        self.gridLayout.addLayout(self.objRadioLayout, 1, 1, 1, 1)
        self.objComboLayout = QtGui.QVBoxLayout()
        self.objComboLayout.setObjectName("objComboLayout")
        self.gridLayout.addLayout(self.objComboLayout, 1, 2, 1, 1)
        spacerItem = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem, 1, 3, 1, 1)
        spacerItem1 = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem1, 0, 3, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Position:", None, QtGui.QApplication.UnicodeUTF8))
        self.positionLabel.setText(QtGui.QApplication.translate("Form", "0, 0", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "Objective:", None, QtGui.QApplication.UnicodeUTF8))

