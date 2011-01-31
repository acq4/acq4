# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'MapCtrlTemplate.ui'
#
# Created: Sun Jan 30 12:53:05 2011
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(308, 250)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName("gridLayout")
        self.mapTable = QtGui.QTreeWidget(Form)
        self.mapTable.setObjectName("mapTable")
        self.gridLayout.addWidget(self.mapTable, 0, 0, 1, 3)
        self.newMapBtn = QtGui.QPushButton(Form)
        self.newMapBtn.setObjectName("newMapBtn")
        self.gridLayout.addWidget(self.newMapBtn, 1, 0, 1, 1)
        self.loadMapBtn = QtGui.QPushButton(Form)
        self.loadMapBtn.setObjectName("loadMapBtn")
        self.gridLayout.addWidget(self.loadMapBtn, 1, 1, 1, 1)
        self.delMapBtn = QtGui.QPushButton(Form)
        self.delMapBtn.setObjectName("delMapBtn")
        self.gridLayout.addWidget(self.delMapBtn, 1, 2, 1, 1)
        self.addScanBtn = QtGui.QPushButton(Form)
        self.addScanBtn.setObjectName("addScanBtn")
        self.gridLayout.addWidget(self.addScanBtn, 2, 0, 1, 1)
        self.removeScanBtn = QtGui.QPushButton(Form)
        self.removeScanBtn.setObjectName("removeScanBtn")
        self.gridLayout.addWidget(self.removeScanBtn, 2, 1, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.mapTable.headerItem().setText(0, QtGui.QApplication.translate("Form", "Map/Scan", None, QtGui.QApplication.UnicodeUTF8))
        self.newMapBtn.setText(QtGui.QApplication.translate("Form", "New Map", None, QtGui.QApplication.UnicodeUTF8))
        self.loadMapBtn.setText(QtGui.QApplication.translate("Form", "Load Selected", None, QtGui.QApplication.UnicodeUTF8))
        self.delMapBtn.setText(QtGui.QApplication.translate("Form", "Delete", None, QtGui.QApplication.UnicodeUTF8))
        self.addScanBtn.setText(QtGui.QApplication.translate("Form", "Add Scan", None, QtGui.QApplication.UnicodeUTF8))
        self.removeScanBtn.setText(QtGui.QApplication.translate("Form", "Remove Scan", None, QtGui.QApplication.UnicodeUTF8))

