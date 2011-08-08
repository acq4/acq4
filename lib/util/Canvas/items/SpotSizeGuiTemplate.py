# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'SpotSizeGuiTemplate.ui'
#
# Created: Wed Jul 27 09:46:14 2011
#      by: PyQt4 UI code generator 4.8.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    _fromUtf8 = lambda s: s

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName(_fromUtf8("Form"))
        Form.resize(268, 105)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.verticalLayout_2 = QtGui.QVBoxLayout()
        self.verticalLayout_2.setObjectName(_fromUtf8("verticalLayout_2"))
        self.spotSizeLabel = QtGui.QLabel(Form)
        self.spotSizeLabel.setObjectName(_fromUtf8("spotSizeLabel"))
        self.verticalLayout_2.addWidget(self.spotSizeLabel)
        self.sizeFromCalibrationRadio = QtGui.QRadioButton(Form)
        self.sizeFromCalibrationRadio.setChecked(True)
        self.sizeFromCalibrationRadio.setObjectName(_fromUtf8("sizeFromCalibrationRadio"))
        self.verticalLayout_2.addWidget(self.sizeFromCalibrationRadio)
        self.horizontalLayout_2 = QtGui.QHBoxLayout()
        self.horizontalLayout_2.setObjectName(_fromUtf8("horizontalLayout_2"))
        self.sizeCustomRadio = QtGui.QRadioButton(Form)
        self.sizeCustomRadio.setObjectName(_fromUtf8("sizeCustomRadio"))
        self.horizontalLayout_2.addWidget(self.sizeCustomRadio)
        self.sizeSpin = SpinBox(Form)
        self.sizeSpin.setSuffix(_fromUtf8(""))
        self.sizeSpin.setMinimum(0.0)
        self.sizeSpin.setMaximum(100000.0)
        self.sizeSpin.setSingleStep(1e-06)
        self.sizeSpin.setProperty(_fromUtf8("value"), 0.0)
        self.sizeSpin.setObjectName(_fromUtf8("sizeSpin"))
        self.horizontalLayout_2.addWidget(self.sizeSpin)
        self.verticalLayout_2.addLayout(self.horizontalLayout_2)
        self.gridLayout.addLayout(self.verticalLayout_2, 0, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.spotSizeLabel.setText(QtGui.QApplication.translate("Form", "Spot Display Size:", None, QtGui.QApplication.UnicodeUTF8))
        self.sizeFromCalibrationRadio.setText(QtGui.QApplication.translate("Form", "Use size from calibration", None, QtGui.QApplication.UnicodeUTF8))
        self.sizeCustomRadio.setText(QtGui.QApplication.translate("Form", "Use custom size:", None, QtGui.QApplication.UnicodeUTF8))

from SpinBox import SpinBox
