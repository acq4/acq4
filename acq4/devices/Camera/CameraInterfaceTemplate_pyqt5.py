# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/devices/Camera/CameraInterfaceTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(161, 72)
        self.verticalLayout = QtWidgets.QVBoxLayout(Form)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout.setSpacing(15)
        self.verticalLayout.setObjectName("verticalLayout")
        self.devCtrlWidget = QtWidgets.QWidget(Form)
        self.devCtrlWidget.setObjectName("devCtrlWidget")
        self.gridLayout_4 = QtWidgets.QGridLayout(self.devCtrlWidget)
        self.gridLayout_4.setContentsMargins(0, 0, 0, 0)
        self.gridLayout_4.setSpacing(0)
        self.gridLayout_4.setObjectName("gridLayout_4")
        self.btnFullFrame = QtWidgets.QPushButton(self.devCtrlWidget)
        self.btnFullFrame.setObjectName("btnFullFrame")
        self.gridLayout_4.addWidget(self.btnFullFrame, 2, 0, 1, 2)
        self.label_3 = QtWidgets.QLabel(self.devCtrlWidget)
        self.label_3.setObjectName("label_3")
        self.gridLayout_4.addWidget(self.label_3, 1, 0, 1, 1)
        self.label_2 = QtWidgets.QLabel(self.devCtrlWidget)
        self.label_2.setObjectName("label_2")
        self.gridLayout_4.addWidget(self.label_2, 0, 0, 1, 1)
        self.spinExposure = SpinBox(self.devCtrlWidget)
        self.spinExposure.setMinimumSize(Qt.QSize(80, 0))
        self.spinExposure.setObjectName("spinExposure")
        self.gridLayout_4.addWidget(self.spinExposure, 1, 1, 1, 1)
        self.binningCombo = QtWidgets.QComboBox(self.devCtrlWidget)
        self.binningCombo.setObjectName("binningCombo")
        self.gridLayout_4.addWidget(self.binningCombo, 0, 1, 1, 1)
        self.verticalLayout.addWidget(self.devCtrlWidget)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.btnFullFrame.setToolTip(_translate("Form", "Set the region of interest to the maximum possible area."))
        self.btnFullFrame.setText(_translate("Form", "Full Frame"))
        self.label_3.setText(_translate("Form", "Exposure"))
        self.label_2.setText(_translate("Form", "Binning"))
        self.spinExposure.setToolTip(_translate("Form", "Sets the exposure time for each frame."))

from acq4.pyqtgraph import SpinBox
