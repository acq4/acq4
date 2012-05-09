# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'UncagingTemplate.ui'
#
# Created: Sun Mar 18 17:31:14 2012
#      by: PyQt4 UI code generator 4.8.5
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
        Form.resize(292, 355)
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.horizontalLayout = QtGui.QHBoxLayout(Form)
        self.horizontalLayout.setMargin(0)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.gridLayout = QtGui.QGridLayout()
        self.gridLayout.setVerticalSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label = QtGui.QLabel(Form)
        self.label.setText(QtGui.QApplication.translate("Form", "Camera Module:", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 1, 0, 1, 1)
        self.cameraModCombo = InterfaceCombo(Form)
        self.cameraModCombo.setObjectName(_fromUtf8("cameraModCombo"))
        self.gridLayout.addWidget(self.cameraModCombo, 1, 1, 1, 2)
        self.label_3 = QtGui.QLabel(Form)
        self.label_3.setText(QtGui.QApplication.translate("Form", "Clamp Device:", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout.addWidget(self.label_3, 4, 0, 1, 1)
        self.clampDevCombo = InterfaceCombo(Form)
        self.clampDevCombo.setObjectName(_fromUtf8("clampDevCombo"))
        self.gridLayout.addWidget(self.clampDevCombo, 4, 1, 1, 2)
        self.protList = QtGui.QListWidget(Form)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.protList.sizePolicy().hasHeightForWidth())
        self.protList.setSizePolicy(sizePolicy)
        self.protList.setObjectName(_fromUtf8("protList"))
        self.gridLayout.addWidget(self.protList, 5, 0, 1, 3)
        self.deleteBtn = QtGui.QPushButton(Form)
        self.deleteBtn.setText(QtGui.QApplication.translate("Form", "Delete", None, QtGui.QApplication.UnicodeUTF8))
        self.deleteBtn.setObjectName(_fromUtf8("deleteBtn"))
        self.gridLayout.addWidget(self.deleteBtn, 6, 0, 1, 1)
        self.alphaSlider = QtGui.QSlider(Form)
        self.alphaSlider.setMaximum(255)
        self.alphaSlider.setPageStep(10)
        self.alphaSlider.setProperty("value", 150)
        self.alphaSlider.setOrientation(QtCore.Qt.Horizontal)
        self.alphaSlider.setObjectName(_fromUtf8("alphaSlider"))
        self.gridLayout.addWidget(self.alphaSlider, 6, 1, 1, 2)
        self.scannerDevCombo = InterfaceCombo(Form)
        self.scannerDevCombo.setObjectName(_fromUtf8("scannerDevCombo"))
        self.gridLayout.addWidget(self.scannerDevCombo, 3, 1, 1, 2)
        self.label_4 = QtGui.QLabel(Form)
        self.label_4.setText(QtGui.QApplication.translate("Form", "Scanner Device:", None, QtGui.QApplication.UnicodeUTF8))
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.gridLayout.addWidget(self.label_4, 3, 0, 1, 1)
        self.label_5 = QtGui.QLabel(Form)
        self.label_5.setText(QtGui.QApplication.translate("Form", "Clamp Baseline", None, QtGui.QApplication.UnicodeUTF8))
        self.label_5.setObjectName(_fromUtf8("label_5"))
        self.gridLayout.addWidget(self.label_5, 8, 0, 1, 1)
        self.clampStopSpin = QtGui.QLabel(Form)
        self.clampStopSpin.setText(QtGui.QApplication.translate("Form", "Clamp Test", None, QtGui.QApplication.UnicodeUTF8))
        self.clampStopSpin.setObjectName(_fromUtf8("clampStopSpin"))
        self.gridLayout.addWidget(self.clampStopSpin, 9, 0, 1, 1)
        self.enabledCheck = QtGui.QCheckBox(Form)
        self.enabledCheck.setText(QtGui.QApplication.translate("Form", "Enabled", None, QtGui.QApplication.UnicodeUTF8))
        self.enabledCheck.setObjectName(_fromUtf8("enabledCheck"))
        self.gridLayout.addWidget(self.enabledCheck, 0, 1, 1, 1)
        self.clampBaseStartSpin = QtGui.QDoubleSpinBox(Form)
        self.clampBaseStartSpin.setMaximum(100000.0)
        self.clampBaseStartSpin.setObjectName(_fromUtf8("clampBaseStartSpin"))
        self.gridLayout.addWidget(self.clampBaseStartSpin, 8, 1, 1, 1)
        self.clampTestStartSpin = QtGui.QDoubleSpinBox(Form)
        self.clampTestStartSpin.setMaximum(100000.0)
        self.clampTestStartSpin.setProperty("value", 400.0)
        self.clampTestStartSpin.setObjectName(_fromUtf8("clampTestStartSpin"))
        self.gridLayout.addWidget(self.clampTestStartSpin, 9, 1, 1, 1)
        self.clampTestStopSpin = QtGui.QDoubleSpinBox(Form)
        self.clampTestStopSpin.setMaximum(100000.0)
        self.clampTestStopSpin.setProperty("value", 450.0)
        self.clampTestStopSpin.setObjectName(_fromUtf8("clampTestStopSpin"))
        self.gridLayout.addWidget(self.clampTestStopSpin, 9, 2, 1, 1)
        self.clampBaseStopSpin = QtGui.QDoubleSpinBox(Form)
        self.clampBaseStopSpin.setMaximum(100000.0)
        self.clampBaseStopSpin.setProperty("value", 380.0)
        self.clampBaseStopSpin.setObjectName(_fromUtf8("clampBaseStopSpin"))
        self.gridLayout.addWidget(self.clampBaseStopSpin, 8, 2, 1, 1)
        self.label_6 = QtGui.QLabel(Form)
        self.label_6.setText(QtGui.QApplication.translate("Form", "PSP Tolerance", None, QtGui.QApplication.UnicodeUTF8))
        self.label_6.setObjectName(_fromUtf8("label_6"))
        self.gridLayout.addWidget(self.label_6, 10, 0, 1, 1)
        self.pspToleranceSpin = QtGui.QDoubleSpinBox(Form)
        self.pspToleranceSpin.setProperty("value", 4.0)
        self.pspToleranceSpin.setObjectName(_fromUtf8("pspToleranceSpin"))
        self.gridLayout.addWidget(self.pspToleranceSpin, 10, 1, 1, 2)
        self.recomputeBtn = QtGui.QPushButton(Form)
        self.recomputeBtn.setText(QtGui.QApplication.translate("Form", "Recompute", None, QtGui.QApplication.UnicodeUTF8))
        self.recomputeBtn.setObjectName(_fromUtf8("recomputeBtn"))
        self.gridLayout.addWidget(self.recomputeBtn, 13, 1, 1, 1)
        self.horizontalLayout.addLayout(self.gridLayout)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        pass

from InterfaceCombo import InterfaceCombo
