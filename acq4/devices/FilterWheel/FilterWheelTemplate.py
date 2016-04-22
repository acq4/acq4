# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\FilterWheelTemplate.ui'
#
# Created by: PyQt4 UI code generator 4.11.4
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

class Ui_FilterWheelWidget(object):
    def setupUi(self, FilterWheelWidget):
        FilterWheelWidget.setObjectName(_fromUtf8("FilterWheelWidget"))
        FilterWheelWidget.resize(262, 194)
        self.gridLayout = QtGui.QGridLayout(FilterWheelWidget)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.FastButton = QtGui.QRadioButton(FilterWheelWidget)
        self.FastButton.setObjectName(_fromUtf8("FastButton"))
        self.SpeedButtonGroup = QtGui.QButtonGroup(FilterWheelWidget)
        self.SpeedButtonGroup.setObjectName(_fromUtf8("SpeedButtonGroup"))
        self.SpeedButtonGroup.addButton(self.FastButton)
        self.gridLayout.addWidget(self.FastButton, 0, 2, 1, 1)
        self.inputTrigButton = QtGui.QRadioButton(FilterWheelWidget)
        self.inputTrigButton.setObjectName(_fromUtf8("inputTrigButton"))
        self.TriggerButtonGroup = QtGui.QButtonGroup(FilterWheelWidget)
        self.TriggerButtonGroup.setObjectName(_fromUtf8("TriggerButtonGroup"))
        self.TriggerButtonGroup.addButton(self.inputTrigButton)
        self.gridLayout.addWidget(self.inputTrigButton, 1, 1, 1, 1)
        self.label_3 = QtGui.QLabel(FilterWheelWidget)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label_3.setFont(font)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout.addWidget(self.label_3, 1, 0, 1, 1)
        self.label = QtGui.QLabel(FilterWheelWidget)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label.setFont(font)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.SlowButton = QtGui.QRadioButton(FilterWheelWidget)
        self.SlowButton.setObjectName(_fromUtf8("SlowButton"))
        self.SpeedButtonGroup.addButton(self.SlowButton)
        self.gridLayout.addWidget(self.SlowButton, 0, 1, 1, 1)
        self.outputTrigButton = QtGui.QRadioButton(FilterWheelWidget)
        self.outputTrigButton.setObjectName(_fromUtf8("outputTrigButton"))
        self.TriggerButtonGroup.addButton(self.outputTrigButton)
        self.gridLayout.addWidget(self.outputTrigButton, 1, 2, 1, 1)
        self.PositionGroup = QtGui.QGroupBox(FilterWheelWidget)
        self.PositionGroup.setObjectName(_fromUtf8("PositionGroup"))
        self.PositionGridLayout = QtGui.QGridLayout(self.PositionGroup)
        self.PositionGridLayout.setObjectName(_fromUtf8("PositionGridLayout"))
        self.gridLayout.addWidget(self.PositionGroup, 2, 0, 1, 3)

        self.retranslateUi(FilterWheelWidget)
        QtCore.QMetaObject.connectSlotsByName(FilterWheelWidget)

    def retranslateUi(self, FilterWheelWidget):
        FilterWheelWidget.setWindowTitle(_translate("FilterWheelWidget", "Form", None))
        self.FastButton.setText(_translate("FilterWheelWidget", "fast", None))
        self.inputTrigButton.setText(_translate("FilterWheelWidget", "input", None))
        self.label_3.setText(_translate("FilterWheelWidget", "Trigger Mode", None))
        self.label.setText(_translate("FilterWheelWidget", "Speed", None))
        self.SlowButton.setText(_translate("FilterWheelWidget", "slow", None))
        self.outputTrigButton.setText(_translate("FilterWheelWidget", "output", None))
        self.PositionGroup.setTitle(_translate("FilterWheelWidget", "Current Position", None))

