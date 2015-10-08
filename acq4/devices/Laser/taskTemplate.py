# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\taskTemplate.ui'
#
# Created: Thu Oct 08 16:48:34 2015
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
        Form.resize(218, 236)
        self.gridLayout_2 = QtGui.QGridLayout(Form)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
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
        self.wavelengthWidget = QtGui.QWidget(Form)
        self.wavelengthWidget.setObjectName(_fromUtf8("wavelengthWidget"))
        self.horizontalLayout = QtGui.QHBoxLayout(self.wavelengthWidget)
        self.horizontalLayout.setSpacing(0)
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
        self.adjustLengthCheck = QtGui.QCheckBox(Form)
        self.adjustLengthCheck.setChecked(True)
        self.adjustLengthCheck.setTristate(False)
        self.adjustLengthCheck.setObjectName(_fromUtf8("adjustLengthCheck"))
        self.gridLayout_2.addWidget(self.adjustLengthCheck, 3, 0, 1, 3)
        self.checkPowerCheck = QtGui.QCheckBox(Form)
        self.checkPowerCheck.setChecked(True)
        self.checkPowerCheck.setObjectName(_fromUtf8("checkPowerCheck"))
        self.gridLayout_2.addWidget(self.checkPowerCheck, 2, 0, 1, 3)
        self.releaseBetweenTasks = QtGui.QRadioButton(Form)
        self.releaseBetweenTasks.setObjectName(_fromUtf8("releaseBetweenTasks"))
        self.releaseButtonGroup = QtGui.QButtonGroup(Form)
        self.releaseButtonGroup.setObjectName(_fromUtf8("releaseButtonGroup"))
        self.releaseButtonGroup.addButton(self.releaseBetweenTasks)
        self.gridLayout_2.addWidget(self.releaseBetweenTasks, 6, 0, 1, 3)
        self.releaseAfterSequence = QtGui.QRadioButton(Form)
        self.releaseAfterSequence.setChecked(True)
        self.releaseAfterSequence.setObjectName(_fromUtf8("releaseAfterSequence"))
        self.releaseButtonGroup.addButton(self.releaseAfterSequence)
        self.gridLayout_2.addWidget(self.releaseAfterSequence, 7, 0, 1, 3)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.groupBox.setTitle(_translate("Form", "Control Mode:", None))
        self.powerWaveRadio.setText(_translate("Form", "Power waveform (W)", None))
        self.switchWaveRadio.setText(_translate("Form", "Switch waveform (%)", None))
        self.setWavelengthCheck.setText(_translate("Form", "Set wavelength", None))
        self.wavelengthSpin.setSuffix(_translate("Form", " nm", None))
        self.label_2.setText(_translate("Form", "Output Power:", None))
        self.outputPowerLabel.setText(_translate("Form", "0mW", None))
        self.checkPowerBtn.setText(_translate("Form", "Check Power", None))
        self.label_3.setText(_translate("Form", "Power at Sample:", None))
        self.samplePowerLabel.setText(_translate("Form", "0mW", None))
        self.adjustLengthCheck.setToolTip(_translate("Form", "If the output power of the laser changes, adjust the length of laser pulses to maintain constant pulse energy.", None))
        self.adjustLengthCheck.setText(_translate("Form", "Adjust pulse length if power changes", None))
        self.checkPowerCheck.setText(_translate("Form", "Check power before task start", None))
        self.releaseBetweenTasks.setText(_translate("Form", "Release between tasks", None))
        self.releaseAfterSequence.setText(_translate("Form", "Release after sequence", None))

