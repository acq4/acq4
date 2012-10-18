import os
from lib.analysis.modules.EventDetector.EventDetector import EventDetector
from pyqtgraph.metaarray import MetaArray
import pyqtgraph as pg
import numpy as np


class RoiEventDetector(EventDetector):
    
    def __init__(self, host, flowchartDir=None, dbIdentity="RoiEventDetector"):
        if flowchartDir == None:
            flowchartDir = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "flowcharts")
            
        EventDetector.__init__(self, host, flowchartDir=flowchartDir, dbIdentity=dbIdentity)
        
        self.dbCtrl.storeBtn.setText("Save to csv")
        self.data = {} ## will be a nested dict of {'csvName':{'roiname': array()}} pairs
        
        self.fileLoader = self.getElement('File Loader', create=True)
        self.fileLoader.sigSelectedFileChanged.connect(self.selectedFileChanged)
        self.fileLoader.sigFileLoaded.connect(self.addVirtualFiles)
        
        
        
    def loadFileRequested(self, fhList):
        ## need to add handling of .csv files
        ## there are a couple of options:
        ##    1. pull the csv into one big array
        ##    2. pull each trace in the csv into a separate array, then hand each array to flowchart in turn (favored, i think)
        for fh in fhList:
            arr = fh.read()
            d = {}
            names = []
            time = arr['time(sec)']
            rois = self.getRoiInfo(fh)
            for f in arr.dtype.names:
                if 'time' not in f:
                    i = int(f[-3:])
                    d[f] = MetaArray(arr[f], info=[{'name':'time', 'units':'s', 'values':time},{'roiX':rois[i][0], 'roiY':rois[i][1], 'roiHeight':rois[i][2], 'roiWidth':rois[i][3]}])
                    names.append(f)
            self.data[fh.name(relativeTo=self.fileLoader.baseDir())] = d
            
        return True
    
    def addVirtualFiles(self, fh):
        name = fh.name(relativeTo=self.fileLoader.baseDir())
        self.fileLoader.addVirtualFiles(self.data[name].keys(), parentName=name)
    
    def storeClicked(self):
        ## save events table as csv (with info about which roi and which video csv file they're from)
        pass
    
    def selectedFileChanged(self, item):
        data = self.data[str(item.parent().text(0))][str(item.text(0))]
        self.flowchart.setInput(dataIn=data)
        
    def getRoiInfo(self, fh):
        """Return the corresponding roi information for the .csv file (fh)"""
        fn = fh.name()
        rf = open(fn[:-4]+'.roi', 'r')
        rois = np.loadtxt(rf)
        return rois
        