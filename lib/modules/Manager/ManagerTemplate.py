# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ManagerTemplate.ui'
#
# Created: Sat Jan 09 12:14:41 2010
#      by: PyQt4 UI code generator 4.5.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(800, 600)
        self.centralwidget = QtGui.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.verticalLayout_2 = QtGui.QVBoxLayout(self.centralwidget)
        self.verticalLayout_2.setMargin(1)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.verticalLayout = QtGui.QVBoxLayout()
        self.verticalLayout.setObjectName("verticalLayout")
        self.groupBox = QtGui.QGroupBox(self.centralwidget)
        self.groupBox.setObjectName("groupBox")
        self.verticalLayout_3 = QtGui.QVBoxLayout(self.groupBox)
        self.verticalLayout_3.setMargin(1)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.configList = QtGui.QListWidget(self.groupBox)
        self.configList.setObjectName("configList")
        self.verticalLayout_3.addWidget(self.configList)
        self.loadConfigBtn = QtGui.QPushButton(self.groupBox)
        self.loadConfigBtn.setObjectName("loadConfigBtn")
        self.verticalLayout_3.addWidget(self.loadConfigBtn)
        self.verticalLayout.addWidget(self.groupBox)
        self.groupBox_2 = QtGui.QGroupBox(self.centralwidget)
        self.groupBox_2.setObjectName("groupBox_2")
        self.verticalLayout_4 = QtGui.QVBoxLayout(self.groupBox_2)
        self.verticalLayout_4.setMargin(1)
        self.verticalLayout_4.setObjectName("verticalLayout_4")
        self.moduleList = QtGui.QListWidget(self.groupBox_2)
        self.moduleList.setObjectName("moduleList")
        self.verticalLayout_4.addWidget(self.moduleList)
        self.loadModuleBtn = QtGui.QPushButton(self.groupBox_2)
        self.loadModuleBtn.setObjectName("loadModuleBtn")
        self.verticalLayout_4.addWidget(self.loadModuleBtn)
        self.verticalLayout.addWidget(self.groupBox_2)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem)
        self.quitBtn = QtGui.QPushButton(self.centralwidget)
        self.quitBtn.setObjectName("quitBtn")
        self.verticalLayout.addWidget(self.quitBtn)
        self.verticalLayout_2.addLayout(self.verticalLayout)
        MainWindow.setCentralWidget(self.centralwidget)
        self.statusBar = QtGui.QStatusBar(MainWindow)
        self.statusBar.setObjectName("statusBar")
        MainWindow.setStatusBar(self.statusBar)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QtGui.QApplication.translate("MainWindow", "ACQ4 Manager", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox.setTitle(QtGui.QApplication.translate("MainWindow", "Configuration", None, QtGui.QApplication.UnicodeUTF8))
        self.loadConfigBtn.setText(QtGui.QApplication.translate("MainWindow", "Load Configuration", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_2.setTitle(QtGui.QApplication.translate("MainWindow", "Modules", None, QtGui.QApplication.UnicodeUTF8))
        self.loadModuleBtn.setText(QtGui.QApplication.translate("MainWindow", "Load Module", None, QtGui.QApplication.UnicodeUTF8))
        self.quitBtn.setText(QtGui.QApplication.translate("MainWindow", "Quit ACQ4", None, QtGui.QApplication.UnicodeUTF8))

