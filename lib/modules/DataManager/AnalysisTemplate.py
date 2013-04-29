# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/modules/DataManager/AnalysisTemplate.ui'
#
# Created: Sun Apr 14 15:34:06 2013
#      by: PyQt4 UI code generator 4.9.4
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
        Form.resize(584, 501)
        self.gridLayout_3 = QtGui.QGridLayout(Form)
        self.gridLayout_3.setObjectName(_fromUtf8("gridLayout_3"))
        self.groupBox = QtGui.QGroupBox(Form)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout = QtGui.QGridLayout(self.groupBox)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label = QtGui.QLabel(self.groupBox)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.openDbBtn = QtGui.QPushButton(self.groupBox)
        self.openDbBtn.setObjectName(_fromUtf8("openDbBtn"))
        self.gridLayout.addWidget(self.openDbBtn, 0, 2, 1, 1)
        self.createDbBtn = QtGui.QPushButton(self.groupBox)
        self.createDbBtn.setObjectName(_fromUtf8("createDbBtn"))
        self.gridLayout.addWidget(self.createDbBtn, 0, 3, 1, 1)
        self.refreshDbBtn = QtGui.QPushButton(self.groupBox)
        self.refreshDbBtn.setObjectName(_fromUtf8("refreshDbBtn"))
        self.gridLayout.addWidget(self.refreshDbBtn, 0, 4, 1, 1)
        self.databaseCombo = QtGui.QComboBox(self.groupBox)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.databaseCombo.sizePolicy().hasHeightForWidth())
        self.databaseCombo.setSizePolicy(sizePolicy)
        self.databaseCombo.setObjectName(_fromUtf8("databaseCombo"))
        self.gridLayout.addWidget(self.databaseCombo, 0, 1, 1, 1)
        self.gridLayout_3.addWidget(self.groupBox, 0, 0, 1, 2)
        spacerItem = QtGui.QSpacerItem(168, 250, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout_3.addItem(spacerItem, 3, 0, 1, 2)
        self.groupBox_3 = QtGui.QGroupBox(Form)
        self.groupBox_3.setObjectName(_fromUtf8("groupBox_3"))
        self.gridLayout_4 = QtGui.QGridLayout(self.groupBox_3)
        self.gridLayout_4.setObjectName(_fromUtf8("gridLayout_4"))
        self.dataModelCombo = QtGui.QComboBox(self.groupBox_3)
        self.dataModelCombo.setObjectName(_fromUtf8("dataModelCombo"))
        self.gridLayout_4.addWidget(self.dataModelCombo, 0, 0, 1, 1)
        self.gridLayout_3.addWidget(self.groupBox_3, 1, 0, 1, 1)
        self.groupBox_2 = QtGui.QGroupBox(Form)
        self.groupBox_2.setObjectName(_fromUtf8("groupBox_2"))
        self.gridLayout_2 = QtGui.QGridLayout(self.groupBox_2)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.analysisModuleList = QtGui.QListWidget(self.groupBox_2)
        self.analysisModuleList.setObjectName(_fromUtf8("analysisModuleList"))
        self.gridLayout_2.addWidget(self.analysisModuleList, 0, 0, 1, 2)
        self.modDescriptionText = QtGui.QTextBrowser(self.groupBox_2)
        self.modDescriptionText.setObjectName(_fromUtf8("modDescriptionText"))
        self.gridLayout_2.addWidget(self.modDescriptionText, 0, 2, 1, 1)
        self.loadModuleBtn = QtGui.QPushButton(self.groupBox_2)
        self.loadModuleBtn.setObjectName(_fromUtf8("loadModuleBtn"))
        self.gridLayout_2.addWidget(self.loadModuleBtn, 1, 1, 1, 1)
        spacerItem1 = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout_2.addItem(spacerItem1, 1, 0, 1, 1)
        self.gridLayout_3.addWidget(self.groupBox_2, 1, 1, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox.setTitle(QtGui.QApplication.translate("Form", "Database", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Database:", None, QtGui.QApplication.UnicodeUTF8))
        self.openDbBtn.setText(QtGui.QApplication.translate("Form", "Open", None, QtGui.QApplication.UnicodeUTF8))
        self.createDbBtn.setText(QtGui.QApplication.translate("Form", "Create", None, QtGui.QApplication.UnicodeUTF8))
        self.refreshDbBtn.setText(QtGui.QApplication.translate("Form", "Refresh", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_3.setTitle(QtGui.QApplication.translate("Form", "Data Model", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_2.setTitle(QtGui.QApplication.translate("Form", "Analysis Modules", None, QtGui.QApplication.UnicodeUTF8))
        self.loadModuleBtn.setText(QtGui.QApplication.translate("Form", "Load Module", None, QtGui.QApplication.UnicodeUTF8))

