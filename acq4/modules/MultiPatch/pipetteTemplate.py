# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'pipetteTemplate.ui'
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

class Ui_PipetteControl(object):
    def setupUi(self, PipetteControl):
        PipetteControl.setObjectName(_fromUtf8("PipetteControl"))
        PipetteControl.resize(333, 75)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(PipetteControl.sizePolicy().hasHeightForWidth())
        PipetteControl.setSizePolicy(sizePolicy)
        self.gridLayout = QtGui.QGridLayout(PipetteControl)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.targetBtn = QtGui.QPushButton(PipetteControl)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.MinimumExpanding, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.targetBtn.sizePolicy().hasHeightForWidth())
        self.targetBtn.setSizePolicy(sizePolicy)
        self.targetBtn.setMaximumSize(QtCore.QSize(40, 16777215))
        self.targetBtn.setObjectName(_fromUtf8("targetBtn"))
        self.gridLayout.addWidget(self.targetBtn, 1, 4, 1, 1)
        self.stateCombo = QtGui.QComboBox(PipetteControl)
        self.stateCombo.setObjectName(_fromUtf8("stateCombo"))
        self.stateCombo.addItem(_fromUtf8(""))
        self.stateCombo.addItem(_fromUtf8(""))
        self.stateCombo.addItem(_fromUtf8(""))
        self.stateCombo.addItem(_fromUtf8(""))
        self.stateCombo.addItem(_fromUtf8(""))
        self.stateCombo.addItem(_fromUtf8(""))
        self.stateCombo.addItem(_fromUtf8(""))
        self.stateCombo.addItem(_fromUtf8(""))
        self.gridLayout.addWidget(self.stateCombo, 0, 3, 1, 2)
        self.plotLayoutWidget = QtGui.QWidget(PipetteControl)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.plotLayoutWidget.sizePolicy().hasHeightForWidth())
        self.plotLayoutWidget.setSizePolicy(sizePolicy)
        self.plotLayoutWidget.setObjectName(_fromUtf8("plotLayoutWidget"))
        self.plotLayout = QtGui.QHBoxLayout(self.plotLayoutWidget)
        self.plotLayout.setMargin(0)
        self.plotLayout.setSpacing(0)
        self.plotLayout.setObjectName(_fromUtf8("plotLayout"))
        self.gridLayout.addWidget(self.plotLayoutWidget, 0, 5, 4, 1)
        self.selectBtn = QtGui.QPushButton(PipetteControl)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Maximum, QtGui.QSizePolicy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.selectBtn.sizePolicy().hasHeightForWidth())
        self.selectBtn.setSizePolicy(sizePolicy)
        self.selectBtn.setMaximumSize(QtCore.QSize(30, 16777215))
        font = QtGui.QFont()
        font.setPointSize(12)
        font.setBold(True)
        font.setWeight(75)
        self.selectBtn.setFont(font)
        self.selectBtn.setCheckable(True)
        self.selectBtn.setObjectName(_fromUtf8("selectBtn"))
        self.gridLayout.addWidget(self.selectBtn, 0, 0, 4, 1)
        self.tipBtn = QtGui.QPushButton(PipetteControl)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.tipBtn.sizePolicy().hasHeightForWidth())
        self.tipBtn.setSizePolicy(sizePolicy)
        self.tipBtn.setMaximumSize(QtCore.QSize(40, 16777215))
        self.tipBtn.setObjectName(_fromUtf8("tipBtn"))
        self.gridLayout.addWidget(self.tipBtn, 2, 4, 1, 1)
        self.soloBtn = QtGui.QPushButton(PipetteControl)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.soloBtn.sizePolicy().hasHeightForWidth())
        self.soloBtn.setSizePolicy(sizePolicy)
        self.soloBtn.setMaximumSize(QtCore.QSize(30, 16777215))
        self.soloBtn.setCheckable(True)
        self.soloBtn.setObjectName(_fromUtf8("soloBtn"))
        self.gridLayout.addWidget(self.soloBtn, 2, 3, 1, 1)
        self.lockBtn = QtGui.QPushButton(PipetteControl)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.lockBtn.sizePolicy().hasHeightForWidth())
        self.lockBtn.setSizePolicy(sizePolicy)
        self.lockBtn.setMaximumSize(QtCore.QSize(30, 16777215))
        self.lockBtn.setCheckable(True)
        self.lockBtn.setObjectName(_fromUtf8("lockBtn"))
        self.gridLayout.addWidget(self.lockBtn, 1, 3, 1, 1)

        self.retranslateUi(PipetteControl)
        QtCore.QMetaObject.connectSlotsByName(PipetteControl)

    def retranslateUi(self, PipetteControl):
        PipetteControl.setWindowTitle(_translate("PipetteControl", "Form", None))
        self.targetBtn.setText(_translate("PipetteControl", "target", None))
        self.stateCombo.setItemText(0, _translate("PipetteControl", "out", None))
        self.stateCombo.setItemText(1, _translate("PipetteControl", "bath", None))
        self.stateCombo.setItemText(2, _translate("PipetteControl", "approach", None))
        self.stateCombo.setItemText(3, _translate("PipetteControl", "seal", None))
        self.stateCombo.setItemText(4, _translate("PipetteControl", "attached", None))
        self.stateCombo.setItemText(5, _translate("PipetteControl", "break in", None))
        self.stateCombo.setItemText(6, _translate("PipetteControl", "whole cell", None))
        self.stateCombo.setItemText(7, _translate("PipetteControl", "outside-out", None))
        self.selectBtn.setText(_translate("PipetteControl", "1", None))
        self.tipBtn.setText(_translate("PipetteControl", "tip", None))
        self.soloBtn.setText(_translate("PipetteControl", "Solo", None))
        self.lockBtn.setText(_translate("PipetteControl", "Lock", None))

