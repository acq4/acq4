# -*- coding: utf-8 -*-
from __future__ import print_function

from collections import OrderedDict

from acq4.analysis.AnalysisModule import AnalysisModule
from acq4.util import Qt

Ui_Form = Qt.importTemplate('.ctrlTemplate')


class AtlasBuilder(AnalysisModule):
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        self.ctrlWidget = Qt.QWidget()
        self.ctrl = Ui_Form()
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


        

