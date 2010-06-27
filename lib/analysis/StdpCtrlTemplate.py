# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'stdpCtrlTemplate.ui'
#
# Created: Wed Jun 23 12:36:52 2010
#      by: PyQt4 UI code generator 4.5.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_StdpCtrlWidget(object):
    def setupUi(self, StdpCtrlWidget):
        StdpCtrlWidget.setObjectName("StdpCtrlWidget")
        StdpCtrlWidget.resize(275, 198)
        self.gridLayout = QtGui.QGridLayout(StdpCtrlWidget)
        self.gridLayout.setObjectName("gridLayout")
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label = QtGui.QLabel(StdpCtrlWidget)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.thresholdSpin = QtGui.QDoubleSpinBox(StdpCtrlWidget)
        self.thresholdSpin.setObjectName("thresholdSpin")
        self.horizontalLayout.addWidget(self.thresholdSpin)
        self.gridLayout.addLayout(self.horizontalLayout, 0, 0, 1, 2)
        self.horizontalLayout_2 = QtGui.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.label_2 = QtGui.QLabel(StdpCtrlWidget)
        self.label_2.setObjectName("label_2")
        self.horizontalLayout_2.addWidget(self.label_2)
        self.durationSpin = QtGui.QSpinBox(StdpCtrlWidget)
        self.durationSpin.setObjectName("durationSpin")
        self.horizontalLayout_2.addWidget(self.durationSpin)
        self.gridLayout.addLayout(self.horizontalLayout_2, 1, 0, 1, 2)
        self.horizontalLayout_5 = QtGui.QHBoxLayout()
        self.horizontalLayout_5.setObjectName("horizontalLayout_5")
        self.label_4 = QtGui.QLabel(StdpCtrlWidget)
        self.label_4.setObjectName("label_4")
        self.horizontalLayout_5.addWidget(self.label_4)
        self.slopeWidthSpin = QtGui.QDoubleSpinBox(StdpCtrlWidget)
        self.slopeWidthSpin.setObjectName("slopeWidthSpin")
        self.horizontalLayout_5.addWidget(self.slopeWidthSpin)
        self.gridLayout.addLayout(self.horizontalLayout_5, 2, 0, 1, 2)
        self.apExclusionCheck = QtGui.QCheckBox(StdpCtrlWidget)
        self.apExclusionCheck.setObjectName("apExclusionCheck")
        self.gridLayout.addWidget(self.apExclusionCheck, 3, 0, 1, 1)
        self.horizontalLayout_4 = QtGui.QHBoxLayout()
        self.horizontalLayout_4.setObjectName("horizontalLayout_4")
        spacerItem = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout_4.addItem(spacerItem)
        self.label_3 = QtGui.QLabel(StdpCtrlWidget)
        self.label_3.setObjectName("label_3")
        self.horizontalLayout_4.addWidget(self.label_3)
        self.horizontalLayout_3 = QtGui.QHBoxLayout()
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.apthresholdSpin = QtGui.QDoubleSpinBox(StdpCtrlWidget)
        self.apthresholdSpin.setObjectName("apthresholdSpin")
        self.horizontalLayout_3.addWidget(self.apthresholdSpin)
        self.horizontalLayout_4.addLayout(self.horizontalLayout_3)
        self.gridLayout.addLayout(self.horizontalLayout_4, 4, 0, 1, 2)
        spacerItem1 = QtGui.QSpacerItem(58, 3, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem1, 5, 1, 1, 1)

        self.retranslateUi(StdpCtrlWidget)
        QtCore.QMetaObject.connectSlotsByName(StdpCtrlWidget)

    def retranslateUi(self, StdpCtrlWidget):
        StdpCtrlWidget.setWindowTitle(QtGui.QApplication.translate("StdpCtrlWidget", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("StdpCtrlWidget", "PspThreshold:", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("StdpCtrlWidget", "Post-stim Duration (ms):", None, QtGui.QApplication.UnicodeUTF8))
        self.label_4.setText(QtGui.QApplication.translate("StdpCtrlWidget", "Slope width(ms):", None, QtGui.QApplication.UnicodeUTF8))
        self.apExclusionCheck.setText(QtGui.QApplication.translate("StdpCtrlWidget", "Exclude APs", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("StdpCtrlWidget", "Exclusion Threshold (mV):", None, QtGui.QApplication.UnicodeUTF8))

