# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'CameraInterfaceTemplate.ui'
#
# Created: Tue May 22 18:35:26 2012
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
        Form.resize(220, 791)
        self.gridLayout_3 = QtGui.QGridLayout(Form)
        self.gridLayout_3.setMargin(0)
        self.gridLayout_3.setSpacing(0)
        self.gridLayout_3.setObjectName(_fromUtf8("gridLayout_3"))
        self.groupBox_2 = QtGui.QGroupBox(Form)
        self.groupBox_2.setObjectName(_fromUtf8("groupBox_2"))
        self.gridLayout_4 = QtGui.QGridLayout(self.groupBox_2)
        self.gridLayout_4.setSpacing(0)
        self.gridLayout_4.setContentsMargins(-1, 0, -1, -1)
        self.gridLayout_4.setObjectName(_fromUtf8("gridLayout_4"))
        self.btnFullFrame = QtGui.QPushButton(self.groupBox_2)
        self.btnFullFrame.setObjectName(_fromUtf8("btnFullFrame"))
        self.gridLayout_4.addWidget(self.btnFullFrame, 2, 0, 1, 2)
        self.label_3 = QtGui.QLabel(self.groupBox_2)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout_4.addWidget(self.label_3, 1, 0, 1, 1)
        self.label_2 = QtGui.QLabel(self.groupBox_2)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout_4.addWidget(self.label_2, 0, 0, 1, 1)
        self.spinExposure = SpinBox(self.groupBox_2)
        self.spinExposure.setMinimumSize(QtCore.QSize(80, 0))
        self.spinExposure.setObjectName(_fromUtf8("spinExposure"))
        self.gridLayout_4.addWidget(self.spinExposure, 1, 1, 1, 1)
        self.binningCombo = QtGui.QComboBox(self.groupBox_2)
        self.binningCombo.setObjectName(_fromUtf8("binningCombo"))
        self.gridLayout_4.addWidget(self.binningCombo, 0, 1, 1, 1)
        self.gridLayout_3.addWidget(self.groupBox_2, 1, 0, 1, 1)
        self.groupBox_3 = QtGui.QGroupBox(Form)
        self.groupBox_3.setObjectName(_fromUtf8("groupBox_3"))
        self.gridLayout_2 = QtGui.QGridLayout(self.groupBox_3)
        self.gridLayout_2.setSpacing(0)
        self.gridLayout_2.setContentsMargins(-1, 0, -1, -1)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.histogram = HistogramLUTWidget(self.groupBox_3)
        self.histogram.setObjectName(_fromUtf8("histogram"))
        self.gridLayout_2.addWidget(self.histogram, 0, 0, 1, 2)
        self.btnAutoGain = QtGui.QPushButton(self.groupBox_3)
        self.btnAutoGain.setCheckable(True)
        self.btnAutoGain.setChecked(False)
        self.btnAutoGain.setObjectName(_fromUtf8("btnAutoGain"))
        self.gridLayout_2.addWidget(self.btnAutoGain, 1, 0, 1, 2)
        self.label_6 = QtGui.QLabel(self.groupBox_3)
        self.label_6.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_6.setObjectName(_fromUtf8("label_6"))
        self.gridLayout_2.addWidget(self.label_6, 2, 0, 1, 1)
        self.spinAutoGainSpeed = QtGui.QDoubleSpinBox(self.groupBox_3)
        self.spinAutoGainSpeed.setProperty("value", 2.0)
        self.spinAutoGainSpeed.setObjectName(_fromUtf8("spinAutoGainSpeed"))
        self.gridLayout_2.addWidget(self.spinAutoGainSpeed, 2, 1, 1, 1)
        self.label_8 = QtGui.QLabel(self.groupBox_3)
        self.label_8.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_8.setObjectName(_fromUtf8("label_8"))
        self.gridLayout_2.addWidget(self.label_8, 3, 0, 1, 1)
        self.spinAutoGainCenterWeight = QtGui.QDoubleSpinBox(self.groupBox_3)
        self.spinAutoGainCenterWeight.setMaximum(1.0)
        self.spinAutoGainCenterWeight.setSingleStep(0.1)
        self.spinAutoGainCenterWeight.setObjectName(_fromUtf8("spinAutoGainCenterWeight"))
        self.gridLayout_2.addWidget(self.spinAutoGainCenterWeight, 3, 1, 1, 1)
        self.gridLayout_3.addWidget(self.groupBox_3, 2, 0, 1, 1)
        self.groupBox_4 = QtGui.QGroupBox(Form)
        self.groupBox_4.setObjectName(_fromUtf8("groupBox_4"))
        self.gridLayout_5 = QtGui.QGridLayout(self.groupBox_4)
        self.gridLayout_5.setSpacing(0)
        self.gridLayout_5.setContentsMargins(-1, 0, -1, -1)
        self.gridLayout_5.setObjectName(_fromUtf8("gridLayout_5"))
        self.collectBgBtn = QtGui.QPushButton(self.groupBox_4)
        self.collectBgBtn.setCheckable(True)
        self.collectBgBtn.setObjectName(_fromUtf8("collectBgBtn"))
        self.gridLayout_5.addWidget(self.collectBgBtn, 0, 0, 1, 2)
        self.label_4 = QtGui.QLabel(self.groupBox_4)
        self.label_4.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.gridLayout_5.addWidget(self.label_4, 1, 0, 1, 1)
        self.bgTimeSpin = QtGui.QDoubleSpinBox(self.groupBox_4)
        self.bgTimeSpin.setDecimals(1)
        self.bgTimeSpin.setSingleStep(1.0)
        self.bgTimeSpin.setProperty("value", 3.0)
        self.bgTimeSpin.setObjectName(_fromUtf8("bgTimeSpin"))
        self.gridLayout_5.addWidget(self.bgTimeSpin, 1, 1, 1, 1)
        self.contAvgBgCheck = QtGui.QCheckBox(self.groupBox_4)
        self.contAvgBgCheck.setObjectName(_fromUtf8("contAvgBgCheck"))
        self.gridLayout_5.addWidget(self.contAvgBgCheck, 2, 0, 1, 2)
        self.label_5 = QtGui.QLabel(self.groupBox_4)
        self.label_5.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_5.setObjectName(_fromUtf8("label_5"))
        self.gridLayout_5.addWidget(self.label_5, 3, 0, 1, 1)
        self.bgBlurSpin = QtGui.QDoubleSpinBox(self.groupBox_4)
        self.bgBlurSpin.setProperty("value", 0.0)
        self.bgBlurSpin.setObjectName(_fromUtf8("bgBlurSpin"))
        self.gridLayout_5.addWidget(self.bgBlurSpin, 3, 1, 1, 1)
        self.subtractBgBtn = QtGui.QPushButton(self.groupBox_4)
        self.subtractBgBtn.setCheckable(True)
        self.subtractBgBtn.setAutoExclusive(False)
        self.subtractBgBtn.setObjectName(_fromUtf8("subtractBgBtn"))
        self.gridLayout_5.addWidget(self.subtractBgBtn, 4, 0, 1, 2)
        self.divideBgBtn = QtGui.QPushButton(self.groupBox_4)
        self.divideBgBtn.setCheckable(True)
        self.divideBgBtn.setAutoExclusive(False)
        self.divideBgBtn.setObjectName(_fromUtf8("divideBgBtn"))
        self.gridLayout_5.addWidget(self.divideBgBtn, 5, 0, 1, 2)
        self.gridLayout_3.addWidget(self.groupBox_4, 3, 0, 2, 1)
        self.groupBox = QtGui.QGroupBox(Form)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout = QtGui.QGridLayout(self.groupBox)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setContentsMargins(-1, 0, -1, -1)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label_7 = QtGui.QLabel(self.groupBox)
        self.label_7.setObjectName(_fromUtf8("label_7"))
        self.gridLayout.addWidget(self.label_7, 9, 0, 1, 1)
        self.btnAcquire = QtGui.QPushButton(self.groupBox)
        self.btnAcquire.setCheckable(True)
        self.btnAcquire.setObjectName(_fromUtf8("btnAcquire"))
        self.gridLayout.addWidget(self.btnAcquire, 0, 0, 1, 1)
        self.recordXframesCheck = QtGui.QCheckBox(self.groupBox)
        self.recordXframesCheck.setObjectName(_fromUtf8("recordXframesCheck"))
        self.gridLayout.addWidget(self.recordXframesCheck, 7, 0, 1, 1)
        self.btnSnap = FeedbackButton(self.groupBox)
        self.btnSnap.setObjectName(_fromUtf8("btnSnap"))
        self.gridLayout.addWidget(self.btnSnap, 1, 0, 1, 1)
        self.label = QtGui.QLabel(self.groupBox)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 8, 0, 1, 1)
        self.displayFpsLabel = ValueLabel(self.groupBox)
        self.displayFpsLabel.setObjectName(_fromUtf8("displayFpsLabel"))
        self.gridLayout.addWidget(self.displayFpsLabel, 9, 1, 1, 1)
        self.displayPercentLabel = ValueLabel(self.groupBox)
        self.displayPercentLabel.setObjectName(_fromUtf8("displayPercentLabel"))
        self.gridLayout.addWidget(self.displayPercentLabel, 9, 2, 1, 1)
        self.fpsLabel = ValueLabel(self.groupBox)
        self.fpsLabel.setObjectName(_fromUtf8("fpsLabel"))
        self.gridLayout.addWidget(self.fpsLabel, 8, 1, 1, 2)
        self.recordXframesSpin = QtGui.QSpinBox(self.groupBox)
        self.recordXframesSpin.setEnabled(True)
        self.recordXframesSpin.setMinimum(1)
        self.recordXframesSpin.setMaximum(1000000)
        self.recordXframesSpin.setProperty("value", 100)
        self.recordXframesSpin.setObjectName(_fromUtf8("recordXframesSpin"))
        self.gridLayout.addWidget(self.recordXframesSpin, 7, 1, 1, 2)
        self.pushButton = QtGui.QPushButton(self.groupBox)
        self.pushButton.setObjectName(_fromUtf8("pushButton"))
        self.gridLayout.addWidget(self.pushButton, 1, 1, 1, 2)
        self.btnRecord = QtGui.QPushButton(self.groupBox)
        self.btnRecord.setCheckable(True)
        self.btnRecord.setFlat(False)
        self.btnRecord.setObjectName(_fromUtf8("btnRecord"))
        self.gridLayout.addWidget(self.btnRecord, 0, 1, 1, 2)
        self.gridLayout_3.addWidget(self.groupBox, 0, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_2.setTitle(QtGui.QApplication.translate("Form", "Device Controls", None, QtGui.QApplication.UnicodeUTF8))
        self.btnFullFrame.setToolTip(QtGui.QApplication.translate("Form", "Set the region of interest to the maximum possible area.", None, QtGui.QApplication.UnicodeUTF8))
        self.btnFullFrame.setText(QtGui.QApplication.translate("Form", "Full Frame", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("Form", "Exposure", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "Binning", None, QtGui.QApplication.UnicodeUTF8))
        self.spinExposure.setToolTip(QtGui.QApplication.translate("Form", "Sets the exposure time for each frame.", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_3.setTitle(QtGui.QApplication.translate("Form", "Display Controls", None, QtGui.QApplication.UnicodeUTF8))
        self.btnAutoGain.setToolTip(QtGui.QApplication.translate("Form", "Determines the behavior of the white/black level sliders.\n"
"When enabled, the sliders maximum and minimum values are set\n"
"to the maximum and minimum intensity values in the image.\n"
"When disabled, the minimum is 0 and the maximum is the largest \n"
"possible intensity given the bit depth of the camera.", None, QtGui.QApplication.UnicodeUTF8))
        self.btnAutoGain.setText(QtGui.QApplication.translate("Form", "Auto Gain", None, QtGui.QApplication.UnicodeUTF8))
        self.label_6.setText(QtGui.QApplication.translate("Form", "Auto Gain Delay", None, QtGui.QApplication.UnicodeUTF8))
        self.spinAutoGainSpeed.setToolTip(QtGui.QApplication.translate("Form", "Smooths out the auto gain control, prevents very\n"
"brief flashes from affecting the gain. Larger values\n"
"indicate more smoothing.\n"
"", None, QtGui.QApplication.UnicodeUTF8))
        self.label_8.setText(QtGui.QApplication.translate("Form", "Frame Center Weight", None, QtGui.QApplication.UnicodeUTF8))
        self.spinAutoGainCenterWeight.setToolTip(QtGui.QApplication.translate("Form", "Weights the auto gain measurement to the center 1/3 of\n"
"the frame when set to 1.0. A value of 0.0 meters from \n"
"the entire frame.", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_4.setTitle(QtGui.QApplication.translate("Form", "Background Subtraction", None, QtGui.QApplication.UnicodeUTF8))
        self.collectBgBtn.setText(QtGui.QApplication.translate("Form", "Collect Background", None, QtGui.QApplication.UnicodeUTF8))
        self.label_4.setText(QtGui.QApplication.translate("Form", "Average", None, QtGui.QApplication.UnicodeUTF8))
        self.bgTimeSpin.setToolTip(QtGui.QApplication.translate("Form", "Sets the approximate number of frames to be averaged for\n"
"background division.", None, QtGui.QApplication.UnicodeUTF8))
        self.bgTimeSpin.setSuffix(QtGui.QApplication.translate("Form", " s", None, QtGui.QApplication.UnicodeUTF8))
        self.contAvgBgCheck.setText(QtGui.QApplication.translate("Form", "Continuous Average", None, QtGui.QApplication.UnicodeUTF8))
        self.label_5.setText(QtGui.QApplication.translate("Form", "Blur Background.", None, QtGui.QApplication.UnicodeUTF8))
        self.bgBlurSpin.setToolTip(QtGui.QApplication.translate("Form", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'MS Shell Dlg 2\'; font-size:8.25pt; font-weight:400; font-style:normal;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-size:8pt;\">Blurs the background frame before dividing it from the current frame.</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-size:8pt;\">Large blur values may cause performance to degrade.</span></p></body></html>", None, QtGui.QApplication.UnicodeUTF8))
        self.subtractBgBtn.setText(QtGui.QApplication.translate("Form", "Subtract Background", None, QtGui.QApplication.UnicodeUTF8))
        self.divideBgBtn.setToolTip(QtGui.QApplication.translate("Form", "Enables background division. \n"
"Either a set of static background frames need to have already by collected\n"
"(by pressing \'Static\' above) or \'Continuous\' needs to be pressed.", None, QtGui.QApplication.UnicodeUTF8))
        self.divideBgBtn.setText(QtGui.QApplication.translate("Form", "Divide Background", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox.setTitle(QtGui.QApplication.translate("Form", "Recording", None, QtGui.QApplication.UnicodeUTF8))
        self.label_7.setText(QtGui.QApplication.translate("Form", "Displaying:", None, QtGui.QApplication.UnicodeUTF8))
        self.btnAcquire.setToolTip(QtGui.QApplication.translate("Form", "Start/stop camera acquisition.\n"
"In general, this can just stay on always.", None, QtGui.QApplication.UnicodeUTF8))
        self.btnAcquire.setText(QtGui.QApplication.translate("Form", "Start Video", None, QtGui.QApplication.UnicodeUTF8))
        self.recordXframesCheck.setText(QtGui.QApplication.translate("Form", "Stack Limit", None, QtGui.QApplication.UnicodeUTF8))
        self.btnSnap.setToolTip(QtGui.QApplication.translate("Form", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'MS Shell Dlg 2\'; font-size:8.25pt; font-weight:400; font-style:normal;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-size:8pt;\">Record a single frame. </span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-size:8pt;\">Image is written to the current storage directory set in </span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-size:8pt;\">the data manager window.</span></p></body></html>", None, QtGui.QApplication.UnicodeUTF8))
        self.btnSnap.setText(QtGui.QApplication.translate("Form", "Snap Frame", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Acquiring:", None, QtGui.QApplication.UnicodeUTF8))
        self.displayFpsLabel.setText(QtGui.QApplication.translate("Form", "0 fps", None, QtGui.QApplication.UnicodeUTF8))
        self.displayPercentLabel.setText(QtGui.QApplication.translate("Form", "(0%)", None, QtGui.QApplication.UnicodeUTF8))
        self.fpsLabel.setText(QtGui.QApplication.translate("Form", "0 fps", None, QtGui.QApplication.UnicodeUTF8))
        self.recordXframesSpin.setSuffix(QtGui.QApplication.translate("Form", " frames", None, QtGui.QApplication.UnicodeUTF8))
        self.pushButton.setText(QtGui.QApplication.translate("Form", "Record Frame", None, QtGui.QApplication.UnicodeUTF8))
        self.btnRecord.setToolTip(QtGui.QApplication.translate("Form", "Start/stop recording frames as they are acquired. \n"
"Frames are written to the current storage directory set in \n"
"the data manager window.", None, QtGui.QApplication.UnicodeUTF8))
        self.btnRecord.setText(QtGui.QApplication.translate("Form", "Record Stack", None, QtGui.QApplication.UnicodeUTF8))

from pyqtgraph import ValueLabel, HistogramLUTWidget, SpinBox, FeedbackButton
