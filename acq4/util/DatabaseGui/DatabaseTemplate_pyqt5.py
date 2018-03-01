# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/util/DatabaseGui/DatabaseTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(274, 39)
        self.gridLayout_2 = QtWidgets.QGridLayout(Form)
        self.gridLayout_2.setContentsMargins(0, 0, 0, 0)
        self.gridLayout_2.setSpacing(0)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label = QtWidgets.QLabel(Form)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.dbLabel = QtWidgets.QLabel(Form)
        self.dbLabel.setObjectName("dbLabel")
        self.horizontalLayout.addWidget(self.dbLabel)
        self.gridLayout_2.addLayout(self.horizontalLayout, 0, 0, 1, 2)
        self.tableArea = QtWidgets.QWidget(Form)
        self.tableArea.setObjectName("tableArea")
        self.gridLayout = QtWidgets.QGridLayout(self.tableArea)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setVerticalSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.gridLayout_2.addWidget(self.tableArea, 1, 0, 1, 2)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.label.setText(_translate("Form", "Database:"))
        self.dbLabel.setText(_translate("Form", "[ no DB loaded ]"))

