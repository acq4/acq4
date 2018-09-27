# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/modules/Patch/devicePagetemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(210, 159)
        self.gridLayout = QtWidgets.QGridLayout(Form)
        self.gridLayout.setObjectName("gridLayout")
        self.offModeRadio = QtWidgets.QRadioButton(Form)
        self.offModeRadio.setChecked(False)
        self.offModeRadio.setObjectName("offModeRadio")
        self.gridLayout.addWidget(self.offModeRadio, 0, 0, 1, 1)
        self.vcModeRadio = QtWidgets.QRadioButton(Form)
        self.vcModeRadio.setChecked(True)
        self.vcModeRadio.setObjectName("vcModeRadio")
        self.gridLayout.addWidget(self.vcModeRadio, 1, 0, 1, 1)
        self.vcPulseCheck = QtWidgets.QCheckBox(Form)
        self.vcPulseCheck.setChecked(True)
        self.vcPulseCheck.setObjectName("vcPulseCheck")
        self.gridLayout.addWidget(self.vcPulseCheck, 1, 1, 1, 1)
        self.vcPulseSpin = SpinBox(Form)
        self.vcPulseSpin.setObjectName("vcPulseSpin")
        self.gridLayout.addWidget(self.vcPulseSpin, 1, 2, 1, 1)
        self.vcHoldCheck = QtWidgets.QCheckBox(Form)
        self.vcHoldCheck.setObjectName("vcHoldCheck")
        self.gridLayout.addWidget(self.vcHoldCheck, 2, 1, 1, 1)
        self.vcHoldSpin = SpinBox(Form)
        self.vcHoldSpin.setObjectName("vcHoldSpin")
        self.gridLayout.addWidget(self.vcHoldSpin, 2, 2, 1, 1)
        self.icModeRadio = QtWidgets.QRadioButton(Form)
        self.icModeRadio.setObjectName("icModeRadio")
        self.gridLayout.addWidget(self.icModeRadio, 3, 0, 1, 1)
        self.icPulseCheck = QtWidgets.QCheckBox(Form)
        self.icPulseCheck.setChecked(True)
        self.icPulseCheck.setObjectName("icPulseCheck")
        self.gridLayout.addWidget(self.icPulseCheck, 3, 1, 1, 1)
        self.icPulseSpin = SpinBox(Form)
        self.icPulseSpin.setObjectName("icPulseSpin")
        self.gridLayout.addWidget(self.icPulseSpin, 3, 2, 1, 1)
        self.icHoldCheck = QtWidgets.QCheckBox(Form)
        self.icHoldCheck.setObjectName("icHoldCheck")
        self.gridLayout.addWidget(self.icHoldCheck, 4, 1, 1, 1)
        self.icHoldSpin = SpinBox(Form)
        self.icHoldSpin.setObjectName("icHoldSpin")
        self.gridLayout.addWidget(self.icHoldSpin, 4, 2, 1, 1)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.offModeRadio.setText(_translate("Form", "Off"))
        self.vcModeRadio.setText(_translate("Form", "VC"))
        self.vcPulseCheck.setText(_translate("Form", "Pulse"))
        self.vcPulseSpin.setSuffix(_translate("Form", "V"))
        self.vcHoldCheck.setText(_translate("Form", "Hold"))
        self.vcHoldSpin.setSuffix(_translate("Form", "V"))
        self.icModeRadio.setText(_translate("Form", "IC"))
        self.icPulseCheck.setText(_translate("Form", "Pulse"))
        self.icPulseSpin.setSuffix(_translate("Form", "A"))
        self.icHoldCheck.setText(_translate("Form", "Hold"))
        self.icHoldSpin.setSuffix(_translate("Form", "A"))

from acq4.pyqtgraph import SpinBox
