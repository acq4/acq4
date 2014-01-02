# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/devices/MultiClamp/RackTemplate.ui'
#
# Created: Tue Dec 24 01:49:06 2013
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

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName(_fromUtf8("Form"))
        Form.resize(624, 129)
        self.horizontalLayout = QtGui.QHBoxLayout(Form)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.gridLayout_2 = QtGui.QGridLayout()
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.label_6 = QtGui.QLabel(Form)
        self.label_6.setObjectName(_fromUtf8("label_6"))
        self.gridLayout_2.addWidget(self.label_6, 0, 0, 1, 1)
        self.hostText = QtGui.QLineEdit(Form)
        self.hostText.setObjectName(_fromUtf8("hostText"))
        self.gridLayout_2.addWidget(self.hostText, 0, 1, 1, 1)
        self.clearCacheBtn = QtGui.QPushButton(Form)
        self.clearCacheBtn.setObjectName(_fromUtf8("clearCacheBtn"))
        self.gridLayout_2.addWidget(self.clearCacheBtn, 0, 2, 1, 1)
        self.deviceCombo = QtGui.QComboBox(Form)
        self.deviceCombo.setObjectName(_fromUtf8("deviceCombo"))
        self.gridLayout_2.addWidget(self.deviceCombo, 1, 0, 1, 3)
        self.horizontalLayout.addLayout(self.gridLayout_2)
        self.gridLayout = QtGui.QGridLayout()
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label_4 = QtGui.QLabel(Form)
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.gridLayout.addWidget(self.label_4, 0, 1, 1, 1)
        self.label_5 = QtGui.QLabel(Form)
        self.label_5.setObjectName(_fromUtf8("label_5"))
        self.gridLayout.addWidget(self.label_5, 0, 2, 1, 1)
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 1, 0, 1, 1)
        self.cmdDaqCombo = QtGui.QComboBox(Form)
        self.cmdDaqCombo.setObjectName(_fromUtf8("cmdDaqCombo"))
        self.gridLayout.addWidget(self.cmdDaqCombo, 1, 1, 1, 1)
        self.cmdChanCombo = QtGui.QComboBox(Form)
        self.cmdChanCombo.setObjectName(_fromUtf8("cmdChanCombo"))
        self.gridLayout.addWidget(self.cmdChanCombo, 1, 2, 1, 1)
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout.addWidget(self.label_2, 2, 0, 1, 1)
        self.scaledDaqCombo = QtGui.QComboBox(Form)
        self.scaledDaqCombo.setObjectName(_fromUtf8("scaledDaqCombo"))
        self.gridLayout.addWidget(self.scaledDaqCombo, 2, 1, 1, 1)
        self.scaledChanCombo = QtGui.QComboBox(Form)
        self.scaledChanCombo.setObjectName(_fromUtf8("scaledChanCombo"))
        self.gridLayout.addWidget(self.scaledChanCombo, 2, 2, 1, 1)
        self.label_3 = QtGui.QLabel(Form)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout.addWidget(self.label_3, 3, 0, 1, 1)
        self.rawDaqCombo = QtGui.QComboBox(Form)
        self.rawDaqCombo.setObjectName(_fromUtf8("rawDaqCombo"))
        self.gridLayout.addWidget(self.rawDaqCombo, 3, 1, 1, 1)
        self.rawChanCombo = QtGui.QComboBox(Form)
        self.rawChanCombo.setObjectName(_fromUtf8("rawChanCombo"))
        self.gridLayout.addWidget(self.rawChanCombo, 3, 2, 1, 1)
        self.horizontalLayout.addLayout(self.gridLayout)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.label_6.setText(_translate("Form", "Host", None))
        self.clearCacheBtn.setText(_translate("Form", "Clear Cache", None))
        self.label_4.setText(_translate("Form", "DAQ Device", None))
        self.label_5.setText(_translate("Form", "Channel", None))
        self.label.setText(_translate("Form", "Command", None))
        self.label_2.setText(_translate("Form", "Scaled Output", None))
        self.label_3.setText(_translate("Form", "Raw Output", None))

