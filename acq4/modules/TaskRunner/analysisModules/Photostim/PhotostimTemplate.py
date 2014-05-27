# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'PhotostimTemplate.ui'
#
# Created: Tue May 06 22:44:33 2014
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
        Form.resize(310, 405)
        self.horizontalLayout = QtGui.QHBoxLayout(Form)
        self.horizontalLayout.setMargin(0)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.gridLayout = QtGui.QGridLayout()
        self.gridLayout.setVerticalSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 1, 0, 1, 1)
        self.label_3 = QtGui.QLabel(Form)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout.addWidget(self.label_3, 4, 0, 1, 1)
        self.label_4 = QtGui.QLabel(Form)
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.gridLayout.addWidget(self.label_4, 3, 0, 1, 1)
        self.label_5 = QtGui.QLabel(Form)
        self.label_5.setObjectName(_fromUtf8("label_5"))
        self.gridLayout.addWidget(self.label_5, 7, 0, 1, 1)
        self.clampStopSpin = QtGui.QLabel(Form)
        self.clampStopSpin.setObjectName(_fromUtf8("clampStopSpin"))
        self.gridLayout.addWidget(self.clampStopSpin, 8, 0, 1, 1)
        self.label_6 = QtGui.QLabel(Form)
        self.label_6.setObjectName(_fromUtf8("label_6"))
        self.gridLayout.addWidget(self.label_6, 9, 0, 1, 1)
        self.deleteBtn = QtGui.QPushButton(Form)
        self.deleteBtn.setObjectName(_fromUtf8("deleteBtn"))
        self.gridLayout.addWidget(self.deleteBtn, 13, 0, 1, 1)
        self.clampBaseStopSpin = SpinBox(Form)
        self.clampBaseStopSpin.setMaximum(100000.0)
        self.clampBaseStopSpin.setProperty("value", 0.09)
        self.clampBaseStopSpin.setObjectName(_fromUtf8("clampBaseStopSpin"))
        self.gridLayout.addWidget(self.clampBaseStopSpin, 7, 2, 1, 1)
        self.recomputeBtn = QtGui.QPushButton(Form)
        self.recomputeBtn.setObjectName(_fromUtf8("recomputeBtn"))
        self.gridLayout.addWidget(self.recomputeBtn, 13, 2, 1, 1)
        self.spikeThresholdSpin = SpinBox(Form)
        self.spikeThresholdSpin.setProperty("value", 0.05)
        self.spikeThresholdSpin.setObjectName(_fromUtf8("spikeThresholdSpin"))
        self.gridLayout.addWidget(self.spikeThresholdSpin, 9, 1, 1, 1)
        self.clampBaseStartSpin = SpinBox(Form)
        self.clampBaseStartSpin.setMaximum(100000.0)
        self.clampBaseStartSpin.setObjectName(_fromUtf8("clampBaseStartSpin"))
        self.gridLayout.addWidget(self.clampBaseStartSpin, 7, 1, 1, 1)
        self.clampTestStartSpin = SpinBox(Form)
        self.clampTestStartSpin.setMaximum(100000.0)
        self.clampTestStartSpin.setProperty("value", 0.1)
        self.clampTestStartSpin.setObjectName(_fromUtf8("clampTestStartSpin"))
        self.gridLayout.addWidget(self.clampTestStartSpin, 8, 1, 1, 1)
        self.clampDevCombo = InterfaceCombo(Form)
        self.clampDevCombo.setObjectName(_fromUtf8("clampDevCombo"))
        self.gridLayout.addWidget(self.clampDevCombo, 4, 1, 1, 2)
        self.scannerDevCombo = InterfaceCombo(Form)
        self.scannerDevCombo.setObjectName(_fromUtf8("scannerDevCombo"))
        self.gridLayout.addWidget(self.scannerDevCombo, 3, 1, 1, 2)
        self.cameraModCombo = InterfaceCombo(Form)
        self.cameraModCombo.setObjectName(_fromUtf8("cameraModCombo"))
        self.gridLayout.addWidget(self.cameraModCombo, 1, 1, 1, 2)
        self.enabledCheck = QtGui.QCheckBox(Form)
        self.enabledCheck.setObjectName(_fromUtf8("enabledCheck"))
        self.gridLayout.addWidget(self.enabledCheck, 0, 1, 1, 2)
        self.clampTestStopSpin = SpinBox(Form)
        self.clampTestStopSpin.setMaximum(100000.0)
        self.clampTestStopSpin.setProperty("value", 0.12)
        self.clampTestStopSpin.setObjectName(_fromUtf8("clampTestStopSpin"))
        self.gridLayout.addWidget(self.clampTestStopSpin, 8, 2, 1, 1)
        self.splitter = QtGui.QSplitter(Form)
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter.setObjectName(_fromUtf8("splitter"))
        self.groupBox = QtGui.QGroupBox(self.splitter)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout_2 = QtGui.QGridLayout(self.groupBox)
        self.gridLayout_2.setMargin(3)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.colorMapper = ColorMapWidget(self.groupBox)
        self.colorMapper.setMinimumSize(QtCore.QSize(0, 70))
        self.colorMapper.setObjectName(_fromUtf8("colorMapper"))
        self.gridLayout_2.addWidget(self.colorMapper, 0, 0, 1, 1)
        self.groupBox_2 = QtGui.QGroupBox(self.splitter)
        self.groupBox_2.setObjectName(_fromUtf8("groupBox_2"))
        self.gridLayout_3 = QtGui.QGridLayout(self.groupBox_2)
        self.gridLayout_3.setMargin(3)
        self.gridLayout_3.setObjectName(_fromUtf8("gridLayout_3"))
        self.taskList = QtGui.QListWidget(self.groupBox_2)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.taskList.sizePolicy().hasHeightForWidth())
        self.taskList.setSizePolicy(sizePolicy)
        self.taskList.setObjectName(_fromUtf8("taskList"))
        self.gridLayout_3.addWidget(self.taskList, 0, 0, 1, 1)
        self.gridLayout.addWidget(self.splitter, 10, 0, 1, 3)
        self.horizontalLayout_2 = QtGui.QHBoxLayout()
        self.horizontalLayout_2.setObjectName(_fromUtf8("horizontalLayout_2"))
        self.spikeThresholdAbsRadio = QtGui.QRadioButton(Form)
        self.spikeThresholdAbsRadio.setObjectName(_fromUtf8("spikeThresholdAbsRadio"))
        self.horizontalLayout_2.addWidget(self.spikeThresholdAbsRadio)
        self.spikeThresholdRelRadio = QtGui.QRadioButton(Form)
        self.spikeThresholdRelRadio.setChecked(True)
        self.spikeThresholdRelRadio.setObjectName(_fromUtf8("spikeThresholdRelRadio"))
        self.horizontalLayout_2.addWidget(self.spikeThresholdRelRadio)
        self.gridLayout.addLayout(self.horizontalLayout_2, 9, 2, 1, 1)
        self.horizontalLayout.addLayout(self.gridLayout)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.label.setText(_translate("Form", "Camera Module:", None))
        self.label_3.setText(_translate("Form", "Clamp Device:", None))
        self.label_4.setText(_translate("Form", "Scanner Device:", None))
        self.label_5.setText(_translate("Form", "Clamp Baseline:", None))
        self.clampStopSpin.setText(_translate("Form", "Clamp Test:", None))
        self.label_6.setText(_translate("Form", "Spike Threshold:", None))
        self.deleteBtn.setText(_translate("Form", "Delete", None))
        self.recomputeBtn.setText(_translate("Form", "Recompute", None))
        self.enabledCheck.setText(_translate("Form", "Enabled", None))
        self.groupBox.setTitle(_translate("Form", "Color Map", None))
        self.groupBox_2.setTitle(_translate("Form", "Recordings", None))
        self.spikeThresholdAbsRadio.setText(_translate("Form", "Abs.", None))
        self.spikeThresholdRelRadio.setText(_translate("Form", "Rel.", None))

from acq4.pyqtgraph.widgets.SpinBox import SpinBox
from acq4.pyqtgraph.widgets.ColorMapWidget import ColorMapWidget
from acq4.util.InterfaceCombo import InterfaceCombo
