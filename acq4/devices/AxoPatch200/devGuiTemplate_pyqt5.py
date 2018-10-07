# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/devices/AxoPatch200/devGuiTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_devGui(object):
    def setupUi(self, devGui):
        devGui.setObjectName("devGui")
        devGui.resize(126, 88)
        self.gridLayout = QtWidgets.QGridLayout(devGui)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName("gridLayout")
        self.modeCombo = QtWidgets.QComboBox(devGui)
        self.modeCombo.setObjectName("modeCombo")
        self.gridLayout.addWidget(self.modeCombo, 0, 0, 1, 2)
        self.label = QtWidgets.QLabel(devGui)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 1, 0, 1, 1)
        self.vcHoldingSpin = SpinBox(devGui)
        self.vcHoldingSpin.setObjectName("vcHoldingSpin")
        self.gridLayout.addWidget(self.vcHoldingSpin, 1, 1, 1, 1)
        self.label_2 = QtWidgets.QLabel(devGui)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 2, 0, 1, 1)
        self.icHoldingSpin = SpinBox(devGui)
        self.icHoldingSpin.setObjectName("icHoldingSpin")
        self.gridLayout.addWidget(self.icHoldingSpin, 2, 1, 1, 1)
        spacerItem = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 3, 0, 1, 1)

        self.retranslateUi(devGui)
        Qt.QMetaObject.connectSlotsByName(devGui)

    def retranslateUi(self, devGui):
        _translate = Qt.QCoreApplication.translate
        devGui.setWindowTitle(_translate("devGui", "Form"))
        self.label.setText(_translate("devGui", "VC Holding"))
        self.label_2.setText(_translate("devGui", "IC Holding"))

from acq4.pyqtgraph import SpinBox
