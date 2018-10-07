from __future__ import print_function
from acq4.util import Qt
#import acq4.Manager
import acq4.pyqtgraph as pg
import numpy as np
import acq4.util.functions as fn
from . import MapConvolverTemplate
import scipy
from acq4.analysis.tools import functions as afn

class MapConvolver(Qt.QWidget):
    
    sigOutputChanged = Qt.Signal(object, object)
    sigFieldsChanged = Qt.Signal(object)
    
    def __init__(self, parent=None, filePath=None, data=None):
        Qt.QWidget.__init__(self, parent)
        
        self.ui = MapConvolverTemplate.Ui_Form()
        self.ui.setupUi(self)
        self.ui.spacingSpin.setOpts(suffix='m', value=5e-6, siPrefix=True, dec=False, step=1e-6)
        
        self.addBtn = Qt.QPushButton('Add New')
        item = Qt.QTreeWidgetItem()
        self.ui.tree.addTopLevelItem(item)
        self.ui.tree.setItemWidget(item, 0, self.addBtn)        

        self.items = []
        self.filePath = filePath
        self.data = data
        self.output = None
        self._availableFields = None ## a list of fieldnames that are available for coloring/contouring
        
        self.ui.processBtn.hide()
        self.addBtn.clicked.connect(self.addItem)
        self.ui.processBtn.clicked.connect(self.processClicked)
        
        
    def setData(self, data):
        self.data = data
        fields = []
        #self.blockSignals = True
        try:
            self.blockSignals(True)
            for i in self.items:
                fields.append(i.getParamName())
                i.updateParamCombo(data.dtype.names)
        finally:
            self.blockSignals(False)
            
        newFields = [i.getParamName() for i in self.items]
        if fields != newFields:
            self.fieldsChanged()
        #self.blockSignals = False
        self.process()
        
    def addItem(self):
        item = ConvolverItem(self)
        self.ui.tree.insertTopLevelItem(self.ui.tree.topLevelItemCount()-1, item)
        item.postAdd()
        self.items.append(item)
        #self.blockSignals = True
        if self.data is not None:
            item.updateParamCombo(self.data.dtype.names)
            self.fieldsChanged()
        #self.blockSignals = False
    
    def remClicked(self, item):
        #item = self.ui.tree.currentItem()
        if item is None:
            return
        self.remItem(item)
        #self.emitChanged()
    
    def remItem(self, item):
        index = self.ui.tree.indexOfTopLevelItem(item)
        self.ui.tree.takeTopLevelItem(index)
        self.items.remove(item)   
        self.fieldsChanged()
       
    def fieldsChanged(self):
        #if self.blockSignals:
         #   return
        fields = []
        for i in self.items:
            fields.append(i.getParamName())
        self._availableFields = fields
        self.sigFieldsChanged.emit(fields)
        
    def getFields(self):
        return self._availableFields
        
       
    def itemChanged(self):
        self.process()
        
    def processClicked():
        self.process()
        
    def process(self):
        if self.data == None:
            return
        if len(self.items) == 0:
            return
        
        params = {}
        spacing = self.ui.spacingSpin.value()
        for i in self.items:
            if str(i.convolutionCombo.currentText()) == "Gaussian convolution":
                params[str(i.paramCombo.currentText())] = {'sigma':i.sigmaSpin.value()}
                
            elif str(i.convolutionCombo.currentText()) == "interpolation":
                params[str(i.paramCombo.currentText())]= {'mode':i.modeCombo.currentText()}
            else:
                pass
                
        
        
        arr = MapConvolver.convolveMaptoImage(self.data, params, spacing=spacing)
        arrs = MapConvolver.interpolateMapToImage(self.data, params, spacing)
    
        
        dtype = arr.dtype.descr
        for p in arrs.keys():
            if p not in arr.dtype.names:
                dtype.append((p, float))
            
        self.output = np.zeros(arr.shape, dtype=dtype)
        self.output[:] = arr
        for p in arrs:
            self.output[p] = arrs[p]
        
        self.sigOutputChanged.emit(self.output, spacing)
        
    @staticmethod
    def interpolateMapToImage(data, params, spacing=0.000005):
        """Function for interpolating a list of stimulation spots and their associated values into a fine-scale smoothed image.
                data - a numpy record array which includes fields for 'xPos', 'yPos' and the parameters specified in params.
                params - a dict of parameters to project and their corresponding interpolation modes. Mode options are:
                    'nearest', 'linear', 'cubic' (see documentation for scipy.interpolate.griddata)
                            ex: {'postCharge': {'mode':'nearest'}, 'dirCharge':{'mode':'cubic'}}
                spacing - the size of each pixel in the returned grids (default is 5um)
             """        
        
        xmin = data['xPos'].min()
        ymin = data['yPos'].min()
        xdim = int((data['xPos'].max()-xmin)/spacing)+5
        ydim = int((data['yPos'].max()-ymin)/spacing)+5
        
        pts = np.array([data['xPos'], data['yPos']], dtype=float)
        pts[0] = pts[0]-xmin
        pts[1] = pts[1]-ymin
        pts = pts.transpose()/spacing
        
        xi = np.indices((xdim, ydim))
        xi = xi.transpose(1,2,0)
        
        arrs = {}
        
        for p in params:
            if 'mode' in params[p].keys():
                arrs[p] = scipy.interpolate.griddata(pts, data[p], xi, method=params[p]['mode']) ## griddata function hangs when method='linear' in scipy versions earlier than 0.10.0
                arrs[p][np.isnan(arrs[p])] = 0
        return arrs
        
    @staticmethod
    def convolveMaptoImage(data, params, spacing=5e-6):
        """Function for converting a list of stimulation spots and their associated values into a fine-scale smoothed image using a gaussian convolution.
               data - a numpy record array which includes fields for 'xPos', 'yPos' and the parameters specified in params.
               params - a dict of parameters to project and their corresponding convolution kernels - if 'sigma' is specified it will be used
                        as the stdev of a gaussian kernel, otherwise a custom kernel can be specified.
                           ex: {'postCharge': {'sigma':80e-6}, 'dirCharge':{'kernel': ndarray to use as the convolution kernel}}
               spacing - the size of each pixel in the returned grid (default is 5um)
            """
        #arr = data
        arr = afn.convertPtsToSparseImage(data, list(params.keys()), spacing)
        
                                       
        ## convolve image using either given kernel or gaussian kernel with sigma=sigma
        for p in params:
            if 'mode' in params[p].keys():
                continue
            elif params[p].get('kernel', None) is None:
                if params[p].get('sigma', None) is None:
                    raise Exception("Please specify either a kernel to use for convolution, or sigma for a gaussian kernel for %s param." %p)                    
                arr[p] = scipy.ndimage.filters.gaussian_filter(arr[p], int(params[p]['sigma']/spacing))
            else:
                raise Exception("Convolving by a non-gaussian kernel is not yet supported.")
                #arr[p] = scipy.ndimage.filters.convolve(arr[p], params[p]['kernel'])
                
                
        return arr
        
