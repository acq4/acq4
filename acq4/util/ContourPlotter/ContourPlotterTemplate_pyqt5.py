# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/util/ContourPlotter/ContourPlotterTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(400, 300)
        self.gridLayout = QtWidgets.QGridLayout(Form)
        self.gridLayout.setContentsMargins(3, 3, 3, 3)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName("gridLayout")
        self.drawBtn = QtWidgets.QPushButton(Form)
        self.drawBtn.setObjectName("drawBtn")
        self.gridLayout.addWidget(self.drawBtn, 2, 0, 1, 1)
        self.tree = TreeWidget(Form)
        self.tree.setObjectName("tree")
        self.tree.header().setStretchLastSection(False)
        self.gridLayout.addWidget(self.tree, 0, 0, 1, 1)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.drawBtn.setText(_translate("Form", "Draw"))
        self.tree.headerItem().setText(0, _translate("Form", "Param"))
        self.tree.headerItem().setText(1, _translate("Form", "Threshold"))
        self.tree.headerItem().setText(2, _translate("Form", "% of max"))
        self.tree.headerItem().setText(3, _translate("Form", "Color"))
        self.tree.headerItem().setText(4, _translate("Form", "Remove"))

from pyqtgraph import TreeWidget
