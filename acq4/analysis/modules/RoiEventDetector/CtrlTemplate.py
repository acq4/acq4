# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'CtrlTemplate.ui'
#
# Created: Tue Oct 23 11:31:34 2012
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
        Form.resize(199, 156)
        self.gridLayout_2 = QtGui.QGridLayout(Form)
        self.gridLayout_2.setMargin(3)
        self.gridLayout_2.setSpacing(3)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setSpacing(3)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.label = QtGui.QLabel(Form)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label.setFont(font)
        self.label.setObjectName(_fromUtf8("label"))
        self.horizontalLayout.addWidget(self.label)
        self.fileLabel = QtGui.QLabel(Form)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.fileLabel.setFont(font)
        self.fileLabel.setObjectName(_fromUtf8("fileLabel"))
        self.horizontalLayout.addWidget(self.fileLabel)
        self.horizontalLayout.setStretch(1, 5)
        self.gridLayout_2.addLayout(self.horizontalLayout, 0, 0, 1, 2)
        self.newFileBtn = QtGui.QPushButton(Form)
        self.newFileBtn.setObjectName(_fromUtf8("newFileBtn"))
        self.gridLayout_2.addWidget(self.newFileBtn, 1, 0, 1, 1)
        self.openFileBtn = QtGui.QPushButton(Form)
        self.openFileBtn.setObjectName(_fromUtf8("openFileBtn"))
        self.gridLayout_2.addWidget(self.openFileBtn, 1, 1, 1, 1)
        self.groupBox = QtGui.QGroupBox(Form)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout = QtGui.QGridLayout(self.groupBox)
        self.gridLayout.setMargin(3)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.roiRadio = QtGui.QRadioButton(self.groupBox)
        self.roiRadio.setChecked(True)
        self.roiRadio.setObjectName(_fromUtf8("roiRadio"))
        self.gridLayout.addWidget(self.roiRadio, 1, 0, 1, 1)
        self.videoRadio = QtGui.QRadioButton(self.groupBox)
        self.videoRadio.setObjectName(_fromUtf8("videoRadio"))
        self.gridLayout.addWidget(self.videoRadio, 2, 0, 1, 1)
        self.everythingRadio = QtGui.QRadioButton(self.groupBox)
        self.everythingRadio.setObjectName(_fromUtf8("everythingRadio"))
        self.gridLayout.addWidget(self.everythingRadio, 3, 0, 1, 1)
        self.gridLayout_2.addWidget(self.groupBox, 2, 0, 1, 2)
        self.storeBtn = FeedbackButton(Form)
        self.storeBtn.setObjectName(_fromUtf8("storeBtn"))
        self.gridLayout_2.addWidget(self.storeBtn, 3, 0, 1, 2)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Current storage file:", None, QtGui.QApplication.UnicodeUTF8))
        self.fileLabel.setText(QtGui.QApplication.translate("Form", "None", None, QtGui.QApplication.UnicodeUTF8))
        self.newFileBtn.setText(QtGui.QApplication.translate("Form", "New", None, QtGui.QApplication.UnicodeUTF8))
        self.openFileBtn.setText(QtGui.QApplication.translate("Form", "Open...", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox.setTitle(QtGui.QApplication.translate("Form", "Store:", None, QtGui.QApplication.UnicodeUTF8))
        self.roiRadio.setText(QtGui.QApplication.translate("Form", "only selected ROI", None, QtGui.QApplication.UnicodeUTF8))
        self.videoRadio.setText(QtGui.QApplication.translate("Form", "only selected video", None, QtGui.QApplication.UnicodeUTF8))
        self.everythingRadio.setText(QtGui.QApplication.translate("Form", "everything that\'s loaded", None, QtGui.QApplication.UnicodeUTF8))
        self.storeBtn.setText(QtGui.QApplication.translate("Form", "Store events", None, QtGui.QApplication.UnicodeUTF8))

from pyqtgraph.widgets.FeedbackButton import FeedbackButton
