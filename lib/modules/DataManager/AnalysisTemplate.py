# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'AnalysisTemplate.ui'
#
# Created: Sun Dec 26 18:22:05 2010
#      by: PyQt4 UI code generator 4.7.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(457, 501)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName("gridLayout")
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.databaseText = QtGui.QLineEdit(Form)
        self.databaseText.setObjectName("databaseText")
        self.gridLayout.addWidget(self.databaseText, 0, 1, 1, 2)
        self.openDbBtn = QtGui.QPushButton(Form)
        self.openDbBtn.setObjectName("openDbBtn")
        self.gridLayout.addWidget(self.openDbBtn, 0, 3, 1, 1)
        self.addFileBtn = QtGui.QPushButton(Form)
        self.addFileBtn.setObjectName("addFileBtn")
        self.gridLayout.addWidget(self.addFileBtn, 1, 0, 1, 2)
        spacerItem = QtGui.QSpacerItem(168, 432, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 2, 2, 1, 1)
        self.createDbBtn = QtGui.QPushButton(Form)
        self.createDbBtn.setObjectName("createDbBtn")
        self.gridLayout.addWidget(self.createDbBtn, 0, 4, 1, 1)
        self.tableNameText = QtGui.QLineEdit(Form)
        self.tableNameText.setObjectName("tableNameText")
        self.gridLayout.addWidget(self.tableNameText, 1, 2, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Database:", None, QtGui.QApplication.UnicodeUTF8))
        self.openDbBtn.setText(QtGui.QApplication.translate("Form", "Open", None, QtGui.QApplication.UnicodeUTF8))
        self.addFileBtn.setText(QtGui.QApplication.translate("Form", "Add to table ->", None, QtGui.QApplication.UnicodeUTF8))
        self.createDbBtn.setText(QtGui.QApplication.translate("Form", "Create", None, QtGui.QApplication.UnicodeUTF8))

