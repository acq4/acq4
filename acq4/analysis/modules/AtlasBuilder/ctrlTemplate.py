# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/analysis/modules/AtlasBuilder/ctrlTemplate.ui'
#
# Created: Tue Dec 24 01:49:12 2013
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
        Form.resize(170, 179)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.groupBox = QtGui.QGroupBox(Form)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout_2 = QtGui.QGridLayout(self.groupBox)
        self.gridLayout_2.setMargin(0)
        self.gridLayout_2.setSpacing(0)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.label = QtGui.QLabel(self.groupBox)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout_2.addWidget(self.label, 0, 0, 1, 1)
        self.valueSpin = QtGui.QSpinBox(self.groupBox)
        self.valueSpin.setMaximum(255)
        self.valueSpin.setObjectName(_fromUtf8("valueSpin"))
        self.gridLayout_2.addWidget(self.valueSpin, 0, 1, 1, 1)
        self.label_2 = QtGui.QLabel(self.groupBox)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout_2.addWidget(self.label_2, 1, 0, 1, 1)
        self.labelText = QtGui.QLineEdit(self.groupBox)
        self.labelText.setObjectName(_fromUtf8("labelText"))
        self.gridLayout_2.addWidget(self.labelText, 1, 1, 1, 1)
        self.label_3 = QtGui.QLabel(self.groupBox)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout_2.addWidget(self.label_3, 2, 0, 1, 1)
        self.colorBtn = ColorButton(self.groupBox)
        self.colorBtn.setText(_fromUtf8(""))
        self.colorBtn.setObjectName(_fromUtf8("colorBtn"))
        self.gridLayout_2.addWidget(self.colorBtn, 2, 1, 1, 1)
        self.gridLayout.addWidget(self.groupBox, 0, 0, 1, 2)
        self.label_4 = QtGui.QLabel(Form)
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.gridLayout.addWidget(self.label_4, 1, 0, 1, 1)
        self.penSizeSpin = QtGui.QSpinBox(Form)
        self.penSizeSpin.setMinimum(1)
        self.penSizeSpin.setProperty("value", 1)
        self.penSizeSpin.setObjectName(_fromUtf8("penSizeSpin"))
        self.gridLayout.addWidget(self.penSizeSpin, 1, 1, 1, 1)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 2, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.groupBox.setTitle(_translate("Form", "Labels", None))
        self.label.setText(_translate("Form", "Value", None))
        self.label_2.setText(_translate("Form", "Label", None))
        self.label_3.setText(_translate("Form", "Color", None))
        self.label_4.setText(_translate("Form", "Pen Size", None))

from acq4.pyqtgraph.ColorButton import ColorButton
