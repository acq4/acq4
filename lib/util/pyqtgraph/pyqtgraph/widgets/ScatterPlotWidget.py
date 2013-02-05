from pyqtgraph.Qt import QtGui, QtCore
from .PlotWidget import PlotWidget
import pyqtgraph.parametertree as ptree
import pyqtgraph.functions as fn
import numpy as np

__all__ = ['ScatterPlotWidget']

class ScatterPlotWidget(QtGui.QWidget):
    """
    Given a record array, display a scatter plot of a specific set of data.
    This widget includes controls for selecting the columns to plot,
    filtering data, and determining symbol color and shape. This widget allows
    the user to explore relationships between columns in a record array.
    """
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self)
        self.layout = QtGui.QGridLayout()
        self.setLayout(self.layout)
        self.fieldList = QtGui.QListWidget()
        self.fieldList.setSelectionMode(self.fieldList.ExtendedSelection)
        self.filter = DataFilterWidget()
        self.colorMap = ColorMapWidget()
        self.plot = PlotWidget()
        self.layout.addWidget(self.fieldList, 0, 0)
        self.layout.addWidget(self.filter, 1, 0)
        self.layout.addWidget(self.colorMap, 2, 0)
        self.layout.addWidget(self.plot, 0, 1, 3, 1)
        
        self.data = None
        
        self.fieldList.itemSelectionChanged.connect(self.fieldSelectionChanged)
        self.filter.sigFilterChanged.connect(self.filterChanged)
    
    def setFields(self, fields):
        """
        Set the list of field names/units to be processed.
        Format is: [(name, units), ...]   
        """
        self.fieldList.clear()
        for f in fields:
            item = QtGui.QListWidgetItem(f[0])
            item.units = f[1]
            item = self.fieldList.addItem(item)
        self.filter.setFields(fields)
        self.colorMap.setFields(fields)
        
    def setData(self, data):
        """
        Set the data to be processed and displayed. 
        Argument must be a numpy record array.
        """
        self.data = data
        self.filtered = None
        self.updatePlot()
        
    def fieldSelectionChanged(self):
        self.updatePlot()
        
    def filterChanged(self, f):
        self.filtered = None
        self.updatePlot()
        
    def updatePlot(self):
        self.plot.clear()
        if self.data is None:
            return
        
        if self.filtered is None:
            self.filtered = self.filter.filterData(self.data)
        data = self.filtered
        
        style = dict(pen=None, symbol='o')
        
        sel = list([str(item.text()) for item in self.fieldList.selectedItems()])
        units = list([item.units for item in self.fieldList.selectedItems()])
        if len(sel) == 0:
            self.plot.setTitle('')
        elif len(sel) == 1:
            self.plot.setLabels(left=('N', ''), bottom=(sel[0], units[0]), title='')
            if len(data) == 0:
                return
            x = data[sel[0]]
            mask = ~np.isnan(x)
            x = x[mask]
            #if color is not None:
                #style['symbolBrush'] = color[mask]
            y = fn.pseudoScatter(x)
            self.plot.plot(x, y, clear=True, **style)
        elif len(sel) == 2:
            self.plot.setLabels(left=(sel[1],units[1]), bottom=(sel[0],units[0]))
            if len(data) == 0:
                return
            
            xydata = []
            for ax in [0,1]:
                d = data[sel[ax]]
                ## scatter catecorical values just a bit so they show up better in the scatter plot.
                #if sel[ax] in ['MorphologyBSMean', 'MorphologyTDMean', 'FIType']:
                    #d += np.random.normal(size=len(cells), scale=0.1)
                xydata.append(d)
            x,y = xydata
            mask = ~(np.isnan(x) | np.isnan(y))
            x = x[mask]
            y = y[mask]
            #if color is not None:
                #style['symbolBrush'] = color[mask]
            self.plot.plot(x, y, **style)
            #r,p = stats.pearsonr(x, y)
            #plot.setLabels(title="r=%0.2f, p=%0.2g" % (r,p))
        
        
