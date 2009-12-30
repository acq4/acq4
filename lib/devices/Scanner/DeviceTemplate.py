# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'DeviceTemplate.ui'
#
# Created: Sun Sep 13 16:40:10 2009
#      by: PyQt4 UI code generator 4.5.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(779, 203)
        self.horizontalLayout_3 = QtGui.QHBoxLayout(Form)
        self.horizontalLayout_3.setSpacing(0)
        self.horizontalLayout_3.setMargin(0)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.splitter = QtGui.QSplitter(Form)
        self.splitter.setOrientation(QtCore.Qt.Horizontal)
        self.splitter.setObjectName("splitter")
        self.widget = QtGui.QWidget(self.splitter)
        self.widget.setObjectName("widget")
        self.verticalLayout = QtGui.QVBoxLayout(self.widget)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.calibrationList = QtGui.QTreeWidget(self.widget)
        self.calibrationList.setRootIsDecorated(False)
        self.calibrationList.setItemsExpandable(False)
        self.calibrationList.setObjectName("calibrationList")
        self.calibrationList.header().setStretchLastSection(True)
        self.verticalLayout.addWidget(self.calibrationList)
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label_2 = QtGui.QLabel(self.widget)
        self.label_2.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_2.setObjectName("label_2")
        self.horizontalLayout.addWidget(self.label_2)
        self.cameraCombo = QtGui.QComboBox(self.widget)
        self.cameraCombo.setObjectName("cameraCombo")
        self.horizontalLayout.addWidget(self.cameraCombo)
        self.label_3 = QtGui.QLabel(self.widget)
        self.label_3.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_3.setObjectName("label_3")
        self.horizontalLayout.addWidget(self.label_3)
        self.laserCombo = QtGui.QComboBox(self.widget)
        self.laserCombo.setObjectName("laserCombo")
        self.horizontalLayout.addWidget(self.laserCombo)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.horizontalLayout_2 = QtGui.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.calibrateBtn = QtGui.QPushButton(self.widget)
        self.calibrateBtn.setObjectName("calibrateBtn")
        self.horizontalLayout_2.addWidget(self.calibrateBtn)
        self.testBtn = QtGui.QPushButton(self.widget)
        self.testBtn.setObjectName("testBtn")
        self.horizontalLayout_2.addWidget(self.testBtn)
        self.deleteBtn = QtGui.QPushButton(self.widget)
        self.deleteBtn.setObjectName("deleteBtn")
        self.horizontalLayout_2.addWidget(self.deleteBtn)
        self.verticalLayout.addLayout(self.horizontalLayout_2)
        self.accuracyLabel = QtGui.QLabel(self.widget)
        self.accuracyLabel.setObjectName("accuracyLabel")
        self.verticalLayout.addWidget(self.accuracyLabel)
        self.view = GraphicsView(self.splitter)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.view.sizePolicy().hasHeightForWidth())
        self.view.setSizePolicy(sizePolicy)
        self.view.setObjectName("view")
        self.horizontalLayout_3.addWidget(self.splitter)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.calibrationList.headerItem().setText(0, QtGui.QApplication.translate("Form", "Camera", None, QtGui.QApplication.UnicodeUTF8))
        self.calibrationList.headerItem().setText(1, QtGui.QApplication.translate("Form", "Objective", None, QtGui.QApplication.UnicodeUTF8))
        self.calibrationList.headerItem().setText(2, QtGui.QApplication.translate("Form", "Laser", None, QtGui.QApplication.UnicodeUTF8))
        self.calibrationList.headerItem().setText(3, QtGui.QApplication.translate("Form", "Spot", None, QtGui.QApplication.UnicodeUTF8))
        self.calibrationList.headerItem().setText(4, QtGui.QApplication.translate("Form", "Date", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "Camera:", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("Form", "Laser:", None, QtGui.QApplication.UnicodeUTF8))
        self.calibrateBtn.setText(QtGui.QApplication.translate("Form", "Calibrate", None, QtGui.QApplication.UnicodeUTF8))
        self.testBtn.setText(QtGui.QApplication.translate("Form", "Test", None, QtGui.QApplication.UnicodeUTF8))
        self.deleteBtn.setText(QtGui.QApplication.translate("Form", "Delete", None, QtGui.QApplication.UnicodeUTF8))
        self.accuracyLabel.setText(QtGui.QApplication.translate("Form", "Accuracy:", None, QtGui.QApplication.UnicodeUTF8))

from lib.util.pyqtgraph.GraphicsView import GraphicsView
