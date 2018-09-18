# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/analysis/modules/Photostim/MapAnalysisTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(208, 349)
        self.gridLayout = QtWidgets.QGridLayout(Form)
        self.gridLayout.setObjectName("gridLayout")
        self.rateAverageSpin = SpinBox(Form)
        self.rateAverageSpin.setObjectName("rateAverageSpin")
        self.gridLayout.addWidget(self.rateAverageSpin, 4, 1, 1, 1)
        self.label = QtWidgets.QLabel(Form)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 4, 0, 1, 1)
        self.groupBox_2 = QtWidgets.QGroupBox(Form)
        self.groupBox_2.setObjectName("groupBox_2")
        self.gridLayout_3 = QtWidgets.QGridLayout(self.groupBox_2)
        self.gridLayout_3.setObjectName("gridLayout_3")
        self.poisMaxCheck = QtWidgets.QCheckBox(self.groupBox_2)
        self.poisMaxCheck.setObjectName("poisMaxCheck")
        self.gridLayout_3.addWidget(self.poisMaxCheck, 2, 0, 1, 1)
        self.poisMaxAmpCheck = QtWidgets.QCheckBox(self.groupBox_2)
        self.poisMaxAmpCheck.setObjectName("poisMaxAmpCheck")
        self.gridLayout_3.addWidget(self.poisMaxAmpCheck, 3, 0, 1, 1)
        self.chargeTransferCheck = QtWidgets.QCheckBox(self.groupBox_2)
        self.chargeTransferCheck.setObjectName("chargeTransferCheck")
        self.gridLayout_3.addWidget(self.chargeTransferCheck, 0, 0, 1, 1)
        self.eventCountCheck = QtWidgets.QCheckBox(self.groupBox_2)
        self.eventCountCheck.setObjectName("eventCountCheck")
        self.gridLayout_3.addWidget(self.eventCountCheck, 1, 0, 1, 1)
        self.gridLayout.addWidget(self.groupBox_2, 3, 0, 1, 2)
        self.groupBox = QtWidgets.QGroupBox(Form)
        self.groupBox.setObjectName("groupBox")
        self.gridLayout_2 = QtWidgets.QGridLayout(self.groupBox)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.excitatoryRadio = QtWidgets.QRadioButton(self.groupBox)
        self.excitatoryRadio.setObjectName("excitatoryRadio")
        self.gridLayout_2.addWidget(self.excitatoryRadio, 0, 0, 1, 1)
        self.fitErrorSpin = SpinBox(self.groupBox)
        self.fitErrorSpin.setObjectName("fitErrorSpin")
        self.gridLayout_2.addWidget(self.fitErrorSpin, 1, 1, 1, 1)
        self.label_2 = QtWidgets.QLabel(self.groupBox)
        self.label_2.setObjectName("label_2")
        self.gridLayout_2.addWidget(self.label_2, 1, 0, 1, 1)
        self.inhibitoryRadio = QtWidgets.QRadioButton(self.groupBox)
        self.inhibitoryRadio.setObjectName("inhibitoryRadio")
        self.gridLayout_2.addWidget(self.inhibitoryRadio, 0, 1, 1, 1)
        self.gridLayout.addWidget(self.groupBox, 2, 0, 1, 2)
        self.groupBox_3 = QtWidgets.QGroupBox(Form)
        self.groupBox_3.setObjectName("groupBox_3")
        self.gridLayout_4 = QtWidgets.QGridLayout(self.groupBox_3)
        self.gridLayout_4.setObjectName("gridLayout_4")
        self.label_3 = QtWidgets.QLabel(self.groupBox_3)
        self.label_3.setObjectName("label_3")
        self.gridLayout_4.addWidget(self.label_3, 0, 0, 1, 1)
        self.thresholdSpin = SpinBox(self.groupBox_3)
        self.thresholdSpin.setObjectName("thresholdSpin")
        self.gridLayout_4.addWidget(self.thresholdSpin, 0, 1, 1, 1)
        self.detectionHistogram = PlotWidget(self.groupBox_3)
        self.detectionHistogram.setObjectName("detectionHistogram")
        self.gridLayout_4.addWidget(self.detectionHistogram, 1, 0, 1, 2)
        self.gridLayout.addWidget(self.groupBox_3, 5, 0, 1, 2)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.label.setText(_translate("Form", "Rate Average Window"))
        self.groupBox_2.setTitle(_translate("Form", "Detection Methods"))
        self.poisMaxCheck.setText(_translate("Form", "Poisson max probability"))
        self.poisMaxAmpCheck.setText(_translate("Form", "Poisson max + amplitude"))
        self.chargeTransferCheck.setText(_translate("Form", "Charge transfer z-score"))
        self.eventCountCheck.setText(_translate("Form", "Event Count"))
        self.groupBox.setTitle(_translate("Form", "Event Selection"))
        self.excitatoryRadio.setText(_translate("Form", "Excitatory"))
        self.label_2.setText(_translate("Form", "Fit Error Limit"))
        self.inhibitoryRadio.setText(_translate("Form", "Inhibitory"))
        self.label_3.setText(_translate("Form", "Detection Threshold"))

from acq4.pyqtgraph import PlotWidget, SpinBox
