# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/devices/AxoPatch200/devGuiTemplate.ui'
#
# Created: Wed Aug 17 13:49:53 2011
#      by: pyside-uic 0.2.11 running on PySide 1.0.5
#
# WARNING! All changes made in this file will be lost!

from PySide import QtCore, QtGui

class Ui_devGui(object):
    def setupUi(self, devGui):
        devGui.setObjectName("devGui")
        devGui.resize(126, 88)
        self.gridLayout = QtGui.QGridLayout(devGui)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName("gridLayout")
        self.modeCombo = QtGui.QComboBox(devGui)
        self.modeCombo.setObjectName("modeCombo")
        self.modeCombo.addItem("")
        self.modeCombo.addItem("")
        self.modeCombo.addItem("")
        self.modeCombo.addItem("")
        self.modeCombo.addItem("")
        self.gridLayout.addWidget(self.modeCombo, 0, 0, 1, 2)
        self.label = QtGui.QLabel(devGui)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 1, 0, 1, 1)
        self.vcHoldingSpin = SpinBox(devGui)
        self.vcHoldingSpin.setObjectName("vcHoldingSpin")
        self.gridLayout.addWidget(self.vcHoldingSpin, 1, 1, 1, 1)
        self.label_2 = QtGui.QLabel(devGui)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 2, 0, 1, 1)
        self.icHoldingSpin = SpinBox(devGui)
        self.icHoldingSpin.setObjectName("icHoldingSpin")
        self.gridLayout.addWidget(self.icHoldingSpin, 2, 1, 1, 1)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 3, 0, 1, 1)

        self.retranslateUi(devGui)
        QtCore.QMetaObject.connectSlotsByName(devGui)

    def retranslateUi(self, devGui):
        devGui.setWindowTitle(QtGui.QApplication.translate("devGui", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.modeCombo.setItemText(0, QtGui.QApplication.translate("devGui", "V-Clamp", None, QtGui.QApplication.UnicodeUTF8))
        self.modeCombo.setItemText(1, QtGui.QApplication.translate("devGui", "I=0", None, QtGui.QApplication.UnicodeUTF8))
        self.modeCombo.setItemText(2, QtGui.QApplication.translate("devGui", "I-Clamp Normal", None, QtGui.QApplication.UnicodeUTF8))
        self.modeCombo.setItemText(3, QtGui.QApplication.translate("devGui", "I-Clamp Fast", None, QtGui.QApplication.UnicodeUTF8))
        self.modeCombo.setItemText(4, QtGui.QApplication.translate("devGui", "Track", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("devGui", "VC Holding", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("devGui", "IC Holding", None, QtGui.QApplication.UnicodeUTF8))

from SpinBox import SpinBox
