# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'protoTemplate.ui'
#
# Created: Wed Sep 28 12:46:12 2011
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
        Form.resize(494, 343)
        self.groupBox = QtGui.QGroupBox(Form)
        self.groupBox.setGeometry(QtCore.QRect(10, 30, 171, 108))
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout = QtGui.QGridLayout(self.groupBox)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.powerWaveRadio = QtGui.QRadioButton(self.groupBox)
        self.powerWaveRadio.setChecked(True)
        self.powerWaveRadio.setObjectName(_fromUtf8("powerWaveRadio"))
        self.gridLayout.addWidget(self.powerWaveRadio, 0, 0, 1, 1)
        self.switchWaveRadio = QtGui.QRadioButton(self.groupBox)
        self.switchWaveRadio.setObjectName(_fromUtf8("switchWaveRadio"))
        self.gridLayout.addWidget(self.switchWaveRadio, 1, 0, 1, 1)
        self.pulseWaveRadio = QtGui.QRadioButton(self.groupBox)
        self.pulseWaveRadio.setObjectName(_fromUtf8("pulseWaveRadio"))
        self.gridLayout.addWidget(self.pulseWaveRadio, 2, 0, 1, 1)
        self.pulseTable = QtGui.QTreeWidget(Form)
        self.pulseTable.setGeometry(QtCore.QRect(10, 230, 461, 101))
        self.pulseTable.setObjectName(_fromUtf8("pulseTable"))
        self.wavelengthBox = QtGui.QWidget(Form)
        self.wavelengthBox.setGeometry(QtCore.QRect(10, 0, 147, 25))
        self.wavelengthBox.setObjectName(_fromUtf8("wavelengthBox"))
        self.horizontalLayout = QtGui.QHBoxLayout(self.wavelengthBox)
        self.horizontalLayout.setMargin(0)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.label = QtGui.QLabel(self.wavelengthBox)
        self.label.setObjectName(_fromUtf8("label"))
        self.horizontalLayout.addWidget(self.label)
        self.spinBox = QtGui.QSpinBox(self.wavelengthBox)
        self.spinBox.setMaximum(4000)
        self.spinBox.setProperty(_fromUtf8("value"), 1080)
        self.spinBox.setObjectName(_fromUtf8("spinBox"))
        self.horizontalLayout.addWidget(self.spinBox)
        self.groupBox_2 = QtGui.QGroupBox(Form)
        self.groupBox_2.setGeometry(QtCore.QRect(10, 150, 171, 83))
        self.groupBox_2.setObjectName(_fromUtf8("groupBox_2"))
        self.gridLayout_2 = QtGui.QGridLayout(self.groupBox_2)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.radioButton = QtGui.QRadioButton(self.groupBox_2)
        self.radioButton.setObjectName(_fromUtf8("radioButton"))
        self.gridLayout_2.addWidget(self.radioButton, 0, 0, 1, 1)
        self.radioButton_2 = QtGui.QRadioButton(self.groupBox_2)
        self.radioButton_2.setObjectName(_fromUtf8("radioButton_2"))
        self.gridLayout_2.addWidget(self.radioButton_2, 1, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox.setTitle(QtGui.QApplication.translate("Form", "Control Mode:", None, QtGui.QApplication.UnicodeUTF8))
        self.powerWaveRadio.setText(QtGui.QApplication.translate("Form", "Power waveform (mW)", None, QtGui.QApplication.UnicodeUTF8))
        self.switchWaveRadio.setText(QtGui.QApplication.translate("Form", "Switch Waveform (1/0)", None, QtGui.QApplication.UnicodeUTF8))
        self.pulseWaveRadio.setText(QtGui.QApplication.translate("Form", "Pulses", None, QtGui.QApplication.UnicodeUTF8))
        self.pulseTable.headerItem().setText(0, QtGui.QApplication.translate("Form", "Start (ms)", None, QtGui.QApplication.UnicodeUTF8))
        self.pulseTable.headerItem().setText(1, QtGui.QApplication.translate("Form", "Duration (ms)", None, QtGui.QApplication.UnicodeUTF8))
        self.pulseTable.headerItem().setText(2, QtGui.QApplication.translate("Form", "Power (mW)", None, QtGui.QApplication.UnicodeUTF8))
        self.pulseTable.headerItem().setText(3, QtGui.QApplication.translate("Form", "Energy (pJ)", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Wavelength", None, QtGui.QApplication.UnicodeUTF8))
        self.spinBox.setSuffix(QtGui.QApplication.translate("Form", " nm", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_2.setTitle(QtGui.QApplication.translate("Form", "Power Mode:", None, QtGui.QApplication.UnicodeUTF8))
        self.radioButton.setText(QtGui.QApplication.translate("Form", "Analog", None, QtGui.QApplication.UnicodeUTF8))
        self.radioButton_2.setText(QtGui.QApplication.translate("Form", "PWM", None, QtGui.QApplication.UnicodeUTF8))

