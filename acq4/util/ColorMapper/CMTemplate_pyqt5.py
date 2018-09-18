# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/util/ColorMapper/CMTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(264, 249)
        self.gridLayout = QtWidgets.QGridLayout(Form)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setHorizontalSpacing(0)
        self.gridLayout.setVerticalSpacing(1)
        self.gridLayout.setObjectName("gridLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label = QtWidgets.QLabel(Form)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.fileCombo = QtWidgets.QComboBox(Form)
        self.fileCombo.setEditable(True)
        self.fileCombo.setMaxVisibleItems(20)
        self.fileCombo.setObjectName("fileCombo")
        self.horizontalLayout.addWidget(self.fileCombo)
        self.gridLayout.addLayout(self.horizontalLayout, 0, 0, 1, 3)
        self.saveBtn = FeedbackButton(Form)
        self.saveBtn.setObjectName("saveBtn")
        self.gridLayout.addWidget(self.saveBtn, 1, 0, 1, 1)
        self.saveAsBtn = FeedbackButton(Form)
        self.saveAsBtn.setObjectName("saveAsBtn")
        self.gridLayout.addWidget(self.saveAsBtn, 1, 1, 1, 1)
        self.deleteBtn = FeedbackButton(Form)
        self.deleteBtn.setObjectName("deleteBtn")
        self.gridLayout.addWidget(self.deleteBtn, 1, 2, 1, 1)
        self.tree = TreeWidget(Form)
        self.tree.setRootIsDecorated(False)
        self.tree.setObjectName("tree")
        self.gridLayout.addWidget(self.tree, 2, 0, 1, 3)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.label.setText(_translate("Form", "Color Scheme:"))
        self.saveBtn.setText(_translate("Form", "Save"))
        self.saveAsBtn.setText(_translate("Form", "Save As.."))
        self.deleteBtn.setText(_translate("Form", "Delete"))
        self.tree.headerItem().setText(0, _translate("Form", "arg"))
        self.tree.headerItem().setText(1, _translate("Form", "op"))
        self.tree.headerItem().setText(2, _translate("Form", "min"))
        self.tree.headerItem().setText(3, _translate("Form", "max"))
        self.tree.headerItem().setText(4, _translate("Form", "colors"))
        self.tree.headerItem().setText(5, _translate("Form", "remove"))

from acq4.pyqtgraph import FeedbackButton, TreeWidget
