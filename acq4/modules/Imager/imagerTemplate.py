# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/modules/Imager/imagerTemplate.ui'
#
# Created: Thu Jan 29 18:12:51 2015
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
        Form.resize(180, 69)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(Form.sizePolicy().hasHeightForWidth())
        Form.setSizePolicy(sizePolicy)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.Align_to_Camera = QtGui.QPushButton(Form)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.Align_to_Camera.sizePolicy().hasHeightForWidth())
        self.Align_to_Camera.setSizePolicy(sizePolicy)
        self.Align_to_Camera.setMinimumSize(QtCore.QSize(90, 0))
        self.Align_to_Camera.setObjectName(_fromUtf8("Align_to_Camera"))
        self.gridLayout.addWidget(self.Align_to_Camera, 0, 0, 1, 1)
        self.saveROI = QtGui.QPushButton(Form)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.saveROI.sizePolicy().hasHeightForWidth())
        self.saveROI.setSizePolicy(sizePolicy)
        self.saveROI.setMinimumSize(QtCore.QSize(90, 0))
        self.saveROI.setObjectName(_fromUtf8("saveROI"))
        self.gridLayout.addWidget(self.saveROI, 0, 1, 1, 1)
        self.set_TilesButton = QtGui.QPushButton(Form)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.set_TilesButton.sizePolicy().hasHeightForWidth())
        self.set_TilesButton.setSizePolicy(sizePolicy)
        self.set_TilesButton.setMinimumSize(QtCore.QSize(90, 0))
        self.set_TilesButton.setCheckable(True)
        self.set_TilesButton.setObjectName(_fromUtf8("set_TilesButton"))
        self.gridLayout.addWidget(self.set_TilesButton, 1, 0, 1, 1)
        self.restoreROI = QtGui.QPushButton(Form)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.restoreROI.sizePolicy().hasHeightForWidth())
        self.restoreROI.setSizePolicy(sizePolicy)
        self.restoreROI.setMinimumSize(QtCore.QSize(90, 0))
        self.restoreROI.setObjectName(_fromUtf8("restoreROI"))
        self.gridLayout.addWidget(self.restoreROI, 1, 1, 1, 1)
        self.run_button = QtGui.QPushButton(Form)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.run_button.sizePolicy().hasHeightForWidth())
        self.run_button.setSizePolicy(sizePolicy)
        self.run_button.setMinimumSize(QtCore.QSize(90, 0))
        self.run_button.setObjectName(_fromUtf8("run_button"))
        self.gridLayout.addWidget(self.run_button, 2, 0, 1, 1)
        self.stop_button = QtGui.QPushButton(Form)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.stop_button.sizePolicy().hasHeightForWidth())
        self.stop_button.setSizePolicy(sizePolicy)
        self.stop_button.setMinimumSize(QtCore.QSize(90, 0))
        self.stop_button.setObjectName(_fromUtf8("stop_button"))
        self.gridLayout.addWidget(self.stop_button, 2, 1, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.Align_to_Camera.setText(_translate("Form", "Align to Camera", None))
        self.saveROI.setText(_translate("Form", "Save ROI", None))
        self.set_TilesButton.setText(_translate("Form", "Set Tile Area", None))
        self.restoreROI.setText(_translate("Form", "Restore ROI", None))
        self.run_button.setText(_translate("Form", "Run", None))
        self.stop_button.setText(_translate("Form", "Stop", None))

