# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/util/DatabaseGui/QueryTemplate.ui'
#
# Created: Tue Dec 24 01:49:17 2013
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
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.queryBtn.setText(_translate("Form", "Query", None))

from acq4.pyqtgraph import FeedbackButton, TableWidget
