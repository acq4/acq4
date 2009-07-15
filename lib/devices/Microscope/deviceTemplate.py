# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'deviceTemplate.ui'
#
# Created: Mon Jul 13 16:51:07 2009
#      by: PyQt4 UI code generator 4.4.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(295, 48)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName("gridLayout")
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.positionLabel = QtGui.QLabel(Form)
        self.positionLabel.setObjectName("positionLabel")
        self.gridLayout.addWidget(self.positionLabel, 0, 1, 1, 1)
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)
        self.objectiveLayout = QtGui.QVBoxLayout()
        self.objectiveLayout.setObjectName("objectiveLayout")
        self.gridLayout.addLayout(self.objectiveLayout, 1, 1, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Position:", None, QtGui.QApplication.UnicodeUTF8))
        self.positionLabel.setText(QtGui.QApplication.translate("Form", "0, 0", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "Objective:", None, QtGui.QApplication.UnicodeUTF8))

