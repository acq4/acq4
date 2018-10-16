# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/devices/MultiClamp/RackTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(259, 117)
        self.horizontalLayout = QtWidgets.QHBoxLayout(Form)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.gridLayout_2 = QtWidgets.QGridLayout()
        self.gridLayout_2.setObjectName("gridLayout_2")
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.gridLayout_2.addItem(spacerItem, 1, 2, 1, 1)
        self.vcHoldingLabel = QtWidgets.QLabel(Form)
        self.vcHoldingLabel.setText("")
        self.vcHoldingLabel.setObjectName("vcHoldingLabel")
        self.gridLayout_2.addWidget(self.vcHoldingLabel, 3, 2, 1, 1)
        self.icHoldingSpin = SpinBox(Form)
        self.icHoldingSpin.setMaximumSize(Qt.QSize(150, 16777215))
        self.icHoldingSpin.setObjectName("icHoldingSpin")
        self.gridLayout_2.addWidget(self.icHoldingSpin, 4, 1, 1, 1)
        self.label_6 = QtWidgets.QLabel(Form)
        self.label_6.setObjectName("label_6")
        self.gridLayout_2.addWidget(self.label_6, 0, 0, 1, 1)
        self.label = QtWidgets.QLabel(Form)
        self.label.setObjectName("label")
        self.gridLayout_2.addWidget(self.label, 1, 0, 1, 1)
        self.channelLabel = QtWidgets.QLabel(Form)
        self.channelLabel.setText("")
        self.channelLabel.setObjectName("channelLabel")
        self.gridLayout_2.addWidget(self.channelLabel, 0, 2, 1, 1)
        self.label_3 = QtWidgets.QLabel(Form)
        self.label_3.setObjectName("label_3")
        self.gridLayout_2.addWidget(self.label_3, 4, 0, 1, 1)
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.vcRadio = QtWidgets.QRadioButton(Form)
        self.vcRadio.setObjectName("vcRadio")
        self.horizontalLayout_2.addWidget(self.vcRadio)
        self.i0Radio = QtWidgets.QRadioButton(Form)
        self.i0Radio.setObjectName("i0Radio")
        self.horizontalLayout_2.addWidget(self.i0Radio)
        self.icRadio = QtWidgets.QRadioButton(Form)
        self.icRadio.setObjectName("icRadio")
        self.horizontalLayout_2.addWidget(self.icRadio)
        self.gridLayout_2.addLayout(self.horizontalLayout_2, 1, 1, 1, 1)
        self.label_2 = QtWidgets.QLabel(Form)
        self.label_2.setObjectName("label_2")
        self.gridLayout_2.addWidget(self.label_2, 3, 0, 1, 1)
        self.vcHoldingSpin = SpinBox(Form)
        self.vcHoldingSpin.setMaximumSize(Qt.QSize(150, 16777215))
        self.vcHoldingSpin.setObjectName("vcHoldingSpin")
        self.gridLayout_2.addWidget(self.vcHoldingSpin, 3, 1, 1, 1)
        self.icHoldingLabel = QtWidgets.QLabel(Form)
        self.icHoldingLabel.setText("")
        self.icHoldingLabel.setObjectName("icHoldingLabel")
        self.gridLayout_2.addWidget(self.icHoldingLabel, 4, 2, 1, 1)
        spacerItem1 = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.gridLayout_2.addItem(spacerItem1, 5, 0, 1, 1)
        self.horizontalLayout.addLayout(self.gridLayout_2)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.label_6.setText(_translate("Form", "MultiClamp Channel:"))
        self.label.setText(_translate("Form", "Mode:"))
        self.label_3.setText(_translate("Form", "IC Holding:"))
        self.vcRadio.setText(_translate("Form", "VC"))
        self.i0Radio.setText(_translate("Form", "I=0"))
        self.icRadio.setText(_translate("Form", "IC"))
        self.label_2.setText(_translate("Form", "VC Holding:"))

from acq4.pyqtgraph import SpinBox
