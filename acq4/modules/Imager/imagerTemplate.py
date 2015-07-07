# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\imagerTemplate.ui'
#
# Created: Tue Jul 07 15:17:14 2015
#      by: PyQt4 UI code generator 4.10.4
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
        Form.resize(273, 49)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(Form.sizePolicy().hasHeightForWidth())
        Form.setSizePolicy(sizePolicy)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setMargin(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.Align_to_Camera = QtGui.QPushButton(Form)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.Align_to_Camera.sizePolicy().hasHeightForWidth())
        self.Align_to_Camera.setSizePolicy(sizePolicy)
        self.Align_to_Camera.setMinimumSize(QtCore.QSize(0, 0))
        self.Align_to_Camera.setObjectName(_fromUtf8("Align_to_Camera"))
        self.gridLayout.addWidget(self.Align_to_Camera, 0, 0, 1, 1)
        self.saveROI = QtGui.QPushButton(Form)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.saveROI.sizePolicy().hasHeightForWidth())
        self.saveROI.setSizePolicy(sizePolicy)
        self.saveROI.setMinimumSize(QtCore.QSize(0, 0))
        self.saveROI.setObjectName(_fromUtf8("saveROI"))
        self.gridLayout.addWidget(self.saveROI, 0, 1, 1, 1)
        self.restoreROI = QtGui.QPushButton(Form)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.restoreROI.sizePolicy().hasHeightForWidth())
        self.restoreROI.setSizePolicy(sizePolicy)
        self.restoreROI.setMinimumSize(QtCore.QSize(0, 0))
        self.restoreROI.setObjectName(_fromUtf8("restoreROI"))
        self.gridLayout.addWidget(self.restoreROI, 0, 2, 1, 1)
        self.label = QtGui.QLabel(Form)
        self.label.setIndent(2)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 1, 0, 1, 1)
        self.horizontalWidget = QtGui.QWidget(Form)
        self.horizontalWidget.setObjectName(_fromUtf8("horizontalWidget"))
        self.horizontalLayout = QtGui.QHBoxLayout(self.horizontalWidget)
        self.horizontalLayout.setSpacing(2)
        self.horizontalLayout.setMargin(0)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.zoomSingleBox = QtGui.QSpinBox(self.horizontalWidget)
        self.zoomSingleBox.setMinimum(1)
        self.zoomSingleBox.setObjectName(_fromUtf8("zoomSingleBox"))
        self.horizontalLayout.addWidget(self.zoomSingleBox)
        self.label_2 = QtGui.QLabel(self.horizontalWidget)
        self.label_2.setMaximumSize(QtCore.QSize(5, 16777215))
        font = QtGui.QFont()
        font.setPointSize(15)
        font.setBold(True)
        font.setWeight(75)
        self.label_2.setFont(font)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.horizontalLayout.addWidget(self.label_2)
        self.zoomTenthBox = QtGui.QSpinBox(self.horizontalWidget)
        self.zoomTenthBox.setMaximum(10)
        self.zoomTenthBox.setObjectName(_fromUtf8("zoomTenthBox"))
        self.horizontalLayout.addWidget(self.zoomTenthBox)
        self.gridLayout.addWidget(self.horizontalWidget, 1, 1, 1, 2)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.Align_to_Camera.setText(_translate("Form", "Default View", None))
        self.saveROI.setText(_translate("Form", "Save ROI", None))
        self.restoreROI.setText(_translate("Form", "Restore ROI", None))
        self.label.setText(_translate("Form", "Zoom", None))
        self.label_2.setText(_translate("Form", ".", None))

