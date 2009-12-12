# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ProtocolTemplate.ui'
#
# Created: Fri Dec 11 09:09:22 2009
#      by: PyQt4 UI code generator 4.5.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(770, 365)
        self.verticalLayout = QtGui.QVBoxLayout(Form)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.topSplitter = QtGui.QSplitter(Form)
        self.topSplitter.setOrientation(QtCore.Qt.Horizontal)
        self.topSplitter.setObjectName("topSplitter")
        self.controlSplitter = QtGui.QSplitter(self.topSplitter)
        self.controlSplitter.setOrientation(QtCore.Qt.Vertical)
        self.controlSplitter.setObjectName("controlSplitter")
        self.plotSplitter = QtGui.QSplitter(self.topSplitter)
        self.plotSplitter.setOrientation(QtCore.Qt.Vertical)
        self.plotSplitter.setObjectName("plotSplitter")
        self.verticalLayout.addWidget(self.topSplitter)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))

