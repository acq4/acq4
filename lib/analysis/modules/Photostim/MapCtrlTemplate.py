# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'MapCtrlTemplate.ui'
#
# Created: Wed Feb  2 11:56:12 2011
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(329, 174)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setVerticalSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.mapTable = QtGui.QTreeWidget(Form)
        self.mapTable.setObjectName("mapTable")
        self.gridLayout.addWidget(self.mapTable, 0, 0, 1, 3)
        self.newMapBtn = FeedbackButton(Form)
        self.newMapBtn.setObjectName("newMapBtn")
        self.gridLayout.addWidget(self.newMapBtn, 1, 0, 1, 1)
        self.loadMapBtn = FeedbackButton(Form)
        self.loadMapBtn.setObjectName("loadMapBtn")
        self.gridLayout.addWidget(self.loadMapBtn, 1, 1, 1, 1)
        self.delMapBtn = FeedbackButton(Form)
        self.delMapBtn.setObjectName("delMapBtn")
        self.gridLayout.addWidget(self.delMapBtn, 1, 2, 1, 1)
        self.addScanBtn = FeedbackButton(Form)
        self.addScanBtn.setObjectName("addScanBtn")
        self.gridLayout.addWidget(self.addScanBtn, 2, 0, 1, 1)
        self.removeScanBtn = FeedbackButton(Form)
        self.removeScanBtn.setObjectName("removeScanBtn")
        self.gridLayout.addWidget(self.removeScanBtn, 2, 1, 1, 1)
        self.clearDBSpotBtn = FeedbackButton(Form)
        self.clearDBSpotBtn.setObjectName("clearDBSpotBtn")
        self.gridLayout.addWidget(self.clearDBSpotBtn, 5, 1, 1, 1)
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 5, 0, 1, 1)
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 4, 0, 1, 1)
        self.clearDBScanBtn = FeedbackButton(Form)
        self.clearDBScanBtn.setObjectName("clearDBScanBtn")
        self.gridLayout.addWidget(self.clearDBScanBtn, 4, 1, 1, 1)
        self.storeDBScanBtn = FeedbackButton(Form)
        self.storeDBScanBtn.setObjectName("storeDBScanBtn")
        self.gridLayout.addWidget(self.storeDBScanBtn, 4, 2, 1, 1)
        self.storeDBSpotBtn = FeedbackButton(Form)
        self.storeDBSpotBtn.setObjectName("storeDBSpotBtn")
        self.gridLayout.addWidget(self.storeDBSpotBtn, 5, 2, 1, 1)
        self.line = QtGui.QFrame(Form)
        self.line.setFrameShape(QtGui.QFrame.HLine)
        self.line.setFrameShadow(QtGui.QFrame.Sunken)
        self.line.setObjectName("line")
        self.gridLayout.addWidget(self.line, 3, 0, 1, 3)

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
        self.clearDBSpotBtn.setText(QtGui.QApplication.translate("Form", "Clear DB Entry", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Selected Spot:", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "Selected Scan:", None, QtGui.QApplication.UnicodeUTF8))
        self.clearDBScanBtn.setText(QtGui.QApplication.translate("Form", "Clear DB Entry", None, QtGui.QApplication.UnicodeUTF8))
        self.storeDBScanBtn.setText(QtGui.QApplication.translate("Form", "Store to DB", None, QtGui.QApplication.UnicodeUTF8))
        self.storeDBSpotBtn.setText(QtGui.QApplication.translate("Form", "Store to DB", None, QtGui.QApplication.UnicodeUTF8))

from FeedbackButton import FeedbackButton
