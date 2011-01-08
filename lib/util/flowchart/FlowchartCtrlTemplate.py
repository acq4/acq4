# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'FlowchartCtrlTemplate.ui'
#
# Created: Fri Jan  7 13:21:27 2011
#      by: PyQt4 UI code generator 4.7.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(217, 499)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName("gridLayout")
        self.loadBtn = QtGui.QPushButton(Form)
        self.loadBtn.setObjectName("loadBtn")
        self.gridLayout.addWidget(self.loadBtn, 0, 0, 1, 1)
        self.saveBtn = QtGui.QPushButton(Form)
        self.saveBtn.setObjectName("saveBtn")
        self.gridLayout.addWidget(self.saveBtn, 0, 1, 1, 2)
        self.saveAsBtn = QtGui.QPushButton(Form)
        self.saveAsBtn.setObjectName("saveAsBtn")
        self.gridLayout.addWidget(self.saveAsBtn, 0, 3, 1, 1)
        self.modeBtn = QtGui.QPushButton(Form)
        self.modeBtn.setCheckable(True)
        self.modeBtn.setFlat(False)
        self.modeBtn.setObjectName("modeBtn")
        self.gridLayout.addWidget(self.modeBtn, 3, 0, 1, 2)
        self.showChartBtn = QtGui.QPushButton(Form)
        self.showChartBtn.setCheckable(True)
        self.showChartBtn.setObjectName("showChartBtn")
        self.gridLayout.addWidget(self.showChartBtn, 3, 2, 1, 2)
        self.ctrlList = TreeWidget(Form)
        self.ctrlList.setObjectName("ctrlList")
        self.ctrlList.headerItem().setText(0, "1")
        self.gridLayout.addWidget(self.ctrlList, 2, 0, 1, 4)
        self.fileNameLabel = QtGui.QLabel(Form)
        self.fileNameLabel.setText("")
        self.fileNameLabel.setObjectName("fileNameLabel")
        self.gridLayout.addWidget(self.fileNameLabel, 1, 0, 1, 4)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.loadBtn.setText(QtGui.QApplication.translate("Form", "Load..", None, QtGui.QApplication.UnicodeUTF8))
        self.saveBtn.setText(QtGui.QApplication.translate("Form", "Save", None, QtGui.QApplication.UnicodeUTF8))
        self.saveAsBtn.setText(QtGui.QApplication.translate("Form", "As..", None, QtGui.QApplication.UnicodeUTF8))
        self.modeBtn.setText(QtGui.QApplication.translate("Form", "Advanced..", None, QtGui.QApplication.UnicodeUTF8))
        self.showChartBtn.setText(QtGui.QApplication.translate("Form", "Flowchart", None, QtGui.QApplication.UnicodeUTF8))

from TreeWidget import TreeWidget
