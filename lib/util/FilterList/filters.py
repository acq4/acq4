# -*- coding: utf-8 -*-
    
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

