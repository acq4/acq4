# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/analysis/old/StdpCtrlTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_StdpCtrlWidget(object):
    def setupUi(self, StdpCtrlWidget):
        StdpCtrlWidget.setObjectName("StdpCtrlWidget")
        StdpCtrlWidget.resize(227, 321)
        self.gridLayout = QtWidgets.QGridLayout(StdpCtrlWidget)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.label = QtWidgets.QLabel(StdpCtrlWidget)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.thresholdSpin = QtWidgets.QDoubleSpinBox(StdpCtrlWidget)
        self.thresholdSpin.setObjectName("thresholdSpin")
        self.gridLayout.addWidget(self.thresholdSpin, 0, 1, 1, 2)
        self.label_2 = QtWidgets.QLabel(StdpCtrlWidget)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)
        self.durationSpin = QtWidgets.QSpinBox(StdpCtrlWidget)
        self.durationSpin.setObjectName("durationSpin")
        self.gridLayout.addWidget(self.durationSpin, 1, 1, 1, 2)
        self.label_4 = QtWidgets.QLabel(StdpCtrlWidget)
        self.label_4.setObjectName("label_4")
        self.gridLayout.addWidget(self.label_4, 2, 0, 1, 1)
        self.slopeWidthSpin = SpinBox(StdpCtrlWidget)
        self.slopeWidthSpin.setObjectName("slopeWidthSpin")
        self.gridLayout.addWidget(self.slopeWidthSpin, 2, 1, 1, 2)
        self.apExclusionCheck = QtWidgets.QCheckBox(StdpCtrlWidget)
        self.apExclusionCheck.setObjectName("apExclusionCheck")
        self.gridLayout.addWidget(self.apExclusionCheck, 3, 0, 1, 1)
        self.label_3 = QtWidgets.QLabel(StdpCtrlWidget)
        self.label_3.setObjectName("label_3")
        self.gridLayout.addWidget(self.label_3, 4, 0, 1, 2)
        self.apthresholdSpin = QtWidgets.QDoubleSpinBox(StdpCtrlWidget)
        self.apthresholdSpin.setObjectName("apthresholdSpin")
        self.gridLayout.addWidget(self.apthresholdSpin, 4, 2, 1, 1)
        spacerItem = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 5, 0, 1, 1)

        self.retranslateUi(StdpCtrlWidget)
        Qt.QMetaObject.connectSlotsByName(StdpCtrlWidget)

    def retranslateUi(self, StdpCtrlWidget):
        _translate = Qt.QCoreApplication.translate
        StdpCtrlWidget.setWindowTitle(_translate("StdpCtrlWidget", "Form"))
        self.label.setText(_translate("StdpCtrlWidget", "PspThreshold:"))
        self.label_2.setText(_translate("StdpCtrlWidget", "Post-stim Duration (ms):"))
        self.label_4.setText(_translate("StdpCtrlWidget", "Slope width:"))
        self.apExclusionCheck.setText(_translate("StdpCtrlWidget", "Exclude APs"))
        self.label_3.setText(_translate("StdpCtrlWidget", "Exclusion Threshold (mV):"))

from SpinBox import SpinBox
