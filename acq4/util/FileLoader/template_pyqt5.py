# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/util/FileLoader/template.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(238, 433)
        self.gridLayout = QtWidgets.QGridLayout(Form)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.splitter = QtWidgets.QSplitter(Form)
        self.splitter.setOrientation(Qt.Qt.Vertical)
        self.splitter.setObjectName("splitter")
        self.layoutWidget = QtWidgets.QWidget(self.splitter)
        self.layoutWidget.setObjectName("layoutWidget")
        self.verticalLayout = QtWidgets.QVBoxLayout(self.layoutWidget)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.setDirBtn = QtWidgets.QPushButton(self.layoutWidget)
        self.setDirBtn.setObjectName("setDirBtn")
        self.verticalLayout.addWidget(self.setDirBtn)
        self.dirTree = DirTreeWidget(self.layoutWidget)
        self.dirTree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.dirTree.setHeaderHidden(True)
        self.dirTree.setObjectName("dirTree")
        self.dirTree.headerItem().setText(0, "1")
        self.verticalLayout.addWidget(self.dirTree)
        self.loadBtn = QtWidgets.QPushButton(self.layoutWidget)
        self.loadBtn.setObjectName("loadBtn")
        self.verticalLayout.addWidget(self.loadBtn)
        self.clearBtn = QtWidgets.QPushButton(self.layoutWidget)
        self.clearBtn.setObjectName("clearBtn")
        self.verticalLayout.addWidget(self.clearBtn)
        self.layoutWidget1 = QtWidgets.QWidget(self.splitter)
        self.layoutWidget1.setObjectName("layoutWidget1")
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(self.layoutWidget1)
        self.verticalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_2.setSpacing(0)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.fileTree = QtWidgets.QTreeWidget(self.layoutWidget1)
        self.fileTree.setHeaderHidden(True)
        self.fileTree.setObjectName("fileTree")
        self.fileTree.headerItem().setText(0, "1")
        self.verticalLayout_2.addWidget(self.fileTree)
        self.label = QtWidgets.QLabel(self.layoutWidget1)
        self.label.setObjectName("label")
        self.verticalLayout_2.addWidget(self.label)
        self.notesTextEdit = QtWidgets.QTextEdit(self.layoutWidget1)
        self.notesTextEdit.setObjectName("notesTextEdit")
        self.verticalLayout_2.addWidget(self.notesTextEdit)
        self.gridLayout.addWidget(self.splitter, 0, 0, 1, 1)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.setDirBtn.setText(_translate("Form", "Set Base Dir ->"))
        self.loadBtn.setText(_translate("Form", "Load File ->"))
        self.clearBtn.setText(_translate("Form", "Clear"))
        self.label.setText(_translate("Form", "Notes:"))

from acq4.util.DirTreeWidget import DirTreeWidget
