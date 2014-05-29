# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/analysis/modules/PSPReversal/resultsTemplate.ui'
#
# Created: Tue May 27 12:24:49 2014
#      by: PyQt4 UI code generator 4.9.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    _fromUtf8 = lambda s: s

class Ui_Dialog(object):
    def setupUi(self, Dialog):
        Dialog.setObjectName(_fromUtf8("Dialog"))
        Dialog.resize(350, 500)
        self.resultsPSPReversal_text = QtGui.QTextEdit(Dialog)
        self.resultsPSPReversal_text.setGeometry(QtCore.QRect(10, 20, 331, 471))
        self.resultsPSPReversal_text.setReadOnly(True)
        self.resultsPSPReversal_text.setTabStopWidth(4)
        self.resultsPSPReversal_text.setTextInteractionFlags(QtCore.Qt.TextSelectableByKeyboard|QtCore.Qt.TextSelectableByMouse)
        self.resultsPSPReversal_text.setObjectName(_fromUtf8("resultsPSPReversal_text"))
        self.label = QtGui.QLabel(Dialog)
        self.label.setGeometry(QtCore.QRect(20, 0, 131, 16))
        self.label.setObjectName(_fromUtf8("label"))

        self.retranslateUi(Dialog)
        QtCore.QMetaObject.connectSlotsByName(Dialog)

    def retranslateUi(self, Dialog):
        Dialog.setWindowTitle(QtGui.QApplication.translate("Dialog", "Dialog", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Dialog", "PSP Reversal Results", None, QtGui.QApplication.UnicodeUTF8))

