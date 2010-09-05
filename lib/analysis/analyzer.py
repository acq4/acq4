# -*- coding: utf-8 -*-

from Manager import *
from AnalyzerTemplate import *
from flowchart import *

class Analyzer(QtGui.QWidget):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.ui  =  AnalyzerTemplate()
        self.ui.setupUi(self)
        
        self.flowchart = Flowchart()
        self.ui.flowchartLayout.addWidget(self.flowchart.widget())
        self.flowchart.addInput("dataIn")
        
        QtCore.QObject.connect(self.ui.loadDataBtn, QtCore.SIGNAL("clicked()") self.loadData)
        QtCore.QObject.connect(self.ui.addOutputBtn, QtCore.SIGNAL("clicked()") self.addOutput)

    def addOutput(self):
        self.flowchart.addOutput()
        
    def loadData(self):
        data = Manager.getManager().currentFile.read()
        self.flowchart.setData(dataIn=data)
        
        




