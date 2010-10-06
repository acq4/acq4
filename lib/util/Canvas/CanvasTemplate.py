# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'CanvasTemplate.ui'
#
# Created: Wed Oct  6 12:02:05 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(668, 414)
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
        self.ctrlLayout = QtGui.QVBoxLayout(self.widget)
        self.ctrlLayout.setSpacing(0)
        self.ctrlLayout.setObjectName("ctrlLayout")
        self.pushButton = QtGui.QPushButton(self.widget)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.pushButton.sizePolicy().hasHeightForWidth())
        self.pushButton.setSizePolicy(sizePolicy)
        self.pushButton.setObjectName("pushButton")
        self.ctrlLayout.addWidget(self.pushButton)
        self.itemList = TreeWidget(self.widget)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(100)
        sizePolicy.setHeightForWidth(self.itemList.sizePolicy().hasHeightForWidth())
        self.itemList.setSizePolicy(sizePolicy)
        self.itemList.setHeaderHidden(True)
        self.itemList.setObjectName("itemList")
        self.ctrlLayout.addWidget(self.itemList)
        self.gridLayout.addWidget(self.splitter, 0, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.pushButton.setText(QtGui.QApplication.translate("Form", "Auto Range", None, QtGui.QApplication.UnicodeUTF8))

from TreeWidget import TreeWidget
from pyqtgraph.GraphicsView import GraphicsView
