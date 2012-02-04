# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/modules/DataManager/FileInfoViewTemplate.ui'
#
# Created: Fri Feb  3 12:01:59 2012
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
        Form.resize(400, 300)
        self.verticalLayout = QtGui.QVBoxLayout(Form)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.scrollArea = QtGui.QScrollArea(Form)
        self.scrollArea.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setObjectName(_fromUtf8("scrollArea"))
        self.scrollAreaWidgetContents = QtGui.QWidget()
        self.scrollAreaWidgetContents.setGeometry(QtCore.QRect(0, 0, 398, 298))
        self.scrollAreaWidgetContents.setObjectName(_fromUtf8("scrollAreaWidgetContents"))
        self.formLayout_2 = QtGui.QFormLayout(self.scrollAreaWidgetContents)
        self.formLayout_2.setFieldGrowthPolicy(QtGui.QFormLayout.ExpandingFieldsGrow)
        self.formLayout_2.setMargin(0)
        self.formLayout_2.setHorizontalSpacing(10)
        self.formLayout_2.setVerticalSpacing(0)
        self.formLayout_2.setObjectName(_fromUtf8("formLayout_2"))
        self.scrollArea.setWidget(self.scrollAreaWidgetContents)
        self.verticalLayout.addWidget(self.scrollArea)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))

