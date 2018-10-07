# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
from acq4.analysis.AnalysisModule import AnalysisModule
from collections import OrderedDict
import acq4.pyqtgraph as pg
from acq4.util.metaarray import MetaArray
import numpy as np

from . import ctrlTemplate

class AtlasBuilder(AnalysisModule):
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        self.ctrlWidget = Qt.QWidget()
        self.ctrl = ctrlTemplate.Ui_Form()
        self.ctrl.setupUi(self.ctrlWidget)
        
        ## Setup basic GUI
        self._elements_ = OrderedDict([
            #('File Loader', {'type': 'fileInput', 'size': (200, 300), 'host': self}),
            #('IV Plot', {'type': 'plot', 'pos': ('right', 'File Loader'), 'size': (800, 300)}),
            #('Data Plot', {'type': 'plot', 'pos': ('bottom',), 'size': (800, 300)}),
            ('Canvas', {'type': 'canvas', 'size': (600,600)}),
            ('Ctrl', {'type': 'ctrl', 'object': self.ctrlWidget, 'pos': ('left', 'Canvas'), 'size': (200,600)}),
        ])
        self.initializeElements()


        

