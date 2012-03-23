from PyQt4 import QtCore, QtGui
#import lib.Manager
import pyqtgraph as pg
import numpy as np
#import functions as fn
import MapConvolverTemplate
import scipy


class MapConvolver(QtGui.QWidget):
    
    sigOutputChanged = QtCore.Signal(object, object)
    sigFieldsChanged = QtCore.Signal(object)
    
    def __init__(self, parent=None, filePath=None, data=None):
        QtGui.QWidget.__init__(self, parent)
        
        self.ui = MapConvolverTemplate.Ui_Form()
        self.ui.setupUi(self)
        self.ui.spacingSpin.setOpts(suffix='m', value=5e-6, siPrefix=True, dec=False, step=1e-6)
        
        self.addBtn = QtGui.QPushButton('Add New')
        item = QtGui.QTreeWidgetItem()
        self.ui.tree.addTopLevelItem(item)
        self.ui.tree.setItemWidget(item, 0, self.addBtn)        

        self.items = []
        self.filePath = filePath
        self.data = data
        self.output = None
        
        self.addBtn.clicked.connect(self.addItem)
        self.ui.processBtn.clicked.connect(self.processClicked)
        
        
    def setData(self, data):
        self.data = data
        for i in self.items:
            i.updateParamCombo(data.dtype.names)
            
    def addItem(self):
        item = ConvolverItem(self)
        self.ui.tree.insertTopLevelItem(self.ui.tree.topLevelItemCount()-1, item)
        item.postAdd()
        self.items.append(item) 
        item.updateParamCombo(self.data.dtype.names)
        self.fieldsChanged()
    
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
        fields = []
        for i in self.items:
            fields.append(str(i.paramCombo.currentText()))
        self.sigFieldsChanged.emit(fields)
        
    def processClicked(self):
        if self.data == None:
            return
        params = {}
        for i in self.items:
            if str(i.convolutionCombo.currentText()) == "Gaussian":
                params[str(i.paramCombo.currentText())] = {'sigma':i.sigmaSpin.value()}
            else:
                raise Exception("Loading custom kernels is not yet fully supported.")
        spacing = self.ui.spacingSpin.value()
        self.output = MapConvolver.convolveMaptoImage(self.data, params, spacing=spacing)
        self.sigOutputChanged.emit(self.output, spacing)
        
    @staticmethod
    def convolveMaptoImage(data, params, spacing=5e-6):
        """Function for converting a list of stimulation spots and their associated values into a fine-scale smoothed image.
               data - a numpy record array which includes fields for 'xPos', 'yPos' and the parameters specified in params.
               params - a dict of parameters to project and their corresponding convolution kernels - if 'sigma' is specified it will be used
                        as the stdev of a gaussian kernel, otherwise a custom kernel can be specified.
                           ex: {'postCharge': {'sigma':80e-6}, 'dirCharge':{'kernel': ndarray to use as the convolution kernel}}
               spacing - the size of each pixel in the returned grid (default is 5um)
            """
    
        if params==None:
            raise Exception("Don't know which parameters to process. Options are: %s" %str(data.dtype.names))
        if 'xPos' not in data.dtype.names or 'yPos' not in data.dtype.names:
            raise Exception("Data needs to have fields for 'xPos' and 'yPos'. Current fields are: %s" %str(data.dtype.names))
        
        
        
        ### Project data from current spacing onto finer grid, averaging data from duplicate spots
        xmin = data['xPos'].min()
        ymin = data['yPos'].min()
        xdim = int((data['xPos'].max()-xmin)/spacing)+5
        ydim = int((data['yPos'].max()-ymin)/spacing)+5
        dtype = []
        for p in params.keys():
            dtype.append((p, float))
        dtype.append(('stimNumber', int))
        arr = np.zeros((xdim, ydim), dtype=dtype)
        for s in data:
            x, y = (int((s['xPos']-xmin)/spacing), int((s['yPos']-ymin)/spacing))
            for p in params:
                arr[x,y][p] += s[p]
            arr[x,y]['stimNumber'] += 1
        arr['stimNumber'][arr['stimNumber']==0] = 1
        for f in arr.dtype.names:
            arr[f] = arr[f]/arr['stimNumber']
        #arr = arr/arr['stimNumber']
        arr = np.ascontiguousarray(arr)  
        
        ## get values before convolution for normalization after
        x, y = (int((data[0]['xPos']-xmin)/spacing), int((data[0]['yPos']-ymin)/spacing))
        vals = arr[x,y]
        
                                       
        ## convolve image using either given kernel or gaussian kernel with sigma=sigma
        for p in params:
            if params[p].get('kernel', None) is None:
                if params[p].get('sigma', None) is None:
                    raise Exception("Please specify either a kernel to use for convolution, or sigma for a gaussian kernel for %s param." %p)                    
                arr[p] = scipy.ndimage.filters.gaussian_filter(arr[p], int(params[p]['sigma']/spacing))
            else:
                arr[p] = scipy.ndimage.filters.convolve(arr[p], params[p]['kernel'])
                
        ## do amplitude correction
        factor = vals/arr[x,y]
        arr *= factor
                
        return arr
        
class ConvolverItem(QtGui.QTreeWidgetItem):
    def __init__(self, mc):
        self.mc = mc
        QtGui.QTreeWidgetItem.__init__(self)
        self.paramCombo = QtGui.QComboBox()
        self.convolutionCombo = QtGui.QComboBox()
        self.convolutionCombo.addItem("Gaussian")
        self.sigmaSpin = pg.widgets.SpinBox.SpinBox(value=80e-6, siPrefix=True, suffix='m', dec=True, step=0.1)
        #self.maxSpin = SpinBox(value=1.0)
        #self.gradient = GradientWidget()
        #self.updateArgList()
        #self.opCombo.addItem('+')
        #self.opCombo.addItem('*')
        self.remBtn = QtGui.QPushButton('Remove')
        
        self.remBtn.clicked.connect(self.delete)
        self.paramCombo.currentIndexChanged.connect(self.mc.fieldsChanged)
        
    def postAdd(self):
        t = self.treeWidget()
        #self.setText(0, "-")
        t.setItemWidget(self, 0, self.paramCombo)
        t.setItemWidget(self, 1, self.convolutionCombo)
        t.setItemWidget(self, 2, self.sigmaSpin)
        #t.setItemWidget(self, 3, self.maxSpin)
        #t.setItemWidget(self, 4, self.gradient)
        t.setItemWidget(self, 3, self.remBtn)
        
    def delete(self):
        self.mc.remClicked(self)
        
    def updateParamCombo(self, paramList):
        prev = str(self.paramCombo.currentText())
        self.paramCombo.clear()
        for p in paramList:
            self.paramCombo.addItem(p)
            if p == prev:
                self.paramCombo.setCurrentIndex(self.paramCombo.count()-1)        
