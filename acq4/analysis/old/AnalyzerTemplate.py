# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/analysis/old/AnalyzerTemplate.ui'
#
# Created: Tue Dec 24 01:49:15 2013
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
        MainWindow.resize(721, 559)
        MainWindow.setDockNestingEnabled(True)
        self.centralwidget = QtGui.QWidget(MainWindow)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.centralwidget.sizePolicy().hasHeightForWidth())
        self.centralwidget.setSizePolicy(sizePolicy)
        self.centralwidget.setObjectName(_fromUtf8("centralwidget"))
        MainWindow.setCentralWidget(self.centralwidget)
        self.loaderDock = QtGui.QDockWidget(MainWindow)
        self.loaderDock.setFeatures(QtGui.QDockWidget.DockWidgetMovable)
        self.loaderDock.setObjectName(_fromUtf8("loaderDock"))
        self.dockWidgetContents = QtGui.QWidget()
        self.dockWidgetContents.setObjectName(_fromUtf8("dockWidgetContents"))
        self.loaderDock.setWidget(self.dockWidgetContents)
        MainWindow.addDockWidget(QtCore.Qt.DockWidgetArea(4), self.loaderDock)
        self.dataDock = QtGui.QDockWidget(MainWindow)
        self.dataDock.setFeatures(QtGui.QDockWidget.DockWidgetMovable)
        self.dataDock.setObjectName(_fromUtf8("dataDock"))
        self.dockWidgetContents_2 = QtGui.QWidget()
        self.dockWidgetContents_2.setObjectName(_fromUtf8("dockWidgetContents_2"))
        self.horizontalLayout = QtGui.QHBoxLayout(self.dockWidgetContents_2)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.verticalLayout = QtGui.QVBoxLayout()
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.loadDataBtn = QtGui.QPushButton(self.dockWidgetContents_2)
        self.loadDataBtn.setObjectName(_fromUtf8("loadDataBtn"))
        self.verticalLayout.addWidget(self.loadDataBtn)
        self.loadSequenceBtn = QtGui.QPushButton(self.dockWidgetContents_2)
        self.loadSequenceBtn.setObjectName(_fromUtf8("loadSequenceBtn"))
        self.verticalLayout.addWidget(self.loadSequenceBtn)
        self.loadSessionBtn = QtGui.QPushButton(self.dockWidgetContents_2)
        self.loadSessionBtn.setObjectName(_fromUtf8("loadSessionBtn"))
        self.verticalLayout.addWidget(self.loadSessionBtn)
        self.dataSourceCombo = InterfaceCombo(self.dockWidgetContents_2)
        self.dataSourceCombo.setObjectName(_fromUtf8("dataSourceCombo"))
        self.dataSourceCombo.addItem(_fromUtf8(""))
        self.verticalLayout.addWidget(self.dataSourceCombo)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem)
        self.recompSelectedBtn = QtGui.QPushButton(self.dockWidgetContents_2)
        self.recompSelectedBtn.setObjectName(_fromUtf8("recompSelectedBtn"))
        self.verticalLayout.addWidget(self.recompSelectedBtn)
        self.recompAllBtn = QtGui.QPushButton(self.dockWidgetContents_2)
        self.recompAllBtn.setObjectName(_fromUtf8("recompAllBtn"))
        self.verticalLayout.addWidget(self.recompAllBtn)
        spacerItem1 = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem1)
        self.saveSelectedBtn = QtGui.QPushButton(self.dockWidgetContents_2)
        self.saveSelectedBtn.setObjectName(_fromUtf8("saveSelectedBtn"))
        self.verticalLayout.addWidget(self.saveSelectedBtn)
        self.saveAllBtn = QtGui.QPushButton(self.dockWidgetContents_2)
        self.saveAllBtn.setObjectName(_fromUtf8("saveAllBtn"))
        self.verticalLayout.addWidget(self.saveAllBtn)
        self.horizontalLayout.addLayout(self.verticalLayout)
        self.dataTree = QtGui.QTreeWidget(self.dockWidgetContents_2)
        self.dataTree.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.dataTree.setObjectName(_fromUtf8("dataTree"))
        self.dataTree.headerItem().setText(0, _fromUtf8("1"))
        self.horizontalLayout.addWidget(self.dataTree)
        self.dataDock.setWidget(self.dockWidgetContents_2)
        MainWindow.addDockWidget(QtCore.Qt.DockWidgetArea(4), self.dataDock)
        self.dockWidget_3 = QtGui.QDockWidget(MainWindow)
        self.dockWidget_3.setFeatures(QtGui.QDockWidget.DockWidgetMovable)
        self.dockWidget_3.setObjectName(_fromUtf8("dockWidget_3"))
        self.dockWidgetContents_3 = QtGui.QWidget()
        self.dockWidgetContents_3.setObjectName(_fromUtf8("dockWidgetContents_3"))
        self.gridLayout = QtGui.QGridLayout(self.dockWidgetContents_3)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label = QtGui.QLabel(self.dockWidgetContents_3)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.dockList = QtGui.QListWidget(self.dockWidgetContents_3)
        self.dockList.setObjectName(_fromUtf8("dockList"))
        self.gridLayout.addWidget(self.dockList, 0, 1, 6, 1)
        self.addOutputBtn = QtGui.QPushButton(self.dockWidgetContents_3)
        self.addOutputBtn.setObjectName(_fromUtf8("addOutputBtn"))
        self.gridLayout.addWidget(self.addOutputBtn, 1, 0, 1, 1)
        self.addPlotBtn = QtGui.QPushButton(self.dockWidgetContents_3)
        self.addPlotBtn.setObjectName(_fromUtf8("addPlotBtn"))
        self.gridLayout.addWidget(self.addPlotBtn, 2, 0, 1, 1)
        self.addCanvasBtn = QtGui.QPushButton(self.dockWidgetContents_3)
        self.addCanvasBtn.setObjectName(_fromUtf8("addCanvasBtn"))
        self.gridLayout.addWidget(self.addCanvasBtn, 3, 0, 1, 1)
        self.addTableBtn = QtGui.QPushButton(self.dockWidgetContents_3)
        self.addTableBtn.setObjectName(_fromUtf8("addTableBtn"))
        self.gridLayout.addWidget(self.addTableBtn, 4, 0, 1, 1)
        spacerItem2 = QtGui.QSpacerItem(20, 46, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem2, 5, 0, 2, 1)
        self.removeDockBtn = QtGui.QPushButton(self.dockWidgetContents_3)
        self.removeDockBtn.setObjectName(_fromUtf8("removeDockBtn"))
        self.gridLayout.addWidget(self.removeDockBtn, 6, 1, 1, 1)
        self.dockWidget_3.setWidget(self.dockWidgetContents_3)
        MainWindow.addDockWidget(QtCore.Qt.DockWidgetArea(4), self.dockWidget_3)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(_translate("MainWindow", "Analysis", None))
        self.loaderDock.setWindowTitle(_translate("MainWindow", "Loader", None))
        self.dataDock.setWindowTitle(_translate("MainWindow", "Data", None))
        self.loadDataBtn.setText(_translate("MainWindow", "Load Data", None))
        self.loadSequenceBtn.setText(_translate("MainWindow", "Load Sequence", None))
        self.loadSessionBtn.setText(_translate("MainWindow", "Load Session", None))
        self.dataSourceCombo.setItemText(0, _translate("MainWindow", "Select source..", None))
        self.recompSelectedBtn.setText(_translate("MainWindow", "Recompute Selected", None))
        self.recompAllBtn.setText(_translate("MainWindow", "Recompute All", None))
        self.saveSelectedBtn.setText(_translate("MainWindow", "Save Selected", None))
        self.saveAllBtn.setText(_translate("MainWindow", "Save Session", None))
        self.dockWidget_3.setWindowTitle(_translate("MainWindow", "Components", None))
        self.label.setText(_translate("MainWindow", "Add:", None))
        self.addOutputBtn.setText(_translate("MainWindow", "Output", None))
        self.addPlotBtn.setText(_translate("MainWindow", "Plot", None))
        self.addCanvasBtn.setText(_translate("MainWindow", "Canvas", None))
        self.addTableBtn.setText(_translate("MainWindow", "Table", None))
        self.removeDockBtn.setText(_translate("MainWindow", "Remove", None))

from acq4.util.InterfaceCombo import InterfaceCombo
