# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'DOChannelTemplate.ui'
#
# Created: Fri Dec  1 15:18:39 2017
#      by: PyQt4 UI code generator 4.11.3
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
        Form.resize(321, 218)
        self.verticalLayout_3 = QtGui.QVBoxLayout(Form)
        self.verticalLayout_3.setSpacing(0)
        self.verticalLayout_3.setMargin(0)
        self.verticalLayout_3.setObjectName(_fromUtf8("verticalLayout_3"))
        self.groupBox = GroupBox(Form)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.groupBox.setFont(font)
        self.groupBox.setTitle(_fromUtf8(""))
        self.groupBox.setCheckable(False)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.verticalLayout_2 = QtGui.QVBoxLayout(self.groupBox)
        self.verticalLayout_2.setSpacing(0)
        self.verticalLayout_2.setContentsMargins(5, 0, 0, 0)
        self.verticalLayout_2.setObjectName(_fromUtf8("verticalLayout_2"))
        self.gridLayout = QtGui.QGridLayout()
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.preSetCheck = QtGui.QCheckBox(self.groupBox)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.preSetCheck.setFont(font)
        self.preSetCheck.setObjectName(_fromUtf8("preSetCheck"))
        self.gridLayout.addWidget(self.preSetCheck, 0, 0, 1, 1)
        self.holdingCheck = QtGui.QCheckBox(self.groupBox)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.holdingCheck.setFont(font)
        self.holdingCheck.setObjectName(_fromUtf8("holdingCheck"))
        self.gridLayout.addWidget(self.holdingCheck, 1, 0, 1, 1)
        self.preSetSpin = QtGui.QSpinBox(self.groupBox)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.preSetSpin.setFont(font)
        self.preSetSpin.setMaximum(1)
        self.preSetSpin.setObjectName(_fromUtf8("preSetSpin"))
        self.gridLayout.addWidget(self.preSetSpin, 0, 1, 1, 1)
        self.holdingSpin = QtGui.QSpinBox(self.groupBox)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.holdingSpin.setFont(font)
        self.holdingSpin.setMaximum(1)
        self.holdingSpin.setObjectName(_fromUtf8("holdingSpin"))
        self.gridLayout.addWidget(self.holdingSpin, 1, 1, 1, 1)
        self.verticalLayout_2.addLayout(self.gridLayout)
        self.frame = QtGui.QFrame(self.groupBox)
        self.frame.setFrameShape(QtGui.QFrame.Box)
        self.frame.setFrameShadow(QtGui.QFrame.Raised)
        self.frame.setObjectName(_fromUtf8("frame"))
        self.verticalLayout = QtGui.QVBoxLayout(self.frame)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.functionCheck = QtGui.QCheckBox(self.frame)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.functionCheck.setFont(font)
        self.functionCheck.setObjectName(_fromUtf8("functionCheck"))
        self.horizontalLayout.addWidget(self.functionCheck)
        self.displayCheck = QtGui.QCheckBox(self.frame)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.displayCheck.setFont(font)
        self.displayCheck.setChecked(True)
        self.displayCheck.setObjectName(_fromUtf8("displayCheck"))
        self.horizontalLayout.addWidget(self.displayCheck)
        self.storeWaveCheck = QtGui.QCheckBox(self.frame)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.storeWaveCheck.setFont(font)
        self.storeWaveCheck.setChecked(True)
        self.storeWaveCheck.setObjectName(_fromUtf8("storeWaveCheck"))
        self.horizontalLayout.addWidget(self.storeWaveCheck)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.waveGeneratorWidget = StimGenerator(self.frame)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.waveGeneratorWidget.sizePolicy().hasHeightForWidth())
        self.waveGeneratorWidget.setSizePolicy(sizePolicy)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.waveGeneratorWidget.setFont(font)
        self.waveGeneratorWidget.setObjectName(_fromUtf8("waveGeneratorWidget"))
        self.verticalLayout.addWidget(self.waveGeneratorWidget)
        self.verticalLayout_2.addWidget(self.frame)
        self.verticalLayout_3.addWidget(self.groupBox)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.preSetCheck.setText(_translate("Form", "Pre-set", None))
        self.holdingCheck.setText(_translate("Form", "Holding", None))
        self.functionCheck.setText(_translate("Form", "Enable Function", None))
        self.displayCheck.setText(_translate("Form", "Display", None))
        self.storeWaveCheck.setText(_translate("Form", "Store Waveform", None))

from acq4.pyqtgraph import GroupBox
from acq4.util.generator.StimGenerator import StimGenerator
