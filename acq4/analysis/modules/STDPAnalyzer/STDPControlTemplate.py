# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/analysis/modules/STDPAnalyzer/STDPControlTemplate.ui'
#
# Created: Fri May  1 11:35:43 2015
#      by: PyQt4 UI code generator 4.11.1
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
        Form.resize(252, 139)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(3)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.traceDisplayGroup = QtGui.QGroupBox(Form)
        self.traceDisplayGroup.setObjectName(_fromUtf8("traceDisplayGroup"))
        self.gridLayout_3 = QtGui.QGridLayout(self.traceDisplayGroup)
        self.gridLayout_3.setMargin(3)
        self.gridLayout_3.setSpacing(3)
        self.gridLayout_3.setObjectName(_fromUtf8("gridLayout_3"))
        self.averageCheck = QtGui.QCheckBox(self.traceDisplayGroup)
        self.averageCheck.setObjectName(_fromUtf8("averageCheck"))
        self.gridLayout_3.addWidget(self.averageCheck, 0, 0, 1, 2)
        self.gridLayout_2 = QtGui.QGridLayout()
        self.gridLayout_2.setHorizontalSpacing(1)
        self.gridLayout_2.setVerticalSpacing(3)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.averageTimeRadio = QtGui.QRadioButton(self.traceDisplayGroup)
        self.averageTimeRadio.setChecked(True)
        self.averageTimeRadio.setObjectName(_fromUtf8("averageTimeRadio"))
        self.gridLayout_2.addWidget(self.averageTimeRadio, 0, 0, 1, 1)
        self.averageTimeSpin = SpinBox(self.traceDisplayGroup)
        self.averageTimeSpin.setObjectName(_fromUtf8("averageTimeSpin"))
        self.gridLayout_2.addWidget(self.averageTimeSpin, 0, 1, 1, 2)
        self.averageNumberRadio = QtGui.QRadioButton(self.traceDisplayGroup)
        self.averageNumberRadio.setObjectName(_fromUtf8("averageNumberRadio"))
        self.gridLayout_2.addWidget(self.averageNumberRadio, 1, 0, 1, 2)
        self.averageAnalysisCheck = QtGui.QCheckBox(self.traceDisplayGroup)
        self.averageAnalysisCheck.setMinimumSize(QtCore.QSize(0, 20))
        self.averageAnalysisCheck.setObjectName(_fromUtf8("averageAnalysisCheck"))
        self.gridLayout_2.addWidget(self.averageAnalysisCheck, 2, 0, 1, 3)
        self.averageNumberSpin = SpinBox(self.traceDisplayGroup)
        self.averageNumberSpin.setDecimals(0)
        self.averageNumberSpin.setMaximum(1000.0)
        self.averageNumberSpin.setProperty("value", 5.0)
        self.averageNumberSpin.setObjectName(_fromUtf8("averageNumberSpin"))
        self.gridLayout_2.addWidget(self.averageNumberSpin, 1, 2, 1, 1)
        self.displayTracesCheck = QtGui.QCheckBox(self.traceDisplayGroup)
        self.displayTracesCheck.setMinimumSize(QtCore.QSize(0, 20))
        self.displayTracesCheck.setObjectName(_fromUtf8("displayTracesCheck"))
        self.gridLayout_2.addWidget(self.displayTracesCheck, 3, 0, 1, 3)
        self.gridLayout_2.setColumnStretch(2, 4)
        self.gridLayout_3.addLayout(self.gridLayout_2, 1, 1, 1, 1)
        spacerItem = QtGui.QSpacerItem(10, 20, QtGui.QSizePolicy.MinimumExpanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout_3.addItem(spacerItem, 1, 0, 1, 1)
        self.gridLayout.addWidget(self.traceDisplayGroup, 0, 0, 1, 1)
        spacerItem1 = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem1, 1, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.traceDisplayGroup.setTitle(_translate("Form", "Trace Display:", None))
        self.averageCheck.setText(_translate("Form", "Average traces based on:", None))
        self.averageTimeRadio.setText(_translate("Form", "Time:", None))
        self.averageNumberRadio.setText(_translate("Form", "Number:", None))
        self.averageAnalysisCheck.setText(_translate("Form", "Use averaged traces for analysis", None))
        self.displayTracesCheck.setText(_translate("Form", "Display original traces (slow)", None))

from acq4.pyqtgraph.widgets.SpinBox import SpinBox
