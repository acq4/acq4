# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'SpatialCorrelatorCtrlTemplate.ui'
#
# Created: Thu Mar  8 20:42:05 2012
#      by: PyQt4 UI code generator 4.9
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
        Form.resize(254, 152)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(3)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setSpacing(1)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.horizontalLayout.addWidget(self.label)
        self.spontSpin = SpinBox(Form)
        self.spontSpin.setSuffix(_fromUtf8(""))
        self.spontSpin.setObjectName(_fromUtf8("spontSpin"))
        self.horizontalLayout.addWidget(self.spontSpin)
        self.gridLayout.addLayout(self.horizontalLayout, 0, 0, 1, 2)
        self.horizontalLayout_2 = QtGui.QHBoxLayout()
        self.horizontalLayout_2.setSpacing(1)
        self.horizontalLayout_2.setObjectName(_fromUtf8("horizontalLayout_2"))
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.horizontalLayout_2.addWidget(self.label_2)
        self.deltaTSpin = SpinBox(Form)
        self.deltaTSpin.setObjectName(_fromUtf8("deltaTSpin"))
        self.horizontalLayout_2.addWidget(self.deltaTSpin)
        self.gridLayout.addLayout(self.horizontalLayout_2, 1, 0, 1, 2)
        self.horizontalLayout_3 = QtGui.QHBoxLayout()
        self.horizontalLayout_3.setSpacing(1)
        self.horizontalLayout_3.setObjectName(_fromUtf8("horizontalLayout_3"))
        self.label_3 = QtGui.QLabel(Form)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.horizontalLayout_3.addWidget(self.label_3)
        self.radiusSpin = SpinBox(Form)
        self.radiusSpin.setObjectName(_fromUtf8("radiusSpin"))
        self.horizontalLayout_3.addWidget(self.radiusSpin)
        self.gridLayout.addLayout(self.horizontalLayout_3, 2, 0, 1, 2)
        self.horizontalLayout_4 = QtGui.QHBoxLayout()
        self.horizontalLayout_4.setSpacing(1)
        self.horizontalLayout_4.setObjectName(_fromUtf8("horizontalLayout_4"))
        self.label_4 = QtGui.QLabel(Form)
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.horizontalLayout_4.addWidget(self.label_4)
        self.significanceSpin = SpinBox(Form)
        self.significanceSpin.setObjectName(_fromUtf8("significanceSpin"))
        self.horizontalLayout_4.addWidget(self.significanceSpin)
        self.gridLayout.addLayout(self.horizontalLayout_4, 3, 0, 1, 2)
        self.disableChk = QtGui.QCheckBox(Form)
        self.disableChk.setObjectName(_fromUtf8("disableChk"))
        self.gridLayout.addWidget(self.disableChk, 4, 0, 1, 1)
        self.processBtn = QtGui.QPushButton(Form)
        self.processBtn.setObjectName(_fromUtf8("processBtn"))
        self.gridLayout.addWidget(self.processBtn, 4, 1, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Spontaneous Event Rate:", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "Post-stimulus time window:", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("Form", "Correlation Radius:", None, QtGui.QApplication.UnicodeUTF8))
        self.label_4.setText(QtGui.QApplication.translate("Form", "Significance Threshold:", None, QtGui.QApplication.UnicodeUTF8))
        self.disableChk.setText(QtGui.QApplication.translate("Form", "Disable", None, QtGui.QApplication.UnicodeUTF8))
        self.processBtn.setText(QtGui.QApplication.translate("Form", "Process", None, QtGui.QApplication.UnicodeUTF8))

from pyqtgraph.widgets.SpinBox import SpinBox
