# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'CMTemplate.ui'
#
# Created: Wed Feb  2 22:49:42 2011
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(400, 247)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.tree = TreeWidget(Form)
        self.tree.setRootIsDecorated(False)
        self.tree.setObjectName("tree")
        self.gridLayout.addWidget(self.tree, 0, 0, 1, 4)
        self.addBtn = QtGui.QPushButton(Form)
        self.addBtn.setMaximumSize(QtCore.QSize(40, 16777215))
        self.addBtn.setObjectName("addBtn")
        self.gridLayout.addWidget(self.addBtn, 1, 0, 1, 1)
        self.remBtn = QtGui.QPushButton(Form)
        self.remBtn.setMaximumSize(QtCore.QSize(40, 16777215))
        self.remBtn.setObjectName("remBtn")
        self.gridLayout.addWidget(self.remBtn, 1, 1, 1, 1)
        self.fileCombo = QtGui.QComboBox(Form)
        self.fileCombo.setEditable(True)
        self.fileCombo.setObjectName("fileCombo")
        self.gridLayout.addWidget(self.fileCombo, 1, 2, 1, 1)
        self.delBtn = QtGui.QToolButton(Form)
        self.delBtn.setObjectName("delBtn")
        self.gridLayout.addWidget(self.delBtn, 1, 3, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(0, QtGui.QApplication.translate("Form", " ", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(1, QtGui.QApplication.translate("Form", "arg", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(2, QtGui.QApplication.translate("Form", "op", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(3, QtGui.QApplication.translate("Form", "min", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(4, QtGui.QApplication.translate("Form", "max", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(5, QtGui.QApplication.translate("Form", "colors", None, QtGui.QApplication.UnicodeUTF8))
        self.addBtn.setText(QtGui.QApplication.translate("Form", "+", None, QtGui.QApplication.UnicodeUTF8))
        self.remBtn.setText(QtGui.QApplication.translate("Form", "-", None, QtGui.QApplication.UnicodeUTF8))
        self.delBtn.setText(QtGui.QApplication.translate("Form", "X", None, QtGui.QApplication.UnicodeUTF8))

from TreeWidget import TreeWidget
