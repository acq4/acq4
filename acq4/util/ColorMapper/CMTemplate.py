# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/util/ColorMapper/CMTemplate.ui'
#
# Created: Tue Dec 24 01:49:16 2013
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
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.label.setText(_translate("Form", "Color Scheme:", None))
        self.saveBtn.setText(_translate("Form", "Save", None))
        self.saveAsBtn.setText(_translate("Form", "Save As..", None))
        self.deleteBtn.setText(_translate("Form", "Delete", None))
        self.tree.headerItem().setText(0, _translate("Form", "arg", None))
        self.tree.headerItem().setText(1, _translate("Form", "op", None))
        self.tree.headerItem().setText(2, _translate("Form", "min", None))
        self.tree.headerItem().setText(3, _translate("Form", "max", None))
        self.tree.headerItem().setText(4, _translate("Form", "colors", None))
        self.tree.headerItem().setText(5, _translate("Form", "remove", None))

from acq4.pyqtgraph import FeedbackButton, TreeWidget
