# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/analysis/atlas/atlasCtrlTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(233, 114)
        self.gridLayout = QtWidgets.QGridLayout(Form)
        self.gridLayout.setContentsMargins(3, 3, 3, 3)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName("gridLayout")
        self.setSliceBtn = QtWidgets.QPushButton(Form)
        self.setSliceBtn.setObjectName("setSliceBtn")
        self.gridLayout.addWidget(self.setSliceBtn, 0, 0, 1, 2)
        self.label_2 = QtWidgets.QLabel(Form)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)
        self.sliceLabel = QtWidgets.QLabel(Form)
        font = Qt.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.sliceLabel.setFont(font)
        self.sliceLabel.setObjectName("sliceLabel")
        self.gridLayout.addWidget(self.sliceLabel, 1, 1, 1, 1)
        self.groupBox = QtWidgets.QGroupBox(Form)
        self.groupBox.setObjectName("groupBox")
        self.gridLayout_3 = QtWidgets.QGridLayout(self.groupBox)
        self.gridLayout_3.setContentsMargins(2, 2, 2, 2)
        self.gridLayout_3.setSpacing(1)
        self.gridLayout_3.setObjectName("gridLayout_3")
        self.dbWidget = DatabaseGui(self.groupBox)
        self.dbWidget.setObjectName("dbWidget")
        self.gridLayout_3.addWidget(self.dbWidget, 0, 0, 1, 3)
        self.storeBtn = FeedbackButton(self.groupBox)
        self.storeBtn.setObjectName("storeBtn")
        self.gridLayout_3.addWidget(self.storeBtn, 1, 0, 1, 1)
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.gridLayout_3.addItem(spacerItem, 1, 2, 1, 1)
        self.gridLayout.addWidget(self.groupBox, 2, 0, 1, 2)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.setSliceBtn.setText(_translate("Form", "Set current slice from selecion"))
        self.label_2.setText(_translate("Form", "Current slice:"))
        self.sliceLabel.setText(_translate("Form", "None"))
        self.groupBox.setTitle(_translate("Form", "Database Tables"))
        self.storeBtn.setText(_translate("Form", "Store item positions to DB"))

from acq4.pyqtgraph.widgets.FeedbackButton import FeedbackButton
from acq4.util.DatabaseGui import DatabaseGui