class DataFilterWidget(QtGui.QWidget):
    sigFilterChanged = QtCore.Signal(object)
    def __init__(self):
        QtGui.QWidget.__init__(self)
        self.layout = QtGui.QGridLayout()
        self.setLayout(self.layout)
        self.ptree = ptree.ParameterTree()
        self.layout.addWidget(self.ptree)
        
        self.fields = []
        self.params = ptree.Parameter.create(name='Data Filter', type='group', addText='Add filter..', addList=[])
        self.params.addNew = self.addNew
        
        self.ptree.setParameters(self.params)
        self.params.sigTreeStateChanged.connect(self.filterChanged)
    
    def addNew(self, name):
        #fp = ptree.Parameter.create(name='Filter', autoIncrementName=True, type='bool', value=True, removable=True, renamable=True, children=[
            #dict(name="Field", type='list', value=typ, values=self.fieldNames()),
            #dict(name='Min', type='float', value=0.0),
            #dict(name='Max', type='float', value=1.0),
            #])
        self.params.addChild(FilterItem(name, self.units[name]))
        
    def filterChanged(self):
        self.sigFilterChanged.emit(self)
        
    def fieldNames(self):
        return [f[0] for f in self.fields]
    
    def parameters(self):
        return self.params
        
    def setFields(self, fields):
        self.fields = fields
        #self.fields.sort()
        names = self.fieldNames()
        self.units = dict(fields)
        self.params.setAddList(names)
        #for fp in self.params:
            #if fp.name() == 'Amplitude Sign':
                #continue
            #fp.param('Field').setLimits(names)
    
    def filterData(self, data):
        if len(data) == 0:
            return data
        
        #self.updateKeys(events.dtype.names)
        
        #if self.params['Amplitude Sign'] == '+':
            #events = events[events['fitAmplitude'] > 0]
        #else:
            #events = events[events['fitAmplitude'] < 0]
        
        #for fp in self.params:
            ##if fp.name() == 'Amplitude Sign':
                ##continue
            #if fp.value() is False:
                #continue
            #key, mn, mx = fp['Field'], fp['Min'], fp['Max']
            #vals = data[key]
            #mask = (vals >= mn) * (vals < mx)  ## Use inclusive minimum and non-inclusive maximum. This makes it easier to create non-overlapping selections
            #data = data[mask]
            
        return data[self.generateMask(data)]
    
    def generateMask(self, data):
        mask = np.ones(len(data), dtype=bool)
        if len(data) == 0:
            return mask
        for fp in self.params:
            #if fp.name() == 'Amplitude Sign':
                #continue
            if fp.value() is False:
                continue
            key, mn, mx = fp.fieldName, fp['Min'], fp['Max']
            vals = data[key]
            mask &= (vals >= mn)
            mask &= (vals < mx)  ## Use inclusive minimum and non-inclusive maximum. This makes it easier to create non-overlapping selections
        return mask

class FilterItem(ptree.types.SimpleParameter):
    def __init__(self, name, units):
        self.fieldName = name
        ptree.types.SimpleParameter.__init__(self, 
            name=name, autoIncrementName=True, type='bool', value=True, removable=True, renamable=True, 
            children=[
                #dict(name="Field", type='list', value=name, values=fields),
                dict(name='Min', type='float', value=0.0, suffix=units, siPrefix=True),
                dict(name='Max', type='float', value=1.0, suffix=units, siPrefix=True),
            ])
    
    
class ColorMapWidget(QtGui.QWidget):
    def __init__(self):
        QtGui.QWidget.__init__(self)
        self.layout = QtGui.QGridLayout()
        self.setLayout(self.layout)
        self.ptree = ptree.ParameterTree()
        self.layout.addWidget(self.ptree)
        
        self.fields = []
        self.params = ptree.Parameter.create(name='Color Map', type='group', addText='Add..')
        self.params.addNew = self.addNew
        
        self.ptree.setParameters(self.params)
        self.params.sigTreeStateChanged.connect(self.filterChanged)
    
    def addNew(self, name):
        #fp = ptree.Parameter.create(name='Filter', autoIncrementName=True, type='bool', value=True, removable=True, renamable=True, children=[
            #dict(name="Field", type='list', value=typ, values=self.fieldNames()),
            #dict(name='Min', type='float', value=0.0),
            #dict(name='Max', type='float', value=1.0),
            #])
        self.params.addChild(FilterItem())
        
    def setFields(self, fields):
        pass
    
class ColorMapItem(ptree.types.SimpleParameter):
    def __init__(self, name, units):
        self.fieldName = name
        ptree.types.SimpleParameter.__init__(self, 
            name=name, autoIncrementName=True, type='bool', value=True, removable=True, renamable=True, 
            children=[
                #dict(name="Field", type='list', value=name, values=fields),
                dict(name='Min', type='float', value=0.0, suffix=units, siPrefix=True),
                dict(name='Max', type='float', value=1.0, suffix=units, siPrefix=True),
            ])
    
