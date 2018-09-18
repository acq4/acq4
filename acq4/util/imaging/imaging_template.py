# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'imaging_template.ui'
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
        Form.resize(187, 247)
        self.gridLayout_2 = QtGui.QGridLayout(Form)
        self.gridLayout_2.setMargin(0)
        self.gridLayout_2.setSpacing(0)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout_2.addItem(spacerItem, 2, 0, 1, 1)
        self.line = QtGui.QFrame(Form)
        self.line.setFrameShape(QtGui.QFrame.HLine)
        self.line.setFrameShadow(QtGui.QFrame.Sunken)
        self.line.setObjectName(_fromUtf8("line"))
        self.gridLayout_2.addWidget(self.line, 1, 0, 1, 2)
        self.acqBtnLayout = QtGui.QGridLayout()
        self.acqBtnLayout.setObjectName(_fromUtf8("acqBtnLayout"))
        self.acquireFrameBtn = QtGui.QPushButton(Form)
        self.acquireFrameBtn.setObjectName(_fromUtf8("acquireFrameBtn"))
        self.acqBtnLayout.addWidget(self.acquireFrameBtn, 0, 0, 1, 1)
        self.acquireVideoBtn = QtGui.QPushButton(Form)
        self.acquireVideoBtn.setCheckable(True)
        self.acquireVideoBtn.setObjectName(_fromUtf8("acquireVideoBtn"))
        self.acqBtnLayout.addWidget(self.acquireVideoBtn, 0, 1, 1, 1)
        self.gridLayout_2.addLayout(self.acqBtnLayout, 0, 0, 1, 2)
        self.gridLayout = QtGui.QGridLayout()
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label_7 = QtGui.QLabel(Form)
        self.label_7.setObjectName(_fromUtf8("label_7"))
        self.gridLayout.addWidget(self.label_7, 7, 0, 1, 1)
        self.label_9 = QtGui.QLabel(Form)
        self.label_9.setObjectName(_fromUtf8("label_9"))
        self.gridLayout.addWidget(self.label_9, 4, 0, 1, 1)
        self.stackSizeLabel = QtGui.QLabel(Form)
        self.stackSizeLabel.setObjectName(_fromUtf8("stackSizeLabel"))
        self.gridLayout.addWidget(self.stackSizeLabel, 4, 1, 1, 2)
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 6, 0, 1, 1)
        self.fpsLabel = ValueLabel(Form)
        self.fpsLabel.setObjectName(_fromUtf8("fpsLabel"))
        self.gridLayout.addWidget(self.fpsLabel, 6, 1, 1, 1)
        self.recordXframesSpin = QtGui.QSpinBox(Form)
        self.recordXframesSpin.setEnabled(True)
        self.recordXframesSpin.setMinimum(1)
        self.recordXframesSpin.setMaximum(1000000)
        self.recordXframesSpin.setProperty("value", 100)
        self.recordXframesSpin.setObjectName(_fromUtf8("recordXframesSpin"))
        self.gridLayout.addWidget(self.recordXframesSpin, 3, 1, 1, 2)
        self.recordXframesCheck = QtGui.QCheckBox(Form)
        self.recordXframesCheck.setObjectName(_fromUtf8("recordXframesCheck"))
        self.gridLayout.addWidget(self.recordXframesCheck, 3, 0, 1, 1)
        self.recordStackBtn = QtGui.QPushButton(Form)
        self.recordStackBtn.setCheckable(True)
        self.recordStackBtn.setFlat(False)
        self.recordStackBtn.setObjectName(_fromUtf8("recordStackBtn"))
        self.gridLayout.addWidget(self.recordStackBtn, 2, 0, 1, 3)
        spacerItem1 = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem1, 5, 0, 1, 1)
        self.displayPercentLabel = ValueLabel(Form)
        self.displayPercentLabel.setObjectName(_fromUtf8("displayPercentLabel"))
        self.gridLayout.addWidget(self.displayPercentLabel, 7, 2, 1, 1)
        spacerItem2 = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem2, 1, 0, 1, 1)
        self.displayFpsLabel = ValueLabel(Form)
        self.displayFpsLabel.setObjectName(_fromUtf8("displayFpsLabel"))
        self.gridLayout.addWidget(self.displayFpsLabel, 7, 1, 1, 1)
        self.clearPinnedFramesBtn = QtGui.QPushButton(Form)
        self.clearPinnedFramesBtn.setObjectName(_fromUtf8("clearPinnedFramesBtn"))
        self.gridLayout.addWidget(self.clearPinnedFramesBtn, 0, 1, 1, 2)
        self.gridLayout_2.addLayout(self.gridLayout, 5, 0, 1, 2)
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.saveFrameBtn = FeedbackButton(Form)
        self.saveFrameBtn.setObjectName(_fromUtf8("saveFrameBtn"))
        self.horizontalLayout.addWidget(self.saveFrameBtn)
        self.linkSavePinBtn = QtGui.QPushButton(Form)
        self.linkSavePinBtn.setMaximumSize(QtCore.QSize(20, 16777215))
        self.linkSavePinBtn.setCheckable(True)
        self.linkSavePinBtn.setObjectName(_fromUtf8("linkSavePinBtn"))
        self.horizontalLayout.addWidget(self.linkSavePinBtn)
        self.pinFrameBtn = QtGui.QPushButton(Form)
        self.pinFrameBtn.setObjectName(_fromUtf8("pinFrameBtn"))
        self.horizontalLayout.addWidget(self.pinFrameBtn)
        self.gridLayout_2.addLayout(self.horizontalLayout, 3, 0, 1, 2)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.acquireFrameBtn.setText(_translate("Form", "Acquire Frame", None))
        self.acquireVideoBtn.setToolTip(_translate("Form", "Start/stop camera acquisition.\n"
"In general, this can just stay on always.", None))
        self.acquireVideoBtn.setText(_translate("Form", "Acquire Video", None))
        self.label_7.setText(_translate("Form", "Displaying:", None))
        self.label_9.setText(_translate("Form", "Stack Size:", None))
        self.stackSizeLabel.setText(_translate("Form", "0 frames", None))
        self.label.setText(_translate("Form", "Acquiring:", None))
        self.fpsLabel.setText(_translate("Form", "0 fps", None))
        self.recordXframesSpin.setSuffix(_translate("Form", " frames", None))
        self.recordXframesCheck.setText(_translate("Form", "Stack Limit", None))
        self.recordStackBtn.setToolTip(_translate("Form", "Start/stop recording frames as they are acquired. \n"
"Frames are written to the current storage directory set in \n"
"the data manager window.", None))
        self.recordStackBtn.setText(_translate("Form", "Record Stack", None))
        self.displayPercentLabel.setText(_translate("Form", "(0%)", None))
        self.displayFpsLabel.setText(_translate("Form", "0 fps", None))
        self.clearPinnedFramesBtn.setText(_translate("Form", "Clear Pinned Frames", None))
        self.saveFrameBtn.setToolTip(_translate("Form", "Store the last acquired frame to disk", None))
        self.saveFrameBtn.setText(_translate("Form", "Save Frame", None))
        self.linkSavePinBtn.setToolTip(_translate("Form", "Link the Save Frame and Pin Frame buttons so that clicking either button performs both functions", None))
        self.linkSavePinBtn.setText(_translate("Form", "<>", None))
        self.pinFrameBtn.setToolTip(_translate("Form", "Pin the last acquired frame to the view background", None))
        self.pinFrameBtn.setText(_translate("Form", "Pin Frame", None))

from acq4.pyqtgraph import FeedbackButton, ValueLabel
