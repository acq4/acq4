# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/modules/DataManager/AnalysisTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(584, 501)
        self.gridLayout_3 = QtWidgets.QGridLayout(Form)
        self.gridLayout_3.setObjectName("gridLayout_3")
        self.groupBox = QtWidgets.QGroupBox(Form)
        self.groupBox.setObjectName("groupBox")
        self.gridLayout = QtWidgets.QGridLayout(self.groupBox)
        self.gridLayout.setObjectName("gridLayout")
        self.label = QtWidgets.QLabel(self.groupBox)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.openDbBtn = QtWidgets.QPushButton(self.groupBox)
        self.openDbBtn.setObjectName("openDbBtn")
        self.gridLayout.addWidget(self.openDbBtn, 0, 2, 1, 1)
        self.createDbBtn = QtWidgets.QPushButton(self.groupBox)
        self.createDbBtn.setObjectName("createDbBtn")
        self.gridLayout.addWidget(self.createDbBtn, 0, 3, 1, 1)
        self.refreshDbBtn = QtWidgets.QPushButton(self.groupBox)
        self.refreshDbBtn.setObjectName("refreshDbBtn")
        self.gridLayout.addWidget(self.refreshDbBtn, 0, 4, 1, 1)
        self.databaseCombo = ComboBox(self.groupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.databaseCombo.sizePolicy().hasHeightForWidth())
        self.databaseCombo.setSizePolicy(sizePolicy)
        self.databaseCombo.setMinimumContentsLength(0)
        self.databaseCombo.setObjectName("databaseCombo")
        self.gridLayout.addWidget(self.databaseCombo, 0, 1, 1, 1)
        self.gridLayout_3.addWidget(self.groupBox, 0, 0, 1, 2)
        spacerItem = QtWidgets.QSpacerItem(168, 250, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.gridLayout_3.addItem(spacerItem, 3, 0, 1, 2)
        self.groupBox_3 = QtWidgets.QGroupBox(Form)
        self.groupBox_3.setObjectName("groupBox_3")
        self.gridLayout_4 = QtWidgets.QGridLayout(self.groupBox_3)
        self.gridLayout_4.setObjectName("gridLayout_4")
        self.dataModelCombo = QtWidgets.QComboBox(self.groupBox_3)
        self.dataModelCombo.setObjectName("dataModelCombo")
        self.gridLayout_4.addWidget(self.dataModelCombo, 0, 0, 1, 1)
        self.gridLayout_3.addWidget(self.groupBox_3, 1, 0, 1, 1)
        self.groupBox_2 = QtWidgets.QGroupBox(Form)
        self.groupBox_2.setObjectName("groupBox_2")
        self.gridLayout_2 = QtWidgets.QGridLayout(self.groupBox_2)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.analysisModuleList = QtWidgets.QListWidget(self.groupBox_2)
        self.analysisModuleList.setObjectName("analysisModuleList")
        self.gridLayout_2.addWidget(self.analysisModuleList, 0, 0, 1, 2)
        self.modDescriptionText = QtWidgets.QTextBrowser(self.groupBox_2)
        self.modDescriptionText.setObjectName("modDescriptionText")
        self.gridLayout_2.addWidget(self.modDescriptionText, 0, 2, 1, 1)
        self.loadModuleBtn = QtWidgets.QPushButton(self.groupBox_2)
        self.loadModuleBtn.setObjectName("loadModuleBtn")
        self.gridLayout_2.addWidget(self.loadModuleBtn, 1, 1, 1, 1)
        spacerItem1 = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.gridLayout_2.addItem(spacerItem1, 1, 0, 1, 1)
        self.gridLayout_3.addWidget(self.groupBox_2, 1, 1, 1, 1)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.groupBox.setTitle(_translate("Form", "Database"))
        self.label.setText(_translate("Form", "Database:"))
        self.openDbBtn.setText(_translate("Form", "Open"))
        self.createDbBtn.setText(_translate("Form", "Create"))
        self.refreshDbBtn.setText(_translate("Form", "Refresh"))
        self.groupBox_3.setTitle(_translate("Form", "Data Model"))
        self.groupBox_2.setTitle(_translate("Form", "Analysis Modules"))
        self.loadModuleBtn.setText(_translate("Form", "Load Module"))

from acq4.pyqtgraph.widgets.ComboBox import ComboBox
