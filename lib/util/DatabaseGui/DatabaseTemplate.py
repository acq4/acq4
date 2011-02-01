# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'DatabaseTemplate.ui'
#
# Created: Tue Feb  1 10:33:35 2011
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(274, 39)
        self.gridLayout_2 = QtGui.QGridLayout(Form)
        self.gridLayout_2.setMargin(0)
        self.gridLayout_2.setSpacing(0)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.dbLabel = QtGui.QLabel(Form)
        self.dbLabel.setObjectName("dbLabel")
        self.horizontalLayout.addWidget(self.dbLabel)
        self.gridLayout_2.addLayout(self.horizontalLayout, 0, 0, 1, 2)
        self.tableArea = QtGui.QWidget(Form)
        self.tableArea.setObjectName("tableArea")
        self.gridLayout = QtGui.QGridLayout(self.tableArea)
        self.gridLayout.setVerticalSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.gridLayout_2.addWidget(self.tableArea, 1, 0, 1, 2)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Database:", None, QtGui.QApplication.UnicodeUTF8))
        self.dbLabel.setText(QtGui.QApplication.translate("Form", "[ no DB loaded ]", None, QtGui.QApplication.UnicodeUTF8))

