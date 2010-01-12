# -*- coding: utf-8 -*-

class SpinBox(QtGui.QAbstractSpinBox):
    """QSpinBox widget on steroids. Allows selection of numerical value, with extra features:
      - Int/float values with linear, log, and decimal stepping (1-9,10-90,100-900,etc.)
      - Option for unbounded values
      - Unit power of 3 labels (m, k, M, G, etc.)
      - Sparse tables--list of acceptable values
      - Support for sequence variables (for ProtocolRunner)
      - Delay to set; allows multiple consecutive changes to generate only one change signal
    """
    
    
    