# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/devices/Camera/TaskTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(209, 134)
        self.horizontalLayout = QtWidgets.QHBoxLayout(Form)
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.horizSplitter = QtWidgets.QSplitter(Form)
        self.horizSplitter.setOrientation(Qt.Qt.Horizontal)
        self.horizSplitter.setObjectName("horizSplitter")
        self.ctrlSplitter = QtWidgets.QSplitter(self.horizSplitter)
        self.ctrlSplitter.setOrientation(Qt.Qt.Vertical)
        self.ctrlSplitter.setObjectName("ctrlSplitter")
        self.cameraGroupBox = QtWidgets.QGroupBox(self.ctrlSplitter)
        font = Qt.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.cameraGroupBox.setFont(font)
        self.cameraGroupBox.setObjectName("cameraGroupBox")
        self.gridLayout = QtWidgets.QGridLayout(self.cameraGroupBox)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.recordCheck = QtWidgets.QCheckBox(self.cameraGroupBox)
        font = Qt.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.recordCheck.setFont(font)
        self.recordCheck.setChecked(True)
        self.recordCheck.setObjectName("recordCheck")
        self.gridLayout.addWidget(self.recordCheck, 0, 0, 1, 1)
        self.displayCheck = QtWidgets.QCheckBox(self.cameraGroupBox)
        font = Qt.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.displayCheck.setFont(font)
        self.displayCheck.setChecked(True)
        self.displayCheck.setObjectName("displayCheck")
        self.gridLayout.addWidget(self.displayCheck, 0, 1, 1, 1)
        self.triggerModeCombo = QtWidgets.QComboBox(self.cameraGroupBox)
        font = Qt.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.triggerModeCombo.setFont(font)
        self.triggerModeCombo.setObjectName("triggerModeCombo")
        self.gridLayout.addWidget(self.triggerModeCombo, 1, 0, 1, 2)
        self.triggerCheck = QtWidgets.QCheckBox(self.cameraGroupBox)
        font = Qt.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.triggerCheck.setFont(font)
        self.triggerCheck.setObjectName("triggerCheck")
        self.gridLayout.addWidget(self.triggerCheck, 2, 0, 1, 2)
        self.releaseBetweenRadio = QtWidgets.QRadioButton(self.cameraGroupBox)
        font = Qt.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.releaseBetweenRadio.setFont(font)
        self.releaseBetweenRadio.setObjectName("releaseBetweenRadio")
        self.gridLayout.addWidget(self.releaseBetweenRadio, 3, 0, 1, 2)
        self.releaseAfterRadio = QtWidgets.QRadioButton(self.cameraGroupBox)
        font = Qt.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.releaseAfterRadio.setFont(font)
        self.releaseAfterRadio.setChecked(True)
        self.releaseAfterRadio.setObjectName("releaseAfterRadio")
        self.gridLayout.addWidget(self.releaseAfterRadio, 4, 0, 1, 2)
        self.plotSplitter = QtWidgets.QSplitter(self.horizSplitter)
        self.plotSplitter.setOrientation(Qt.Qt.Vertical)
        self.plotSplitter.setObjectName("plotSplitter")
        self.imageView = ImageView(self.plotSplitter)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.imageView.sizePolicy().hasHeightForWidth())
        self.imageView.setSizePolicy(sizePolicy)
        self.imageView.setObjectName("imageView")
        self.horizontalLayout.addWidget(self.horizSplitter)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.cameraGroupBox.setTitle(_translate("Form", "Camera"))
        self.recordCheck.setText(_translate("Form", "Record"))
        self.displayCheck.setText(_translate("Form", "Display"))
        self.triggerCheck.setToolTip(_translate("Form", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'Sans Serif\'; font-size:7pt; font-weight:400; font-style:normal;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">Checking this forces the camera to start <span style=\" font-style:italic;\">after</span> all</p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">other devices in the task have started so that it</p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">can correctly act as a starting trigger.</p></body></html>"))
        self.triggerCheck.setText(_translate("Form", "Camera triggers task"))
        self.releaseBetweenRadio.setText(_translate("Form", "Release between tasks"))
        self.releaseAfterRadio.setText(_translate("Form", "Release after sequence"))

from acq4.pyqtgraph import ImageView
