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
        PipetteControl.resize(414, 74)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(PipetteControl.sizePolicy().hasHeightForWidth())
        PipetteControl.setSizePolicy(sizePolicy)
        self.gridLayout = QtGui.QGridLayout(PipetteControl)
        self.gridLayout.setMargin(2)
        self.gridLayout.setSpacing(2)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.stateCombo = QtGui.QComboBox(PipetteControl)
        self.stateCombo.setObjectName(_fromUtf8("stateCombo"))
        self.gridLayout.addWidget(self.stateCombo, 0, 2, 1, 2)
        self.lockBtn = QtGui.QPushButton(PipetteControl)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.lockBtn.sizePolicy().hasHeightForWidth())
        self.lockBtn.setSizePolicy(sizePolicy)
        self.lockBtn.setCheckable(True)
        self.lockBtn.setObjectName(_fromUtf8("lockBtn"))
        self.gridLayout.addWidget(self.lockBtn, 2, 2, 1, 2)
        self.selectBtn = QtGui.QPushButton(PipetteControl)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.selectBtn.sizePolicy().hasHeightForWidth())
        self.selectBtn.setSizePolicy(sizePolicy)
        self.selectBtn.setMaximumSize(QtCore.QSize(30, 16777215))
        self.selectBtn.setCheckable(True)
        self.selectBtn.setObjectName(_fromUtf8("selectBtn"))
        self.gridLayout.addWidget(self.selectBtn, 0, 1, 4, 1)
        self.activeBtn = QtGui.QPushButton(PipetteControl)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Maximum, QtGui.QSizePolicy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.activeBtn.sizePolicy().hasHeightForWidth())
        self.activeBtn.setSizePolicy(sizePolicy)
        self.activeBtn.setMaximumSize(QtCore.QSize(30, 16777215))
        font = QtGui.QFont()
        font.setPointSize(12)
        font.setBold(True)
        font.setWeight(75)
        self.activeBtn.setFont(font)
        self.activeBtn.setCheckable(True)
        self.activeBtn.setObjectName(_fromUtf8("activeBtn"))
        self.gridLayout.addWidget(self.activeBtn, 0, 0, 4, 1)
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
        self.gridLayout.addWidget(self.plotLayoutWidget, 0, 4, 4, 1)
        self.targetBtn = QtGui.QPushButton(PipetteControl)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.MinimumExpanding, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.targetBtn.sizePolicy().hasHeightForWidth())
        self.targetBtn.setSizePolicy(sizePolicy)
        self.targetBtn.setMaximumSize(QtCore.QSize(40, 16777215))
        self.targetBtn.setObjectName(_fromUtf8("targetBtn"))
        self.gridLayout.addWidget(self.targetBtn, 1, 2, 1, 1)
        self.tipBtn = QtGui.QPushButton(PipetteControl)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.tipBtn.sizePolicy().hasHeightForWidth())
        self.tipBtn.setSizePolicy(sizePolicy)
        self.tipBtn.setMaximumSize(QtCore.QSize(40, 16777215))
        self.tipBtn.setObjectName(_fromUtf8("tipBtn"))
        self.gridLayout.addWidget(self.tipBtn, 1, 3, 1, 1)

        self.retranslateUi(PipetteControl)
        QtCore.QMetaObject.connectSlotsByName(PipetteControl)

    def retranslateUi(self, PipetteControl):
        PipetteControl.setWindowTitle(_translate("PipetteControl", "Form", None))
        self.lockBtn.setText(_translate("PipetteControl", "Lock", None))
        self.selectBtn.setText(_translate("PipetteControl", "Sel", None))
        self.activeBtn.setText(_translate("PipetteControl", "1", None))
        self.targetBtn.setText(_translate("PipetteControl", "target", None))
        self.tipBtn.setText(_translate("PipetteControl", "tip", None))

