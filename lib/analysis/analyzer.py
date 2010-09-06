# -*- coding: utf-8 -*-

from lib.Manager import getManager
from AnalyzerTemplate import *
from flowchart import *
from PyQt4 import QtGui, QtCore

class Analyzer(QtGui.QWidget):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.ui  =  Ui_Form()
        self.ui.setupUi(self)
        
        self.flowchart = Flowchart()
        self.ui.flowchartLayout.addWidget(self.flowchart.widget())
        self.flowchart.addInput("dataIn")
        
        QtCore.QObject.connect(self.ui.loadDataBtn, QtCore.SIGNAL("clicked()"), self.loadData)
        QtCore.QObject.connect(self.ui.addOutputBtn, QtCore.SIGNAL("clicked()"), self.addOutput)

    def addOutput(self):
        self.flowchart.addOutput()
        
    def loadData(self):
        data = getManager().currentFile
        self.flowchart.setInput(dataIn=data)
        


class AnalyzerWindow(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.ui = Analyzer()
        self.setCentralWidget(self.ui)
        self.resize(800,600)
        self.show()