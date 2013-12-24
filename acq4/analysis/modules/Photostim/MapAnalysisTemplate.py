# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/analysis/modules/Photostim/MapAnalysisTemplate.ui'
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
        Form.resize(208, 349)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.rateAverageSpin = SpinBox(Form)
        self.rateAverageSpin.setObjectName(_fromUtf8("rateAverageSpin"))
        self.gridLayout.addWidget(self.rateAverageSpin, 4, 1, 1, 1)
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 4, 0, 1, 1)
        self.groupBox_2 = QtGui.QGroupBox(Form)
        self.groupBox_2.setObjectName(_fromUtf8("groupBox_2"))
        self.gridLayout_3 = QtGui.QGridLayout(self.groupBox_2)
        self.gridLayout_3.setObjectName(_fromUtf8("gridLayout_3"))
        self.poisMaxCheck = QtGui.QCheckBox(self.groupBox_2)
        self.poisMaxCheck.setObjectName(_fromUtf8("poisMaxCheck"))
        self.gridLayout_3.addWidget(self.poisMaxCheck, 2, 0, 1, 1)
        self.poisMaxAmpCheck = QtGui.QCheckBox(self.groupBox_2)
        self.poisMaxAmpCheck.setObjectName(_fromUtf8("poisMaxAmpCheck"))
        self.gridLayout_3.addWidget(self.poisMaxAmpCheck, 3, 0, 1, 1)
        self.chargeTransferCheck = QtGui.QCheckBox(self.groupBox_2)
        self.chargeTransferCheck.setObjectName(_fromUtf8("chargeTransferCheck"))
        self.gridLayout_3.addWidget(self.chargeTransferCheck, 0, 0, 1, 1)
        self.eventCountCheck = QtGui.QCheckBox(self.groupBox_2)
        self.eventCountCheck.setObjectName(_fromUtf8("eventCountCheck"))
        self.gridLayout_3.addWidget(self.eventCountCheck, 1, 0, 1, 1)
        self.gridLayout.addWidget(self.groupBox_2, 3, 0, 1, 2)
        self.groupBox = QtGui.QGroupBox(Form)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout_2 = QtGui.QGridLayout(self.groupBox)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.excitatoryRadio = QtGui.QRadioButton(self.groupBox)
        self.excitatoryRadio.setObjectName(_fromUtf8("excitatoryRadio"))
        self.gridLayout_2.addWidget(self.excitatoryRadio, 0, 0, 1, 1)
        self.fitErrorSpin = SpinBox(self.groupBox)
        self.fitErrorSpin.setObjectName(_fromUtf8("fitErrorSpin"))
        self.gridLayout_2.addWidget(self.fitErrorSpin, 1, 1, 1, 1)
        self.label_2 = QtGui.QLabel(self.groupBox)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout_2.addWidget(self.label_2, 1, 0, 1, 1)
        self.inhibitoryRadio = QtGui.QRadioButton(self.groupBox)
        self.inhibitoryRadio.setObjectName(_fromUtf8("inhibitoryRadio"))
        self.gridLayout_2.addWidget(self.inhibitoryRadio, 0, 1, 1, 1)
        self.gridLayout.addWidget(self.groupBox, 2, 0, 1, 2)
        self.groupBox_3 = QtGui.QGroupBox(Form)
        self.groupBox_3.setObjectName(_fromUtf8("groupBox_3"))
        self.gridLayout_4 = QtGui.QGridLayout(self.groupBox_3)
        self.gridLayout_4.setObjectName(_fromUtf8("gridLayout_4"))
        self.label_3 = QtGui.QLabel(self.groupBox_3)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout_4.addWidget(self.label_3, 0, 0, 1, 1)
        self.thresholdSpin = SpinBox(self.groupBox_3)
        self.thresholdSpin.setObjectName(_fromUtf8("thresholdSpin"))
        self.gridLayout_4.addWidget(self.thresholdSpin, 0, 1, 1, 1)
        self.detectionHistogram = PlotWidget(self.groupBox_3)
        self.detectionHistogram.setObjectName(_fromUtf8("detectionHistogram"))
        self.gridLayout_4.addWidget(self.detectionHistogram, 1, 0, 1, 2)
        self.gridLayout.addWidget(self.groupBox_3, 5, 0, 1, 2)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.label.setText(_translate("Form", "Rate Average Window", None))
        self.groupBox_2.setTitle(_translate("Form", "Detection Methods", None))
        self.poisMaxCheck.setText(_translate("Form", "Poisson max probability", None))
        self.poisMaxAmpCheck.setText(_translate("Form", "Poisson max + amplitude", None))
        self.chargeTransferCheck.setText(_translate("Form", "Charge transfer z-score", None))
        self.eventCountCheck.setText(_translate("Form", "Event Count", None))
        self.groupBox.setTitle(_translate("Form", "Event Selection", None))
        self.excitatoryRadio.setText(_translate("Form", "Excitatory", None))
        self.label_2.setText(_translate("Form", "Fit Error Limit", None))
        self.inhibitoryRadio.setText(_translate("Form", "Inhibitory", None))
        self.label_3.setText(_translate("Form", "Detection Threshold", None))

from acq4.pyqtgraph import SpinBox, PlotWidget
