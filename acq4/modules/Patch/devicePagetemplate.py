# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\acq4\modules\Patch\devicePagetemplate.ui'
#
# Created: Thu Jan 15 20:16:09 2015
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
        Form.resize(210, 159)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.offModeRadio = QtGui.QRadioButton(Form)
        self.offModeRadio.setChecked(False)
        self.offModeRadio.setObjectName(_fromUtf8("offModeRadio"))
        self.gridLayout.addWidget(self.offModeRadio, 0, 0, 1, 1)
        self.vcModeRadio = QtGui.QRadioButton(Form)
        self.vcModeRadio.setChecked(True)
        self.vcModeRadio.setObjectName(_fromUtf8("vcModeRadio"))
        self.gridLayout.addWidget(self.vcModeRadio, 1, 0, 1, 1)
        self.vcPulseCheck = QtGui.QCheckBox(Form)
        self.vcPulseCheck.setChecked(True)
        self.vcPulseCheck.setObjectName(_fromUtf8("vcPulseCheck"))
        self.gridLayout.addWidget(self.vcPulseCheck, 1, 1, 1, 1)
        self.vcPulseSpin = SpinBox(Form)
        self.vcPulseSpin.setObjectName(_fromUtf8("vcPulseSpin"))
        self.gridLayout.addWidget(self.vcPulseSpin, 1, 2, 1, 1)
        self.vcHoldCheck = QtGui.QCheckBox(Form)
        self.vcHoldCheck.setObjectName(_fromUtf8("vcHoldCheck"))
        self.gridLayout.addWidget(self.vcHoldCheck, 2, 1, 1, 1)
        self.vcHoldSpin = SpinBox(Form)
        self.vcHoldSpin.setObjectName(_fromUtf8("vcHoldSpin"))
        self.gridLayout.addWidget(self.vcHoldSpin, 2, 2, 1, 1)
        self.icModeRadio = QtGui.QRadioButton(Form)
        self.icModeRadio.setObjectName(_fromUtf8("icModeRadio"))
        self.gridLayout.addWidget(self.icModeRadio, 3, 0, 1, 1)
        self.icPulseCheck = QtGui.QCheckBox(Form)
        self.icPulseCheck.setChecked(True)
        self.icPulseCheck.setObjectName(_fromUtf8("icPulseCheck"))
        self.gridLayout.addWidget(self.icPulseCheck, 3, 1, 1, 1)
        self.icPulseSpin = SpinBox(Form)
        self.icPulseSpin.setObjectName(_fromUtf8("icPulseSpin"))
        self.gridLayout.addWidget(self.icPulseSpin, 3, 2, 1, 1)
        self.icHoldCheck = QtGui.QCheckBox(Form)
        self.icHoldCheck.setObjectName(_fromUtf8("icHoldCheck"))
        self.gridLayout.addWidget(self.icHoldCheck, 4, 1, 1, 1)
        self.icHoldSpin = SpinBox(Form)
        self.icHoldSpin.setObjectName(_fromUtf8("icHoldSpin"))
        self.gridLayout.addWidget(self.icHoldSpin, 4, 2, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.offModeRadio.setText(_translate("Form", "Off", None))
        self.vcModeRadio.setText(_translate("Form", "VC", None))
        self.vcPulseCheck.setText(_translate("Form", "Pulse", None))
        self.vcPulseSpin.setSuffix(_translate("Form", "V", None))
        self.vcHoldCheck.setText(_translate("Form", "Hold", None))
        self.vcHoldSpin.setSuffix(_translate("Form", "V", None))
        self.icModeRadio.setText(_translate("Form", "IC", None))
        self.icPulseCheck.setText(_translate("Form", "Pulse", None))
        self.icPulseSpin.setSuffix(_translate("Form", "A", None))
        self.icHoldCheck.setText(_translate("Form", "Hold", None))
        self.icHoldSpin.setSuffix(_translate("Form", "A", None))

from acq4.pyqtgraph import SpinBox
