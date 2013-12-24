# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/analysis/modules/Photostim/MapCtrlTemplate.ui'
#
# Created: Tue Dec 24 01:49:12 2013
#      by: PyQt4 UI code generator 4.10
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    def _fromUtf8(s):
        return s

try:
    _encoding = QtGui.QApplication.UnicodeUTF8
    def _translate(context, text, disambig):
        return QtGui.QApplication.translate(context, text, disambig, _encoding)
except AttributeError:
    def _translate(context, text, disambig):
        return QtGui.QApplication.translate(context, text, disambig)

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName(_fromUtf8("Form"))
        Form.resize(299, 371)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.groupBox_2 = QtGui.QGroupBox(Form)
        self.groupBox_2.setObjectName(_fromUtf8("groupBox_2"))
        self.gridLayout_3 = QtGui.QGridLayout(self.groupBox_2)
        self.gridLayout_3.setMargin(0)
        self.gridLayout_3.setVerticalSpacing(0)
        self.gridLayout_3.setObjectName(_fromUtf8("gridLayout_3"))
        self.mapTable = QtGui.QTreeWidget(self.groupBox_2)
        self.mapTable.setObjectName(_fromUtf8("mapTable"))
        self.gridLayout_3.addWidget(self.mapTable, 0, 0, 1, 3)
        self.newMapBtn = FeedbackButton(self.groupBox_2)
        self.newMapBtn.setObjectName(_fromUtf8("newMapBtn"))
        self.gridLayout_3.addWidget(self.newMapBtn, 1, 0, 1, 1)
        self.loadMapBtn = FeedbackButton(self.groupBox_2)
        self.loadMapBtn.setObjectName(_fromUtf8("loadMapBtn"))
        self.gridLayout_3.addWidget(self.loadMapBtn, 1, 1, 1, 1)
        self.delMapBtn = FeedbackButton(self.groupBox_2)
        self.delMapBtn.setObjectName(_fromUtf8("delMapBtn"))
        self.gridLayout_3.addWidget(self.delMapBtn, 1, 2, 1, 1)
        self.addScanBtn = FeedbackButton(self.groupBox_2)
        self.addScanBtn.setObjectName(_fromUtf8("addScanBtn"))
        self.gridLayout_3.addWidget(self.addScanBtn, 2, 0, 1, 1)
        self.removeScanBtn = FeedbackButton(self.groupBox_2)
        self.removeScanBtn.setObjectName(_fromUtf8("removeScanBtn"))
        self.gridLayout_3.addWidget(self.removeScanBtn, 2, 1, 1, 1)
        self.gridLayout.addWidget(self.groupBox_2, 3, 0, 1, 3)
        self.groupBox = QtGui.QGroupBox(Form)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout_2 = QtGui.QGridLayout(self.groupBox)
        self.gridLayout_2.setMargin(0)
        self.gridLayout_2.setVerticalSpacing(0)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.storeDBSpotBtn = FeedbackButton(self.groupBox)
        self.storeDBSpotBtn.setObjectName(_fromUtf8("storeDBSpotBtn"))
        self.gridLayout_2.addWidget(self.storeDBSpotBtn, 2, 2, 1, 1)
        self.label_2 = QtGui.QLabel(self.groupBox)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout_2.addWidget(self.label_2, 1, 0, 1, 1)
        self.rewriteSpotPosBtn = FeedbackButton(self.groupBox)
        self.rewriteSpotPosBtn.setObjectName(_fromUtf8("rewriteSpotPosBtn"))
        self.gridLayout_2.addWidget(self.rewriteSpotPosBtn, 3, 1, 1, 2)
        self.clearDBScanBtn = FeedbackButton(self.groupBox)
        self.clearDBScanBtn.setObjectName(_fromUtf8("clearDBScanBtn"))
        self.gridLayout_2.addWidget(self.clearDBScanBtn, 1, 1, 1, 1)
        self.clearDBSpotBtn = FeedbackButton(self.groupBox)
        self.clearDBSpotBtn.setObjectName(_fromUtf8("clearDBSpotBtn"))
        self.gridLayout_2.addWidget(self.clearDBSpotBtn, 2, 1, 1, 1)
        self.storeDBScanBtn = FeedbackButton(self.groupBox)
        self.storeDBScanBtn.setObjectName(_fromUtf8("storeDBScanBtn"))
        self.gridLayout_2.addWidget(self.storeDBScanBtn, 1, 2, 1, 1)
        self.label = QtGui.QLabel(self.groupBox)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout_2.addWidget(self.label, 2, 0, 1, 1)
        self.scanTree = TreeWidget(self.groupBox)
        self.scanTree.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.scanTree.setHeaderHidden(False)
        self.scanTree.setObjectName(_fromUtf8("scanTree"))
        self.scanTree.header().setDefaultSectionSize(60)
        self.scanTree.header().setMinimumSectionSize(10)
        self.gridLayout_2.addWidget(self.scanTree, 0, 0, 1, 3)
        self.gridLayout.addWidget(self.groupBox, 2, 0, 1, 3)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.groupBox_2.setTitle(_translate("Form", "Maps", None))
        self.mapTable.headerItem().setText(0, _translate("Form", "Map/Scan", None))
        self.newMapBtn.setText(_translate("Form", "New Map", None))
        self.loadMapBtn.setText(_translate("Form", "Load Selected", None))
        self.delMapBtn.setText(_translate("Form", "Delete", None))
        self.addScanBtn.setText(_translate("Form", "Add Scan", None))
        self.removeScanBtn.setText(_translate("Form", "Remove Scan", None))
        self.groupBox.setTitle(_translate("Form", "Scans Loaded", None))
        self.storeDBSpotBtn.setText(_translate("Form", "Store to DB", None))
        self.label_2.setText(_translate("Form", "Selected Scan:", None))
        self.rewriteSpotPosBtn.setText(_translate("Form", "Re-write spot locations", None))
        self.clearDBScanBtn.setText(_translate("Form", "Clear DB Entry", None))
        self.clearDBSpotBtn.setText(_translate("Form", "Clear DB Entry", None))
        self.storeDBScanBtn.setText(_translate("Form", "Store to DB", None))
        self.label.setText(_translate("Form", "Selected Spot:", None))
        self.scanTree.headerItem().setText(0, _translate("Form", "Scan", None))
        self.scanTree.headerItem().setText(1, _translate("Form", "Display", None))
        self.scanTree.headerItem().setText(2, _translate("Form", "Events", None))
        self.scanTree.headerItem().setText(3, _translate("Form", "Stats", None))

from acq4.pyqtgraph import FeedbackButton, TreeWidget
