# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/modules/Imager/imagerTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(180, 46)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(Form.sizePolicy().hasHeightForWidth())
        Form.setSizePolicy(sizePolicy)
        self.gridLayout = QtWidgets.QGridLayout(Form)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.Align_to_Camera = QtWidgets.QPushButton(Form)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.Align_to_Camera.sizePolicy().hasHeightForWidth())
        self.Align_to_Camera.setSizePolicy(sizePolicy)
        self.Align_to_Camera.setMinimumSize(Qt.QSize(90, 0))
        self.Align_to_Camera.setObjectName("Align_to_Camera")
        self.gridLayout.addWidget(self.Align_to_Camera, 0, 0, 1, 1)
        self.saveROI = QtWidgets.QPushButton(Form)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.saveROI.sizePolicy().hasHeightForWidth())
        self.saveROI.setSizePolicy(sizePolicy)
        self.saveROI.setMinimumSize(Qt.QSize(90, 0))
        self.saveROI.setObjectName("saveROI")
        self.gridLayout.addWidget(self.saveROI, 0, 1, 1, 1)
        self.restoreROI = QtWidgets.QPushButton(Form)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.restoreROI.sizePolicy().hasHeightForWidth())
        self.restoreROI.setSizePolicy(sizePolicy)
        self.restoreROI.setMinimumSize(Qt.QSize(90, 0))
        self.restoreROI.setObjectName("restoreROI")
        self.gridLayout.addWidget(self.restoreROI, 1, 1, 1, 1)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.Align_to_Camera.setText(_translate("Form", "Align to Camera"))
        self.saveROI.setText(_translate("Form", "Save ROI"))
        self.restoreROI.setText(_translate("Form", "Restore ROI"))

