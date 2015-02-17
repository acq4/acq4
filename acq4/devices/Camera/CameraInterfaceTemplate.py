# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/devices/Camera/CameraInterfaceTemplate.ui'
#
# Created: Fri Jan 23 18:18:20 2015
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
        Form.resize(198, 256)
        self.verticalLayout = QtGui.QVBoxLayout(Form)
        self.verticalLayout.setSpacing(15)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.recordCtrlWidget = QtGui.QWidget(Form)
        self.recordCtrlWidget.setObjectName(_fromUtf8("recordCtrlWidget"))
        self.gridLayout_3 = QtGui.QGridLayout(self.recordCtrlWidget)
        self.gridLayout_3.setSpacing(0)
        self.gridLayout_3.setMargin(0)
        self.gridLayout_3.setObjectName(_fromUtf8("gridLayout_3"))
        self.acquireVideoBtn = QtGui.QPushButton(self.recordCtrlWidget)
        self.acquireVideoBtn.setCheckable(True)
        self.acquireVideoBtn.setObjectName(_fromUtf8("acquireVideoBtn"))
        self.gridLayout_3.addWidget(self.acquireVideoBtn, 0, 1, 1, 1)
        self.acquireFrameBtn = QtGui.QPushButton(self.recordCtrlWidget)
        self.acquireFrameBtn.setObjectName(_fromUtf8("acquireFrameBtn"))
        self.gridLayout_3.addWidget(self.acquireFrameBtn, 0, 0, 1, 1)
        self.line = QtGui.QFrame(self.recordCtrlWidget)
        self.line.setFrameShape(QtGui.QFrame.HLine)
        self.line.setFrameShadow(QtGui.QFrame.Sunken)
        self.line.setObjectName(_fromUtf8("line"))
        self.gridLayout_3.addWidget(self.line, 4, 0, 1, 2)
        self.recordStackBtn = QtGui.QPushButton(self.recordCtrlWidget)
        self.recordStackBtn.setCheckable(True)
        self.recordStackBtn.setFlat(False)
        self.recordStackBtn.setObjectName(_fromUtf8("recordStackBtn"))
        self.gridLayout_3.addWidget(self.recordStackBtn, 6, 1, 1, 1)
        self.gridLayout = QtGui.QGridLayout()
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.recordXframesCheck = QtGui.QCheckBox(self.recordCtrlWidget)
        self.recordXframesCheck.setObjectName(_fromUtf8("recordXframesCheck"))
        self.gridLayout.addWidget(self.recordXframesCheck, 0, 0, 1, 1)
        self.recordXframesSpin = QtGui.QSpinBox(self.recordCtrlWidget)
        self.recordXframesSpin.setEnabled(True)
        self.recordXframesSpin.setMinimum(1)
        self.recordXframesSpin.setMaximum(1000000)
        self.recordXframesSpin.setProperty("value", 100)
        self.recordXframesSpin.setObjectName(_fromUtf8("recordXframesSpin"))
        self.gridLayout.addWidget(self.recordXframesSpin, 0, 1, 1, 2)
        self.label_9 = QtGui.QLabel(self.recordCtrlWidget)
        self.label_9.setObjectName(_fromUtf8("label_9"))
        self.gridLayout.addWidget(self.label_9, 1, 0, 1, 1)
        self.stackSizeLabel = ValueLabel(self.recordCtrlWidget)
        self.stackSizeLabel.setObjectName(_fromUtf8("stackSizeLabel"))
        self.gridLayout.addWidget(self.stackSizeLabel, 1, 1, 1, 1)
        self.label = QtGui.QLabel(self.recordCtrlWidget)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 2, 0, 1, 1)
        self.fpsLabel = ValueLabel(self.recordCtrlWidget)
        self.fpsLabel.setObjectName(_fromUtf8("fpsLabel"))
        self.gridLayout.addWidget(self.fpsLabel, 2, 1, 1, 1)
        self.label_7 = QtGui.QLabel(self.recordCtrlWidget)
        self.label_7.setObjectName(_fromUtf8("label_7"))
        self.gridLayout.addWidget(self.label_7, 3, 0, 1, 1)
        self.displayFpsLabel = ValueLabel(self.recordCtrlWidget)
        self.displayFpsLabel.setObjectName(_fromUtf8("displayFpsLabel"))
        self.gridLayout.addWidget(self.displayFpsLabel, 3, 1, 1, 1)
        self.displayPercentLabel = ValueLabel(self.recordCtrlWidget)
        self.displayPercentLabel.setObjectName(_fromUtf8("displayPercentLabel"))
        self.gridLayout.addWidget(self.displayPercentLabel, 3, 2, 1, 1)
        self.gridLayout_3.addLayout(self.gridLayout, 7, 0, 1, 2)
        self.saveFrameBtn = FeedbackButton(self.recordCtrlWidget)
        self.saveFrameBtn.setObjectName(_fromUtf8("saveFrameBtn"))
        self.gridLayout_3.addWidget(self.saveFrameBtn, 6, 0, 1, 1)
        self.frameToBgBtn = QtGui.QPushButton(self.recordCtrlWidget)
        self.frameToBgBtn.setObjectName(_fromUtf8("frameToBgBtn"))
        self.gridLayout_3.addWidget(self.frameToBgBtn, 3, 0, 1, 2)
        self.verticalLayout.addWidget(self.recordCtrlWidget)
        self.devCtrlWidget = QtGui.QWidget(Form)
        self.devCtrlWidget.setObjectName(_fromUtf8("devCtrlWidget"))
        self.gridLayout_4 = QtGui.QGridLayout(self.devCtrlWidget)
        self.gridLayout_4.setSpacing(0)
        self.gridLayout_4.setContentsMargins(-1, 0, -1, -1)
        self.gridLayout_4.setObjectName(_fromUtf8("gridLayout_4"))
        self.btnFullFrame = QtGui.QPushButton(self.devCtrlWidget)
        self.btnFullFrame.setObjectName(_fromUtf8("btnFullFrame"))
        self.gridLayout_4.addWidget(self.btnFullFrame, 2, 0, 1, 2)
        self.label_3 = QtGui.QLabel(self.devCtrlWidget)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout_4.addWidget(self.label_3, 1, 0, 1, 1)
        self.label_2 = QtGui.QLabel(self.devCtrlWidget)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout_4.addWidget(self.label_2, 0, 0, 1, 1)
        self.spinExposure = SpinBox(self.devCtrlWidget)
        self.spinExposure.setMinimumSize(QtCore.QSize(80, 0))
        self.spinExposure.setObjectName(_fromUtf8("spinExposure"))
        self.gridLayout_4.addWidget(self.spinExposure, 1, 1, 1, 1)
        self.binningCombo = QtGui.QComboBox(self.devCtrlWidget)
        self.binningCombo.setObjectName(_fromUtf8("binningCombo"))
        self.gridLayout_4.addWidget(self.binningCombo, 0, 1, 1, 1)
        self.verticalLayout.addWidget(self.devCtrlWidget)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.acquireVideoBtn.setToolTip(_translate("Form", "Start/stop camera acquisition.\n"
"In general, this can just stay on always.", None))
        self.acquireVideoBtn.setText(_translate("Form", "Acquire Video", None))
        self.acquireFrameBtn.setText(_translate("Form", "Acquire Frame", None))
        self.recordStackBtn.setToolTip(_translate("Form", "Start/stop recording frames as they are acquired. \n"
"Frames are written to the current storage directory set in \n"
"the data manager window.", None))
        self.recordStackBtn.setText(_translate("Form", "Record Stack", None))
        self.recordXframesCheck.setText(_translate("Form", "Stack Limit", None))
        self.recordXframesSpin.setSuffix(_translate("Form", " frames", None))
        self.label_9.setText(_translate("Form", "Stack Size:", None))
        self.stackSizeLabel.setText(_translate("Form", "0 frames", None))
        self.label.setText(_translate("Form", "Acquiring:", None))
        self.fpsLabel.setText(_translate("Form", "0 fps", None))
        self.label_7.setText(_translate("Form", "Displaying:", None))
        self.displayFpsLabel.setText(_translate("Form", "0 fps", None))
        self.displayPercentLabel.setText(_translate("Form", "(0%)", None))
        self.saveFrameBtn.setText(_translate("Form", "Save Frame", None))
        self.frameToBgBtn.setText(_translate("Form", "Last Frame → Background", None))
        self.btnFullFrame.setToolTip(_translate("Form", "Set the region of interest to the maximum possible area.", None))
        self.btnFullFrame.setText(_translate("Form", "Full Frame", None))
        self.label_3.setText(_translate("Form", "Exposure", None))
        self.label_2.setText(_translate("Form", "Binning", None))
        self.spinExposure.setToolTip(_translate("Form", "Sets the exposure time for each frame.", None))

from acq4.pyqtgraph import ValueLabel, FeedbackButton, SpinBox
