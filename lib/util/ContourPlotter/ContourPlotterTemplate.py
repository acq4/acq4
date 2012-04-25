# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ContourPlotterTemplate.ui'
#
# Created: Thu Mar 22 11:09:49 2012
#      by: PyQt4 UI code generator 4.9
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
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.drawBtn.setText(QtGui.QApplication.translate("Form", "Draw", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(0, QtGui.QApplication.translate("Form", "Param", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(1, QtGui.QApplication.translate("Form", "Threshold", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(2, QtGui.QApplication.translate("Form", "% of max", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(3, QtGui.QApplication.translate("Form", "Color", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(4, QtGui.QApplication.translate("Form", "Remove", None, QtGui.QApplication.UnicodeUTF8))

from pyqtgraph import TreeWidget
