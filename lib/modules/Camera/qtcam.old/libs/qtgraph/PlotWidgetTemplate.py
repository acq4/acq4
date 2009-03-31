# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'PlotWidget.ui'
#
# Created: Mon Oct  6 23:38:59 2008
#      by: PyQt4 UI code generator 4.4.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(567, 139)
        self.horizontalLayout = QtGui.QHBoxLayout(Form)
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setMargin(0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.centralWidget = QtGui.QWidget(Form)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.centralWidget.sizePolicy().hasHeightForWidth())
        #self.centralWidget.setSizePolicy(sizePolicy)
        self.centralWidget.setObjectName("centralWidget")
        self.horizontalLayout.addWidget(self.centralWidget)
        self.frame = QtGui.QFrame(Form)
        self.frame.setFrameShape(QtGui.QFrame.StyledPanel)
        self.frame.setFrameShadow(QtGui.QFrame.Raised)
        self.frame.setObjectName("frame")
        self.verticalLayout = QtGui.QVBoxLayout(self.frame)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.btnClose = QtGui.QToolButton(self.frame)
        self.btnClose.setObjectName("btnClose")
        self.verticalLayout.addWidget(self.btnClose)
        self.btnHorizScale = QtGui.QToolButton(self.frame)
        self.btnHorizScale.setCheckable(True)
        self.btnHorizScale.setObjectName("btnHorizScale")
        self.verticalLayout.addWidget(self.btnHorizScale)
        self.btnSvg = QtGui.QToolButton(self.frame)
        self.btnSvg.setObjectName("btnSvg")
        self.verticalLayout.addWidget(self.btnSvg)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem)
        self.horizontalLayout.addWidget(self.frame)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.btnClose.setText(QtGui.QApplication.translate("Form", "X", None, QtGui.QApplication.UnicodeUTF8))
        self.btnHorizScale.setText(QtGui.QApplication.translate("Form", "<>", None, QtGui.QApplication.UnicodeUTF8))
        self.btnSvg.setText(QtGui.QApplication.translate("Form", "svg", None, QtGui.QApplication.UnicodeUTF8))

