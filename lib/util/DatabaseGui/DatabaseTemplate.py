# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'DatabaseTemplate.ui'
#
# Created: Thu Jan 13 08:22:09 2011
#      by: PyQt4 UI code generator 4.7.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(274, 282)
        self.gridLayout_2 = QtGui.QGridLayout(Form)
        self.gridLayout_2.setMargin(0)
        self.gridLayout_2.setSpacing(0)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.dbLabel = QtGui.QLabel(Form)
        self.dbLabel.setText("")
        self.dbLabel.setObjectName("dbLabel")
        self.horizontalLayout.addWidget(self.dbLabel)
        self.gridLayout_2.addLayout(self.horizontalLayout, 0, 0, 1, 2)
        self.tableArea = QtGui.QWidget(Form)
        self.tableArea.setObjectName("tableArea")
        self.gridLayout = QtGui.QGridLayout(self.tableArea)
        self.gridLayout.setObjectName("gridLayout")
        self.gridLayout_2.addWidget(self.tableArea, 1, 0, 1, 2)
        self.queryText = QtGui.QLineEdit(Form)
        self.queryText.setObjectName("queryText")
        self.gridLayout_2.addWidget(self.queryText, 2, 0, 1, 1)
        self.queryBtn = QtGui.QPushButton(Form)
        self.queryBtn.setObjectName("queryBtn")
        self.gridLayout_2.addWidget(self.queryBtn, 2, 1, 1, 1)
        self.queryTable = TableWidget(Form)
        self.queryTable.setObjectName("queryTable")
        self.queryTable.setColumnCount(0)
        self.queryTable.setRowCount(0)
        self.gridLayout_2.addWidget(self.queryTable, 3, 0, 1, 2)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Database:", None, QtGui.QApplication.UnicodeUTF8))
        self.queryBtn.setText(QtGui.QApplication.translate("Form", "Query", None, QtGui.QApplication.UnicodeUTF8))

from TableWidget import TableWidget
