from __future__ import print_function

from acq4.pyqtgraph.PlotWidget import *
from .AnalysisPlotWidgetTemplate import *
import exceptions

class AnalysisPlotWidget(Qt.QWidget):
    def __init__(self, parent=None):
        Qt.QWidget.__init__(self, parent)
        self.ui = Ui_AnalysisPlotWidgetTemplate()
        self.ui.setupUi(self)
        self.ui.xAxisCombo.insertItems(0, ['stim intensity', 'latency', 'slope', 'amplitude', 'firing rate'])
        self.ui.yAxisCombo.insertItems(0, ['stim intensity', 'latency', 'slope', 'amplitude', 'firing rate'])
        self.dataSource = None
        self.host = None
        
        Qt.QObject.connect(self.ui.removeBtn, Qt.SIGNAL('clicked()'), self.remove)
        Qt.QObject.connect(self.ui.xAxisCombo, Qt.SIGNAL('comboIndexChanged()'), self.updatePlot)
        Qt.QObject.connect(self.ui.yAxisCombo, Qt.SIGNAL('comboIndexChanged()'), self.updatePlot)
        
    def remove(self):
        #Qt.QObject.disconnect(self.ui.removeBtn, 0,0,0)
        self.setParent(None)
        
    def updatePlot(self):
        pass
    
    def setDataSource(self, source):
        self.dataSource = source
        
    def setHost(self, host):
        self.host = host
        
    