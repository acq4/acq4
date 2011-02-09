# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'CanvasTemplate.ui'
#
# Created: Wed Feb  2 23:10:44 2011
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(487, 422)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.splitter = QtGui.QSplitter(Form)
        self.splitter.setOrientation(QtCore.Qt.Horizontal)
        self.splitter.setObjectName("splitter")
        self.view = GraphicsView(self.splitter)
        self.view.setObjectName("view")
        self.widget = QtGui.QWidget(self.splitter)
        self.widget.setObjectName("widget")
        self.verticalLayout = QtGui.QVBoxLayout(self.widget)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.storeSvgBtn = QtGui.QPushButton(self.widget)
        self.storeSvgBtn.setObjectName("storeSvgBtn")
        self.horizontalLayout.addWidget(self.storeSvgBtn)
        self.storePngBtn = QtGui.QPushButton(self.widget)
        self.storePngBtn.setObjectName("storePngBtn")
        self.horizontalLayout.addWidget(self.storePngBtn)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.autoRangeBtn = QtGui.QPushButton(self.widget)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.autoRangeBtn.sizePolicy().hasHeightForWidth())
        self.autoRangeBtn.setSizePolicy(sizePolicy)
        self.autoRangeBtn.setObjectName("autoRangeBtn")
        self.verticalLayout.addWidget(self.autoRangeBtn)
        self.itemList = TreeWidget(self.widget)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(100)
        sizePolicy.setHeightForWidth(self.itemList.sizePolicy().hasHeightForWidth())
        self.itemList.setSizePolicy(sizePolicy)
        self.itemList.setHeaderHidden(True)
        self.itemList.setObjectName("itemList")
        self.itemList.headerItem().setText(0, "1")
        self.verticalLayout.addWidget(self.itemList)
        self.ctrlLayout = QtGui.QGridLayout()
        self.ctrlLayout.setSpacing(0)
        self.ctrlLayout.setObjectName("ctrlLayout")
        self.verticalLayout.addLayout(self.ctrlLayout)
        self.gridLayout.addWidget(self.splitter, 0, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.storeSvgBtn.setText(QtGui.QApplication.translate("Form", "Store SVG", None, QtGui.QApplication.UnicodeUTF8))
        self.storePngBtn.setText(QtGui.QApplication.translate("Form", "Store PNG", None, QtGui.QApplication.UnicodeUTF8))
        self.autoRangeBtn.setText(QtGui.QApplication.translate("Form", "Auto Range", None, QtGui.QApplication.UnicodeUTF8))

from TreeWidget import TreeWidget
from pyqtgraph.GraphicsView import GraphicsView
