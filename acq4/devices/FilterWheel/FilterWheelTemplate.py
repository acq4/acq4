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
        FilterWheelWidget.resize(304, 188)
        self.verticalLayout = QtGui.QVBoxLayout(FilterWheelWidget)
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.FilterWheelControlGroup = QtGui.QGroupBox(FilterWheelWidget)
        self.FilterWheelControlGroup.setObjectName(_fromUtf8("FilterWheelControlGroup"))
        self.gridLayout_12 = QtGui.QGridLayout(self.FilterWheelControlGroup)
        self.gridLayout_12.setObjectName(_fromUtf8("gridLayout_12"))
        self.outputTrigButton = QtGui.QRadioButton(self.FilterWheelControlGroup)
        self.outputTrigButton.setObjectName(_fromUtf8("outputTrigButton"))
        self.TriggerButtonGroup = QtGui.QButtonGroup(FilterWheelWidget)
        self.TriggerButtonGroup.setObjectName(_fromUtf8("TriggerButtonGroup"))
        self.TriggerButtonGroup.addButton(self.outputTrigButton)
        self.gridLayout_12.addWidget(self.outputTrigButton, 1, 2, 1, 1)
        self.PositionGroup = QtGui.QGroupBox(self.FilterWheelControlGroup)
        self.PositionGroup.setObjectName(_fromUtf8("PositionGroup"))
        self.gridLayout_11 = QtGui.QGridLayout(self.PositionGroup)
        self.gridLayout_11.setObjectName(_fromUtf8("gridLayout_11"))
        self.gridLayout_12.addWidget(self.PositionGroup, 2, 0, 1, 3)
        self.inputTrigButton = QtGui.QRadioButton(self.FilterWheelControlGroup)
        self.inputTrigButton.setObjectName(_fromUtf8("inputTrigButton"))
        self.TriggerButtonGroup.addButton(self.inputTrigButton)
        self.gridLayout_12.addWidget(self.inputTrigButton, 1, 1, 1, 1)
        self.label = QtGui.QLabel(self.FilterWheelControlGroup)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label.setFont(font)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout_12.addWidget(self.label, 0, 0, 1, 1)
        self.label_3 = QtGui.QLabel(self.FilterWheelControlGroup)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label_3.setFont(font)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout_12.addWidget(self.label_3, 1, 0, 1, 1)
        self.SlowButton = QtGui.QRadioButton(self.FilterWheelControlGroup)
        self.SlowButton.setObjectName(_fromUtf8("SlowButton"))
        self.SpeedButtonGroup = QtGui.QButtonGroup(FilterWheelWidget)
        self.SpeedButtonGroup.setObjectName(_fromUtf8("SpeedButtonGroup"))
        self.SpeedButtonGroup.addButton(self.SlowButton)
        self.gridLayout_12.addWidget(self.SlowButton, 0, 1, 1, 1)
        self.FastButton = QtGui.QRadioButton(self.FilterWheelControlGroup)
        self.FastButton.setObjectName(_fromUtf8("FastButton"))
        self.SpeedButtonGroup.addButton(self.FastButton)
        self.gridLayout_12.addWidget(self.FastButton, 0, 2, 1, 1)
        self.verticalLayout.addWidget(self.FilterWheelControlGroup)

        self.retranslateUi(FilterWheelWidget)
        QtCore.QMetaObject.connectSlotsByName(FilterWheelWidget)

    def retranslateUi(self, FilterWheelWidget):
        FilterWheelWidget.setWindowTitle(_translate("FilterWheelWidget", "Form", None))
        self.FilterWheelControlGroup.setTitle(_translate("FilterWheelWidget", "Thorlabs Filter Wheel Control", None))
        self.outputTrigButton.setText(_translate("FilterWheelWidget", "output", None))
        self.PositionGroup.setTitle(_translate("FilterWheelWidget", "Current Position", None))
        self.inputTrigButton.setText(_translate("FilterWheelWidget", "input", None))
        self.label.setText(_translate("FilterWheelWidget", "Speed", None))
        self.label_3.setText(_translate("FilterWheelWidget", "Trigger Mode", None))
        self.SlowButton.setText(_translate("FilterWheelWidget", "slow", None))
        self.FastButton.setText(_translate("FilterWheelWidget", "fast", None))

