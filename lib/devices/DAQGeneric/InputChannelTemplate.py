# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'InputChannelTemplate.ui'
#
# Created: Wed Jun 10 17:48:32 2009
#      by: PyQt4 UI code generator 4.4.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(273, 90)
        self.verticalLayout = QtGui.QVBoxLayout(Form)
        self.verticalLayout.setObjectName("verticalLayout")
        self.recordCheck = QtGui.QCheckBox(Form)
        self.recordCheck.setChecked(True)
        self.recordCheck.setObjectName("recordCheck")
        self.verticalLayout.addWidget(self.recordCheck)
        self.recordInitCheck = QtGui.QCheckBox(Form)
        self.recordInitCheck.setObjectName("recordInitCheck")
        self.verticalLayout.addWidget(self.recordInitCheck)
        self.displayCheck = QtGui.QCheckBox(Form)
        self.displayCheck.setChecked(True)
        self.displayCheck.setObjectName("displayCheck")
        self.verticalLayout.addWidget(self.displayCheck)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.recordCheck.setText(QtGui.QApplication.translate("Form", "Record Trace", None, QtGui.QApplication.UnicodeUTF8))
        self.recordInitCheck.setText(QtGui.QApplication.translate("Form", "Record Initial State", None, QtGui.QApplication.UnicodeUTF8))
        self.displayCheck.setText(QtGui.QApplication.translate("Form", "Display", None, QtGui.QApplication.UnicodeUTF8))

