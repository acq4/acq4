# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/modules/Manager/ManagerTemplate.ui'
#
# Created: Wed Apr 18 12:58:58 2012
#      by: PyQt4 UI code generator 4.8.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    _fromUtf8 = lambda s: s

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName(_fromUtf8("MainWindow"))
        MainWindow.resize(800, 600)
        MainWindow.setStyleSheet(_fromUtf8(""))
        MainWindow.setDockOptions(QtGui.QMainWindow.AllowNestedDocks|QtGui.QMainWindow.AllowTabbedDocks|QtGui.QMainWindow.AnimatedDocks)
        self.centralwidget = QtGui.QWidget(MainWindow)
        self.centralwidget.setObjectName(_fromUtf8("centralwidget"))
        self.verticalLayout_2 = QtGui.QVBoxLayout(self.centralwidget)
        self.verticalLayout_2.setSpacing(0)
        self.verticalLayout_2.setMargin(0)
        self.verticalLayout_2.setObjectName(_fromUtf8("verticalLayout_2"))
        self.verticalLayout = QtGui.QVBoxLayout()
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.groupBox = QtGui.QGroupBox(self.centralwidget)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.verticalLayout_3 = QtGui.QVBoxLayout(self.groupBox)
        self.verticalLayout_3.setSpacing(0)
        self.verticalLayout_3.setMargin(0)
        self.verticalLayout_3.setObjectName(_fromUtf8("verticalLayout_3"))
        self.configList = QtGui.QListWidget(self.groupBox)
        self.configList.setObjectName(_fromUtf8("configList"))
        self.verticalLayout_3.addWidget(self.configList)
        self.loadConfigBtn = QtGui.QPushButton(self.groupBox)
        self.loadConfigBtn.setObjectName(_fromUtf8("loadConfigBtn"))
        self.verticalLayout_3.addWidget(self.loadConfigBtn)
        self.verticalLayout.addWidget(self.groupBox)
        self.groupBox_2 = QtGui.QGroupBox(self.centralwidget)
        self.groupBox_2.setObjectName(_fromUtf8("groupBox_2"))
        self.verticalLayout_4 = QtGui.QVBoxLayout(self.groupBox_2)
        self.verticalLayout_4.setSpacing(0)
        self.verticalLayout_4.setMargin(0)
        self.verticalLayout_4.setObjectName(_fromUtf8("verticalLayout_4"))
        self.moduleList = QtGui.QListWidget(self.groupBox_2)
        self.moduleList.setObjectName(_fromUtf8("moduleList"))
        self.verticalLayout_4.addWidget(self.moduleList)
        self.loadModuleBtn = QtGui.QPushButton(self.groupBox_2)
        self.loadModuleBtn.setObjectName(_fromUtf8("loadModuleBtn"))
        self.verticalLayout_4.addWidget(self.loadModuleBtn)
        self.logBtn = QtGui.QPushButton(self.groupBox_2)
        self.logBtn.setObjectName(_fromUtf8("logBtn"))
        self.verticalLayout_4.addWidget(self.logBtn)
        self.verticalLayout.addWidget(self.groupBox_2)
        self.logBtn1 = LogButton(self.centralwidget)
        self.logBtn1.setObjectName(_fromUtf8("logBtn1"))
        self.verticalLayout.addWidget(self.logBtn1)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem)
        self.reloadModuleBtn = QtGui.QPushButton(self.centralwidget)
        self.reloadModuleBtn.setObjectName(_fromUtf8("reloadModuleBtn"))
        self.verticalLayout.addWidget(self.reloadModuleBtn)
        self.quitBtn = QtGui.QPushButton(self.centralwidget)
        self.quitBtn.setObjectName(_fromUtf8("quitBtn"))
        self.verticalLayout.addWidget(self.quitBtn)
        self.verticalLayout_2.addLayout(self.verticalLayout)
        MainWindow.setCentralWidget(self.centralwidget)
        self.statusBar = QtGui.QStatusBar(MainWindow)
        self.statusBar.setObjectName(_fromUtf8("statusBar"))
        MainWindow.setStatusBar(self.statusBar)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QtGui.QApplication.translate("MainWindow", "ACQ4 Manager", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox.setTitle(QtGui.QApplication.translate("MainWindow", "Configuration", None, QtGui.QApplication.UnicodeUTF8))
        self.loadConfigBtn.setText(QtGui.QApplication.translate("MainWindow", "Load Configuration", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_2.setTitle(QtGui.QApplication.translate("MainWindow", "Modules", None, QtGui.QApplication.UnicodeUTF8))
        self.loadModuleBtn.setText(QtGui.QApplication.translate("MainWindow", "Load Module", None, QtGui.QApplication.UnicodeUTF8))
        self.logBtn.setText(QtGui.QApplication.translate("MainWindow", "Log", None, QtGui.QApplication.UnicodeUTF8))
        self.logBtn1.setText(QtGui.QApplication.translate("MainWindow", "Log", None, QtGui.QApplication.UnicodeUTF8))
        self.reloadModuleBtn.setText(QtGui.QApplication.translate("MainWindow", "Reload Libraries", None, QtGui.QApplication.UnicodeUTF8))
        self.quitBtn.setText(QtGui.QApplication.translate("MainWindow", "Quit ACQ4", None, QtGui.QApplication.UnicodeUTF8))

from lib.LogWindow import LogButton
