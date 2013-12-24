# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/analysis/old/StdpCtrlTemplate.ui'
#
# Created: Tue Dec 24 01:49:15 2013
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
        StdpCtrlWidget.setWindowTitle(_translate("StdpCtrlWidget", "Form", None))
        self.label.setText(_translate("StdpCtrlWidget", "PspThreshold:", None))
        self.label_2.setText(_translate("StdpCtrlWidget", "Post-stim Duration (ms):", None))
        self.label_4.setText(_translate("StdpCtrlWidget", "Slope width:", None))
        self.apExclusionCheck.setText(_translate("StdpCtrlWidget", "Exclude APs", None))
        self.label_3.setText(_translate("StdpCtrlWidget", "Exclusion Threshold (mV):", None))

from SpinBox import SpinBox
