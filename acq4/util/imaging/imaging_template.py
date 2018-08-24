# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4\util\imaging\imaging_template.ui'
#
# Created by: PyQt4 UI code generator 4.11.4
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
        Form.resize(189, 194)
        self.gridLayout_4 = QtGui.QGridLayout(Form)
        self.gridLayout_4.setMargin(0)
        self.gridLayout_4.setSpacing(3)
        self.gridLayout_4.setObjectName(_fromUtf8("gridLayout_4"))
        self.stackWidget = QtGui.QWidget(Form)
        self.stackWidget.setObjectName(_fromUtf8("stackWidget"))
        self.gridLayout = QtGui.QGridLayout(self.stackWidget)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.recordXframesCheck = QtGui.QCheckBox(self.stackWidget)
        self.recordXframesCheck.setObjectName(_fromUtf8("recordXframesCheck"))
        self.gridLayout.addWidget(self.recordXframesCheck, 1, 0, 1, 1)
        self.recordXframesSpin = QtGui.QSpinBox(self.stackWidget)
        self.recordXframesSpin.setEnabled(True)
        self.recordXframesSpin.setMinimum(1)
        self.recordXframesSpin.setMaximum(1000000)
        self.recordXframesSpin.setProperty("value", 100)
        self.recordXframesSpin.setObjectName(_fromUtf8("recordXframesSpin"))
        self.gridLayout.addWidget(self.recordXframesSpin, 1, 1, 1, 1)
        self.label_9 = QtGui.QLabel(self.stackWidget)
        self.label_9.setObjectName(_fromUtf8("label_9"))
        self.gridLayout.addWidget(self.label_9, 2, 0, 1, 1)
        self.stackSizeLabel = QtGui.QLabel(self.stackWidget)
        self.stackSizeLabel.setObjectName(_fromUtf8("stackSizeLabel"))
        self.gridLayout.addWidget(self.stackSizeLabel, 2, 1, 1, 1)
        self.recordStackBtn = QtGui.QPushButton(self.stackWidget)
        self.recordStackBtn.setCheckable(True)
        self.recordStackBtn.setFlat(False)
        self.recordStackBtn.setObjectName(_fromUtf8("recordStackBtn"))
        self.gridLayout.addWidget(self.recordStackBtn, 0, 0, 1, 2)
        self.gridLayout_4.addWidget(self.stackWidget, 5, 0, 1, 1)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout_4.addItem(spacerItem, 2, 0, 1, 1)
        self.savePinLayout = QtGui.QGridLayout()
        self.savePinLayout.setObjectName(_fromUtf8("savePinLayout"))
        self.saveFrameBtn = FeedbackButton(Form)
        self.saveFrameBtn.setObjectName(_fromUtf8("saveFrameBtn"))
        self.savePinLayout.addWidget(self.saveFrameBtn, 0, 0, 1, 1)
        self.pinFrameBtn = QtGui.QPushButton(Form)
        self.pinFrameBtn.setObjectName(_fromUtf8("pinFrameBtn"))
        self.savePinLayout.addWidget(self.pinFrameBtn, 0, 2, 1, 1)
        self.linkSavePinBtn = QtGui.QPushButton(Form)
        self.linkSavePinBtn.setMaximumSize(QtCore.QSize(20, 16777215))
        self.linkSavePinBtn.setCheckable(True)
        self.linkSavePinBtn.setObjectName(_fromUtf8("linkSavePinBtn"))
        self.savePinLayout.addWidget(self.linkSavePinBtn, 0, 1, 1, 1)
        self.clearPinnedFramesBtn = QtGui.QPushButton(Form)
        self.clearPinnedFramesBtn.setObjectName(_fromUtf8("clearPinnedFramesBtn"))
        self.savePinLayout.addWidget(self.clearPinnedFramesBtn, 1, 1, 1, 2)
        self.gridLayout_4.addLayout(self.savePinLayout, 3, 0, 1, 1)
        spacerItem1 = QtGui.QSpacerItem(20, 1, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout_4.addItem(spacerItem1, 6, 0, 1, 1)
        spacerItem2 = QtGui.QSpacerItem(20, 0, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout_4.addItem(spacerItem2, 4, 0, 1, 1)
        self.acqBtnLayout = QtGui.QGridLayout()
        self.acqBtnLayout.setObjectName(_fromUtf8("acqBtnLayout"))
        self.acquireFrameBtn = QtGui.QPushButton(Form)
        self.acquireFrameBtn.setObjectName(_fromUtf8("acquireFrameBtn"))
        self.acqBtnLayout.addWidget(self.acquireFrameBtn, 0, 0, 1, 1)
        self.acquireVideoBtn = QtGui.QPushButton(Form)
        self.acquireVideoBtn.setCheckable(True)
        self.acquireVideoBtn.setObjectName(_fromUtf8("acquireVideoBtn"))
        self.acqBtnLayout.addWidget(self.acquireVideoBtn, 0, 1, 1, 1)
        self.gridLayout_4.addLayout(self.acqBtnLayout, 0, 0, 1, 1)
        self.line = QtGui.QFrame(Form)
        self.line.setFrameShape(QtGui.QFrame.HLine)
        self.line.setFrameShadow(QtGui.QFrame.Sunken)
        self.line.setObjectName(_fromUtf8("line"))
        self.gridLayout_4.addWidget(self.line, 1, 0, 1, 1)
        self.frameRateWidget = QtGui.QWidget(Form)
        self.frameRateWidget.setObjectName(_fromUtf8("frameRateWidget"))
        self.gridLayout_2 = QtGui.QGridLayout(self.frameRateWidget)
        self.gridLayout_2.setMargin(0)
        self.gridLayout_2.setSpacing(3)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.label = QtGui.QLabel(self.frameRateWidget)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout_2.addWidget(self.label, 0, 0, 1, 1)
        self.fpsLabel = ValueLabel(self.frameRateWidget)
        self.fpsLabel.setObjectName(_fromUtf8("fpsLabel"))
        self.gridLayout_2.addWidget(self.fpsLabel, 0, 1, 1, 1)
        self.label_7 = QtGui.QLabel(self.frameRateWidget)
        self.label_7.setObjectName(_fromUtf8("label_7"))
        self.gridLayout_2.addWidget(self.label_7, 1, 0, 1, 1)
        self.displayFpsLabel = ValueLabel(self.frameRateWidget)
        self.displayFpsLabel.setObjectName(_fromUtf8("displayFpsLabel"))
        self.gridLayout_2.addWidget(self.displayFpsLabel, 1, 1, 1, 1)
        self.displayPercentLabel = ValueLabel(self.frameRateWidget)
        self.displayPercentLabel.setObjectName(_fromUtf8("displayPercentLabel"))
        self.gridLayout_2.addWidget(self.displayPercentLabel, 1, 2, 1, 1)
        self.gridLayout_4.addWidget(self.frameRateWidget, 7, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.recordXframesCheck.setText(_translate("Form", "Stack Limit", None))
        self.recordXframesSpin.setSuffix(_translate("Form", " frames", None))
        self.label_9.setText(_translate("Form", "Stack Size:", None))
        self.stackSizeLabel.setText(_translate("Form", "0 frames", None))
        self.recordStackBtn.setToolTip(_translate("Form", "Start/stop recording frames as they are acquired. \n"
"Frames are written to the current storage directory set in \n"
"the data manager window.", None))
        self.recordStackBtn.setText(_translate("Form", "Record Stack", None))
        self.saveFrameBtn.setToolTip(_translate("Form", "Store the last acquired frame to disk", None))
        self.saveFrameBtn.setText(_translate("Form", "Save Frame", None))
        self.pinFrameBtn.setToolTip(_translate("Form", "Pin the last acquired frame to the view background", None))
        self.pinFrameBtn.setText(_translate("Form", "Pin Frame", None))
        self.linkSavePinBtn.setToolTip(_translate("Form", "Link the Save Frame and Pin Frame buttons so that clicking either button performs both functions", None))
        self.linkSavePinBtn.setText(_translate("Form", "<>", None))
        self.clearPinnedFramesBtn.setText(_translate("Form", "Clear Pinned Frames", None))
        self.acquireFrameBtn.setText(_translate("Form", "Acquire Frame", None))
        self.acquireVideoBtn.setToolTip(_translate("Form", "Start/stop camera acquisition.\n"
"In general, this can just stay on always.", None))
        self.acquireVideoBtn.setText(_translate("Form", "Acquire Video", None))
        self.label.setText(_translate("Form", "Acquiring:", None))
        self.fpsLabel.setText(_translate("Form", "0 fps", None))
        self.label_7.setText(_translate("Form", "Displaying:", None))
        self.displayFpsLabel.setText(_translate("Form", "0 fps", None))
        self.displayPercentLabel.setText(_translate("Form", "(0%)", None))

from acq4.pyqtgraph import FeedbackButton, ValueLabel
