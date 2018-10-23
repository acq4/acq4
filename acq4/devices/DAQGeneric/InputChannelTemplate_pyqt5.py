# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/devices/DAQGeneric/InputChannelTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(427, 220)
        self.verticalLayout = QtWidgets.QVBoxLayout(Form)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.groupBox = GroupBox(Form)
        font = Qt.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.groupBox.setFont(font)
        self.groupBox.setCheckable(False)
        self.groupBox.setObjectName("groupBox")
        self.gridLayout = QtWidgets.QGridLayout(self.groupBox)
        self.gridLayout.setContentsMargins(5, 0, 0, 0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.recordCheck = QtWidgets.QCheckBox(self.groupBox)
        font = Qt.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.recordCheck.setFont(font)
        self.recordCheck.setChecked(True)
        self.recordCheck.setObjectName("recordCheck")
        self.gridLayout.addWidget(self.recordCheck, 0, 0, 1, 1)
        self.displayCheck = QtWidgets.QCheckBox(self.groupBox)
        font = Qt.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.displayCheck.setFont(font)
        self.displayCheck.setChecked(True)
        self.displayCheck.setObjectName("displayCheck")
        self.gridLayout.addWidget(self.displayCheck, 0, 1, 1, 1)
        self.recordInitCheck = QtWidgets.QCheckBox(self.groupBox)
        font = Qt.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.recordInitCheck.setFont(font)
        self.recordInitCheck.setObjectName("recordInitCheck")
        self.gridLayout.addWidget(self.recordInitCheck, 1, 0, 1, 2)
        spacerItem = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 2, 0, 1, 1)
        self.verticalLayout.addWidget(self.groupBox)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.groupBox.setTitle(_translate("Form", "GroupBox"))
        self.recordCheck.setText(_translate("Form", "Record Trace"))
        self.displayCheck.setText(_translate("Form", "Display"))
        self.recordInitCheck.setText(_translate("Form", "Record Initial State"))

from acq4.pyqtgraph import GroupBox
