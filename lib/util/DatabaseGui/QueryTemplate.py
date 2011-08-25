# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/util/DatabaseGui/QueryTemplate.ui'
#
# Created: Wed Aug 17 13:49:54 2011
#      by: pyside-uic 0.2.11 running on PySide 1.0.5
#
# WARNING! All changes made in this file will be lost!

from PySide import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(400, 300)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.queryText = QtGui.QLineEdit(Form)
        self.queryText.setObjectName("queryText")
        self.gridLayout.addWidget(self.queryText, 0, 0, 1, 1)
        self.queryBtn = FeedbackButton(Form)
        self.queryBtn.setObjectName("queryBtn")
        self.gridLayout.addWidget(self.queryBtn, 0, 1, 1, 1)
        self.queryTable = TableWidget(Form)
        self.queryTable.setObjectName("queryTable")
        self.queryTable.setColumnCount(0)
        self.queryTable.setRowCount(0)
        self.gridLayout.addWidget(self.queryTable, 1, 0, 1, 2)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.queryBtn.setText(QtGui.QApplication.translate("Form", "Query", None, QtGui.QApplication.UnicodeUTF8))

from FeedbackButton import FeedbackButton
from TableWidget import TableWidget
