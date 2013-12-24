# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/devices/Camera/TaskTemplate.ui'
#
# Created: Tue Dec 24 01:49:07 2013
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
        Form.resize(209, 134)
        self.horizontalLayout = QtGui.QHBoxLayout(Form)
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setMargin(0)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.horizSplitter = QtGui.QSplitter(Form)
        self.horizSplitter.setOrientation(QtCore.Qt.Horizontal)
        self.horizSplitter.setObjectName(_fromUtf8("horizSplitter"))
        self.ctrlSplitter = QtGui.QSplitter(self.horizSplitter)
        self.ctrlSplitter.setOrientation(QtCore.Qt.Vertical)
        self.ctrlSplitter.setObjectName(_fromUtf8("ctrlSplitter"))
        self.cameraGroupBox = QtGui.QGroupBox(self.ctrlSplitter)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.cameraGroupBox.setFont(font)
        self.cameraGroupBox.setObjectName(_fromUtf8("cameraGroupBox"))
        self.gridLayout = QtGui.QGridLayout(self.cameraGroupBox)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.recordCheck = QtGui.QCheckBox(self.cameraGroupBox)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.recordCheck.setFont(font)
        self.recordCheck.setChecked(True)
        self.recordCheck.setObjectName(_fromUtf8("recordCheck"))
        self.gridLayout.addWidget(self.recordCheck, 0, 0, 1, 1)
        self.displayCheck = QtGui.QCheckBox(self.cameraGroupBox)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.displayCheck.setFont(font)
        self.displayCheck.setChecked(True)
        self.displayCheck.setObjectName(_fromUtf8("displayCheck"))
        self.gridLayout.addWidget(self.displayCheck, 0, 1, 1, 1)
        self.triggerModeCombo = QtGui.QComboBox(self.cameraGroupBox)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.triggerModeCombo.setFont(font)
        self.triggerModeCombo.setObjectName(_fromUtf8("triggerModeCombo"))
        self.gridLayout.addWidget(self.triggerModeCombo, 1, 0, 1, 2)
        self.triggerCheck = QtGui.QCheckBox(self.cameraGroupBox)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.triggerCheck.setFont(font)
        self.triggerCheck.setObjectName(_fromUtf8("triggerCheck"))
        self.gridLayout.addWidget(self.triggerCheck, 2, 0, 1, 2)
        self.releaseBetweenRadio = QtGui.QRadioButton(self.cameraGroupBox)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.releaseBetweenRadio.setFont(font)
        self.releaseBetweenRadio.setObjectName(_fromUtf8("releaseBetweenRadio"))
        self.gridLayout.addWidget(self.releaseBetweenRadio, 3, 0, 1, 2)
        self.releaseAfterRadio = QtGui.QRadioButton(self.cameraGroupBox)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.releaseAfterRadio.setFont(font)
        self.releaseAfterRadio.setChecked(True)
        self.releaseAfterRadio.setObjectName(_fromUtf8("releaseAfterRadio"))
        self.gridLayout.addWidget(self.releaseAfterRadio, 4, 0, 1, 2)
        self.plotSplitter = QtGui.QSplitter(self.horizSplitter)
        self.plotSplitter.setOrientation(QtCore.Qt.Vertical)
        self.plotSplitter.setObjectName(_fromUtf8("plotSplitter"))
        self.imageView = ImageView(self.plotSplitter)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.imageView.sizePolicy().hasHeightForWidth())
        self.imageView.setSizePolicy(sizePolicy)
        self.imageView.setObjectName(_fromUtf8("imageView"))
        self.horizontalLayout.addWidget(self.horizSplitter)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.cameraGroupBox.setTitle(_translate("Form", "Camera", None))
        self.recordCheck.setText(_translate("Form", "Record", None))
        self.displayCheck.setText(_translate("Form", "Display", None))
        self.triggerCheck.setToolTip(_translate("Form", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'Sans Serif\'; font-size:7pt; font-weight:400; font-style:normal;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">Checking this forces the camera to start <span style=\" font-style:italic;\">after</span> all</p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">other devices in the task have started so that it</p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">can correctly act as a starting trigger.</p></body></html>", None))
        self.triggerCheck.setText(_translate("Form", "Camera triggers task", None))
        self.releaseBetweenRadio.setText(_translate("Form", "Release between tasks", None))
        self.releaseAfterRadio.setText(_translate("Form", "Release after sequence", None))

from acq4.pyqtgraph import ImageView
