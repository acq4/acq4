# -*- coding: utf-8 -*-
from __future__ import print_function

from acq4.Manager import getManager
from .AnalyzerTemplate import *
from acq4.util.flowchart import *
from acq4.util import Qt
from acq4.util.DirTreeWidget import DirTreeLoader
from acq4.pyqtgraph.PlotWidget import *
from acq4.util.Canvas import *
import acq4.util.configfile as configfile
import pickle
from acq4.util.DataManager import getHandle

class Analyzer(Qt.QMainWindow):
    def __init__(self, protoDir, parent=None):
        self.protoDir = protoDir
        Qt.QMainWindow.__init__(self, parent)
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
        
        Qt.QObject.connect(self.ui.dataSourceCombo, Qt.SIGNAL("currentIndexChanged(int)"), self.setDataSource)
        Qt.QObject.connect(self.ui.loadDataBtn, Qt.SIGNAL("clicked()"), self.loadData)
        Qt.QObject.connect(self.ui.loadSequenceBtn, Qt.SIGNAL("clicked()"), self.loadSequence)
        Qt.QObject.connect(self.ui.loadSessionBtn, Qt.SIGNAL("clicked()"), self.loadSession)
        Qt.QObject.connect(self.ui.recompSelectedBtn, Qt.SIGNAL("clicked()"), self.recomputeSelected)
        Qt.QObject.connect(self.ui.recompAllBtn, Qt.SIGNAL("clicked()"), self.recomputeAll)
        Qt.QObject.connect(self.ui.saveAllBtn, Qt.SIGNAL("clicked()"), self.saveAll)
        Qt.QObject.connect(self.ui.addOutputBtn, Qt.SIGNAL("clicked()"), self.addOutput)
        Qt.QObject.connect(self.ui.addPlotBtn, Qt.SIGNAL("clicked()"), self.addPlot)
        Qt.QObject.connect(self.ui.addCanvasBtn, Qt.SIGNAL("clicked()"), self.addCanvas)
        Qt.QObject.connect(self.ui.addTableBtn, Qt.SIGNAL("clicked()"), self.addTable)
        Qt.QObject.connect(self.ui.removeDockBtn, Qt.SIGNAL("clicked()"), self.removeSelected)
        Qt.QObject.connect(self.ui.dataTree, Qt.SIGNAL("currentItemChanged(QTreeWidgetItem*,QTreeWidgetItem*)"), self.dataSelected)

        Qt.QObject.connect(self.flowchart.outputNode, Qt.SIGNAL("terminalRenamed"), self.outputRenamed)
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
            Qt.QObject.disconnect(self.dataSource, Qt.SIGNAL("resultsChanged"), self.dataSourceChanged)
        source = self.ui.dataSourceCombo.getSelectedObj()
        self.dataSource = source
        if source is None:
            return
        Qt.QObject.connect(source, Qt.SIGNAL("resultsChanged"), self.dataSourceChanged)
        #print "connected to", source
        self.dataSourceChanged()
    
    def dumpProtocol(self):
        state = {'docks': {}}
        for name, d in self.dockItems.items():
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
        for name, d in self.dockItems.items():
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
        for name, d in state['docks'].items():
            fn = getattr(self, 'add'+d['type'])
            fn(name, d.get('state', None))
        
        ## restore dock positions
        self.restoreState(Qt.QByteArray.fromPercentEncoding(state['window']))
        
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
        item = Qt.QTreeWidgetItem([data.shortName()])
        item.data = data
        self.ui.dataTree.addTopLevelItem(item)
        self.data.append(data)
        for sub in data.subDirs():
            try:
                int(sub)
            except:
                continue
            subd = data[sub]
            i2 = Qt.QTreeWidgetItem([sub])
            i2.data = subd
            item.addChild(i2)

    def dataSourceChanged(self):
        print("data source changed!")
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
        progressDlg = Qt.QProgressDialog("Processing:", 0, len(inputs))
        progressDlg.setWindowModality(Qt.Qt.WindowModal)
        for i in range(len(inputs)):
            inp = inputs[i]
            progressDlg.setLabelText("Processing: " + inp.name())
            progressDlg.setValue(i)
            Qt.QApplication.instance().processEvents()
            if progressDlg.wasCanceled():
                progressDlg.setValue(len(inputs))
                break
            out = self.flowchart.process(dataIn=inp)
            self.results[inp] = out
            
        progressDlg.setValue(len(inputs))
        self.emit(Qt.SIGNAL('resultsChanged'))
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
            self.fileDialog.setFileMode(Qt.QFileDialog.AnyFile)
            self.fileDialog.setAcceptMode(Qt.QFileDialog.AcceptSave) 
            self.fileDialog.show()
            self.fileDialog.fileSelected.connect(self.saveAll)
            return
        #saveFile = Qt.QFileDialog.getSaveFileName(None, "Save session", os.path.join(saveDir, protoName))
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
        d = Qt.QDockWidget(name)
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

        self.addDockWidget(Qt.Qt.RightDockWidgetArea, d)
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
        
        d = Qt.QDockWidget(name)
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

        self.addDockWidget(Qt.Qt.RightDockWidgetArea, d)
        item = ListItem(name, d)
        self.dockItems[name] = {'type': 'Canvas', 'listItem': item, 'dock': d, 'widget': p, 'node': node}
        self.ui.dockList.addItem(item)
    
    def addTable(self):
        pass
    
    
class CanvasWidget(Qt.QWidget):
    def __init__(self):
        Qt.QWidget.__init__(self)
        self.lay = Qt.QGridLayout()
        self.lay.setSpacing(0)
        self.setLayout(self.lay)
        self.addBtn = Qt.QPushButton('Add Image')
        self.clearBtn = Qt.QPushButton('Clear Images')
        self.autoBtn = Qt.QPushButton('Auto Range')
        self.canvas = Canvas()
        self.lay.addWidget(self.addBtn, 0, 0)
        self.lay.addWidget(self.clearBtn, 0, 1)
        self.lay.addWidget(self.autoBtn, 0, 2)
        self.lay.addWidget(self.canvas, 1, 0, 1, 3)
        self.imageItems = []
        self.z = -1000
        self.canvas.view.setRange(Qt.QRectF(-0.01, -0.01, 0.02, 0.02))

        self.connect(self.addBtn, Qt.SIGNAL('clicked()'), self.addImage)
        self.connect(self.clearBtn, Qt.SIGNAL('clicked()'), self.clearImages)
        self.connect(self.autoBtn, Qt.SIGNAL('clicked()'), self.autoRange)
        
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
    
    
class ListItem(Qt.QListWidgetItem):
    def __init__(self, name, obj):
        Qt.QListWidgetItem.__init__(self, name)
        #self.obj = weakref.ref(obj)