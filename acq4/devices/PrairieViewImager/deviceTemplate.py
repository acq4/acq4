# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4\devices\PrairieViewImager\deviceTemplate.ui'
#
# Created by: PyQt4 UI code generator 4.11.4
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
        Form.resize(94, 72)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(3)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.xOffsetSpin = SpinBox(Form)
        self.xOffsetSpin.setObjectName(_fromUtf8("xOffsetSpin"))
        self.gridLayout.addWidget(self.xOffsetSpin, 0, 1, 1, 1)
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)
        self.yOffsetSpin = SpinBox(Form)
        self.yOffsetSpin.setObjectName(_fromUtf8("yOffsetSpin"))
        self.gridLayout.addWidget(self.yOffsetSpin, 1, 1, 1, 1)
        self.zOffsetSpin = SpinBox(Form)
        self.zOffsetSpin.setObjectName(_fromUtf8("zOffsetSpin"))
        self.gridLayout.addWidget(self.zOffsetSpin, 2, 1, 1, 1)
        self.label_3 = QtGui.QLabel(Form)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout.addWidget(self.label_3, 2, 0, 1, 1)
        self.gridLayout.setColumnStretch(1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.label.setText(_translate("Form", "X:", None))
        self.label_2.setText(_translate("Form", "Y:", None))
        self.label_3.setText(_translate("Form", "Z:", None))

from pyqtgraph.widgets.SpinBox import SpinBox
