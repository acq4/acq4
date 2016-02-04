from acq4.analysis.AnalysisModule import AnalysisModule
from acq4.util.DatabaseGui.DatabaseGui import DatabaseGui
from collections import OrderedDict

class TimecourseAnalyzer(AnalysisModule):

    """A generic module for analyzing features of repeated traces over time."""

    dbIdentity = "TimecourseAnalyzer"

    def __init__(self, host):
        AnalysisModule.__init__(self, host)

        tables = OrderedDict([
            (self.dbIdentity+'.trials', 'TimecourseAnalyzer_Trials')
        ])
        self.dbGui = DatabaseGui(dm=self.dataManager(), tables=tables)

        self._elements_ = OrderedDict([
            ('Database', {'type':'ctrl', 'object': self.dbGui, 'size':(100,100)}),
            ('AnalysisRegionControl', {'type':'parameterTree', 'pos':('above', 'Database'),'size': (100, 400)}),
            ('File Loader', {'type':'fileInput', 'size': (100, 100), 'pos':('above', 'AnalysisRegionControl')}),
            ('Experiment Plot', {'type':'plot', 'pos':('right', 'File Loader'), 'size':(400, 100)}),
            ('Traces Plot', {'type': 'plot', 'pos':('bottom', 'Experiment Plot'), 'size':(400,100)}),
            ('Analysis Plots', {'type':'graphicsLayout', 'pos':('bottom', 'Traces Plot'), 'size': (400,100)})
        ])
        self.initializeElements()