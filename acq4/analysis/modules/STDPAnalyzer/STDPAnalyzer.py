
from PyQt4 import QtGui, QtCore
from acq4.analysis.AnalysisModule import AnalysisModule
import STDPControlTemplate

class STDPAnalyzer(AnalysisModule):

	dbIdentity = "STDPAnalyzer"

	def __init__(self, host):
        AnalysisModule.__init__(self, host)

        self.ctrlWidget = QtGui.QWidget()
        self.ctrl = STDPControlTemplate.Ui_Form()
        self.ctrl.setupUi(self.ctrlWidget)
       
        self.plots = QtGui.QWidget()
        self.plotLayout = QtGui.QVBoxLayout()
        self.plot.setLayout(self.plotLayout)

        self._elements_ = OrderedDict([
            ('File Loader', {'type':'fileInput', 'host':self, 'showFileTree':True, 'size': (160, 100)}),
            ('Control Panel', {'type':'ctrl', 'object': self.ctrlWidget, 'pos':('below', 'File Loader'),'size': (160, 400)}),
            ('Plots', {'type': 'ctrl', 'object': self.plots, 'pos': ('right', 'File Loader'), 'size': (400, 700)})
        ])
          
        ## Plot for displaying when traces were recorded. Used to choose which traces are displayed  
        self.exptPlot = pg.PlotWidget()
        self.plotLayout.addWidget(self.exptPlot)
        self.label_up(self.exptPlot, 'Time (s)', '', 'Experiment Timecourse')

        ## Plot that displays the traces.
        self.tracesPlot = pg.PlotWidget()
        self.plotLayout.addWidget(self.tracesPlot)
        self.label_up(self.tracesPlot, 'Time (s)', 'Voltage', 'Data')

        self.plasticityPlot = pg.PlotWidget()
        self.gridLayout.addWidget(self.plasticityPlot)
        self.label_up(self.plasticityPlot, 'Time (s)', 'Slope' 'Plasticity')

        self.RMP_plot = pg.PlotWidget()
        self.plotLayout.addWidget(self.RMP_plot)
        self.label_up(self.RMP_plot, 'Time (s)', 'V', 'Resting Membrane Potential')

        self.RI_Plot = pg.PlotWidget()
        self.gridLayout.addWidget(self.RI_Plot)
        self.label_up(self.RI_Plot, 'Time (s)', 'Resistance', 'Input Resistance')

        for row, s in enumerate([10, 30, 20, 10, 10]):
            self.gridLayout.setRowStretch(row, s)

    @staticmethod
    def label_up(plot, xtext, ytext, title):
        """helper to label up the plot"""
        plot.setLabel('bottom', xtext)
        plot.setLabel('left', ytext)
        plot.setTitle(title)
