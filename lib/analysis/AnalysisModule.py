# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui

class AnalysisModule(QtCore.Object):
    """
    Generic class for analysis modules. 
    The general purpose of a module is to perform a specific analysis task in any context
    A module may be used for any/all of:
        1. Read data as it is acquired and immediately display analysis
        2. Read data offline from disk and display analysis
        3. Read data (acquired or offline) and output analysis results that could
            - feed into another analysis module
            - be written to disk
            
    Modules have the following interface components:
        - processData()
            Perform the analysis task, display the results, and return the results
            Optionally, display can be disabled.
        - listElements()
            returns a dict describing gui widgets required to operate the module. 
            Some widgets will be created by the module (such as control panels)
            Other widgets may be provided externally, so the module can display results to existing widgets
            Widgets may be optional
        - getElement()
        - setElement()
        
    Notes:
        - Data may be fed in to the module piecewise or in a single chunk, thus we need a way to indicate that we have finished/started a chunk
        - Some modules will want to act like a filter (1-in : 1-out), while others will act as an aggregator (N-in : 1-out)
        - Aggregators may choose to accept multiple data types for input
        
    """
    
    def __init__(self, host):
        self.host = host
        
    def processData(self, data):
        pass
    
    def listElements(self):
        pass