# -*- coding: utf-8 -*-

from acq4.Manager import getManager
from AnalyzerTemplate import *
from acq4.util.flowchart import *
from PyQt4 import QtGui, QtCore
from acq4.util.DirTreeWidget import DirTreeLoader
from acq4.pyqtgraph.PlotWidget import *
from acq4.util.Canvas import *
import acq4.util.configfile as configfile
import pickle
from acq4.util.DataManager import getHandle

class Analyzer(QtGui.QMainWindow):
    def __init__(self, protoDir, parent=None):
        self.protoDir = protoDir
        QtGui.QMainWindow.__init__(self, parent)
        self.ui  =  Ui_MainWindow()
        self.ui.setupUi(self)
        
        self.flowchart = Flowchart()
        self.setCentralWidget(self.flowchart.widget())
        #self.ui.chartDock1.setWidget(self.flowchart.widget())
        self.flowchart.addInput("dataIn")

        self.ui.dataSourceCombo.setTypes(['dataSource'])

        #self.flowchart2 = Flowchart()
        #self.ui.chartDock2.setWidget(self.flowchart2.widget())
        #self.flowchart2.addInput("dataIn")
        
        self.loader = DirTreeLoader(protoDir)
        self.loader.save = self.saveProtocol
        self.loader.new = self.newProtocol
        self.loader.load = self.loadProtocol
        self.ui.loaderDock.setWidget(self.loader)
        
        self.dockItems = {}
        self.data = []   ## Raw data loaded
        self.results = {}  ## Processed output
        
        self.dataSource = None
        
        QtCore.QObject.connect(self.ui.dataSourceCombo, QtCore.SIGNAL("currentIndexChanged(int)"), self.setDataSource)
        QtCore.QObject.connect(self.ui.loadDataBtn, QtCore.SIGNAL("clicked()"), self.loadData)
        QtCore.QObject.connect(self.ui.loadSequenceBtn, QtCore.SIGNAL("clicked()"), self.loadSequence)
        QtCore.QObject.connect(self.ui.loadSessionBtn, QtCore.SIGNAL("clicked()"), self.loadSession)
        QtCore.QObject.connect(self.ui.recompSelectedBtn, QtCore.SIGNAL("clicked()"), self.recomputeSelected)
        QtCore.QObject.connect(self.ui.recompAllBtn, QtCore.SIGNAL("clicked()"), self.recomputeAll)
        QtCore.QObject.connect(self.ui.saveAllBtn, QtCore.SIGNAL("clicked()"), self.saveAll)
        QtCore.QObject.connect(self.ui.addOutputBtn, QtCore.SIGNAL("clicked()"), self.addOutput)
        QtCore.QObject.connect(self.ui.addPlotBtn, QtCore.SIGNAL("clicked()"), self.addPlot)
        QtCore.QObject.connect(self.ui.addCanvasBtn, QtCore.SIGNAL("clicked()"), self.addCanvas)
        QtCore.QObject.connect(self.ui.addTableBtn, QtCore.SIGNAL("clicked()"), self.addTable)
        QtCore.QObject.connect(self.ui.removeDockBtn, QtCore.SIGNAL("clicked()"), self.removeSelected)
        QtCore.QObject.connect(self.ui.dataTree, QtCore.SIGNAL("currentItemChanged(QTreeWidgetItem*,QTreeWidgetItem*)"), self.dataSelected)

        QtCore.QObject.connect(self.flowchart.outputNode, QtCore.SIGNAL("terminalRenamed"), self.outputRenamed)
        i = 0
        while True:
            name = "Analyzer-%d"%i
            if getManager().declareInterface(name, ['dataSource'], self):
                break
            i += 1
        self.setWindowTitle(name)
        
        
        self.resize(1200,800)
        self.show()
        
    def setDataSource(self):
        if self.dataSource is not None:
            QtCore.QObject.disconnect(self.dataSource, QtCore.SIGNAL("resultsChanged"), self.dataSourceChanged)
        source = self.ui.dataSourceCombo.getSelectedObj()
        self.dataSource = source
        if source is None:
            return
        QtCore.QObject.connect(source, QtCore.SIGNAL("resultsChanged"), self.dataSourceChanged)
        #print "connected to", source
        self.dataSourceChanged()
    
    def dumpProtocol(self):
        state = {'docks': {}}
        for name, d in self.dockItems.iteritems():
            s = {'type': d['type']}
            if 'widget' in d and hasattr(d['widget'], 'saveState'):
                s['state'] = d['widget'].saveState()
            else:
                s['state'] = {}
            state['docks'][name] = s
        state['window'] = str(self.saveState().toPercentEncoding())
        state['flowchart'] = self.flowchart.saveState()
        return state

    def saveProtocol(self, handle):
        state = self.dumpProtocol()
        configfile.writeConfigFile(state, handle.name())
        return True
        
    def newProtocol(self):
        for name, d in self.dockItems.iteritems():
            self.removeDockWidget(d['dock'])
            d['dock'].setObjectName('')
        self.ui.dockList.clear()
        self.flowchart.clear()
        self.flowchart.addInput('dataIn')
        self.dockItems = {}
        
        return True
    
    def loadProtocol(self, handle):
        self.newProtocol()
        state = configfile.readConfigFile(handle.name())
        return self.restoreProtocol(state)
        
    def restoreProtocol(self, state):
        ## restore flowchart
        self.flowchart.restoreState(state['flowchart'])
        
        ## recreate docks
        for name, d in state['docks'].iteritems():
            fn = getattr(self, 'add'+d['type'])
            fn(name, d.get('state', None))
        
        ## restore dock positions
        self.restoreState(QtCore.QByteArray.fromPercentEncoding(state['window']))
        
        return True
        

    def removeSelected(self):
        sel = self.ui.dockList.currentItem()
        if sel is None:
            return
        name = str(sel.text())
        self.ui.dockList.takeItem(self.ui.dockList.currentRow())
        
        d = self.dockItems[name]
        if d['type'] == 'Output':
            self.flowchart.removeTerminal(name)
        elif d['type'] == 'Plot':
            d['widget'].quit()
            
        if 'node' in d:
            self.flowchart.removeNode(d['node'])
            
        if 'dock' in d:
            self.removeDockWidget(d['dock'])
            
        del self.dockItems[name]
        
    def outputRenamed(self, term, oldName):
        name = term.name()
        d = self.dockItems[oldName]
        del self.dockItems[oldName]
        self.dockItems[name] = d
        
        item = d['listItem']
        item.setText(name)
        
        

    def addOutput(self):
        term = self.flowchart.addOutput(renamable=True)
        name = term.name()
        item = ListItem(name, None)
        self.dockItems[name] = {'type': 'Output', 'listItem': item, 'term': self.flowchart.internalTerminal(term)}
        self.ui.dockList.addItem(item)
        
    def loadData(self):
        data = getManager().currentFile
        self.flowchart.setInput(dataIn=data)
        
    def loadSequence(self, data=None):
        if data is None:
            data = getManager().currentFile
        item = QtGui.QTreeWidgetItem([data.shortName()])
        item.data = data
        self.ui.dataTree.addTopLevelItem(item)
        self.data.append(data)
        for sub in data.subDirs():
            try:
                int(sub)
            except:
                continue
            subd = data[sub]
            i2 = QtGui.QTreeWidgetItem([sub])
            i2.data = subd
            item.addChild(i2)

    def dataSourceChanged(self):
        print "data source changed!"
        result = self.dataSource.results
        self.flowchart.setInput(dataIn=result)

    def clearData(self):
        self.ui.dataTree.clear()
        self.data = []
        

    def dataSelected(self, current, old):
        if current is None:
            return
        if current.data in self.data:
            return
        self.flowchart.setInput(dataIn=current.data)
        #print "set data", current.data
        
    def recomputeAll(self):
        inputs = []
        for d in self.data:
            inputs.extend([d[sd] for sd in d.subDirs() if sd[0] in '0123456789'])
        self.recompute(inputs)
        
    def recomputeSelected(self):
        items = self.ui.dataTree.selectedItems()
        self.recompute([i.data for i in items])
        
    def recompute(self, inputs):
        progressDlg = QtGui.QProgressDialog("Processing:", 0, len(inputs))
        progressDlg.setWindowModality(QtCore.Qt.WindowModal)
        for i in range(len(inputs)):
            inp = inputs[i]
            progressDlg.setLabelText("Processing: " + inp.name())
            progressDlg.setValue(i)
            QtGui.QApplication.instance().processEvents()
            if progressDlg.wasCanceled():
                progressDlg.setValue(len(inputs))
                break
            out = self.flowchart.process(dataIn=inp)
            self.results[inp] = out
            
        progressDlg.setValue(len(inputs))
        self.emit(QtCore.SIGNAL('resultsChanged'))
        #self.flowchart2.dataIn.setValue(self.results)
                    
    def saveAll(self, saveFile=None):
        saveDir = self.data[0].name()
        proto = self.loader.currentFile
        if proto is None:
            protoName = "Analysis.pk"
        else:
            protoName = proto.shortName() + '.pk'
        if saveFile is None:
            self.fileDialog = FileDialog(None, "Save session", os.path.join(saveDir, protoName))
            self.fileDialog.setFileMode(QtGui.QFileDialog.AnyFile)
            self.fileDialog.setAcceptMode(QtGui.QFileDialog.AcceptSave) 
            self.fileDialog.show()
            self.fileDialog.fileSelected.connect(self.saveAll)
            return
        #saveFile = QtGui.QFileDialog.getSaveFileName(None, "Save session", os.path.join(saveDir, protoName))
        state = {}
        state['program'] = self.dumpProtocol()
        state['data'] = self.data
        state['results'] = self.results
        pickle.dump(state, open(saveFile, 'w'))
        
    def loadSession(self):
        fh = open(getManager().currentFile.name())
        state = pickle.load(fh)
        fh.close()
        
        self.restoreProtocol(state['program'])
        self.clearData()
        for d in state['data']:
            self.loadSequence(d)
        
        self.results = state['results']
        
        
    def addPlot(self, name=None, state=None):
        if name is None:
            name = 'Plot'
            i = 0
            while True:
                name2 = '%s_%03d' % (name, i)
                if name2 not in self.dockItems:
                    break
                i += 1
            name = name2
        
        p = PlotWidget(name=name)
        d = QtGui.QDockWidget(name)
        d.setObjectName(name)
        d.setWidget(p)
        
        if state is not None:
            p.restoreState(state)

        nodes = self.flowchart.nodes()
        #print name, nodes
        if name in nodes:
            node = nodes[name]
        else:
            node = self.flowchart.createNode('PlotWidget', name=name)
        node.setPlot(p)

        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, d)
        item = ListItem(name, d)
        self.dockItems[name] = {'type': 'Plot', 'listItem': item, 'dock': d, 'widget': p, 'node': node}
        self.ui.dockList.addItem(item)
        

    def addCanvas(self, name=None, state=None):
        if name is None:
            name = 'Canvas'
            i = 0
            while True:
                name2 = '%s_%03d' % (name, i)
                if name2 not in self.dockItems:
                    break
                i += 1
            name = name2
        
        p = CanvasWidget()
        
        d = QtGui.QDockWidget(name)
        d.setObjectName(name)
        d.setWidget(p)
        
        #if state is not None:
            #p.restoreState(state)

        nodes = self.flowchart.nodes()
        #print name, nodes
        if name in nodes:
            node = nodes[name]
        else:
            node = self.flowchart.createNode('CanvasWidget', name=name)
        node.setCanvas(p.canvas)

        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, d)
        item = ListItem(name, d)
        self.dockItems[name] = {'type': 'Canvas', 'listItem': item, 'dock': d, 'widget': p, 'node': node}
        self.ui.dockList.addItem(item)
    
    def addTable(self):
        pass
    
    
