
from acq4.pyqtgraph.PlotWidget import *
from AnalysisPlotWidgetTemplate import *
import exceptions

class AnalysisPlotWidget(QtGui.QWidget):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.ui = Ui_AnalysisPlotWidgetTemplate()
        self.ui.setupUi(self)
        self.ui.xAxisCombo.insertItems(0, ['stim intensity', 'latency', 'slope', 'amplitude', 'firing rate'])
        self.ui.yAxisCombo.insertItems(0, ['stim intensity', 'latency', 'slope', 'amplitude', 'firing rate'])
        self.dataSource = None
        self.host = None
        
        QtCore.QObject.connect(self.ui.removeBtn, QtCore.SIGNAL('clicked()'), self.remove)
        QtCore.QObject.connect(self.ui.xAxisCombo, QtCore.SIGNAL('comboIndexChanged()'), self.updatePlot)
        QtCore.QObject.connect(self.ui.yAxisCombo, QtCore.SIGNAL('comboIndexChanged()'), self.updatePlot)
        
    def remove(self):
        #QtCore.QObject.disconnect(self.ui.removeBtn, 0,0,0)
        self.setParent(None)
        
    def updatePlot(self):
        pass
    
    def setDataSource(self, source):
        self.dataSource = source
        
    def setHost(self, host):
        self.host = host
        
    