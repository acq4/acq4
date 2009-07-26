# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'InputChannelTemplate.ui'
#
# Created: Sun Jul 26 17:33:38 2009
#      by: PyQt4 UI code generator 4.4.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(427, 220)
        self.verticalLayout = QtGui.QVBoxLayout(Form)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.groupBox = QtGui.QGroupBox(Form)
        font = QtGui.QFont()
        font.setWeight(75)
        font.setBold(True)
        self.groupBox.setFont(font)
        self.groupBox.setCheckable(True)
        self.groupBox.setObjectName("groupBox")
        self.gridLayout = QtGui.QGridLayout(self.groupBox)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setContentsMargins(5, 0, 0, 0)
        self.gridLayout.setObjectName("gridLayout")
        self.recordCheck = QtGui.QCheckBox(self.groupBox)
        font = QtGui.QFont()
        font.setWeight(50)
        font.setBold(False)
        self.recordCheck.setFont(font)
        self.recordCheck.setChecked(True)
        self.recordCheck.setObjectName("recordCheck")
        self.gridLayout.addWidget(self.recordCheck, 0, 0, 1, 1)
        self.displayCheck = QtGui.QCheckBox(self.groupBox)
        font = QtGui.QFont()
        font.setWeight(50)
        font.setBold(False)
        self.displayCheck.setFont(font)
        self.displayCheck.setChecked(True)
        self.displayCheck.setObjectName("displayCheck")
        self.gridLayout.addWidget(self.displayCheck, 0, 1, 1, 1)
        self.recordInitCheck = QtGui.QCheckBox(self.groupBox)
        font = QtGui.QFont()
        font.setWeight(50)
        font.setBold(False)
        self.recordInitCheck.setFont(font)
        self.recordInitCheck.setObjectName("recordInitCheck")
        self.gridLayout.addWidget(self.recordInitCheck, 1, 0, 1, 2)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 2, 0, 1, 1)
        self.verticalLayout.addWidget(self.groupBox)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox.setTitle(QtGui.QApplication.translate("Form", "GroupBox", None, QtGui.QApplication.UnicodeUTF8))
        self.recordCheck.setText(QtGui.QApplication.translate("Form", "Record Trace", None, QtGui.QApplication.UnicodeUTF8))
        self.displayCheck.setText(QtGui.QApplication.translate("Form", "Display", None, QtGui.QApplication.UnicodeUTF8))
        self.recordInitCheck.setText(QtGui.QApplication.translate("Form", "Record Initial State", None, QtGui.QApplication.UnicodeUTF8))

