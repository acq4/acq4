# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'InputChannelTemplate.ui'
#
# Created: Wed Jun  3 18:04:41 2009
#      by: PyQt4 UI code generator 4.4.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(273, 70)
        self.verticalLayout = QtGui.QVBoxLayout(Form)
        self.verticalLayout.setObjectName("verticalLayout")
        self.recordCheck = QtGui.QCheckBox(Form)
        self.recordCheck.setChecked(True)
        self.recordCheck.setObjectName("recordCheck")
        self.verticalLayout.addWidget(self.recordCheck)
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
        self.recordCheck.setText(QtGui.QApplication.translate("Form", "Record", None, QtGui.QApplication.UnicodeUTF8))
        self.displayCheck.setText(QtGui.QApplication.translate("Form", "Display", None, QtGui.QApplication.UnicodeUTF8))