class ConvolverItem(Qt.QTreeWidgetItem):
    def __init__(self, mc):
        self.mc = mc
        Qt.QTreeWidgetItem.__init__(self)
        self.paramCombo = pg.ComboBox()
        self.convolutionCombo = pg.ComboBox(items=["Gaussian convolution", "interpolation"], default="Gaussian convolution")
        #self.convolutionCombo.addItems(["Gaussian convolution", "interpolation"])
        self.sigmaSpin = pg.SpinBox(value=45e-6, siPrefix=True, suffix='m', dec=True, step=0.1)
        self.modeCombo = pg.ComboBox(items=['nearest', 'linear', 'cubic'], default='nearest')
        #self.modeCombo.addItems(['nearest', 'linear', 'cubic'])
        self.modeCombo.setEnabled(False)
        self.remBtn = Qt.QPushButton('Remove')
        
        self.remBtn.clicked.connect(self.delete)
        self.paramCombo.currentIndexChanged.connect(self.mc.fieldsChanged)
        self.convolutionCombo.currentIndexChanged.connect(self.methodChanged)
        self.paramCombo.currentIndexChanged.connect(self.itemChanged)
        self.sigmaSpin.sigValueChanged.connect(self.itemChanged)
        self.modeCombo.currentIndexChanged.connect(self.itemChanged)
        
        
        
    def postAdd(self):
        t = self.treeWidget()
        #self.setText(0, "-")
        t.setItemWidget(self, 0, self.paramCombo)
        t.setItemWidget(self, 1, self.convolutionCombo)
        t.setItemWidget(self, 2, self.sigmaSpin)
        t.setItemWidget(self, 3, self.modeCombo)
        t.setItemWidget(self, 4, self.remBtn)
        
    def itemChanged(self):
        self.mc.itemChanged()
        
    def delete(self):
        self.mc.remClicked(self)
        
    def getParamName(self):
        return str(self.paramCombo.currentText())
    
    def updateParamCombo(self, paramList):
        #prev = str(self.paramCombo.currentText())
        #self.paramCombo.clear()
        #for p in paramList:
            #self.paramCombo.addItem(p)
            #if p == prev:
                #self.paramCombo.setCurrentIndex(self.paramCombo.count()-1)     
        self.paramCombo.updateList(paramList)

    def methodChanged(self):
        method = str(self.convolutionCombo.currentText())
        if method == 'Gaussian convolution':
            self.sigmaSpin.setEnabled(True)
            self.modeCombo.setEnabled(False)
        elif method == 'interpolation':
            self.sigmaSpin.setEnabled(False)
            self.modeCombo.setEnabled(True)
        self.itemChanged()