# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'DataManagerTemplate.ui'
#
# Created: Mon Apr 13 12:59:49 2009
#      by: PyQt4 UI code generator 4.4.4
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
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.horizontalLayout_2 = QtGui.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.label = QtGui.QLabel(self.centralwidget)
        self.label.setObjectName("label")
        self.horizontalLayout_2.addWidget(self.label)
        self.storageDirText = QtGui.QLineEdit(self.centralwidget)
        self.storageDirText.setObjectName("storageDirText")
        self.horizontalLayout_2.addWidget(self.storageDirText)
        self.selectDirBtn = QtGui.QPushButton(self.centralwidget)
        self.selectDirBtn.setObjectName("selectDirBtn")
        self.horizontalLayout_2.addWidget(self.selectDirBtn)
        self.verticalLayout_2.addLayout(self.horizontalLayout_2)
        self.splitter = QtGui.QSplitter(self.centralwidget)
        self.splitter.setOrientation(QtCore.Qt.Horizontal)
        self.splitter.setObjectName("splitter")
        self.fileTreeView = QtGui.QTreeView(self.splitter)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(3)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.fileTreeView.sizePolicy().hasHeightForWidth())
        self.fileTreeView.setSizePolicy(sizePolicy)
        self.fileTreeView.setObjectName("fileTreeView")
        self.fileDisplayTabs = QtGui.QTabWidget(self.splitter)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(8)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.fileDisplayTabs.sizePolicy().hasHeightForWidth())
        self.fileDisplayTabs.setSizePolicy(sizePolicy)
        self.fileDisplayTabs.setObjectName("fileDisplayTabs")
        self.tab = QtGui.QWidget()
        self.tab.setObjectName("tab")
        self.fileDisplayTabs.addTab(self.tab, "")
        self.tab_3 = QtGui.QWidget()
        self.tab_3.setObjectName("tab_3")
        self.fileDisplayTabs.addTab(self.tab_3, "")
        self.tab_2 = QtGui.QWidget()
        self.tab_2.setObjectName("tab_2")
        self.fileDisplayTabs.addTab(self.tab_2, "")
        self.verticalLayout_2.addWidget(self.splitter)
        MainWindow.setCentralWidget(self.centralwidget)
        self.dockWidget = QtGui.QDockWidget(MainWindow)
        self.dockWidget.setFloating(False)
        self.dockWidget.setFeatures(QtGui.QDockWidget.DockWidgetFloatable|QtGui.QDockWidget.DockWidgetMovable)
        self.dockWidget.setObjectName("dockWidget")
        self.dockWidgetContents = QtGui.QWidget()
        self.dockWidgetContents.setObjectName("dockWidgetContents")
        self.verticalLayout = QtGui.QVBoxLayout(self.dockWidgetContents)
        self.verticalLayout.setObjectName("verticalLayout")
        self.logDisplayText = QtGui.QTextEdit(self.dockWidgetContents)
        self.logDisplayText.setObjectName("logDisplayText")
        self.verticalLayout.addWidget(self.logDisplayText)
        self.logEntryText = QtGui.QLineEdit(self.dockWidgetContents)
        self.logEntryText.setObjectName("logEntryText")
        self.verticalLayout.addWidget(self.logEntryText)
        self.dockWidget.setWidget(self.dockWidgetContents)
        MainWindow.addDockWidget(QtCore.Qt.DockWidgetArea(8), self.dockWidget)

        self.retranslateUi(MainWindow)
        self.fileDisplayTabs.setCurrentIndex(0)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QtGui.QApplication.translate("MainWindow", "MainWindow", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("MainWindow", "Storage Directory:", None, QtGui.QApplication.UnicodeUTF8))
        self.selectDirBtn.setText(QtGui.QApplication.translate("MainWindow", "...", None, QtGui.QApplication.UnicodeUTF8))
        self.fileDisplayTabs.setTabText(self.fileDisplayTabs.indexOf(self.tab), QtGui.QApplication.translate("MainWindow", "Info", None, QtGui.QApplication.UnicodeUTF8))
        self.fileDisplayTabs.setTabText(self.fileDisplayTabs.indexOf(self.tab_3), QtGui.QApplication.translate("MainWindow", "Data", None, QtGui.QApplication.UnicodeUTF8))
        self.fileDisplayTabs.setTabText(self.fileDisplayTabs.indexOf(self.tab_2), QtGui.QApplication.translate("MainWindow", "Analysis", None, QtGui.QApplication.UnicodeUTF8))
        self.dockWidget.setWindowTitle(QtGui.QApplication.translate("MainWindow", "Log", None, QtGui.QApplication.UnicodeUTF8))

