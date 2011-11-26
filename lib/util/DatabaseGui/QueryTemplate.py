# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/util/DatabaseGui/QueryTemplate.ui'
#
# Created: Wed May 18 20:44:16 2011
#      by: PyQt4 UI code generator 4.8.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    _fromUtf8 = lambda s: s

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName(_fromUtf8("Form"))
        Form.resize(400, 300)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.queryText = QtGui.QLineEdit(Form)
        self.queryText.setObjectName(_fromUtf8("queryText"))
        self.gridLayout.addWidget(self.queryText, 0, 0, 1, 1)
        self.queryBtn = FeedbackButton(Form)
        self.queryBtn.setObjectName(_fromUtf8("queryBtn"))
        self.gridLayout.addWidget(self.queryBtn, 0, 1, 1, 1)
        self.queryTable = TableWidget(Form)
        self.queryTable.setObjectName(_fromUtf8("queryTable"))
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
