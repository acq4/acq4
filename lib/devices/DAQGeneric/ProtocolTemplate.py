# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ProtocolTemplate.ui'
#
# Created: Sun Dec 18 19:22:36 2011
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
        Form.resize(770, 365)
        self.verticalLayout = QtGui.QVBoxLayout(Form)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.topSplitter = QtGui.QSplitter(Form)
        self.topSplitter.setOrientation(QtCore.Qt.Horizontal)
        self.topSplitter.setObjectName(_fromUtf8("topSplitter"))
        self.controlSplitter = QtGui.QSplitter(self.topSplitter)
        self.controlSplitter.setOrientation(QtCore.Qt.Vertical)
        self.controlSplitter.setObjectName(_fromUtf8("controlSplitter"))
        self.plotSplitter = QtGui.QSplitter(self.topSplitter)
        self.plotSplitter.setOrientation(QtCore.Qt.Vertical)
        self.plotSplitter.setObjectName(_fromUtf8("plotSplitter"))
        self.verticalLayout.addWidget(self.topSplitter)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))