class CanvasWidget(QtGui.QWidget):
    def __init__(self):
        QtGui.QWidget.__init__(self)
        self.lay = QtGui.QGridLayout()
        self.lay.setSpacing(0)
        self.setLayout(self.lay)
        self.addBtn = QtGui.QPushButton('Add Image')
        self.clearBtn = QtGui.QPushButton('Clear Images')
        self.autoBtn = QtGui.QPushButton('Auto Range')
        self.canvas = Canvas()
        self.lay.addWidget(self.addBtn, 0, 0)
        self.lay.addWidget(self.clearBtn, 0, 1)
        self.lay.addWidget(self.autoBtn, 0, 2)
        self.lay.addWidget(self.canvas, 1, 0, 1, 3)
        self.imageItems = []
        self.z = -1000
        self.canvas.view.setRange(QtCore.QRectF(-0.01, -0.01, 0.02, 0.02))

        self.connect(self.addBtn, QtCore.SIGNAL('clicked()'), self.addImage)
        self.connect(self.clearBtn, QtCore.SIGNAL('clicked()'), self.clearImages)
        self.connect(self.autoBtn, QtCore.SIGNAL('clicked()'), self.autoRange)
        
    def autoRange(self):
        bounds = self.imageItems[0].sceneBoundingRect()
        self.canvas.view.setRange(bounds)
        
    def addItem(self, *args, **kargs):
        return self.canvas.addItem(*args, **kargs)
        
    def addImage(self):
        fd = getManager().currentFile
        img = fd.read()
        if 'imagePosition' in fd.info():
            ps = fd.info()['pixelSize']
            pos = fd.info()['imagePosition']
        else:
            info = img.infoCopy()[-1]
            ps = info['pixelSize']
            pos = info['imagePosition']
            
        img = img.view(ndarray)
        if img.ndim == 3:
            img = img.max(axis=0)
        #print pos, ps, img.shape, img.dtype, img.max(), img.min()
        item = ImageItem(img)
        self.canvas.addItem(item, pos, scale=ps, z=self.z, name=fd.shortName())
        self.z += 1
        self.imageItems.append(item)
        
        
    def clearImages(self):
        for item in self.imageItems:
            self.canvas.removeItem(item)
        self.imageItems = []
    
    
class ListItem(QtGui.QListWidgetItem):
    def __init__(self, name, obj):
        QtGui.QListWidgetItem.__init__(self, name)
        #self.obj = weakref.ref(obj)