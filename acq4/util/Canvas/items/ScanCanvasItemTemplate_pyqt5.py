# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/util/Canvas/items/ScanCanvasItemTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(242, 159)
        self.gridLayout = QtWidgets.QGridLayout(Form)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.spotSizeLabel = QtWidgets.QLabel(Form)
        self.spotSizeLabel.setObjectName("spotSizeLabel")
        self.gridLayout.addWidget(self.spotSizeLabel, 0, 0, 1, 1)
        self.sizeFromCalibrationRadio = QtWidgets.QRadioButton(Form)
        self.sizeFromCalibrationRadio.setChecked(True)
        self.sizeFromCalibrationRadio.setObjectName("sizeFromCalibrationRadio")
        self.gridLayout.addWidget(self.sizeFromCalibrationRadio, 1, 0, 1, 3)
        self.sizeCustomRadio = QtWidgets.QRadioButton(Form)
        self.sizeCustomRadio.setObjectName("sizeCustomRadio")
        self.gridLayout.addWidget(self.sizeCustomRadio, 2, 0, 1, 1)
        self.sizeSpin = SpinBox(Form)
        self.sizeSpin.setSuffix("")
        self.sizeSpin.setMinimum(0.0)
        self.sizeSpin.setMaximum(100000.0)
        self.sizeSpin.setSingleStep(1e-06)
        self.sizeSpin.setProperty("value", 0.0)
        self.sizeSpin.setObjectName("sizeSpin")
        self.gridLayout.addWidget(self.sizeSpin, 2, 1, 1, 2)
        self.loadSpotImagesBtn = QtWidgets.QPushButton(Form)
        self.loadSpotImagesBtn.setObjectName("loadSpotImagesBtn")
        self.gridLayout.addWidget(self.loadSpotImagesBtn, 6, 0, 1, 3)
        self.label = QtWidgets.QLabel(Form)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 7, 0, 1, 1)
        self.spotFrameSpin = QtWidgets.QSpinBox(Form)
        self.spotFrameSpin.setProperty("value", 1)
        self.spotFrameSpin.setObjectName("spotFrameSpin")
        self.gridLayout.addWidget(self.spotFrameSpin, 7, 1, 1, 2)
        self.bgFrameCheck = QtWidgets.QCheckBox(Form)
        self.bgFrameCheck.setChecked(True)
        self.bgFrameCheck.setObjectName("bgFrameCheck")
        self.gridLayout.addWidget(self.bgFrameCheck, 8, 0, 1, 1)
        self.bgFrameSpin = QtWidgets.QSpinBox(Form)
        self.bgFrameSpin.setObjectName("bgFrameSpin")
        self.gridLayout.addWidget(self.bgFrameSpin, 8, 1, 1, 2)
        self.line = QtWidgets.QFrame(Form)
        self.line.setFrameShape(QtWidgets.QFrame.HLine)
        self.line.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line.setObjectName("line")
        self.gridLayout.addWidget(self.line, 5, 0, 1, 3)
        self.line_2 = QtWidgets.QFrame(Form)
        self.line_2.setFrameShape(QtWidgets.QFrame.HLine)
        self.line_2.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line_2.setObjectName("line_2")
        self.gridLayout.addWidget(self.line_2, 3, 0, 1, 3)
        self.label_2 = QtWidgets.QLabel(Form)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 4, 0, 1, 1)
        self.outlineColorBtn = ColorButton(Form)
        self.outlineColorBtn.setText("")
        self.outlineColorBtn.setObjectName("outlineColorBtn")
        self.gridLayout.addWidget(self.outlineColorBtn, 4, 1, 1, 2)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.spotSizeLabel.setText(_translate("Form", "Spot Display Size:"))
        self.sizeFromCalibrationRadio.setText(_translate("Form", "Use size from calibration"))
        self.sizeCustomRadio.setText(_translate("Form", "Use custom size:"))
        self.loadSpotImagesBtn.setToolTip(_translate("Form", "Generates a single frame which combines the photostimulation spot images from each scan point. "))
        self.loadSpotImagesBtn.setText(_translate("Form", "Load Spot Images"))
        self.label.setText(_translate("Form", "Spot Frame Number"))
        self.bgFrameCheck.setText(_translate("Form", "Background Frame"))
        self.label_2.setText(_translate("Form", "Outline Color"))

from acq4.pyqtgraph import ColorButton, SpinBox
