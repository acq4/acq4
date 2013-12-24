# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/analysis/atlas/atlasCtrlTemplate.ui'
#
# Created: Tue Dec 24 01:49:11 2013
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
        Form.resize(233, 114)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(3)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.setSliceBtn = QtGui.QPushButton(Form)
        self.setSliceBtn.setObjectName(_fromUtf8("setSliceBtn"))
        self.gridLayout.addWidget(self.setSliceBtn, 0, 0, 1, 2)
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)
        self.sliceLabel = QtGui.QLabel(Form)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.sliceLabel.setFont(font)
        self.sliceLabel.setObjectName(_fromUtf8("sliceLabel"))
        self.gridLayout.addWidget(self.sliceLabel, 1, 1, 1, 1)
        self.groupBox = QtGui.QGroupBox(Form)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout_3 = QtGui.QGridLayout(self.groupBox)
        self.gridLayout_3.setMargin(2)
        self.gridLayout_3.setSpacing(1)
        self.gridLayout_3.setObjectName(_fromUtf8("gridLayout_3"))
        self.dbWidget = DatabaseGui(self.groupBox)
        self.dbWidget.setObjectName(_fromUtf8("dbWidget"))
        self.gridLayout_3.addWidget(self.dbWidget, 0, 0, 1, 3)
        self.storeBtn = FeedbackButton(self.groupBox)
        self.storeBtn.setObjectName(_fromUtf8("storeBtn"))
        self.gridLayout_3.addWidget(self.storeBtn, 1, 0, 1, 1)
        spacerItem = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout_3.addItem(spacerItem, 1, 2, 1, 1)
        self.gridLayout.addWidget(self.groupBox, 2, 0, 1, 2)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.setSliceBtn.setText(_translate("Form", "Set current slice from selecion", None))
        self.label_2.setText(_translate("Form", "Current slice:", None))
        self.sliceLabel.setText(_translate("Form", "None", None))
        self.groupBox.setTitle(_translate("Form", "Database Tables", None))
        self.storeBtn.setText(_translate("Form", "Store item positions to DB", None))

from acq4.util.DatabaseGui import DatabaseGui
from acq4.pyqtgraph.widgets.FeedbackButton import FeedbackButton
