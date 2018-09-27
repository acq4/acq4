# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/analysis/modules/RoiEventDetector/CtrlTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(199, 156)
        self.gridLayout_2 = QtWidgets.QGridLayout(Form)
        self.gridLayout_2.setContentsMargins(3, 3, 3, 3)
        self.gridLayout_2.setSpacing(3)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setSpacing(3)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label = QtWidgets.QLabel(Form)
        font = Qt.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label.setFont(font)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.fileLabel = QtWidgets.QLabel(Form)
        font = Qt.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.fileLabel.setFont(font)
        self.fileLabel.setObjectName("fileLabel")
        self.horizontalLayout.addWidget(self.fileLabel)
        self.horizontalLayout.setStretch(1, 5)
        self.gridLayout_2.addLayout(self.horizontalLayout, 0, 0, 1, 2)
        self.newFileBtn = QtWidgets.QPushButton(Form)
        self.newFileBtn.setObjectName("newFileBtn")
        self.gridLayout_2.addWidget(self.newFileBtn, 1, 0, 1, 1)
        self.openFileBtn = QtWidgets.QPushButton(Form)
        self.openFileBtn.setObjectName("openFileBtn")
        self.gridLayout_2.addWidget(self.openFileBtn, 1, 1, 1, 1)
        self.groupBox = QtWidgets.QGroupBox(Form)
        self.groupBox.setObjectName("groupBox")
        self.gridLayout = QtWidgets.QGridLayout(self.groupBox)
        self.gridLayout.setContentsMargins(3, 3, 3, 3)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName("gridLayout")
        self.roiRadio = QtWidgets.QRadioButton(self.groupBox)
        self.roiRadio.setChecked(True)
        self.roiRadio.setObjectName("roiRadio")
        self.gridLayout.addWidget(self.roiRadio, 1, 0, 1, 1)
        self.videoRadio = QtWidgets.QRadioButton(self.groupBox)
        self.videoRadio.setObjectName("videoRadio")
        self.gridLayout.addWidget(self.videoRadio, 2, 0, 1, 1)
        self.everythingRadio = QtWidgets.QRadioButton(self.groupBox)
        self.everythingRadio.setObjectName("everythingRadio")
        self.gridLayout.addWidget(self.everythingRadio, 3, 0, 1, 1)
        self.gridLayout_2.addWidget(self.groupBox, 2, 0, 1, 2)
        self.storeBtn = FeedbackButton(Form)
        self.storeBtn.setObjectName("storeBtn")
        self.gridLayout_2.addWidget(self.storeBtn, 3, 0, 1, 2)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.label.setText(_translate("Form", "Current storage file:"))
        self.fileLabel.setText(_translate("Form", "None"))
        self.newFileBtn.setText(_translate("Form", "New"))
        self.openFileBtn.setText(_translate("Form", "Open..."))
        self.groupBox.setTitle(_translate("Form", "Store:"))
        self.roiRadio.setText(_translate("Form", "only selected ROI"))
        self.videoRadio.setText(_translate("Form", "only selected video"))
        self.everythingRadio.setText(_translate("Form", "everything that\'s loaded"))
        self.storeBtn.setText(_translate("Form", "Store events"))

from acq4.pyqtgraph.widgets.FeedbackButton import FeedbackButton
