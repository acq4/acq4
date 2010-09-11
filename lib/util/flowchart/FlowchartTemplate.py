# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'FlowchartTemplate.ui'
#
# Created: Sat Sep 11 17:39:29 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(779, 454)
        self.gridLayout_2 = QtGui.QGridLayout(Form)
        self.gridLayout_2.setMargin(0)
        self.gridLayout_2.setSpacing(0)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.splitter = QtGui.QSplitter(Form)
        self.splitter.setOrientation(QtCore.Qt.Horizontal)
        self.splitter.setObjectName("splitter")
        self.layoutWidget = QtGui.QWidget(self.splitter)
        self.layoutWidget.setObjectName("layoutWidget")
        self.verticalLayout = QtGui.QVBoxLayout(self.layoutWidget)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.addNodeBtn = QtGui.QPushButton(self.layoutWidget)
        self.addNodeBtn.setObjectName("addNodeBtn")
        self.verticalLayout.addWidget(self.addNodeBtn)
        self.ctrlList = TreeWidget(self.layoutWidget)
        self.ctrlList.setObjectName("ctrlList")
        self.ctrlList.headerItem().setText(0, "1")
        self.verticalLayout.addWidget(self.ctrlList)
        self.view = FlowchartGraphicsView(self.splitter)
        self.view.setObjectName("view")
        self.layoutWidget1 = QtGui.QWidget(self.splitter)
        self.layoutWidget1.setObjectName("layoutWidget1")
        self.gridLayout = QtGui.QGridLayout(self.layoutWidget1)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.label = QtGui.QLabel(self.layoutWidget1)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 0, 0, 1, 2)
        self.outputTree = DataTreeWidget(self.layoutWidget1)
        self.outputTree.setObjectName("outputTree")
        self.gridLayout.addWidget(self.outputTree, 1, 0, 1, 2)
        self.selDescLabel = QtGui.QLabel(self.layoutWidget1)
        self.selDescLabel.setText("")
        self.selDescLabel.setAlignment(QtCore.Qt.AlignLeading|QtCore.Qt.AlignLeft|QtCore.Qt.AlignTop)
        self.selDescLabel.setWordWrap(True)
        self.selDescLabel.setObjectName("selDescLabel")
        self.gridLayout.addWidget(self.selDescLabel, 4, 0, 1, 2)
        self.selectedTree = DataTreeWidget(self.layoutWidget1)
        self.selectedTree.setObjectName("selectedTree")
        self.gridLayout.addWidget(self.selectedTree, 5, 0, 1, 2)
        self.selNameLabel = QtGui.QLabel(self.layoutWidget1)
        font = QtGui.QFont()
        font.setWeight(75)
        font.setBold(True)
        self.selNameLabel.setFont(font)
        self.selNameLabel.setText("")
        self.selNameLabel.setObjectName("selNameLabel")
        self.gridLayout.addWidget(self.selNameLabel, 3, 1, 1, 1)
        self.gridLayout_2.addWidget(self.splitter, 0, 0, 1, 1)
        self.hoverLabel = QtGui.QLineEdit(Form)
        self.hoverLabel.setReadOnly(True)
        self.hoverLabel.setObjectName("hoverLabel")
        self.gridLayout_2.addWidget(self.hoverLabel, 1, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.addNodeBtn.setText(QtGui.QApplication.translate("Form", "Add Node..", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Output:", None, QtGui.QApplication.UnicodeUTF8))

from DataTreeWidget import DataTreeWidget
from FlowchartGraphicsView import FlowchartGraphicsView
from TreeWidget import TreeWidget
