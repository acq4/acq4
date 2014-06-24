# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/analysis/modules/PSPReversal/scriptTemplate.ui'
#
# Created: Fri Jun 13 08:15:06 2014
#      by: PyQt4 UI code generator 4.9.4
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
        Form.resize(350, 468)
        self.label = QtGui.QLabel(Form)
        self.label.setGeometry(QtCore.QRect(11, 5, 95, 16))
        self.label.setObjectName(_fromUtf8("label"))
        self.widget = QtGui.QWidget(Form)
        self.widget.setGeometry(QtCore.QRect(10, 30, 331, 32))
        self.widget.setObjectName(_fromUtf8("widget"))
        self.horizontalLayout = QtGui.QHBoxLayout(self.widget)
        self.horizontalLayout.setMargin(0)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.PSPReversal_ScriptFile_Btn = QtGui.QPushButton(self.widget)
        self.PSPReversal_ScriptFile_Btn.setObjectName(_fromUtf8("PSPReversal_ScriptFile_Btn"))
        self.horizontalLayout.addWidget(self.PSPReversal_ScriptFile_Btn)
        self.PSPReversal_ScriptRerun_Btn = QtGui.QPushButton(self.widget)
        self.PSPReversal_ScriptRerun_Btn.setObjectName(_fromUtf8("PSPReversal_ScriptRerun_Btn"))
        self.horizontalLayout.addWidget(self.PSPReversal_ScriptRerun_Btn)
        self.widget1 = QtGui.QWidget(Form)
        self.widget1.setGeometry(QtCore.QRect(5, 70, 341, 391))
        self.widget1.setObjectName(_fromUtf8("widget1"))
        self.verticalLayout = QtGui.QVBoxLayout(self.widget1)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.horizontalLayout_2 = QtGui.QHBoxLayout()
        self.horizontalLayout_2.setObjectName(_fromUtf8("horizontalLayout_2"))
        self.label_3 = QtGui.QLabel(self.widget1)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.horizontalLayout_2.addWidget(self.label_3)
        self.PSPReversal_ScriptFile = QtGui.QLabel(self.widget1)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.PSPReversal_ScriptFile.sizePolicy().hasHeightForWidth())
        self.PSPReversal_ScriptFile.setSizePolicy(sizePolicy)
        self.PSPReversal_ScriptFile.setMinimumSize(QtCore.QSize(220, 0))
        self.PSPReversal_ScriptFile.setObjectName(_fromUtf8("PSPReversal_ScriptFile"))
        self.horizontalLayout_2.addWidget(self.PSPReversal_ScriptFile)
        self.verticalLayout.addLayout(self.horizontalLayout_2)
        self.PSPReversal_Script_TextEdit = QtGui.QPlainTextEdit(self.widget1)
        font = QtGui.QFont()
        font.setKerning(False)
        self.PSPReversal_Script_TextEdit.setFont(font)
        self.PSPReversal_Script_TextEdit.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.PSPReversal_Script_TextEdit.setLineWrapMode(QtGui.QPlainTextEdit.NoWrap)
        self.PSPReversal_Script_TextEdit.setObjectName(_fromUtf8("PSPReversal_Script_TextEdit"))
        self.verticalLayout.addWidget(self.PSPReversal_Script_TextEdit)
        self.horizontalLayout_3 = QtGui.QHBoxLayout()
        self.horizontalLayout_3.setObjectName(_fromUtf8("horizontalLayout_3"))
        self.label_4 = QtGui.QLabel(self.widget1)
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.horizontalLayout_3.addWidget(self.label_4)
        self.PSPReversal_ScriptPrint_Btn = QtGui.QPushButton(self.widget1)
        self.PSPReversal_ScriptPrint_Btn.setObjectName(_fromUtf8("PSPReversal_ScriptPrint_Btn"))
        self.horizontalLayout_3.addWidget(self.PSPReversal_ScriptPrint_Btn)
        self.PSPReversal_ScriptCopy_Btn = QtGui.QPushButton(self.widget1)
        self.PSPReversal_ScriptCopy_Btn.setObjectName(_fromUtf8("PSPReversal_ScriptCopy_Btn"))
        self.horizontalLayout_3.addWidget(self.PSPReversal_ScriptCopy_Btn)
        self.PSPReversal_ScriptFormatted_Btn = QtGui.QPushButton(self.widget1)
        self.PSPReversal_ScriptFormatted_Btn.setObjectName(_fromUtf8("PSPReversal_ScriptFormatted_Btn"))
        self.horizontalLayout_3.addWidget(self.PSPReversal_ScriptFormatted_Btn)
        self.verticalLayout.addLayout(self.horizontalLayout_3)
        self.PSPReversal_ScriptResults_text = QtGui.QPlainTextEdit(self.widget1)
        self.PSPReversal_ScriptResults_text.setObjectName(_fromUtf8("PSPReversal_ScriptResults_text"))
        self.verticalLayout.addWidget(self.PSPReversal_ScriptResults_text)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Script Manager", None, QtGui.QApplication.UnicodeUTF8))
        self.PSPReversal_ScriptFile_Btn.setText(QtGui.QApplication.translate("Form", "Open and Run", None, QtGui.QApplication.UnicodeUTF8))
        self.PSPReversal_ScriptRerun_Btn.setText(QtGui.QApplication.translate("Form", "Rerun", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("Form", "Script:", None, QtGui.QApplication.UnicodeUTF8))
        self.PSPReversal_ScriptFile.setText(QtGui.QApplication.translate("Form", "No File", None, QtGui.QApplication.UnicodeUTF8))
        self.label_4.setText(QtGui.QApplication.translate("Form", "Output", None, QtGui.QApplication.UnicodeUTF8))
        self.PSPReversal_ScriptPrint_Btn.setText(QtGui.QApplication.translate("Form", "Print", None, QtGui.QApplication.UnicodeUTF8))
        self.PSPReversal_ScriptCopy_Btn.setText(QtGui.QApplication.translate("Form", "Copy", None, QtGui.QApplication.UnicodeUTF8))
        self.PSPReversal_ScriptFormatted_Btn.setText(QtGui.QApplication.translate("Form", "Print Formtted", None, QtGui.QApplication.UnicodeUTF8))

