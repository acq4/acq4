# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ProtocolTemplate.ui'
#
# Created: Fri Dec 11 09:08:52 2009
#      by: PyQt4 UI code generator 4.5.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(252, 141)
        self.horizontalLayout = QtGui.QHBoxLayout(Form)
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setMargin(0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.horizSplitter = QtGui.QSplitter(Form)
        self.horizSplitter.setOrientation(QtCore.Qt.Horizontal)
        self.horizSplitter.setObjectName("horizSplitter")
        self.ctrlSplitter = QtGui.QSplitter(self.horizSplitter)
        self.ctrlSplitter.setOrientation(QtCore.Qt.Vertical)
        self.ctrlSplitter.setObjectName("ctrlSplitter")
        self.cameraGroupBox = QtGui.QGroupBox(self.ctrlSplitter)
        font = QtGui.QFont()
        font.setWeight(75)
        font.setBold(True)
        self.cameraGroupBox.setFont(font)
        self.cameraGroupBox.setObjectName("cameraGroupBox")
        self.gridLayout = QtGui.QGridLayout(self.cameraGroupBox)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.recordCheck = QtGui.QCheckBox(self.cameraGroupBox)
        font = QtGui.QFont()
        font.setWeight(50)
        font.setBold(False)
        self.recordCheck.setFont(font)
        self.recordCheck.setChecked(True)
        self.recordCheck.setObjectName("recordCheck")
        self.gridLayout.addWidget(self.recordCheck, 0, 0, 1, 1)
        self.displayCheck = QtGui.QCheckBox(self.cameraGroupBox)
        font = QtGui.QFont()
        font.setWeight(50)
        font.setBold(False)
        self.displayCheck.setFont(font)
        self.displayCheck.setChecked(True)
        self.displayCheck.setObjectName("displayCheck")
        self.gridLayout.addWidget(self.displayCheck, 0, 1, 1, 1)
        self.triggerModeCombo = QtGui.QComboBox(self.cameraGroupBox)
        font = QtGui.QFont()
        font.setWeight(50)
        font.setBold(False)
        self.triggerModeCombo.setFont(font)
        self.triggerModeCombo.setObjectName("triggerModeCombo")
        self.gridLayout.addWidget(self.triggerModeCombo, 1, 0, 1, 2)
        self.triggerCheck = QtGui.QCheckBox(self.cameraGroupBox)
        font = QtGui.QFont()
        font.setWeight(50)
        font.setBold(False)
        self.triggerCheck.setFont(font)
        self.triggerCheck.setObjectName("triggerCheck")
        self.gridLayout.addWidget(self.triggerCheck, 2, 0, 1, 2)
        self.plotSplitter = QtGui.QSplitter(self.horizSplitter)
        self.plotSplitter.setOrientation(QtCore.Qt.Vertical)
        self.plotSplitter.setObjectName("plotSplitter")
        self.imageView = ImageView(self.plotSplitter)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.imageView.sizePolicy().hasHeightForWidth())
        self.imageView.setSizePolicy(sizePolicy)
        self.imageView.setObjectName("imageView")
        self.horizontalLayout.addWidget(self.horizSplitter)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.cameraGroupBox.setTitle(QtGui.QApplication.translate("Form", "Camera", None, QtGui.QApplication.UnicodeUTF8))
        self.recordCheck.setText(QtGui.QApplication.translate("Form", "Record", None, QtGui.QApplication.UnicodeUTF8))
        self.displayCheck.setText(QtGui.QApplication.translate("Form", "Display", None, QtGui.QApplication.UnicodeUTF8))
        self.triggerCheck.setToolTip(QtGui.QApplication.translate("Form", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'Sans Serif\'; font-size:7pt; font-weight:400; font-style:normal;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">Checking this forces the camera to start <span style=\" font-style:italic;\">after</span> all</p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">other devices in the protocol have started so that it</p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">can correctly act as a starting trigger.</p></body></html>", None, QtGui.QApplication.UnicodeUTF8))
        self.triggerCheck.setText(QtGui.QApplication.translate("Form", "Camera triggers protocol", None, QtGui.QApplication.UnicodeUTF8))

from lib.util.pyqtgraph.ImageView import ImageView
