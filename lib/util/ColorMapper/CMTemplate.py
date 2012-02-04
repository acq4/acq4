# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/util/ColorMapper/CMTemplate.ui'
#
# Created: Fri Feb  3 12:02:00 2012
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
        Form.resize(264, 249)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(0)
        self.gridLayout.setHorizontalSpacing(0)
        self.gridLayout.setVerticalSpacing(1)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.horizontalLayout.addWidget(self.label)
        self.fileCombo = QtGui.QComboBox(Form)
        self.fileCombo.setEditable(True)
        self.fileCombo.setMaxVisibleItems(20)
        self.fileCombo.setObjectName(_fromUtf8("fileCombo"))
        self.horizontalLayout.addWidget(self.fileCombo)
        self.gridLayout.addLayout(self.horizontalLayout, 0, 0, 1, 3)
        self.saveBtn = FeedbackButton(Form)
        self.saveBtn.setObjectName(_fromUtf8("saveBtn"))
        self.gridLayout.addWidget(self.saveBtn, 1, 0, 1, 1)
        self.saveAsBtn = FeedbackButton(Form)
        self.saveAsBtn.setObjectName(_fromUtf8("saveAsBtn"))
        self.gridLayout.addWidget(self.saveAsBtn, 1, 1, 1, 1)
        self.deleteBtn = FeedbackButton(Form)
        self.deleteBtn.setObjectName(_fromUtf8("deleteBtn"))
        self.gridLayout.addWidget(self.deleteBtn, 1, 2, 1, 1)
        self.tree = TreeWidget(Form)
        self.tree.setRootIsDecorated(False)
        self.tree.setObjectName(_fromUtf8("tree"))
        self.gridLayout.addWidget(self.tree, 2, 0, 1, 3)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Color Scheme:", None, QtGui.QApplication.UnicodeUTF8))
        self.saveBtn.setText(QtGui.QApplication.translate("Form", "Save", None, QtGui.QApplication.UnicodeUTF8))
        self.saveAsBtn.setText(QtGui.QApplication.translate("Form", "Save As..", None, QtGui.QApplication.UnicodeUTF8))
        self.deleteBtn.setText(QtGui.QApplication.translate("Form", "Delete", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(0, QtGui.QApplication.translate("Form", "arg", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(1, QtGui.QApplication.translate("Form", "op", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(2, QtGui.QApplication.translate("Form", "min", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(3, QtGui.QApplication.translate("Form", "max", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(4, QtGui.QApplication.translate("Form", "colors", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(5, QtGui.QApplication.translate("Form", "remove", None, QtGui.QApplication.UnicodeUTF8))

from pyqtgraph import TreeWidget
from FeedbackButton import FeedbackButton
