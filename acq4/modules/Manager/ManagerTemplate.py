# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/modules/Manager/ManagerTemplate.ui'
#
# Created: Thu Jan  2 16:39:23 2014
#      by: PyQt4 UI code generator 4.10
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
        self.verticalLayout.addWidget(self.groupBox_2)
        self.logBtn = LogButton(self.centralwidget)
        self.logBtn.setObjectName(_fromUtf8("logBtn"))
        self.verticalLayout.addWidget(self.logBtn)
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
        MainWindow.setWindowTitle(_translate("MainWindow", "ACQ4 Manager", None))
        self.groupBox.setTitle(_translate("MainWindow", "Configuration", None))
        self.loadConfigBtn.setText(_translate("MainWindow", "Load Configuration", None))
        self.groupBox_2.setTitle(_translate("MainWindow", "Modules", None))
        self.loadModuleBtn.setText(_translate("MainWindow", "Load Module", None))
        self.logBtn.setText(_translate("MainWindow", "Log", None))
        self.reloadModuleBtn.setText(_translate("MainWindow", "Reload Libraries", None))
        self.quitBtn.setText(_translate("MainWindow", "Quit ACQ4", None))

from acq4.LogWindow import LogButton
