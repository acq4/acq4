# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'TransformGuiTemplate.ui'
#
# Created: Fri Apr 22 17:01:47 2011
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
        Form.resize(289, 101)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(Form.sizePolicy().hasHeightForWidth())
        Form.setSizePolicy(sizePolicy)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setSizeConstraint(QtGui.QLayout.SetNoConstraint)
        self.gridLayout.setMargin(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.verticalLayout = QtGui.QVBoxLayout()
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.translateLabel = QtGui.QLabel(Form)
        self.translateLabel.setObjectName(_fromUtf8("translateLabel"))
        self.verticalLayout.addWidget(self.translateLabel)
        self.rotateLabel = QtGui.QLabel(Form)
        self.rotateLabel.setObjectName(_fromUtf8("rotateLabel"))
        self.verticalLayout.addWidget(self.rotateLabel)
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.scaleLabel = QtGui.QLabel(Form)
        self.scaleLabel.setObjectName(_fromUtf8("scaleLabel"))
        self.horizontalLayout.addWidget(self.scaleLabel)
        spacerItem = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.mirrorImageCheck = QtGui.QCheckBox(Form)
        self.mirrorImageCheck.setObjectName(_fromUtf8("mirrorImageCheck"))
        self.horizontalLayout.addWidget(self.mirrorImageCheck)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.gridLayout.addLayout(self.verticalLayout, 0, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.translateLabel.setText(QtGui.QApplication.translate("Form", "Translate:", None, QtGui.QApplication.UnicodeUTF8))
        self.rotateLabel.setText(QtGui.QApplication.translate("Form", "Rotate:", None, QtGui.QApplication.UnicodeUTF8))
        self.scaleLabel.setText(QtGui.QApplication.translate("Form", "Scale:", None, QtGui.QApplication.UnicodeUTF8))
        self.mirrorImageCheck.setText(QtGui.QApplication.translate("Form", "MirrorImage", None, QtGui.QApplication.UnicodeUTF8))

