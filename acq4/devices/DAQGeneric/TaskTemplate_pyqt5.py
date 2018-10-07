# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/devices/DAQGeneric/TaskTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(770, 365)
        self.verticalLayout = QtWidgets.QVBoxLayout(Form)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.topSplitter = QtWidgets.QSplitter(Form)
        self.topSplitter.setOrientation(Qt.Qt.Horizontal)
        self.topSplitter.setObjectName("topSplitter")
        self.controlSplitter = QtWidgets.QSplitter(self.topSplitter)
        self.controlSplitter.setOrientation(Qt.Qt.Vertical)
        self.controlSplitter.setObjectName("controlSplitter")
        self.plotSplitter = QtWidgets.QSplitter(self.topSplitter)
        self.plotSplitter.setOrientation(Qt.Qt.Vertical)
        self.plotSplitter.setObjectName("plotSplitter")
        self.verticalLayout.addWidget(self.topSplitter)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))

