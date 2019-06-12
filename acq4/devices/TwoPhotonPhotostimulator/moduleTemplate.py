# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'moduleTemplate.ui'
#
# Created: Mon Jan  7 11:04:34 2019
#      by: PyQt4 UI code generator 4.11.3
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
        Form.resize(447, 437)
        self.gridLayout_2 = QtGui.QGridLayout(Form)
        self.gridLayout_2.setMargin(3)
        self.gridLayout_2.setSpacing(3)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.verticalLayout = QtGui.QVBoxLayout()
        self.verticalLayout.setSpacing(3)
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setSpacing(3)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.horizontalLayout.addWidget(self.label)
        self.focusWidthSpin = SpinBox(Form)
        self.focusWidthSpin.setObjectName(_fromUtf8("focusWidthSpin"))
        self.horizontalLayout.addWidget(self.focusWidthSpin)
        self.horizontalLayout.setStretch(1, 1)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.autofocusCheck = QtGui.QGroupBox(Form)
        self.autofocusCheck.setCheckable(True)
        self.autofocusCheck.setChecked(False)
        self.autofocusCheck.setObjectName(_fromUtf8("autofocusCheck"))
        self.gridLayout = QtGui.QGridLayout(self.autofocusCheck)
        self.gridLayout.setMargin(3)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label_2 = QtGui.QLabel(self.autofocusCheck)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout.addWidget(self.label_2, 0, 0, 1, 1)
        self.focusDepthSpin = SpinBox(self.autofocusCheck)
        self.focusDepthSpin.setObjectName(_fromUtf8("focusDepthSpin"))
        self.gridLayout.addWidget(self.focusDepthSpin, 0, 1, 1, 1)
        self.gridLayout.setColumnMinimumWidth(1, 2)
        self.verticalLayout.addWidget(self.autofocusCheck)
        self.stimulusParamTree = ParameterTree(Form)
        self.stimulusParamTree.setObjectName(_fromUtf8("stimulusParamTree"))
        self.verticalLayout.addWidget(self.stimulusParamTree)
        self.verticalLayout.setStretch(2, 4)
        self.gridLayout_2.addLayout(self.verticalLayout, 0, 0, 1, 1)
        self.verticalLayout_2 = QtGui.QVBoxLayout()
        self.verticalLayout_2.setSpacing(3)
        self.verticalLayout_2.setObjectName(_fromUtf8("verticalLayout_2"))
        self.markPointsBtn = FeedbackButton(Form)
        self.markPointsBtn.setCheckable(True)
        self.markPointsBtn.setObjectName(_fromUtf8("markPointsBtn"))
        self.verticalLayout_2.addWidget(self.markPointsBtn)
        self.pointsParamTree = ParameterTree(Form)
        self.pointsParamTree.setObjectName(_fromUtf8("pointsParamTree"))
        self.verticalLayout_2.addWidget(self.pointsParamTree)
        self.verticalLayout_2.setStretch(1, 4)
        self.gridLayout_2.addLayout(self.verticalLayout_2, 0, 1, 1, 1)
        self.gridLayout_2.setColumnMinimumWidth(1, 5)
        self.gridLayout_2.setColumnStretch(1, 5)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.label.setText(_translate("Form", "Stimulation focus width", None))
        self.autofocusCheck.setTitle(_translate("Form", "Automatically lower focus", None))
        self.label_2.setText(_translate("Form", "Stimulation depth", None))
        self.markPointsBtn.setText(_translate("Form", "Mark Points", None))

from acq4.pyqtgraph.parametertree import ParameterTree
from acq4.pyqtgraph import SpinBox, FeedbackButton
