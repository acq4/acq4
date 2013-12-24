# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/analysis/modules/RoiEventDetector/CtrlTemplate.ui'
#
# Created: Tue Dec 24 01:49:13 2013
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
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.label.setText(_translate("Form", "Current storage file:", None))
        self.fileLabel.setText(_translate("Form", "None", None))
        self.newFileBtn.setText(_translate("Form", "New", None))
        self.openFileBtn.setText(_translate("Form", "Open...", None))
        self.groupBox.setTitle(_translate("Form", "Store:", None))
        self.roiRadio.setText(_translate("Form", "only selected ROI", None))
        self.videoRadio.setText(_translate("Form", "only selected video", None))
        self.everythingRadio.setText(_translate("Form", "everything that\'s loaded", None))
        self.storeBtn.setText(_translate("Form", "Store events", None))

from acq4.pyqtgraph.widgets.FeedbackButton import FeedbackButton
