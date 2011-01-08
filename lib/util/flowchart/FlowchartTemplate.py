# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'FlowchartTemplate.ui'
#
# Created: Fri Jan  7 13:21:25 2011
#      by: PyQt4 UI code generator 4.7.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(792, 517)
        self.gridLayout_2 = QtGui.QGridLayout(Form)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.splitter_2 = QtGui.QSplitter(Form)
        self.splitter_2.setOrientation(QtCore.Qt.Vertical)
        self.splitter_2.setObjectName("splitter_2")
        self.splitter = QtGui.QSplitter(self.splitter_2)
        self.splitter.setOrientation(QtCore.Qt.Horizontal)
        self.splitter.setObjectName("splitter")
        self.view = FlowchartGraphicsView(self.splitter)
        self.view.setObjectName("view")
        self.layoutWidget = QtGui.QWidget(self.splitter)
        self.layoutWidget.setObjectName("layoutWidget")
        self.gridLayout = QtGui.QGridLayout(self.layoutWidget)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.label = QtGui.QLabel(self.layoutWidget)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 1, 0, 1, 2)
        self.outputTree = DataTreeWidget(self.layoutWidget)
        self.outputTree.setObjectName("outputTree")
        self.outputTree.headerItem().setText(0, "1")
        self.gridLayout.addWidget(self.outputTree, 2, 0, 1, 2)
        self.selDescLabel = QtGui.QLabel(self.layoutWidget)
        self.selDescLabel.setText("")
        self.selDescLabel.setAlignment(QtCore.Qt.AlignLeading|QtCore.Qt.AlignLeft|QtCore.Qt.AlignTop)
        self.selDescLabel.setWordWrap(True)
        self.selDescLabel.setObjectName("selDescLabel")
        self.gridLayout.addWidget(self.selDescLabel, 5, 0, 1, 2)
        self.selectedTree = DataTreeWidget(self.layoutWidget)
        self.selectedTree.setObjectName("selectedTree")
        self.selectedTree.headerItem().setText(0, "1")
        self.gridLayout.addWidget(self.selectedTree, 6, 0, 1, 2)
        self.selNameLabel = QtGui.QLabel(self.layoutWidget)
        font = QtGui.QFont()
        font.setWeight(75)
        font.setBold(True)
        self.selNameLabel.setFont(font)
        self.selNameLabel.setText("")
        self.selNameLabel.setObjectName("selNameLabel")
        self.gridLayout.addWidget(self.selNameLabel, 4, 1, 1, 1)
        self.addNodeBtn = QtGui.QPushButton(self.layoutWidget)
        self.addNodeBtn.setObjectName("addNodeBtn")
        self.gridLayout.addWidget(self.addNodeBtn, 0, 0, 1, 1)
        self.hoverText = QtGui.QTextEdit(self.splitter_2)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.hoverText.sizePolicy().hasHeightForWidth())
        self.hoverText.setSizePolicy(sizePolicy)
        self.hoverText.setObjectName("hoverText")
        self.gridLayout_2.addWidget(self.splitter_2, 0, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Output:", None, QtGui.QApplication.UnicodeUTF8))
        self.addNodeBtn.setText(QtGui.QApplication.translate("Form", "Add Node..", None, QtGui.QApplication.UnicodeUTF8))

from DataTreeWidget import DataTreeWidget
from FlowchartGraphicsView import FlowchartGraphicsView
