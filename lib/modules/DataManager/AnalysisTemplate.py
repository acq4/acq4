# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'AnalysisTemplate.ui'
#
# Created: Tue Feb  1 17:46:54 2011
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(584, 501)
        self.verticalLayout = QtGui.QVBoxLayout(Form)
        self.verticalLayout.setObjectName("verticalLayout")
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
        self.addFileBtn = QtGui.QPushButton(self.groupBox)
        self.addFileBtn.setObjectName("addFileBtn")
        self.gridLayout.addWidget(self.addFileBtn, 1, 0, 1, 2)
        self.tableNameText = QtGui.QLineEdit(self.groupBox)
        self.tableNameText.setObjectName("tableNameText")
        self.gridLayout.addWidget(self.tableNameText, 1, 2, 1, 1)
        self.refreshDbBtn = QtGui.QPushButton(self.groupBox)
        self.refreshDbBtn.setObjectName("refreshDbBtn")
        self.gridLayout.addWidget(self.refreshDbBtn, 0, 5, 1, 1)
        self.verticalLayout.addWidget(self.groupBox)
        spacerItem = QtGui.QSpacerItem(168, 432, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem)
        self.groupBox_2 = QtGui.QGroupBox(Form)
        self.groupBox_2.setObjectName("groupBox_2")
        self.gridLayout_2 = QtGui.QGridLayout(self.groupBox_2)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.analysisCombo = QtGui.QComboBox(self.groupBox_2)
        self.analysisCombo.setObjectName("analysisCombo")
        self.analysisCombo.addItem("")
        self.gridLayout_2.addWidget(self.analysisCombo, 0, 0, 1, 1)
        self.verticalLayout.addWidget(self.groupBox_2)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox.setTitle(QtGui.QApplication.translate("Form", "Database", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Database:", None, QtGui.QApplication.UnicodeUTF8))
        self.openDbBtn.setText(QtGui.QApplication.translate("Form", "Open", None, QtGui.QApplication.UnicodeUTF8))
        self.createDbBtn.setText(QtGui.QApplication.translate("Form", "Create", None, QtGui.QApplication.UnicodeUTF8))
        self.addFileBtn.setText(QtGui.QApplication.translate("Form", "Add to table ->", None, QtGui.QApplication.UnicodeUTF8))
        self.refreshDbBtn.setText(QtGui.QApplication.translate("Form", "Refresh", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_2.setTitle(QtGui.QApplication.translate("Form", "Analysis Modules", None, QtGui.QApplication.UnicodeUTF8))
        self.analysisCombo.setItemText(0, QtGui.QApplication.translate("Form", "Load...", None, QtGui.QApplication.UnicodeUTF8))

