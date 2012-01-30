# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/util/DatabaseGui/DatabaseTemplate.ui'
#
# Created: Wed Jan 11 17:59:35 2012
#      by: PyQt4 UI code generator 4.8.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    _fromUtf8 = lambda s: s

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName(_fromUtf8("Form"))
        Form.resize(274, 39)
        self.gridLayout_2 = QtGui.QGridLayout(Form)
        self.gridLayout_2.setMargin(0)
        self.gridLayout_2.setSpacing(0)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.horizontalLayout.addWidget(self.label)
        self.dbLabel = QtGui.QLabel(Form)
        self.dbLabel.setObjectName(_fromUtf8("dbLabel"))
        self.horizontalLayout.addWidget(self.dbLabel)
        self.gridLayout_2.addLayout(self.horizontalLayout, 0, 0, 1, 2)
        self.tableArea = QtGui.QWidget(Form)
        self.tableArea.setObjectName(_fromUtf8("tableArea"))
        self.gridLayout = QtGui.QGridLayout(self.tableArea)
        self.gridLayout.setMargin(0)
        self.gridLayout.setVerticalSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.gridLayout_2.addWidget(self.tableArea, 1, 0, 1, 2)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Database:", None, QtGui.QApplication.UnicodeUTF8))
        self.dbLabel.setText(QtGui.QApplication.translate("Form", "[ no DB loaded ]", None, QtGui.QApplication.UnicodeUTF8))

