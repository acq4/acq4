# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'CanvasTemplate.ui'
#
# Created: Fri Oct  1 22:08:41 2010
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
        self.verticalLayout = QtGui.QVBoxLayout(self.widget)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.gridCheck = QtGui.QCheckBox(self.widget)
        self.gridCheck.setObjectName("gridCheck")
        self.verticalLayout.addWidget(self.gridCheck)
        self.itemList = TreeWidget(self.widget)
        self.itemList.setObjectName("itemList")
        self.verticalLayout.addWidget(self.itemList)
        self.gridLayout.addWidget(self.splitter, 0, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.gridCheck.setText(QtGui.QApplication.translate("Form", "Show Grid", None, QtGui.QApplication.UnicodeUTF8))

from TreeWidget import TreeWidget
from pyqtgraph.GraphicsView import GraphicsView
