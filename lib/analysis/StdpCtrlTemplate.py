# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'StdpCtrlTemplate.ui'
#
# Created: Thu Sep  9 00:31:45 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_StdpCtrlWidget(object):
    def setupUi(self, StdpCtrlWidget):
        StdpCtrlWidget.setObjectName("StdpCtrlWidget")
        StdpCtrlWidget.resize(227, 321)
        self.gridLayout = QtGui.QGridLayout(StdpCtrlWidget)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.label = QtGui.QLabel(StdpCtrlWidget)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.thresholdSpin = QtGui.QDoubleSpinBox(StdpCtrlWidget)
        self.thresholdSpin.setObjectName("thresholdSpin")
        self.gridLayout.addWidget(self.thresholdSpin, 0, 1, 1, 2)
        self.label_2 = QtGui.QLabel(StdpCtrlWidget)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)
        self.durationSpin = QtGui.QSpinBox(StdpCtrlWidget)
        self.durationSpin.setObjectName("durationSpin")
        self.gridLayout.addWidget(self.durationSpin, 1, 1, 1, 2)
        self.label_4 = QtGui.QLabel(StdpCtrlWidget)
        self.label_4.setObjectName("label_4")
        self.gridLayout.addWidget(self.label_4, 2, 0, 1, 1)
        self.slopeWidthSpin = SpinBox(StdpCtrlWidget)
        self.slopeWidthSpin.setObjectName("slopeWidthSpin")
        self.gridLayout.addWidget(self.slopeWidthSpin, 2, 1, 1, 2)
        self.apExclusionCheck = QtGui.QCheckBox(StdpCtrlWidget)
        self.apExclusionCheck.setObjectName("apExclusionCheck")
        self.gridLayout.addWidget(self.apExclusionCheck, 3, 0, 1, 1)
        self.label_3 = QtGui.QLabel(StdpCtrlWidget)
        self.label_3.setObjectName("label_3")
        self.gridLayout.addWidget(self.label_3, 4, 0, 1, 2)
        self.apthresholdSpin = QtGui.QDoubleSpinBox(StdpCtrlWidget)
        self.apthresholdSpin.setObjectName("apthresholdSpin")
        self.gridLayout.addWidget(self.apthresholdSpin, 4, 2, 1, 1)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 5, 0, 1, 1)

        self.retranslateUi(StdpCtrlWidget)
        QtCore.QMetaObject.connectSlotsByName(StdpCtrlWidget)

    def retranslateUi(self, StdpCtrlWidget):
        StdpCtrlWidget.setWindowTitle(QtGui.QApplication.translate("StdpCtrlWidget", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("StdpCtrlWidget", "PspThreshold:", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("StdpCtrlWidget", "Post-stim Duration (ms):", None, QtGui.QApplication.UnicodeUTF8))
        self.label_4.setText(QtGui.QApplication.translate("StdpCtrlWidget", "Slope width:", None, QtGui.QApplication.UnicodeUTF8))
        self.apExclusionCheck.setText(QtGui.QApplication.translate("StdpCtrlWidget", "Exclude APs", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("StdpCtrlWidget", "Exclusion Threshold (mV):", None, QtGui.QApplication.UnicodeUTF8))

from SpinBox import SpinBox
