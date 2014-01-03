# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/modules/TaskRunner/analysisModules/Uncaging/UncagingTemplate.ui'
#
# Created: Tue Dec 24 01:49:11 2013
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
        Form.resize(292, 355)
        self.horizontalLayout = QtGui.QHBoxLayout(Form)
        self.horizontalLayout.setMargin(0)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.gridLayout = QtGui.QGridLayout()
        self.gridLayout.setVerticalSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 1, 0, 1, 1)
        self.cameraModCombo = InterfaceCombo(Form)
        self.cameraModCombo.setObjectName(_fromUtf8("cameraModCombo"))
        self.gridLayout.addWidget(self.cameraModCombo, 1, 1, 1, 2)
        self.label_3 = QtGui.QLabel(Form)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout.addWidget(self.label_3, 4, 0, 1, 1)
        self.clampDevCombo = InterfaceCombo(Form)
        self.clampDevCombo.setObjectName(_fromUtf8("clampDevCombo"))
        self.gridLayout.addWidget(self.clampDevCombo, 4, 1, 1, 2)
        self.taskList = QtGui.QListWidget(Form)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.taskList.sizePolicy().hasHeightForWidth())
        self.taskList.setSizePolicy(sizePolicy)
        self.taskList.setObjectName(_fromUtf8("taskList"))
        self.gridLayout.addWidget(self.taskList, 5, 0, 1, 3)
        self.deleteBtn = QtGui.QPushButton(Form)
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
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.gridLayout.addWidget(self.label_4, 3, 0, 1, 1)
        self.label_5 = QtGui.QLabel(Form)
        self.label_5.setObjectName(_fromUtf8("label_5"))
        self.gridLayout.addWidget(self.label_5, 8, 0, 1, 1)
        self.clampStopSpin = QtGui.QLabel(Form)
        self.clampStopSpin.setObjectName(_fromUtf8("clampStopSpin"))
        self.gridLayout.addWidget(self.clampStopSpin, 9, 0, 1, 1)
        self.enabledCheck = QtGui.QCheckBox(Form)
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
        self.label_6.setObjectName(_fromUtf8("label_6"))
        self.gridLayout.addWidget(self.label_6, 10, 0, 1, 1)
        self.pspToleranceSpin = QtGui.QDoubleSpinBox(Form)
        self.pspToleranceSpin.setProperty("value", 4.0)
        self.pspToleranceSpin.setObjectName(_fromUtf8("pspToleranceSpin"))
        self.gridLayout.addWidget(self.pspToleranceSpin, 10, 1, 1, 2)
        self.recomputeBtn = QtGui.QPushButton(Form)
        self.recomputeBtn.setObjectName(_fromUtf8("recomputeBtn"))
        self.gridLayout.addWidget(self.recomputeBtn, 13, 1, 1, 1)
        self.horizontalLayout.addLayout(self.gridLayout)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.label.setText(_translate("Form", "Camera Module:", None))
        self.label_3.setText(_translate("Form", "Clamp Device:", None))
        self.deleteBtn.setText(_translate("Form", "Delete", None))
        self.label_4.setText(_translate("Form", "Scanner Device:", None))
        self.label_5.setText(_translate("Form", "Clamp Baseline", None))
        self.clampStopSpin.setText(_translate("Form", "Clamp Test", None))
        self.enabledCheck.setText(_translate("Form", "Enabled", None))
        self.label_6.setText(_translate("Form", "PSP Tolerance", None))
        self.recomputeBtn.setText(_translate("Form", "Recompute", None))

from acq4.util.InterfaceCombo import InterfaceCombo
