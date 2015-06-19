# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'devGuiTemplate.ui'
#
# Created: Tue May 12 17:53:27 2015
#      by: PyQt4 UI code generator 4.11.3
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

class Ui_devGui(object):
    def setupUi(self, devGui):
        devGui.setObjectName(_fromUtf8("devGui"))
        devGui.resize(126, 88)
        self.gridLayout = QtGui.QGridLayout(devGui)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setMargin(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.modeCombo = QtGui.QComboBox(devGui)
        self.modeCombo.setObjectName(_fromUtf8("modeCombo"))
        self.gridLayout.addWidget(self.modeCombo, 0, 0, 1, 2)
        self.label = QtGui.QLabel(devGui)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 1, 0, 1, 1)
        self.vcHoldingSpin = SpinBox(devGui)
        self.vcHoldingSpin.setObjectName(_fromUtf8("vcHoldingSpin"))
        self.gridLayout.addWidget(self.vcHoldingSpin, 1, 1, 1, 1)
        self.label_2 = QtGui.QLabel(devGui)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout.addWidget(self.label_2, 2, 0, 1, 1)
        self.icHoldingSpin = SpinBox(devGui)
        self.icHoldingSpin.setObjectName(_fromUtf8("icHoldingSpin"))
        self.gridLayout.addWidget(self.icHoldingSpin, 2, 1, 1, 1)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 3, 0, 1, 1)

        self.retranslateUi(devGui)
        QtCore.QMetaObject.connectSlotsByName(devGui)

    def retranslateUi(self, devGui):
        devGui.setWindowTitle(_translate("devGui", "Form", None))
        self.label.setText(_translate("devGui", "VC Holding", None))
        self.label_2.setText(_translate("devGui", "IC Holding", None))

from acq4.pyqtgraph import SpinBox
