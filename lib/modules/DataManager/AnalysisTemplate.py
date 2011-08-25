# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/modules/DataManager/AnalysisTemplate.ui'
#
# Created: Wed Aug 17 13:49:56 2011
#      by: pyside-uic 0.2.11 running on PySide 1.0.5
#
# WARNING! All changes made in this file will be lost!

from PySide import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(584, 501)
        self.gridLayout_3 = QtGui.QGridLayout(Form)
        self.gridLayout_3.setObjectName("gridLayout_3")
        self.groupBox = QtGui.QGroupBox(Form)
        self.groupBox.setObjectName("groupBox")
        self.gridLayout = QtGui.QGridLayout(self.groupBox)
        self.gridLayout.setObjectName("gridLayout")
        self.label = QtGui.QLabel(self.groupBox)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.databaseText = QtGui.QLineEdit(self.groupBox)
        self.databaseText.setObjectName("databaseText")
        self.gridLayout.addWidget(self.databaseText, 0, 1, 1, 2)
        self.openDbBtn = QtGui.QPushButton(self.groupBox)
        self.openDbBtn.setObjectName("openDbBtn")
        self.gridLayout.addWidget(self.openDbBtn, 0, 3, 1, 1)
        self.createDbBtn = QtGui.QPushButton(self.groupBox)
        self.createDbBtn.setObjectName("createDbBtn")
        self.gridLayout.addWidget(self.createDbBtn, 0, 4, 1, 1)
        self.refreshDbBtn = QtGui.QPushButton(self.groupBox)
        self.refreshDbBtn.setObjectName("refreshDbBtn")
        self.gridLayout.addWidget(self.refreshDbBtn, 0, 5, 1, 1)
        self.gridLayout_3.addWidget(self.groupBox, 0, 0, 1, 2)
        self.groupBox_2 = QtGui.QGroupBox(Form)
        self.groupBox_2.setObjectName("groupBox_2")
        self.gridLayout_2 = QtGui.QGridLayout(self.groupBox_2)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.analysisCombo = QtGui.QComboBox(self.groupBox_2)
        self.analysisCombo.setObjectName("analysisCombo")
        self.analysisCombo.addItem("")
        self.gridLayout_2.addWidget(self.analysisCombo, 0, 0, 1, 1)
        self.gridLayout_3.addWidget(self.groupBox_2, 1, 1, 1, 1)
        spacerItem = QtGui.QSpacerItem(168, 432, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout_3.addItem(spacerItem, 3, 0, 1, 2)
        self.groupBox_3 = QtGui.QGroupBox(Form)
        self.groupBox_3.setObjectName("groupBox_3")
        self.gridLayout_4 = QtGui.QGridLayout(self.groupBox_3)
        self.gridLayout_4.setObjectName("gridLayout_4")
        self.dataModelCombo = QtGui.QComboBox(self.groupBox_3)
        self.dataModelCombo.setObjectName("dataModelCombo")
        self.gridLayout_4.addWidget(self.dataModelCombo, 0, 0, 1, 1)
        self.gridLayout_3.addWidget(self.groupBox_3, 1, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox.setTitle(QtGui.QApplication.translate("Form", "Database", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Database:", None, QtGui.QApplication.UnicodeUTF8))
        self.openDbBtn.setText(QtGui.QApplication.translate("Form", "Open", None, QtGui.QApplication.UnicodeUTF8))
        self.createDbBtn.setText(QtGui.QApplication.translate("Form", "Create", None, QtGui.QApplication.UnicodeUTF8))
        self.refreshDbBtn.setText(QtGui.QApplication.translate("Form", "Refresh", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_2.setTitle(QtGui.QApplication.translate("Form", "Analysis Modules", None, QtGui.QApplication.UnicodeUTF8))
        self.analysisCombo.setItemText(0, QtGui.QApplication.translate("Form", "Load...", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_3.setTitle(QtGui.QApplication.translate("Form", "Data Model", None, QtGui.QApplication.UnicodeUTF8))

