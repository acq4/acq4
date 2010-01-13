# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore


class SpinBox(QtGui.QAbstractSpinBox):
    """QSpinBox widget on steroids. Allows selection of numerical value, with extra features:
      - Int/float values with linear, log, and decimal stepping (1-9,10-90,100-900,etc.)
      - Option for unbounded values
      - Unit power of 3 labels (m, k, M, G, etc.)
      - Sparse tables--list of acceptable values
      - Support for sequence variables (for ProtocolRunner)
      - Delay to set; allows multiple consecutive changes to generate only one change signal
    """
    
    def __init__(self, *args):
        QtGui.QAbstractSpinBox.__init__(self)
        self.opts = {
            'dtype': int,
            'bounds': [None, None],
            'default': 0,
            'stepSize': 1,
            'scale': 1,
            'log': False,
            'dec': False,
            'suffix': '',
            'unitScale': False,
            'delay': False
        }
        
    ##lots of config options, just gonna stuff 'em all in here rather than do the get/set crap.
    def setOpts(self, **opts):
        pass
    
    def fixup(self):
        pass
    
    