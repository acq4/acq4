# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/analysis/old/StdpCtrlTemplate.ui'
#
# Created: Wed Apr 18 13:40:12 2012
#      by: PyQt4 UI code generator 4.8.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    _fromUtf8 = lambda s: s

class Ui_StdpCtrlWidget(object):
    def setupUi(self, StdpCtrlWidget):
        StdpCtrlWidget.setObjectName(_fromUtf8("StdpCtrlWidget"))
        StdpCtrlWidget.resize(227, 321)
        self.gridLayout = QtGui.QGridLayout(StdpCtrlWidget)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label = QtGui.QLabel(StdpCtrlWidget)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.thresholdSpin = QtGui.QDoubleSpinBox(StdpCtrlWidget)
        self.thresholdSpin.setObjectName(_fromUtf8("thresholdSpin"))
        self.gridLayout.addWidget(self.thresholdSpin, 0, 1, 1, 2)
        self.label_2 = QtGui.QLabel(StdpCtrlWidget)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)
        self.durationSpin = QtGui.QSpinBox(StdpCtrlWidget)
        self.durationSpin.setObjectName(_fromUtf8("durationSpin"))
        self.gridLayout.addWidget(self.durationSpin, 1, 1, 1, 2)
        self.label_4 = QtGui.QLabel(StdpCtrlWidget)
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.gridLayout.addWidget(self.label_4, 2, 0, 1, 1)
        self.slopeWidthSpin = SpinBox(StdpCtrlWidget)
        self.slopeWidthSpin.setObjectName(_fromUtf8("slopeWidthSpin"))
        self.gridLayout.addWidget(self.slopeWidthSpin, 2, 1, 1, 2)
        self.apExclusionCheck = QtGui.QCheckBox(StdpCtrlWidget)
        self.apExclusionCheck.setObjectName(_fromUtf8("apExclusionCheck"))
        self.gridLayout.addWidget(self.apExclusionCheck, 3, 0, 1, 1)
        self.label_3 = QtGui.QLabel(StdpCtrlWidget)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout.addWidget(self.label_3, 4, 0, 1, 2)
        self.apthresholdSpin = QtGui.QDoubleSpinBox(StdpCtrlWidget)
        self.apthresholdSpin.setObjectName(_fromUtf8("apthresholdSpin"))
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
