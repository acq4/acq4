from __future__ import print_function
import os, re, zipfile
from acq4.analysis.modules.EventDetector.EventDetector import EventDetector
from acq4.pyqtgraph.metaarray import MetaArray
import acq4.pyqtgraph as pg
import numpy as np
from . import CtrlTemplate
from acq4.util import Qt


class RoiEventDetector(EventDetector):
    
    def __init__(self, host, flowchartDir=None, dbIdentity="RoiEventDetector"):
        if flowchartDir == None:
            flowchartDir = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "flowcharts")
            
        EventDetector.__init__(self, host, flowchartDir=flowchartDir, dbIdentity=dbIdentity, dbCtrl=Ctrl)
        
        #self.dbCtrl.storeBtn.setText("Save to csv")
        self.dbCtrl.ui.storeBtn.clicked.connect(self.storeClicked)
        self.dbCtrl.ui.newFileBtn.clicked.connect(self.newStorageFileClicked)
        self.dbCtrl.ui.openFileBtn.clicked.connect(self.openStorageFileClicked)
        
        self.data = {} ## will be a nested dict of {'csvName':{'roiname': array()}} pairs
        self.storageFile = None
        self.paramStorageFile = None
        self.fcZip = None
        self.outputFields = None
        
        #print self.flowchart.nodes()
        if self.flowchart.nodes()['Input'].terminals.get('roi', None) is None:
            self.flowchart.addInput('roi', removable=True)
        
        self.fileLoader = self.getElement('File Loader', create=True)
        self.fileLoader.sigSelectedFileChanged.connect(self.selectedFileChanged)
        self.fileLoader.sigFileLoaded.connect(self.addVirtualFiles)
        
        
    def loadFileRequested(self, fhList):
        ##    -- pull each trace in the csv into a separate array, then hand each array to flowchart in turn
        for fh in fhList:
            arr = fh.read()
            d = {}
            names = []
            time = arr['time(sec)']
            rois = self.getRoiInfo(fh)
            for f in arr.dtype.names:
                if 'time' not in f:
                    i = int(f[-3:])
                    d[f] = MetaArray(arr[f], info=[{'name':'Time', 'units':'s', 'values':time},{'roiX':rois[i][0], 'roiY':rois[i][1], 'roiHeight':rois[i][2], 'roiWidth':rois[i][3], 'SourceFile':fh.name()}])
                    names.append(f)
            self.data[fh.name(relativeTo=self.fileLoader.baseDir())] = d
            
        return True
    
    def addVirtualFiles(self, fh):
        name = fh.name(relativeTo=self.fileLoader.baseDir())
        self.fileLoader.addVirtualFiles(list(self.data[name].keys()), parentName=name)
    
    def selectedFileChanged(self, item):
        data = self.data[str(item.parent().text(0))][str(item.text(0))]
        self.flowchart.setInput(dataIn=data, roi=str(item.text(0)))
        
    def getRoiInfo(self, fh):
        """Return the corresponding roi information for the .csv file (fh)"""
        fn = fh.name()
        rf = open(fn[:-4]+'.roi', 'r')
        rois = np.loadtxt(rf)
        return rois
    
    def storeClicked(self):
        ## save events table as csv (with info about which roi and which video csv file they're from)
        #print "store clicked."
        try:
            self.store()
            self.dbCtrl.ui.storeBtn.success('Stored!')
        except:
            self.dbCtrl.ui.storeBtn.failure('Error')
            raise
        
    def store(self):    
        if self.storageFile is None:
            raise Exception("No storage file is specified. Please open a storage file before storing events")
        
        if self.dbCtrl.getSaveMode() == 'roi':
            self.write(self.flowchart.output()['events'])
            self.writeParams()
            self.writeFcZip()
            
        elif self.dbCtrl.getSaveMode() == 'video':
            raise Exception('Saving whole video is not yet implemented')
        elif self.dbCtrl.getSaveMode() == 'all':
            raise Exception('Saving everything loaded is not yet implemented')
        
    def writeFcZip(self):
        info = self.flowchart.saveState()
        roi = str(self.fileLoader.ui.fileTree.currentItem().text(0))
        
        with zipfile.ZipFile(self.fcZip, 'a') as z:
            z.writestr(roi, str(info))
                
        
    
    def write(self, data):
        roi = str(self.fileLoader.ui.fileTree.currentItem().text(0))
        self.deleteOldROI(self.storageFile, roi)
        
        with open(self.storageFile, 'r+') as f:
            
            if data is not None:
                header = f.readline()
                fields = ','.join(data.dtype.names) + '\n'
                f.seek(0, 2)
                
                if header != fields: ## check to make sure the first line has the field names
                    f.write(fields)           
                    
                for d in data:
                    f.write(','.join([repr(x) for x in d])+'\n')
                    
            else: ## no events were found
                f.seek(0,2)
                item = self.fileLoader.ui.fileTree.currentItem()
                data = self.data[str(item.parent().text(0))][str(item.text(0))]
                roi = str(item.text(0))
                info = data.infoCopy()[-1]
                arr = np.zeros((1), dtype=[('roiX', int), ('roiY', int), ('roiWidth', int), ('roiHeight', int), ('SourceFile', '|S100'), ('roi', '|S10')])
                for k in ['roiX', 'roiY', 'roiWidth', 'roiHeight', 'SourceFile']:
                    arr[k] = info[k]
                arr['roi'] = roi
                
                f.write("0,0,0,0,0,0,0,0,0,0,0,0,0,"+','.join([repr(x) for x in arr[0]])+ '\n')
                
            f.write('\n')
            
    def deleteOldROI(self, filename, roi):
        ## read all old lines
        with open(self.storageFile, 'r') as f:
            lines = f.readlines()
            print("# of old lines:", len(lines))
            
        ## overwrite file, then write lines back in if they aren't ones we want to delete
        with open(self.storageFile, 'w') as f:
            if len(lines) < 1:
                return
            f.write(lines[0]) ## don't delete the header line
            for l in lines[1:]: 
                if roi not in l:
                    f.write(l)
                #else:
                    #print "not writing ", l
    
    def writeParams(self):
        nodes = self.flowchart.nodes()
        params = {}
        #excludes=['Input', 'Output', 'GatherInfo', 'NegativeEventFilter', 'EventListPlotter', 'ColumnJoin', 'ColumnSelect', 'Plot']
        includes = ['DenoiseFilter','LowPassBesselFilter','HighPassBesselFilter','DetrendFilter','HistogramDetrend','ExpDeconvolve','ThresholdEvents','CaEventFitter']
        
        ## get previously stored values
        if os.path.exists(self.paramStorageFile):
            prev = pg.configfile.readConfigFile(self.paramStorageFile)
        else:
            prev = {}
        
        for name in includes:
            node = nodes[name]
            d = {}
            if hasattr(node, 'ctrls'):
                for k, v in node.ctrls.items():
                    if type(v) == type(Qt.QCheckBox()):
                        d[k] = v.isChecked()
                    elif type(v) == type(Qt.QComboBox()):
                        d[k] = str(v.currentText())
                    elif type(v) in [type(Qt.QSpinBox()), type(Qt.QDoubleSpinBox()), type(pg.SpinBox())]:
                        d[k] = v.value()
                    else:
                        print("Not saving param %s for node %s because we don't know how to record value of type %s" %(k, name, str(type(v))))
            d['bypassed'] = node.isBypassed()
            params[name] = d
        
        item = self.fileLoader.ui.fileTree.currentItem()
        roi = str(item.text(0))
        
        ## replace or add previously stored values
        prev[roi] = params
        pg.configfile.writeConfigFile(prev, self.paramStorageFile)
        
    
    def newStorageFileClicked(self):
        self.fileDialog = pg.FileDialog(self.dbCtrl, "New Storage File", self.fileLoader.baseDir().name(), "CSV File (*.csv);;All Files (*.*)")
        self.fileDialog.setAcceptMode(Qt.QFileDialog.AcceptSave) 
        self.fileDialog.show()
        self.fileDialog.fileSelected.connect(self.createNewStorageFile)
        
    def createNewStorageFile(self, fileName): 
        fileName = str(fileName)
        if fileName is None:
            return
        
        #if self.storageFile is not None: ## close previous file, if there was one open
            #self.storageFile.close()
        #    self.outputFields = None
            
        self.storageFile = fileName  
        f = open(fileName, 'w')
        f.close()
        self.dbCtrl.setFileName(fileName)
        
        ## make paramStorageFile -- for storing easy-readable flowchart params
        if fileName[-4:] == '.csv':
            fn = fileName[:-4]
        else:
            fn = fileName
        self.paramStorageFile = fn + '.params'
        
        ## make fcZip -- for storing whole flowcharts
        self.fcZip = fn+'_flowchart.zip'
        z = zipfile.ZipFile(self.fcZip, 'w')
        z.close()
        
        
    def openStorageFileClicked(self):
            self.fileDialog = pg.FileDialog(self.dbCtrl, "Load Storage File", self.fileLoader.baseDir().name(), "CSV file (*.csv);;All Files (*.*)")
            #self.fileDialog.setFileMode(Qt.QFileDialog.AnyFile)
            self.fileDialog.show()
            self.fileDialog.fileSelected.connect(self.openStorageFile)
                
    def openStorageFile(self, fileName):
        fileName = str(fileName)
        if fileName == '':
            return 
        
        self.storageFile = fileName
        self.paramStorageFile = fileName[:-4]+'.params'
        self.fcZip = fileName[:-4]+'_flowchart.zip'
        
        self.dbCtrl.setFileName(fileName)
        
        
        #header = ''
        #line=None
        #while line != '':
            #line = self.storageFile.readline()
            #if 'SourceFile' in line: ## pick a name that is likely to be present in a header row -- I need a better method for this....
                #header = line
                
        #self.outputFields = re.split(',', header)
        
    
    #def close(self):
        ### called when module window is closed
        ### make sure save file is closed
        
        ##if self.storageFile is not None:
        ##    self.storageFile.close()
        #pass
    
        
        
class Ctrl(Qt.QWidget):
    def __init__(self, host, identity):
        Qt.QWidget.__init__(self)
        self.host = host
        
        self.ui = CtrlTemplate.Ui_Form()
        self.ui.setupUi(self)
        
    def setFileName(self, name):
        self.ui.fileLabel.setText(name)
        
    def getSaveMode(self):
        if self.ui.roiRadio.isChecked():
            return 'roi'
        elif self.ui.videoRadio.isChecked():
            return 'video'
        elif self.ui.everythingRadio.isChecked():
            return 'all'
        
        #self.layout = Qt.QVBoxLayout()
        #self.setLayout(self.layout)
        #self.dbgui = DatabaseGui.DatabaseGui(dm=host.dataManager(), tables={identity: 'EventDetector_events'})
        #self.storeBtn = pg.FeedbackButton("Store to DB")
        #self.storeBtn.clicked.connect(self.storeClicked)
        #self.layout.addWidget(self.dbgui)
        #self.layout.addWidget(self.storeBtn)
        #for name in ['getTableName', 'getDb']:
        #    setattr(self, name, getattr(self.dbgui, name))