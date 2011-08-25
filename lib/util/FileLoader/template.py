# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/util/FileLoader/template.ui'
#
# Created: Wed Aug 17 13:49:54 2011
#      by: pyside-uic 0.2.11 running on PySide 1.0.5
#
# WARNING! All changes made in this file will be lost!

from PySide import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(361, 557)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.splitter = QtGui.QSplitter(Form)
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter.setObjectName("splitter")
        self.layoutWidget = QtGui.QWidget(self.splitter)
        self.layoutWidget.setObjectName("layoutWidget")
        self.verticalLayout = QtGui.QVBoxLayout(self.layoutWidget)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.setDirBtn = QtGui.QPushButton(self.layoutWidget)
        self.setDirBtn.setObjectName("setDirBtn")
        self.verticalLayout.addWidget(self.setDirBtn)
        self.dirTree = DirTreeWidget(self.layoutWidget)
        self.dirTree.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.dirTree.setHeaderHidden(True)
        self.dirTree.setObjectName("dirTree")
        self.dirTree.headerItem().setText(0, "1")
        self.verticalLayout.addWidget(self.dirTree)
        self.layoutWidget1 = QtGui.QWidget(self.splitter)
        self.layoutWidget1.setObjectName("layoutWidget1")
        self.verticalLayout_2 = QtGui.QVBoxLayout(self.layoutWidget1)
        self.verticalLayout_2.setSpacing(0)
        self.verticalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.loadBtn = QtGui.QPushButton(self.layoutWidget1)
        self.loadBtn.setObjectName("loadBtn")
        self.verticalLayout_2.addWidget(self.loadBtn)
        self.fileTree = QtGui.QTreeWidget(self.layoutWidget1)
        self.fileTree.setHeaderHidden(True)
        self.fileTree.setObjectName("fileTree")
        self.fileTree.headerItem().setText(0, "1")
        self.verticalLayout_2.addWidget(self.fileTree)
        self.label = QtGui.QLabel(self.layoutWidget1)
        self.label.setObjectName("label")
        self.verticalLayout_2.addWidget(self.label)
        self.notesTextEdit = QtGui.QTextEdit(self.layoutWidget1)
        self.notesTextEdit.setObjectName("notesTextEdit")
        self.verticalLayout_2.addWidget(self.notesTextEdit)
        self.gridLayout.addWidget(self.splitter, 0, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.setDirBtn.setText(QtGui.QApplication.translate("Form", "Set Base Dir ->", None, QtGui.QApplication.UnicodeUTF8))
        self.loadBtn.setText(QtGui.QApplication.translate("Form", "Load File ->", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Notes:", None, QtGui.QApplication.UnicodeUTF8))

from DirTreeWidget import DirTreeWidget
