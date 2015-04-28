# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'RackTemplate.ui'
#
# Created: Mon Apr 06 21:43:17 2015
#      by: PyQt4 UI code generator 4.10.4
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
        Form.resize(259, 117)
        self.horizontalLayout = QtGui.QHBoxLayout(Form)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.gridLayout_2 = QtGui.QGridLayout()
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        spacerItem = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout_2.addItem(spacerItem, 1, 2, 1, 1)
        self.vcHoldingLabel = QtGui.QLabel(Form)
        self.vcHoldingLabel.setText(_fromUtf8(""))
        self.vcHoldingLabel.setObjectName(_fromUtf8("vcHoldingLabel"))
        self.gridLayout_2.addWidget(self.vcHoldingLabel, 3, 2, 1, 1)
        self.icHoldingSpin = SpinBox(Form)
        self.icHoldingSpin.setMaximumSize(QtCore.QSize(150, 16777215))
        self.icHoldingSpin.setObjectName(_fromUtf8("icHoldingSpin"))
        self.gridLayout_2.addWidget(self.icHoldingSpin, 4, 1, 1, 1)
        self.label_6 = QtGui.QLabel(Form)
        self.label_6.setObjectName(_fromUtf8("label_6"))
        self.gridLayout_2.addWidget(self.label_6, 0, 0, 1, 1)
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout_2.addWidget(self.label, 1, 0, 1, 1)
        self.channelLabel = QtGui.QLabel(Form)
        self.channelLabel.setText(_fromUtf8(""))
        self.channelLabel.setObjectName(_fromUtf8("channelLabel"))
        self.gridLayout_2.addWidget(self.channelLabel, 0, 2, 1, 1)
        self.label_3 = QtGui.QLabel(Form)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout_2.addWidget(self.label_3, 4, 0, 1, 1)
        self.horizontalLayout_2 = QtGui.QHBoxLayout()
        self.horizontalLayout_2.setObjectName(_fromUtf8("horizontalLayout_2"))
        self.vcRadio = QtGui.QRadioButton(Form)
        self.vcRadio.setObjectName(_fromUtf8("vcRadio"))
        self.horizontalLayout_2.addWidget(self.vcRadio)
        self.i0Radio = QtGui.QRadioButton(Form)
        self.i0Radio.setObjectName(_fromUtf8("i0Radio"))
        self.horizontalLayout_2.addWidget(self.i0Radio)
        self.icRadio = QtGui.QRadioButton(Form)
        self.icRadio.setObjectName(_fromUtf8("icRadio"))
        self.horizontalLayout_2.addWidget(self.icRadio)
        self.gridLayout_2.addLayout(self.horizontalLayout_2, 1, 1, 1, 1)
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout_2.addWidget(self.label_2, 3, 0, 1, 1)
        self.vcHoldingSpin = SpinBox(Form)
        self.vcHoldingSpin.setMaximumSize(QtCore.QSize(150, 16777215))
        self.vcHoldingSpin.setObjectName(_fromUtf8("vcHoldingSpin"))
        self.gridLayout_2.addWidget(self.vcHoldingSpin, 3, 1, 1, 1)
        self.icHoldingLabel = QtGui.QLabel(Form)
        self.icHoldingLabel.setText(_fromUtf8(""))
        self.icHoldingLabel.setObjectName(_fromUtf8("icHoldingLabel"))
        self.gridLayout_2.addWidget(self.icHoldingLabel, 4, 2, 1, 1)
        spacerItem1 = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout_2.addItem(spacerItem1, 5, 0, 1, 1)
        self.horizontalLayout.addLayout(self.gridLayout_2)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.label_6.setText(_translate("Form", "MultiClamp Channel:", None))
        self.label.setText(_translate("Form", "Mode:", None))
        self.label_3.setText(_translate("Form", "IC Holding:", None))
        self.vcRadio.setText(_translate("Form", "VC", None))
        self.i0Radio.setText(_translate("Form", "I=0", None))
        self.icRadio.setText(_translate("Form", "IC", None))
        self.label_2.setText(_translate("Form", "VC Holding:", None))

from acq4.pyqtgraph import SpinBox
