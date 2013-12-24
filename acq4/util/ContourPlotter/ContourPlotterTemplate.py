# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/util/ContourPlotter/ContourPlotterTemplate.ui'
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
        Form.resize(400, 300)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(3)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.drawBtn = QtGui.QPushButton(Form)
        self.drawBtn.setObjectName(_fromUtf8("drawBtn"))
        self.gridLayout.addWidget(self.drawBtn, 2, 0, 1, 1)
        self.tree = TreeWidget(Form)
        self.tree.setObjectName(_fromUtf8("tree"))
        self.tree.header().setStretchLastSection(False)
        self.gridLayout.addWidget(self.tree, 0, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.drawBtn.setText(_translate("Form", "Draw", None))
        self.tree.headerItem().setText(0, _translate("Form", "Param", None))
        self.tree.headerItem().setText(1, _translate("Form", "Threshold", None))
        self.tree.headerItem().setText(2, _translate("Form", "% of max", None))
        self.tree.headerItem().setText(3, _translate("Form", "Color", None))
        self.tree.headerItem().setText(4, _translate("Form", "Remove", None))

from pyqtgraph import TreeWidget
