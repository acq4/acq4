# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/util/Canvas/items/ScanCanvasItemTemplate.ui'
#
# Created: Tue Dec 24 01:49:16 2013
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
        Form.resize(242, 159)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.spotSizeLabel = QtGui.QLabel(Form)
        self.spotSizeLabel.setObjectName(_fromUtf8("spotSizeLabel"))
        self.gridLayout.addWidget(self.spotSizeLabel, 0, 0, 1, 1)
        self.sizeFromCalibrationRadio = QtGui.QRadioButton(Form)
        self.sizeFromCalibrationRadio.setChecked(True)
        self.sizeFromCalibrationRadio.setObjectName(_fromUtf8("sizeFromCalibrationRadio"))
        self.gridLayout.addWidget(self.sizeFromCalibrationRadio, 1, 0, 1, 3)
        self.sizeCustomRadio = QtGui.QRadioButton(Form)
        self.sizeCustomRadio.setObjectName(_fromUtf8("sizeCustomRadio"))
        self.gridLayout.addWidget(self.sizeCustomRadio, 2, 0, 1, 1)
        self.sizeSpin = SpinBox(Form)
        self.sizeSpin.setSuffix(_fromUtf8(""))
        self.sizeSpin.setMinimum(0.0)
        self.sizeSpin.setMaximum(100000.0)
        self.sizeSpin.setSingleStep(1e-06)
        self.sizeSpin.setProperty("value", 0.0)
        self.sizeSpin.setObjectName(_fromUtf8("sizeSpin"))
        self.gridLayout.addWidget(self.sizeSpin, 2, 1, 1, 2)
        self.loadSpotImagesBtn = QtGui.QPushButton(Form)
        self.loadSpotImagesBtn.setObjectName(_fromUtf8("loadSpotImagesBtn"))
        self.gridLayout.addWidget(self.loadSpotImagesBtn, 6, 0, 1, 3)
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 7, 0, 1, 1)
        self.spotFrameSpin = QtGui.QSpinBox(Form)
        self.spotFrameSpin.setProperty("value", 1)
        self.spotFrameSpin.setObjectName(_fromUtf8("spotFrameSpin"))
        self.gridLayout.addWidget(self.spotFrameSpin, 7, 1, 1, 2)
        self.bgFrameCheck = QtGui.QCheckBox(Form)
        self.bgFrameCheck.setChecked(True)
        self.bgFrameCheck.setObjectName(_fromUtf8("bgFrameCheck"))
        self.gridLayout.addWidget(self.bgFrameCheck, 8, 0, 1, 1)
        self.bgFrameSpin = QtGui.QSpinBox(Form)
        self.bgFrameSpin.setObjectName(_fromUtf8("bgFrameSpin"))
        self.gridLayout.addWidget(self.bgFrameSpin, 8, 1, 1, 2)
        self.line = QtGui.QFrame(Form)
        self.line.setFrameShape(QtGui.QFrame.HLine)
        self.line.setFrameShadow(QtGui.QFrame.Sunken)
        self.line.setObjectName(_fromUtf8("line"))
        self.gridLayout.addWidget(self.line, 5, 0, 1, 3)
        self.line_2 = QtGui.QFrame(Form)
        self.line_2.setFrameShape(QtGui.QFrame.HLine)
        self.line_2.setFrameShadow(QtGui.QFrame.Sunken)
        self.line_2.setObjectName(_fromUtf8("line_2"))
        self.gridLayout.addWidget(self.line_2, 3, 0, 1, 3)
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout.addWidget(self.label_2, 4, 0, 1, 1)
        self.outlineColorBtn = ColorButton(Form)
        self.outlineColorBtn.setText(_fromUtf8(""))
        self.outlineColorBtn.setObjectName(_fromUtf8("outlineColorBtn"))
        self.gridLayout.addWidget(self.outlineColorBtn, 4, 1, 1, 2)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.spotSizeLabel.setText(_translate("Form", "Spot Display Size:", None))
        self.sizeFromCalibrationRadio.setText(_translate("Form", "Use size from calibration", None))
        self.sizeCustomRadio.setText(_translate("Form", "Use custom size:", None))
        self.loadSpotImagesBtn.setToolTip(_translate("Form", "Generates a single frame which combines the photostimulation spot images from each scan point. ", None))
        self.loadSpotImagesBtn.setText(_translate("Form", "Load Spot Images", None))
        self.label.setText(_translate("Form", "Spot Frame Number", None))
        self.bgFrameCheck.setText(_translate("Form", "Background Frame", None))
        self.label_2.setText(_translate("Form", "Outline Color", None))

from acq4.pyqtgraph import SpinBox, ColorButton
