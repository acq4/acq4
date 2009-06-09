# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'AOChannelTemplate.ui'
#
# Created: Tue Jun 09 14:00:09 2009
#      by: PyQt4 UI code generator 4.4.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(370, 310)
        self.verticalLayout_2 = QtGui.QVBoxLayout(Form)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.gridLayout = QtGui.QGridLayout()
        self.gridLayout.setObjectName("gridLayout")
        self.preSetCheck = QtGui.QCheckBox(Form)
        self.preSetCheck.setObjectName("preSetCheck")
        self.gridLayout.addWidget(self.preSetCheck, 0, 0, 1, 1)
        self.preSetSpin = QtGui.QDoubleSpinBox(Form)
        self.preSetSpin.setObjectName("preSetSpin")
        self.gridLayout.addWidget(self.preSetSpin, 0, 1, 1, 1)
        self.holdingCheck = QtGui.QCheckBox(Form)
        self.holdingCheck.setObjectName("holdingCheck")
        self.gridLayout.addWidget(self.holdingCheck, 1, 0, 1, 1)
        self.holdingSpin = QtGui.QDoubleSpinBox(Form)
        self.holdingSpin.setObjectName("holdingSpin")
        self.gridLayout.addWidget(self.holdingSpin, 1, 1, 1, 1)
        self.verticalLayout_2.addLayout(self.gridLayout)
        self.frame = QtGui.QFrame(Form)
        self.frame.setFrameShape(QtGui.QFrame.Box)
        self.frame.setFrameShadow(QtGui.QFrame.Raised)
        self.frame.setObjectName("frame")
        self.verticalLayout = QtGui.QVBoxLayout(self.frame)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.functionCheck = QtGui.QCheckBox(self.frame)
        self.functionCheck.setObjectName("functionCheck")
        self.horizontalLayout.addWidget(self.functionCheck)
        self.displayCheck = QtGui.QCheckBox(self.frame)
        self.displayCheck.setChecked(True)
        self.displayCheck.setObjectName("displayCheck")
        self.horizontalLayout.addWidget(self.displayCheck)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.waveGeneratorWidget = StimGenerator(self.frame)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.waveGeneratorWidget.sizePolicy().hasHeightForWidth())
        self.waveGeneratorWidget.setSizePolicy(sizePolicy)
        self.waveGeneratorWidget.setObjectName("waveGeneratorWidget")
        self.verticalLayout.addWidget(self.waveGeneratorWidget)
        self.verticalLayout_2.addWidget(self.frame)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.preSetCheck.setText(QtGui.QApplication.translate("Form", "Pre-set", None, QtGui.QApplication.UnicodeUTF8))
        self.holdingCheck.setText(QtGui.QApplication.translate("Form", "Holding", None, QtGui.QApplication.UnicodeUTF8))
        self.functionCheck.setText(QtGui.QApplication.translate("Form", "Enable Function", None, QtGui.QApplication.UnicodeUTF8))
        self.displayCheck.setText(QtGui.QApplication.translate("Form", "Display", None, QtGui.QApplication.UnicodeUTF8))

from lib.util.generator.StimGenerator import StimGenerator
