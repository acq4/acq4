# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'AnalyzerTemplate.ui'
#
# Created: Sat Sep  4 19:52:06 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(940, 762)
        self.loadSequenceBtn = QtGui.QPushButton(Form)
        self.loadSequenceBtn.setGeometry(QtCore.QRect(220, 10, 105, 24))
        self.loadSequenceBtn.setObjectName("loadSequenceBtn")
        self.loadDataBtn = QtGui.QPushButton(Form)
        self.loadDataBtn.setGeometry(QtCore.QRect(110, 10, 105, 24))
        self.loadDataBtn.setObjectName("loadDataBtn")
        self.outputTree = DataTreeWidget(Form)
        self.outputTree.setGeometry(QtCore.QRect(700, 0, 241, 761))
        self.outputTree.setObjectName("outputTree")
        self.outputTree.headerItem().setText(0, "1")
        self.verticalLayoutWidget = QtGui.QWidget(Form)
        self.verticalLayoutWidget.setGeometry(QtCore.QRect(0, 40, 691, 711))
        self.verticalLayoutWidget.setObjectName("verticalLayoutWidget")
        self.flowchartLayout = QtGui.QVBoxLayout(self.verticalLayoutWidget)
        self.flowchartLayout.setObjectName("flowchartLayout")
        self.addOutputBtn = QtGui.QPushButton(Form)
        self.addOutputBtn.setGeometry(QtCore.QRect(0, 10, 105, 24))
        self.addOutputBtn.setObjectName("addOutputBtn")

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.loadSequenceBtn.setText(QtGui.QApplication.translate("Form", "Load Sequence", None, QtGui.QApplication.UnicodeUTF8))
        self.loadDataBtn.setText(QtGui.QApplication.translate("Form", "Load Data", None, QtGui.QApplication.UnicodeUTF8))
        self.addOutputBtn.setText(QtGui.QApplication.translate("Form", "Add Output", None, QtGui.QApplication.UnicodeUTF8))

from DataTreeWidget import DataTreeWidget
