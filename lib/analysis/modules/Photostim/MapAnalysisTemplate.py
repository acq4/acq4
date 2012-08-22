# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'MapAnalysisTemplate.ui'
#
# Created: Mon Jul  9 17:31:38 2012
#      by: PyQt4 UI code generator 4.9.1
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
        Form.resize(214, 108)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout.addWidget(self.label_2, 2, 0, 1, 1)
        self.fitErrorSpin = QtGui.QDoubleSpinBox(Form)
        self.fitErrorSpin.setObjectName(_fromUtf8("fitErrorSpin"))
        self.gridLayout.addWidget(self.fitErrorSpin, 2, 1, 1, 1)
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 3, 0, 1, 1)
        self.rateAverageSpin = QtGui.QDoubleSpinBox(Form)
        self.rateAverageSpin.setObjectName(_fromUtf8("rateAverageSpin"))
        self.gridLayout.addWidget(self.rateAverageSpin, 3, 1, 1, 1)
        self.measureAmpProbCheck = QtGui.QCheckBox(Form)
        self.measureAmpProbCheck.setObjectName(_fromUtf8("measureAmpProbCheck"))
        self.gridLayout.addWidget(self.measureAmpProbCheck, 4, 0, 1, 2)
        self.excitatoryRadio = QtGui.QRadioButton(Form)
        self.excitatoryRadio.setObjectName(_fromUtf8("excitatoryRadio"))
        self.gridLayout.addWidget(self.excitatoryRadio, 0, 0, 1, 1)
        self.inhibitoryRadio = QtGui.QRadioButton(Form)
        self.inhibitoryRadio.setObjectName(_fromUtf8("inhibitoryRadio"))
        self.gridLayout.addWidget(self.inhibitoryRadio, 0, 1, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "Fit Error Limit", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Rate Average Window", None, QtGui.QApplication.UnicodeUTF8))
        self.measureAmpProbCheck.setText(QtGui.QApplication.translate("Form", "Measure Amplitude Probability", None, QtGui.QApplication.UnicodeUTF8))
        self.excitatoryRadio.setText(QtGui.QApplication.translate("Form", "Excitatory", None, QtGui.QApplication.UnicodeUTF8))
        self.inhibitoryRadio.setText(QtGui.QApplication.translate("Form", "Inhibitory", None, QtGui.QApplication.UnicodeUTF8))

