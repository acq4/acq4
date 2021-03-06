# -*- coding: utf-8 -*-
from __future__ import print_function

# Form implementation generated from reading ui file 'TaskTemplate.ui'
#
# Created: Sun Feb 22 09:54:16 2015
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
        Form.resize(840, 504)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(4)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(Form.sizePolicy().hasHeightForWidth())
        Form.setSizePolicy(sizePolicy)
        self.gridLayout_4 = QtGui.QGridLayout(Form)
        self.gridLayout_4.setMargin(3)
        self.gridLayout_4.setHorizontalSpacing(9)
        self.gridLayout_4.setVerticalSpacing(2)
        self.gridLayout_4.setObjectName(_fromUtf8("gridLayout_4"))
        self.gridLayout = QtGui.QGridLayout()
        self.gridLayout.setSizeConstraint(QtGui.QLayout.SetMaximumSize)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.cameraCombo = InterfaceCombo(Form)
        self.cameraCombo.setObjectName(_fromUtf8("cameraCombo"))
        self.gridLayout.addWidget(self.cameraCombo, 0, 1, 1, 1)
        self.loadConfigBtn = QtGui.QPushButton(Form)
        self.loadConfigBtn.setObjectName(_fromUtf8("loadConfigBtn"))
        self.gridLayout.addWidget(self.loadConfigBtn, 6, 0, 1, 2)
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)
        self.laserCombo = InterfaceCombo(Form)
        self.laserCombo.setObjectName(_fromUtf8("laserCombo"))
        self.gridLayout.addWidget(self.laserCombo, 1, 1, 1, 1)
        self.simulateShutterCheck = QtGui.QCheckBox(Form)
        self.simulateShutterCheck.setObjectName(_fromUtf8("simulateShutterCheck"))
        self.gridLayout.addWidget(self.simulateShutterCheck, 2, 0, 1, 2)
        self.enablePosCtrlCheck = QtGui.QCheckBox(Form)
        self.enablePosCtrlCheck.setChecked(True)
        self.enablePosCtrlCheck.setObjectName(_fromUtf8("enablePosCtrlCheck"))
        self.gridLayout.addWidget(self.enablePosCtrlCheck, 3, 0, 1, 2)
        self.enableScanProgCheck = QtGui.QCheckBox(Form)
        self.enableScanProgCheck.setChecked(True)
        self.enableScanProgCheck.setObjectName(_fromUtf8("enableScanProgCheck"))
        self.gridLayout.addWidget(self.enableScanProgCheck, 4, 0, 1, 2)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 5, 0, 1, 1)
        self.gridLayout_4.addLayout(self.gridLayout, 0, 0, 2, 1)
        self.positionCtrlGroup = QtGui.QGroupBox(Form)
        self.positionCtrlGroup.setCheckable(False)
        self.positionCtrlGroup.setChecked(False)
        self.positionCtrlGroup.setObjectName(_fromUtf8("positionCtrlGroup"))
        self.gridLayout_5 = QtGui.QGridLayout(self.positionCtrlGroup)
        self.gridLayout_5.setMargin(5)
        self.gridLayout_5.setObjectName(_fromUtf8("gridLayout_5"))
        self.showPosCtrlCheck = QtGui.QCheckBox(self.positionCtrlGroup)
        self.showPosCtrlCheck.setEnabled(True)
        self.showPosCtrlCheck.setChecked(True)
        self.showPosCtrlCheck.setObjectName(_fromUtf8("showPosCtrlCheck"))
        self.gridLayout_5.addWidget(self.showPosCtrlCheck, 1, 0, 1, 1)
        self.spotDisplayGroup = GroupBox(self.positionCtrlGroup)
        self.spotDisplayGroup.setObjectName(_fromUtf8("spotDisplayGroup"))
        self.gridLayout_2 = QtGui.QGridLayout(self.spotDisplayGroup)
        self.gridLayout_2.setMargin(3)
        self.gridLayout_2.setSpacing(0)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.sizeFromCalibrationRadio = QtGui.QRadioButton(self.spotDisplayGroup)
        self.sizeFromCalibrationRadio.setChecked(True)
        self.sizeFromCalibrationRadio.setObjectName(_fromUtf8("sizeFromCalibrationRadio"))
        self.gridLayout_2.addWidget(self.sizeFromCalibrationRadio, 0, 0, 1, 2)
        self.sizeCustomRadio = QtGui.QRadioButton(self.spotDisplayGroup)
        self.sizeCustomRadio.setObjectName(_fromUtf8("sizeCustomRadio"))
        self.gridLayout_2.addWidget(self.sizeCustomRadio, 1, 0, 1, 1)
        self.sizeSpin = SpinBox(self.spotDisplayGroup)
        self.sizeSpin.setSuffix(_fromUtf8(""))
        self.sizeSpin.setMinimum(0.0)
        self.sizeSpin.setMaximum(100000.0)
        self.sizeSpin.setSingleStep(1e-06)
        self.sizeSpin.setProperty("value", 0.0)
        self.sizeSpin.setObjectName(_fromUtf8("sizeSpin"))
        self.gridLayout_2.addWidget(self.sizeSpin, 1, 1, 1, 1)
        self.showLastSpotCheck = QtGui.QCheckBox(self.spotDisplayGroup)
        self.showLastSpotCheck.setObjectName(_fromUtf8("showLastSpotCheck"))
        self.gridLayout_2.addWidget(self.showLastSpotCheck, 2, 0, 1, 1)
        self.gridLayout_5.addWidget(self.spotDisplayGroup, 3, 0, 1, 1)
        self.spotSequenceGroup = GroupBox(self.positionCtrlGroup)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.spotSequenceGroup.sizePolicy().hasHeightForWidth())
        self.spotSequenceGroup.setSizePolicy(sizePolicy)
        self.spotSequenceGroup.setObjectName(_fromUtf8("spotSequenceGroup"))
        self.gridLayout_3 = QtGui.QGridLayout(self.spotSequenceGroup)
        self.gridLayout_3.setMargin(3)
        self.gridLayout_3.setSpacing(3)
        self.gridLayout_3.setObjectName(_fromUtf8("gridLayout_3"))
        self.minTimeSpin = SpinBox(self.spotSequenceGroup)
        self.minTimeSpin.setSuffix(_fromUtf8(""))
        self.minTimeSpin.setDecimals(2)
        self.minTimeSpin.setMaximum(1000000.0)
        self.minTimeSpin.setObjectName(_fromUtf8("minTimeSpin"))
        self.gridLayout_3.addWidget(self.minTimeSpin, 1, 1, 1, 1)
        self.timeLabel = QtGui.QLabel(self.spotSequenceGroup)
        self.timeLabel.setObjectName(_fromUtf8("timeLabel"))
        self.gridLayout_3.addWidget(self.timeLabel, 4, 0, 1, 2)
        self.minDistSpin = SpinBox(self.spotSequenceGroup)
        self.minDistSpin.setSuffix(_fromUtf8(""))
        self.minDistSpin.setMaximum(1000000.0)
        self.minDistSpin.setObjectName(_fromUtf8("minDistSpin"))
        self.gridLayout_3.addWidget(self.minDistSpin, 2, 1, 1, 1)
        self.label_3 = QtGui.QLabel(self.spotSequenceGroup)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout_3.addWidget(self.label_3, 1, 0, 1, 1)
        self.recomputeBtn = QtGui.QPushButton(self.spotSequenceGroup)
        self.recomputeBtn.setObjectName(_fromUtf8("recomputeBtn"))
        self.gridLayout_3.addWidget(self.recomputeBtn, 5, 0, 1, 2)
        self.label_4 = QtGui.QLabel(self.spotSequenceGroup)
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.gridLayout_3.addWidget(self.label_4, 2, 0, 1, 1)
        self.tdPlotWidget = PlotWidget(self.spotSequenceGroup)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.tdPlotWidget.sizePolicy().hasHeightForWidth())
        self.tdPlotWidget.setSizePolicy(sizePolicy)
        self.tdPlotWidget.setMinimumSize(QtCore.QSize(0, 100))
        self.tdPlotWidget.setMaximumSize(QtCore.QSize(16777215, 100))
        self.tdPlotWidget.setObjectName(_fromUtf8("tdPlotWidget"))
        self.gridLayout_3.addWidget(self.tdPlotWidget, 0, 0, 1, 2)
        self.gridLayout_5.addWidget(self.spotSequenceGroup, 2, 0, 1, 1)
        self.itemTree = ParameterTree(self.positionCtrlGroup)
        self.itemTree.setObjectName(_fromUtf8("itemTree"))
        self.itemTree.headerItem().setText(0, _fromUtf8("1"))
        self.itemTree.header().setVisible(False)
        self.gridLayout_5.addWidget(self.itemTree, 0, 0, 1, 1)
        self.gridLayout_4.addWidget(self.positionCtrlGroup, 0, 1, 2, 1)
        self.scanProgramGroup = QtGui.QGroupBox(Form)
        self.scanProgramGroup.setCheckable(False)
        self.scanProgramGroup.setChecked(False)
        self.scanProgramGroup.setObjectName(_fromUtf8("scanProgramGroup"))
        self.gridLayout_6 = QtGui.QGridLayout(self.scanProgramGroup)
        self.gridLayout_6.setMargin(5)
        self.gridLayout_6.setObjectName(_fromUtf8("gridLayout_6"))
        self.gridLayout_9 = QtGui.QGridLayout()
        self.gridLayout_9.setObjectName(_fromUtf8("gridLayout_9"))
        self.previewBtn = QtGui.QPushButton(self.scanProgramGroup)
        self.previewBtn.setCheckable(True)
        self.previewBtn.setObjectName(_fromUtf8("previewBtn"))
        self.gridLayout_9.addWidget(self.previewBtn, 1, 0, 1, 1)
        spacerItem1 = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout_9.addItem(spacerItem1, 1, 1, 1, 1)
        self.programPreviewSlider = QtGui.QSlider(self.scanProgramGroup)
        self.programPreviewSlider.setMaximum(999)
        self.programPreviewSlider.setProperty("value", 666)
        self.programPreviewSlider.setOrientation(QtCore.Qt.Horizontal)
        self.programPreviewSlider.setTickPosition(QtGui.QSlider.TicksBelow)
        self.programPreviewSlider.setTickInterval(333)
        self.programPreviewSlider.setObjectName(_fromUtf8("programPreviewSlider"))
        self.gridLayout_9.addWidget(self.programPreviewSlider, 1, 2, 1, 1)
        self.gridLayout_6.addLayout(self.gridLayout_9, 1, 0, 1, 1)
        self.scanProgramSplitter = QtGui.QSplitter(self.scanProgramGroup)
        self.scanProgramSplitter.setOrientation(QtCore.Qt.Vertical)
        self.scanProgramSplitter.setObjectName(_fromUtf8("scanProgramSplitter"))
        self.programTree = ParameterTree(self.scanProgramSplitter)
        self.programTree.setObjectName(_fromUtf8("programTree"))
        self.programTree.headerItem().setText(0, _fromUtf8("1"))
        self.programTree.header().setVisible(False)
        self.programTimeline = PlotWidget(self.scanProgramSplitter)
        self.programTimeline.setObjectName(_fromUtf8("programTimeline"))
        self.gridLayout_6.addWidget(self.scanProgramSplitter, 0, 0, 1, 1)
        self.gridLayout_4.addWidget(self.scanProgramGroup, 1, 2, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.cameraCombo.setToolTip(_translate("Form", "Selects the camera module to use with the scanner. This, along with the laser device, determines which calibration files will be used.", None))
        self.loadConfigBtn.setText(_translate("Form", "Load Last Config", None))
        self.label.setText(_translate("Form", "Camera Module:", None))
        self.label_2.setText(_translate("Form", "Laser Device:", None))
        self.laserCombo.setToolTip(_translate("Form", "Selects the laser to be used.", None))
        self.simulateShutterCheck.setText(_translate("Form", "Simulate Shutter", None))
        self.enablePosCtrlCheck.setText(_translate("Form", "Enable position controls", None))
        self.enableScanProgCheck.setText(_translate("Form", "Enable scan programs", None))
        self.positionCtrlGroup.setTitle(_translate("Form", "Position Controls", None))
        self.showPosCtrlCheck.setToolTip(_translate("Form", "Hide all items from view.", None))
        self.showPosCtrlCheck.setText(_translate("Form", "Show position controls", None))
        self.spotDisplayGroup.setTitle(_translate("Form", "Spot Display", None))
        self.sizeFromCalibrationRadio.setToolTip(_translate("Form", "Causes target spots to be displayed at the size determined by the calibration file. Does not affect how data is collected.", None))
        self.sizeFromCalibrationRadio.setText(_translate("Form", "Use size from scanner calibration", None))
        self.sizeCustomRadio.setToolTip(_translate("Form", "Lets the user change the display size of target spots. Does not change the way data is collected.", None))
        self.sizeCustomRadio.setText(_translate("Form", "Use custom size:", None))
        self.sizeSpin.setToolTip(_translate("Form", "Specifies the display size of the target spots. Does not change the way data is collected.", None))
        self.showLastSpotCheck.setText(_translate("Form", "Show last spot", None))
        self.spotSequenceGroup.setTitle(_translate("Form", "Spot Sequence", None))
        self.minTimeSpin.setToolTip(_translate("Form", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'MS Shell Dlg 2\'; font-size:8.25pt; font-weight:400; font-style:normal;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-size:8pt;\">When stimulating a sequence of points, this is the minimum amount of time that must pass before stimulating the same spot a second time. Points farther away will require smaller delays. Points farther than the minimum distance (specified below) will require no delay.</span></p></body></html>", None))
        self.timeLabel.setText(_translate("Form", "Total Time:", None))
        self.minDistSpin.setToolTip(_translate("Form", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'MS Shell Dlg 2\'; font-size:8.25pt; font-weight:400; font-style:normal;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-size:8pt;\">When stimulating a sequence of points, this is the minimum distance between two spots such that no time delay is required between stimulating them. Points closer than this distance will require some delay, which is determined in part by the minimum time specified above.</span></p></body></html>", None))
        self.label_3.setText(_translate("Form", "Minimum time", None))
        self.recomputeBtn.setText(_translate("Form", "Recompute Order", None))
        self.label_4.setText(_translate("Form", "Minimum distance", None))
        self.scanProgramGroup.setTitle(_translate("Form", "Scan Program Controls", None))
        self.previewBtn.setText(_translate("Form", "Preview", None))

from acq4.pyqtgraph.parametertree import ParameterTree
from acq4.pyqtgraph import SpinBox, PlotWidget, GroupBox
from acq4.util.InterfaceCombo import InterfaceCombo
