# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/util/DirTreeWidget/DirTreeTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(282, 285)
        self.gridLayout = QtWidgets.QGridLayout(Form)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.titleLabel = QtWidgets.QLabel(Form)
        self.titleLabel.setAlignment(Qt.Qt.AlignCenter)
        self.titleLabel.setObjectName("titleLabel")
        self.gridLayout.addWidget(self.titleLabel, 0, 0, 1, 2)
        self.newBtn = QtWidgets.QPushButton(Form)
        self.newBtn.setObjectName("newBtn")
        self.gridLayout.addWidget(self.newBtn, 0, 2, 1, 1)
        self.loadBtn = QtWidgets.QPushButton(Form)
        self.loadBtn.setObjectName("loadBtn")
        self.gridLayout.addWidget(self.loadBtn, 1, 2, 1, 1)
        spacerItem = QtWidgets.QSpacerItem(88, 77, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 2, 2, 1, 1)
        self.saveBtn = QtWidgets.QPushButton(Form)
        self.saveBtn.setEnabled(False)
        self.saveBtn.setObjectName("saveBtn")
        self.gridLayout.addWidget(self.saveBtn, 3, 2, 1, 1)
        self.saveAsBtn = QtWidgets.QPushButton(Form)
        self.saveAsBtn.setEnabled(True)
        self.saveAsBtn.setObjectName("saveAsBtn")
        self.gridLayout.addWidget(self.saveAsBtn, 4, 2, 1, 1)
        spacerItem1 = QtWidgets.QSpacerItem(88, 47, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem1, 6, 2, 1, 1)
        self.deleteBtn = QtWidgets.QPushButton(Form)
        self.deleteBtn.setEnabled(True)
        self.deleteBtn.setObjectName("deleteBtn")
        self.gridLayout.addWidget(self.deleteBtn, 7, 2, 1, 1)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.currentTitleLabel = QtWidgets.QLabel(Form)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.currentTitleLabel.sizePolicy().hasHeightForWidth())
        self.currentTitleLabel.setSizePolicy(sizePolicy)
        self.currentTitleLabel.setObjectName("currentTitleLabel")
        self.horizontalLayout.addWidget(self.currentTitleLabel)
        self.currentLabel = QtWidgets.QLabel(Form)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.currentLabel.sizePolicy().hasHeightForWidth())
        self.currentLabel.setSizePolicy(sizePolicy)
        font = Qt.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.currentLabel.setFont(font)
        self.currentLabel.setText("")
        self.currentLabel.setObjectName("currentLabel")
        self.horizontalLayout.addWidget(self.currentLabel)
        self.gridLayout.addLayout(self.horizontalLayout, 8, 0, 1, 3)
        self.newDirBtn = QtWidgets.QPushButton(Form)
        self.newDirBtn.setObjectName("newDirBtn")
        self.gridLayout.addWidget(self.newDirBtn, 5, 2, 1, 1)
        self.fileTree = DirTreeWidget(Form)
        self.fileTree.setAcceptDrops(True)
        self.fileTree.setHeaderHidden(True)
        self.fileTree.setObjectName("fileTree")
        self.fileTree.headerItem().setText(0, "1")
        self.gridLayout.addWidget(self.fileTree, 1, 1, 7, 1)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.titleLabel.setText(_translate("Form", "Protocols"))
        self.newBtn.setText(_translate("Form", "New"))
        self.loadBtn.setText(_translate("Form", "Load"))
        self.saveBtn.setText(_translate("Form", "Save"))
        self.saveAsBtn.setText(_translate("Form", "Save As.."))
        self.deleteBtn.setText(_translate("Form", "Delete"))
        self.currentTitleLabel.setText(_translate("Form", "Current Protocol:"))
        self.newDirBtn.setText(_translate("Form", "New Dir"))

from acq4.util.DirTreeWidget import DirTreeWidget
