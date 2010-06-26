# -*- coding: utf-8 -*-


class FilterList(QtGui.QWidget):
    """This widget presents a customizable filter chain. The user (or program) can add and remove
    filters from the chain. Each filter defines its own widget of control parameters."""
    
    
    def __init__(self, *args):
        QtGui.QWidget.__init__(self, *args)
        self.filters = []
        
        
    def addFilter(self, filterType=None, opts=None):
        pass
    
    def removeFilter(self, index=None):
        pass
    
    def listFilters(self):
        pass
    
    def processData(self, data):
        pass
    
    def saveState(self):
        pass
    
    def restoreState(self, state):
        pass
    
    
    
class Filter:
    """Abstract filter class. All filters should subclass from here."""
    
    def __init__(self):
        self.ui = None           ## override these two parameters if you want to use the default implementations
        self.stateGroup = None   ## of getCtrlGui, saveState, and restoreState.
    
    def getCtrlGui(self):
        return self.ui
    
    def processData(self, data):
        pass
    
    def saveState(self):
        return self.stateGroup.state()
    
    def restoreState(self, state):
        self.stateGroup.setState(state)
    

class DownsampleFilter(Filter):
    pass

class SubsampleFilter(Filter):
    pass

class BesselFilter(Filter):
    pass

class ButterworthFilter(Filter):
    pass

class MeanFilter(Filter):
    pass

class MedianFilter(Filter):
    pass

class DenoiseFilter(Filter):
    pass

class GaussianFilter(Filter):
    pass

