# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/devices/DAQGeneric/ProtocolTemplate.ui'
#
# Created: Wed Aug 17 13:49:52 2011
#      by: pyside-uic 0.2.11 running on PySide 1.0.5
#
# WARNING! All changes made in this file will be lost!

from PySide import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(770, 365)
        self.verticalLayout = QtGui.QVBoxLayout(Form)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
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

