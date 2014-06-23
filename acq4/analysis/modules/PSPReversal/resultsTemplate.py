# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/analysis/modules/PSPReversal/resultsTemplate.ui'
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

class Ui_ResultsDialogBox(object):
    def setupUi(self, ResultsDialogBox):
        ResultsDialogBox.setObjectName(_fromUtf8("ResultsDialogBox"))
        ResultsDialogBox.resize(350, 468)
        font = QtGui.QFont()
        font.setPointSize(11)
        ResultsDialogBox.setFont(font)
        self.label = QtGui.QLabel(ResultsDialogBox)
        self.label.setGeometry(QtCore.QRect(10, 10, 141, 16))
        self.label.setObjectName(_fromUtf8("label"))
        self.resultsPSPReversal_text = QtGui.QTextEdit(ResultsDialogBox)
        self.resultsPSPReversal_text.setGeometry(QtCore.QRect(10, 30, 331, 431))
        self.resultsPSPReversal_text.setLineWrapMode(QtGui.QTextEdit.NoWrap)
        self.resultsPSPReversal_text.setReadOnly(True)
        self.resultsPSPReversal_text.setTextInteractionFlags(QtCore.Qt.TextSelectableByKeyboard|QtCore.Qt.TextSelectableByMouse)
        self.resultsPSPReversal_text.setObjectName(_fromUtf8("resultsPSPReversal_text"))

        self.retranslateUi(ResultsDialogBox)
        QtCore.QMetaObject.connectSlotsByName(ResultsDialogBox)

    def retranslateUi(self, ResultsDialogBox):
        ResultsDialogBox.setWindowTitle(QtGui.QApplication.translate("ResultsDialogBox", "Dialog", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("ResultsDialogBox", "PSP Reversal Results", None, QtGui.QApplication.UnicodeUTF8))

