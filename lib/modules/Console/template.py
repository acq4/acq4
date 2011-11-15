# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'template.ui'
#
# Created: Tue Nov 15 12:11:27 2011
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
        self.widget = QtGui.QWidget(self.splitter)
        self.widget.setObjectName(_fromUtf8("widget"))
        self.verticalLayout = QtGui.QVBoxLayout(self.widget)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.output = QtGui.QPlainTextEdit(self.widget)
        font = QtGui.QFont()
        font.setFamily(_fromUtf8("Monospace"))
        self.output.setFont(font)
        self.output.setReadOnly(True)
        self.output.setObjectName(_fromUtf8("output"))
        self.verticalLayout.addWidget(self.output)
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.input = CmdInput(self.widget)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.input.sizePolicy().hasHeightForWidth())
        self.input.setSizePolicy(sizePolicy)
        font = QtGui.QFont()
        font.setFamily(_fromUtf8("Monospace"))
        self.input.setFont(font)
        self.input.setObjectName(_fromUtf8("input"))
        self.horizontalLayout.addWidget(self.input)
        self.execBtn = QtGui.QPushButton(self.widget)
        self.execBtn.setObjectName(_fromUtf8("execBtn"))
        self.horizontalLayout.addWidget(self.execBtn)
        self.bgCheck = QtGui.QCheckBox(self.widget)
        self.bgCheck.setChecked(True)
        self.bgCheck.setObjectName(_fromUtf8("bgCheck"))
        self.horizontalLayout.addWidget(self.bgCheck)
        self.historyBtn = QtGui.QPushButton(self.widget)
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
        self.execBtn.setText(QtGui.QApplication.translate("Form", "Exec", None, QtGui.QApplication.UnicodeUTF8))
        self.bgCheck.setText(QtGui.QApplication.translate("Form", "Background", None, QtGui.QApplication.UnicodeUTF8))
        self.historyBtn.setText(QtGui.QApplication.translate("Form", "History..", None, QtGui.QApplication.UnicodeUTF8))

from CmdInput import CmdInput
