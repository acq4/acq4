# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ROPing.ui'
#
# Created: Sat Aug 23 12:38:38 2008
#      by: PyQt4 UI code generator 4.3.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(QtCore.QSize(QtCore.QRect(0,0,785,532).size()).expandedTo(MainWindow.minimumSizeHint()))

        self.centralwidget = QtGui.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")

        self.gridlayout = QtGui.QGridLayout(self.centralwidget)
        self.gridlayout.setObjectName("gridlayout")

        self.splitter = QtGui.QSplitter(self.centralwidget)
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter.setObjectName("splitter")

        self.imageWidget = QtGui.QWidget(self.splitter)
        self.imageWidget.setObjectName("imageWidget")

        self.plotWidget = QtGui.QWidget(self.splitter)
        self.plotWidget.setObjectName("plotWidget")
        self.gridlayout.addWidget(self.splitter,0,0,1,1)
        MainWindow.setCentralWidget(self.centralwidget)

        self.menubar = QtGui.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0,0,785,31))
        self.menubar.setObjectName("menubar")
        MainWindow.setMenuBar(self.menubar)

        self.statusbar = QtGui.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.dockWidget = QtGui.QDockWidget(MainWindow)
        self.dockWidget.setFloating(False)
        self.dockWidget.setFeatures(QtGui.QDockWidget.DockWidgetFloatable|QtGui.QDockWidget.DockWidgetMovable|QtGui.QDockWidget.DockWidgetVerticalTitleBar|QtGui.QDockWidget.NoDockWidgetFeatures)
        self.dockWidget.setObjectName("dockWidget")

        self.dockWidgetContents = QtGui.QWidget(self.dockWidget)
        self.dockWidgetContents.setObjectName("dockWidgetContents")

        self.gridlayout1 = QtGui.QGridLayout(self.dockWidgetContents)
        self.gridlayout1.setObjectName("gridlayout1")

        self.label = QtGui.QLabel(self.dockWidgetContents)
        self.label.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label.setObjectName("label")
        self.gridlayout1.addWidget(self.label,0,1,1,1)

        self.listCameraChannel = QtGui.QComboBox(self.dockWidgetContents)
        self.listCameraChannel.setObjectName("listCameraChannel")
        self.gridlayout1.addWidget(self.listCameraChannel,0,2,1,1)

        self.label_3 = QtGui.QLabel(self.dockWidgetContents)
        self.label_3.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_3.setObjectName("label_3")
        self.gridlayout1.addWidget(self.label_3,0,3,1,1)

        self.spinSampleRate = QtGui.QDoubleSpinBox(self.dockWidgetContents)
        self.spinSampleRate.setMaximum(999999999.0)
        self.spinSampleRate.setProperty("value",QtCore.QVariant(40000.0))
        self.spinSampleRate.setObjectName("spinSampleRate")
        self.gridlayout1.addWidget(self.spinSampleRate,0,4,1,1)

        self.label_2 = QtGui.QLabel(self.dockWidgetContents)
        self.label_2.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_2.setObjectName("label_2")
        self.gridlayout1.addWidget(self.label_2,1,1,1,1)

        self.listCellChannel = QtGui.QComboBox(self.dockWidgetContents)
        self.listCellChannel.setObjectName("listCellChannel")
        self.gridlayout1.addWidget(self.listCellChannel,1,2,1,1)

        self.label_4 = QtGui.QLabel(self.dockWidgetContents)
        self.label_4.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_4.setObjectName("label_4")
        self.gridlayout1.addWidget(self.label_4,1,3,1,1)

        self.spinInputScale = QtGui.QDoubleSpinBox(self.dockWidgetContents)
        self.spinInputScale.setProperty("value",QtCore.QVariant(1.0))
        self.spinInputScale.setObjectName("spinInputScale")
        self.gridlayout1.addWidget(self.spinInputScale,1,4,1,1)

        self.btnAcquire = QtGui.QToolButton(self.dockWidgetContents)
        self.btnAcquire.setCheckable(True)
        self.btnAcquire.setObjectName("btnAcquire")
        self.gridlayout1.addWidget(self.btnAcquire,0,0,1,1)

        self.btnSnap = QtGui.QToolButton(self.dockWidgetContents)
        self.btnSnap.setObjectName("btnSnap")
        self.gridlayout1.addWidget(self.btnSnap,1,0,1,1)

        self.label_5 = QtGui.QLabel(self.dockWidgetContents)
        self.label_5.setObjectName("label_5")
        self.gridlayout1.addWidget(self.label_5,0,5,1,1)

        self.spinDownsample = QtGui.QSpinBox(self.dockWidgetContents)
        self.spinDownsample.setMinimum(1)
        self.spinDownsample.setMaximum(10000)
        self.spinDownsample.setProperty("value",QtCore.QVariant(16))
        self.spinDownsample.setObjectName("spinDownsample")
        self.gridlayout1.addWidget(self.spinDownsample,0,6,1,1)
        self.dockWidget.setWidget(self.dockWidgetContents)
        MainWindow.addDockWidget(QtCore.Qt.DockWidgetArea(4),self.dockWidget)

        self.dockWidget_2 = QtGui.QDockWidget(MainWindow)
        self.dockWidget_2.setFeatures(QtGui.QDockWidget.DockWidgetFloatable|QtGui.QDockWidget.DockWidgetMovable|QtGui.QDockWidget.DockWidgetVerticalTitleBar|QtGui.QDockWidget.NoDockWidgetFeatures)
        self.dockWidget_2.setObjectName("dockWidget_2")

        self.dockWidgetContents_2 = QtGui.QWidget(self.dockWidget_2)
        self.dockWidgetContents_2.setObjectName("dockWidgetContents_2")

        self.gridlayout2 = QtGui.QGridLayout(self.dockWidgetContents_2)
        self.gridlayout2.setObjectName("gridlayout2")

        self.label_6 = QtGui.QLabel(self.dockWidgetContents_2)
        self.label_6.setObjectName("label_6")
        self.gridlayout2.addWidget(self.label_6,0,0,1,1)

        self.spinPspTau = QtGui.QDoubleSpinBox(self.dockWidgetContents_2)
        self.spinPspTau.setDecimals(2)
        self.spinPspTau.setMaximum(1000.0)
        self.spinPspTau.setSingleStep(1.0)
        self.spinPspTau.setProperty("value",QtCore.QVariant(1.0))
        self.spinPspTau.setObjectName("spinPspTau")
        self.gridlayout2.addWidget(self.spinPspTau,0,1,1,1)

        self.label_7 = QtGui.QLabel(self.dockWidgetContents_2)
        self.label_7.setObjectName("label_7")
        self.gridlayout2.addWidget(self.label_7,1,0,1,1)

        self.spinPspTolerance = QtGui.QDoubleSpinBox(self.dockWidgetContents_2)
        self.spinPspTolerance.setSingleStep(0.1)
        self.spinPspTolerance.setProperty("value",QtCore.QVariant(1.7))
        self.spinPspTolerance.setObjectName("spinPspTolerance")
        self.gridlayout2.addWidget(self.spinPspTolerance,1,1,1,1)
        self.dockWidget_2.setWidget(self.dockWidgetContents_2)
        MainWindow.addDockWidget(QtCore.Qt.DockWidgetArea(8),self.dockWidget_2)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QtGui.QApplication.translate("MainWindow", "MainWindow", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("MainWindow", "Camera Channel", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("MainWindow", "Sample Rate", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("MainWindow", "Cell Channel", None, QtGui.QApplication.UnicodeUTF8))
        self.label_4.setText(QtGui.QApplication.translate("MainWindow", "Scale", None, QtGui.QApplication.UnicodeUTF8))
        self.btnAcquire.setText(QtGui.QApplication.translate("MainWindow", "Acquire", None, QtGui.QApplication.UnicodeUTF8))
        self.btnSnap.setText(QtGui.QApplication.translate("MainWindow", "Snap", None, QtGui.QApplication.UnicodeUTF8))
        self.label_5.setText(QtGui.QApplication.translate("MainWindow", "Downsample", None, QtGui.QApplication.UnicodeUTF8))
        self.label_6.setText(QtGui.QApplication.translate("MainWindow", "PSP Tau (ms)", None, QtGui.QApplication.UnicodeUTF8))
        self.label_7.setText(QtGui.QApplication.translate("MainWindow", "PSP Tolerance", None, QtGui.QApplication.UnicodeUTF8))

