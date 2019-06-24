# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'zStackTemplate.ui'
#
# Created by: PyQt4 UI code generator 4.11.4
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
        Form.resize(396, 379)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setContentsMargins(6, 3, 6, 3)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.acquireZStackBtn = QtGui.QPushButton(Form)
        self.acquireZStackBtn.setObjectName(_fromUtf8("acquireZStackBtn"))
        self.gridLayout.addWidget(self.acquireZStackBtn, 0, 0, 1, 3)
        self.bottomLabel = QtGui.QLabel(Form)
        self.bottomLabel.setText(_fromUtf8(""))
        self.bottomLabel.setObjectName(_fromUtf8("bottomLabel"))
        self.gridLayout.addWidget(self.bottomLabel, 2, 2, 3, 1)
        self.topLabel = QtGui.QLabel(Form)
        self.topLabel.setText(_fromUtf8(""))
        self.topLabel.setObjectName(_fromUtf8("topLabel"))
        self.gridLayout.addWidget(self.topLabel, 4, 0, 1, 1)
        self.focusSlider = QtGui.QSlider(Form)
        self.focusSlider.setOrientation(QtCore.Qt.Horizontal)
        self.focusSlider.setObjectName(_fromUtf8("focusSlider"))
        self.gridLayout.addWidget(self.focusSlider, 1, 0, 2, 3)
        self.zStackTree = QtGui.QTreeWidget(Form)
        self.zStackTree.setObjectName(_fromUtf8("zStackTree"))
        self.gridLayout.addWidget(self.zStackTree, 4, 1, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.acquireZStackBtn.setText(_translate("Form", "Acquire Z-Stack", None))

