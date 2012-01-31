# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/modules/Console/template.ui'
#
# Created: Tue Jan 31 12:11:35 2012
#      by: PyQt4 UI code generator 4.8.3
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
        Form.resize(710, 497)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.splitter = QtGui.QSplitter(Form)
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter.setObjectName(_fromUtf8("splitter"))
        self.layoutWidget = QtGui.QWidget(self.splitter)
        self.layoutWidget.setObjectName(_fromUtf8("layoutWidget"))
        self.verticalLayout = QtGui.QVBoxLayout(self.layoutWidget)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.output = QtGui.QPlainTextEdit(self.layoutWidget)
        font = QtGui.QFont()
        font.setFamily(_fromUtf8("Monospace"))
        self.output.setFont(font)
        self.output.setReadOnly(True)
        self.output.setObjectName(_fromUtf8("output"))
        self.verticalLayout.addWidget(self.output)
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.input = CmdInput(self.layoutWidget)
        self.input.setObjectName(_fromUtf8("input"))
        self.horizontalLayout.addWidget(self.input)
        self.historyBtn = QtGui.QPushButton(self.layoutWidget)
        self.historyBtn.setCheckable(True)
        self.historyBtn.setObjectName(_fromUtf8("historyBtn"))
        self.horizontalLayout.addWidget(self.historyBtn)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.historyList = QtGui.QListWidget(self.splitter)
        font = QtGui.QFont()
        font.setFamily(_fromUtf8("Monospace"))
        self.historyList.setFont(font)
        self.historyList.setObjectName(_fromUtf8("historyList"))
        self.gridLayout.addWidget(self.splitter, 0, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.historyBtn.setText(QtGui.QApplication.translate("Form", "History..", None, QtGui.QApplication.UnicodeUTF8))

from CmdInput import CmdInput
