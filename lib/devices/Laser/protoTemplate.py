# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/devices/Laser/protoTemplate.ui'
#
# Created: Fri Feb 17 15:44:36 2012
#      by: PyQt4 UI code generator 4.9.1
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
        Form.resize(218, 190)
        self.gridLayout_2 = QtGui.QGridLayout(Form)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout_2.addWidget(self.label_2, 0, 0, 1, 1)
        self.outputPowerLabel = QtGui.QLabel(Form)
        self.outputPowerLabel.setObjectName(_fromUtf8("outputPowerLabel"))
        self.gridLayout_2.addWidget(self.outputPowerLabel, 0, 1, 1, 1)
        self.checkPowerBtn = QtGui.QPushButton(Form)
        self.checkPowerBtn.setObjectName(_fromUtf8("checkPowerBtn"))
        self.gridLayout_2.addWidget(self.checkPowerBtn, 0, 2, 1, 1)
        self.label_3 = QtGui.QLabel(Form)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.label_3.setFont(font)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout_2.addWidget(self.label_3, 1, 0, 1, 1)
        self.samplePowerLabel = QtGui.QLabel(Form)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.samplePowerLabel.setFont(font)
        self.samplePowerLabel.setObjectName(_fromUtf8("samplePowerLabel"))
        self.gridLayout_2.addWidget(self.samplePowerLabel, 1, 1, 1, 1)
        self.wavelengthWidget = QtGui.QWidget(Form)
        self.wavelengthWidget.setObjectName(_fromUtf8("wavelengthWidget"))
        self.horizontalLayout = QtGui.QHBoxLayout(self.wavelengthWidget)
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setMargin(0)
        self.horizontalLayout.setMargin(0)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.setWavelengthCheck = QtGui.QCheckBox(self.wavelengthWidget)
        self.setWavelengthCheck.setObjectName(_fromUtf8("setWavelengthCheck"))
        self.horizontalLayout.addWidget(self.setWavelengthCheck)
        self.wavelengthSpin = QtGui.QSpinBox(self.wavelengthWidget)
        self.wavelengthSpin.setMaximum(4000)
        self.wavelengthSpin.setSingleStep(10)
        self.wavelengthSpin.setProperty("value", 1080)
        self.wavelengthSpin.setObjectName(_fromUtf8("wavelengthSpin"))
        self.horizontalLayout.addWidget(self.wavelengthSpin)
        self.gridLayout_2.addWidget(self.wavelengthWidget, 4, 0, 1, 3)
        self.groupBox = QtGui.QGroupBox(Form)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout = QtGui.QGridLayout(self.groupBox)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setContentsMargins(3, 0, 3, 3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.powerWaveRadio = QtGui.QRadioButton(self.groupBox)
        self.powerWaveRadio.setChecked(True)
        self.powerWaveRadio.setObjectName(_fromUtf8("powerWaveRadio"))
        self.gridLayout.addWidget(self.powerWaveRadio, 0, 0, 1, 1)
        self.switchWaveRadio = QtGui.QRadioButton(self.groupBox)
        self.switchWaveRadio.setObjectName(_fromUtf8("switchWaveRadio"))
        self.gridLayout.addWidget(self.switchWaveRadio, 1, 0, 1, 1)
        self.gridLayout_2.addWidget(self.groupBox, 5, 0, 1, 3)
        self.adjustLengthCheck = QtGui.QCheckBox(Form)
        self.adjustLengthCheck.setChecked(True)
        self.adjustLengthCheck.setTristate(False)
        self.adjustLengthCheck.setObjectName(_fromUtf8("adjustLengthCheck"))
        self.gridLayout_2.addWidget(self.adjustLengthCheck, 3, 0, 1, 3)
        self.checkPowerCheck = QtGui.QCheckBox(Form)
        self.checkPowerCheck.setChecked(True)
        self.checkPowerCheck.setObjectName(_fromUtf8("checkPowerCheck"))
        self.gridLayout_2.addWidget(self.checkPowerCheck, 2, 0, 1, 3)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "Output Power:", None, QtGui.QApplication.UnicodeUTF8))
        self.outputPowerLabel.setText(QtGui.QApplication.translate("Form", "0mW", None, QtGui.QApplication.UnicodeUTF8))
        self.checkPowerBtn.setText(QtGui.QApplication.translate("Form", "Check Power", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("Form", "Power at Sample:", None, QtGui.QApplication.UnicodeUTF8))
        self.samplePowerLabel.setText(QtGui.QApplication.translate("Form", "0mW", None, QtGui.QApplication.UnicodeUTF8))
        self.setWavelengthCheck.setText(QtGui.QApplication.translate("Form", "Set wavelength", None, QtGui.QApplication.UnicodeUTF8))
        self.wavelengthSpin.setSuffix(QtGui.QApplication.translate("Form", " nm", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox.setTitle(QtGui.QApplication.translate("Form", "Control Mode:", None, QtGui.QApplication.UnicodeUTF8))
        self.powerWaveRadio.setText(QtGui.QApplication.translate("Form", "Power waveform (W)", None, QtGui.QApplication.UnicodeUTF8))
        self.switchWaveRadio.setText(QtGui.QApplication.translate("Form", "Switch waveform (%)", None, QtGui.QApplication.UnicodeUTF8))
        self.adjustLengthCheck.setToolTip(QtGui.QApplication.translate("Form", "If the output power of the laser changes, adjust the length of laser pulses to maintain constant pulse energy.", None, QtGui.QApplication.UnicodeUTF8))
        self.adjustLengthCheck.setText(QtGui.QApplication.translate("Form", "Adjust pulse length if power changes", None, QtGui.QApplication.UnicodeUTF8))
        self.checkPowerCheck.setText(QtGui.QApplication.translate("Form", "Check power before protocol start", None, QtGui.QApplication.UnicodeUTF8))

