# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'DeviceTemplate.ui'
#
# Created: Thu Sep 10 17:18:53 2009
#      by: PyQt4 UI code generator 4.5.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(573, 191)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName("gridLayout")
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.view = QtGui.QGraphicsView(Form)
        self.view.setObjectName("view")
        self.gridLayout.addWidget(self.view, 0, 1, 4, 1)
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.calibrateBtn = QtGui.QPushButton(Form)
        self.calibrateBtn.setObjectName("calibrateBtn")
        self.horizontalLayout.addWidget(self.calibrateBtn)
        self.testBtn = QtGui.QPushButton(Form)
        self.testBtn.setObjectName("testBtn")
        self.horizontalLayout.addWidget(self.testBtn)
        self.deleteBtn = QtGui.QPushButton(Form)
        self.deleteBtn.setObjectName("deleteBtn")
        self.horizontalLayout.addWidget(self.deleteBtn)
        self.gridLayout.addLayout(self.horizontalLayout, 2, 0, 1, 1)
        self.resultLabel = QtGui.QLabel(Form)
        self.resultLabel.setObjectName("resultLabel")
        self.gridLayout.addWidget(self.resultLabel, 3, 0, 1, 1)
        self.calibrationList = QtGui.QTableWidget(Form)
        self.calibrationList.setObjectName("calibrationList")
        self.calibrationList.setColumnCount(3)
        self.calibrationList.setRowCount(0)
        item = QtGui.QTableWidgetItem()
        self.calibrationList.setHorizontalHeaderItem(0, item)
        item = QtGui.QTableWidgetItem()
        self.calibrationList.setHorizontalHeaderItem(1, item)
        item = QtGui.QTableWidgetItem()
        self.calibrationList.setHorizontalHeaderItem(2, item)
        self.gridLayout.addWidget(self.calibrationList, 1, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Calibrations:", None, QtGui.QApplication.UnicodeUTF8))
        self.calibrateBtn.setText(QtGui.QApplication.translate("Form", "Calibrate", None, QtGui.QApplication.UnicodeUTF8))
        self.testBtn.setText(QtGui.QApplication.translate("Form", "Test", None, QtGui.QApplication.UnicodeUTF8))
        self.deleteBtn.setText(QtGui.QApplication.translate("Form", "Delete", None, QtGui.QApplication.UnicodeUTF8))
        self.calibrationList.horizontalHeaderItem(0).setText(QtGui.QApplication.translate("Form", "Objective", None, QtGui.QApplication.UnicodeUTF8))
        self.calibrationList.horizontalHeaderItem(1).setText(QtGui.QApplication.translate("Form", "Spot", None, QtGui.QApplication.UnicodeUTF8))
        self.calibrationList.horizontalHeaderItem(2).setText(QtGui.QApplication.translate("Form", "Date", None, QtGui.QApplication.UnicodeUTF8))

