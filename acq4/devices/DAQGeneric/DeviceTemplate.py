# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/devices/DAQGeneric/DeviceTemplate.ui'
#
# Created: Mon Dec 23 22:46:58 2013
#      by: PyQt4 UI code generator 4.10
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
        Form.resize(299, 136)
        self.gridLayout_2 = QtGui.QGridLayout(Form)
        self.gridLayout_2.setMargin(0)
        self.gridLayout_2.setSpacing(0)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.nameLabel = QtGui.QLabel(Form)
        font = QtGui.QFont()
        font.setPointSize(13)
        font.setBold(True)
        font.setWeight(75)
        self.nameLabel.setFont(font)
        self.nameLabel.setObjectName(_fromUtf8("nameLabel"))
        self.gridLayout_2.addWidget(self.nameLabel, 0, 0, 1, 1)
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setSpacing(3)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.horizontalLayout.addWidget(self.label)
        self.channelCombo = QtGui.QComboBox(Form)
        self.channelCombo.setObjectName(_fromUtf8("channelCombo"))
        self.horizontalLayout.addWidget(self.channelCombo)
        self.gridLayout_2.addLayout(self.horizontalLayout, 1, 0, 1, 1)
        self.horizontalLayout_2 = QtGui.QHBoxLayout()
        self.horizontalLayout_2.setSpacing(0)
        self.horizontalLayout_2.setObjectName(_fromUtf8("horizontalLayout_2"))
        self.inputRadio = QtGui.QRadioButton(Form)
        self.inputRadio.setObjectName(_fromUtf8("inputRadio"))
        self.horizontalLayout_2.addWidget(self.inputRadio)
        self.outputRadio = QtGui.QRadioButton(Form)
        self.outputRadio.setObjectName(_fromUtf8("outputRadio"))
        self.horizontalLayout_2.addWidget(self.outputRadio)
        self.gridLayout_2.addLayout(self.horizontalLayout_2, 1, 1, 1, 2)
        spacerItem = QtGui.QSpacerItem(2, 23, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout_2.addItem(spacerItem, 1, 3, 1, 1)
        self.gridLayout = QtGui.QGridLayout()
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.holdingLabel = QtGui.QLabel(Form)
        self.holdingLabel.setObjectName(_fromUtf8("holdingLabel"))
        self.gridLayout.addWidget(self.holdingLabel, 0, 1, 1, 1)
        self.holdingSpin = SpinBox(Form)
        self.holdingSpin.setObjectName(_fromUtf8("holdingSpin"))
        self.gridLayout.addWidget(self.holdingSpin, 0, 2, 1, 1)
        spacerItem1 = QtGui.QSpacerItem(30, 20, QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem1, 1, 0, 1, 1)
        self.scaleLabel = QtGui.QLabel(Form)
        self.scaleLabel.setObjectName(_fromUtf8("scaleLabel"))
        self.gridLayout.addWidget(self.scaleLabel, 1, 1, 1, 1)
        self.scaleSpin = SpinBox(Form)
        self.scaleSpin.setObjectName(_fromUtf8("scaleSpin"))
        self.gridLayout.addWidget(self.scaleSpin, 1, 2, 1, 1)
        self.scaleDefaultBtn = QtGui.QPushButton(Form)
        self.scaleDefaultBtn.setObjectName(_fromUtf8("scaleDefaultBtn"))
        self.gridLayout.addWidget(self.scaleDefaultBtn, 1, 3, 1, 1)
        self.offsetLabel = QtGui.QLabel(Form)
        self.offsetLabel.setObjectName(_fromUtf8("offsetLabel"))
        self.gridLayout.addWidget(self.offsetLabel, 2, 1, 1, 1)
        self.offsetSpin = SpinBox(Form)
        self.offsetSpin.setObjectName(_fromUtf8("offsetSpin"))
        self.gridLayout.addWidget(self.offsetSpin, 2, 2, 1, 1)
        self.offsetDefaultBtn = QtGui.QPushButton(Form)
        self.offsetDefaultBtn.setObjectName(_fromUtf8("offsetDefaultBtn"))
        self.gridLayout.addWidget(self.offsetDefaultBtn, 2, 3, 1, 1)
        self.invertCheck = QtGui.QCheckBox(Form)
        self.invertCheck.setObjectName(_fromUtf8("invertCheck"))
        self.gridLayout.addWidget(self.invertCheck, 0, 3, 1, 1)
        self.gridLayout_2.addLayout(self.gridLayout, 2, 0, 1, 2)
        spacerItem2 = QtGui.QSpacerItem(60, 91, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout_2.addItem(spacerItem2, 2, 2, 1, 2)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.nameLabel.setText(_translate("Form", "ChannelName", None))
        self.label.setText(_translate("Form", "Channel:", None))
        self.inputRadio.setText(_translate("Form", "Input", None))
        self.outputRadio.setText(_translate("Form", "Output", None))
        self.holdingLabel.setText(_translate("Form", "Holding:", None))
        self.scaleLabel.setText(_translate("Form", "Scale:", None))
        self.scaleDefaultBtn.setText(_translate("Form", "Default", None))
        self.offsetLabel.setText(_translate("Form", "Offset:", None))
        self.offsetDefaultBtn.setText(_translate("Form", "Default", None))
        self.invertCheck.setText(_translate("Form", "Invert", None))

from acq4.pyqtgraph import SpinBox
