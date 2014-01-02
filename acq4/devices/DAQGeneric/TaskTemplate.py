# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/devices/DAQGeneric/TaskTemplate.ui'
#
# Created: Tue Dec 24 01:49:09 2013
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
        Form.setWindowTitle(_translate("Form", "Form", None))

