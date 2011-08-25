# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/util/Canvas/items/ScanCanvasItemTemplate.ui'
#
# Created: Wed Aug 17 13:49:54 2011
#      by: pyside-uic 0.2.11 running on PySide 1.0.5
#
# WARNING! All changes made in this file will be lost!

from PySide import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(185, 134)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setHorizontalSpacing(0)
        self.gridLayout.setVerticalSpacing(3)
        self.gridLayout.setObjectName("gridLayout")
        self.spotSizeLabel = QtGui.QLabel(Form)
        self.spotSizeLabel.setObjectName("spotSizeLabel")
        self.gridLayout.addWidget(self.spotSizeLabel, 0, 0, 1, 1)
        self.sizeFromCalibrationRadio = QtGui.QRadioButton(Form)
        self.sizeFromCalibrationRadio.setChecked(True)
        self.sizeFromCalibrationRadio.setObjectName("sizeFromCalibrationRadio")
        self.gridLayout.addWidget(self.sizeFromCalibrationRadio, 1, 0, 1, 3)
        self.sizeCustomRadio = QtGui.QRadioButton(Form)
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
        self.loadSpotImagesBtn = QtGui.QPushButton(Form)
        self.loadSpotImagesBtn.setObjectName("loadSpotImagesBtn")
        self.gridLayout.addWidget(self.loadSpotImagesBtn, 4, 0, 1, 3)
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 5, 0, 1, 1)
        self.spotFrameSpin = QtGui.QSpinBox(Form)
        self.spotFrameSpin.setProperty("value", 1)
        self.spotFrameSpin.setObjectName("spotFrameSpin")
        self.gridLayout.addWidget(self.spotFrameSpin, 5, 1, 1, 2)
        self.bgFrameCheck = QtGui.QCheckBox(Form)
        self.bgFrameCheck.setChecked(True)
        self.bgFrameCheck.setObjectName("bgFrameCheck")
        self.gridLayout.addWidget(self.bgFrameCheck, 6, 0, 1, 1)
        self.bgFrameSpin = QtGui.QSpinBox(Form)
        self.bgFrameSpin.setObjectName("bgFrameSpin")
        self.gridLayout.addWidget(self.bgFrameSpin, 6, 1, 1, 2)
        self.line = QtGui.QFrame(Form)
        self.line.setFrameShape(QtGui.QFrame.HLine)
        self.line.setFrameShadow(QtGui.QFrame.Sunken)
        self.line.setObjectName("line")
        self.gridLayout.addWidget(self.line, 3, 0, 1, 3)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.spotSizeLabel.setText(QtGui.QApplication.translate("Form", "Spot Display Size:", None, QtGui.QApplication.UnicodeUTF8))
        self.sizeFromCalibrationRadio.setText(QtGui.QApplication.translate("Form", "Use size from calibration", None, QtGui.QApplication.UnicodeUTF8))
        self.sizeCustomRadio.setText(QtGui.QApplication.translate("Form", "Use custom size:", None, QtGui.QApplication.UnicodeUTF8))
        self.loadSpotImagesBtn.setToolTip(QtGui.QApplication.translate("Form", "Generates a single frame which combines the photostimulation spot images from each scan point. ", None, QtGui.QApplication.UnicodeUTF8))
        self.loadSpotImagesBtn.setText(QtGui.QApplication.translate("Form", "Load Spot Images", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Spot Frame Number", None, QtGui.QApplication.UnicodeUTF8))
        self.bgFrameCheck.setText(QtGui.QApplication.translate("Form", "Background Frame", None, QtGui.QApplication.UnicodeUTF8))

from SpinBox import SpinBox
