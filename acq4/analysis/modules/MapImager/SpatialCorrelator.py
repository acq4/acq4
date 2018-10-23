from __future__ import print_function
from acq4.util import Qt
from . import SpatialCorrelatorCtrlTemplate
import math
from acq4.util.HelpfulException import HelpfulException
import numpy as np
import acq4.pyqtgraph as pg
import acq4.analysis.tools.functions as fn
import scipy





class SpatialCorrelator(Qt.QWidget):
    
    sigOutputChanged = Qt.Signal(object)
    
    def __init__(self):
        Qt.QWidget.__init__(self)
        
        self.ctrl = SpatialCorrelatorCtrlTemplate.Ui_Form()
        self.ctrl.setupUi(self)
        
        self.ctrl.deltaTSpin.setOpts(suffix='s', value=50e-3, dec=True, step=0.1, siPrefix=True)
        self.ctrl.radiusSpin.setOpts(suffix='m', value=90e-6, dec=True, step=0.1, siPrefix=True)
        self.ctrl.spontSpin.setOpts(suffix='Hz', value=0, step=0.1, siPrefix=True)
        self.ctrl.thresholdSpin.setOpts(value=0.05)
        
        #self.outline = SpatialOutline()
        self.data = None ## will be a record array with 1 row per stimulation - needs to contain fields xpos, ypos, numOfPostEvents, significance
        
        self.ctrl.processBtn.hide()
        self.ctrl.processBtn.clicked.connect(self.process)
        self.ctrl.deltaTSpin.sigValueChanged.connect(self.paramChanged)
        self.ctrl.radiusSpin.sigValueChanged.connect(self.paramChanged)
        self.ctrl.spontSpin.sigValueChanged.connect(self.paramChanged)
        self.ctrl.thresholdSpin.sigValueChanged.connect(self.paramChanged)
        self.ctrl.probabilityRadio.toggled.connect(self.paramChanged)
        self.ctrl.eventCombo.currentIndexChanged.connect(self.paramChanged)
        
        
    #def getOutline(self):
        #return self.outline
    def populateEventsCombo(self, arr):
        names = arr.dtype.names ## it would be nice to narrow this down to only include integer fields
        self.ctrl.eventCombo.updateList(names)
    
    def setData(self, arr=None, xPos=None, yPos=None, numOfPostEvents=None):
        if arr is not None:
            self.checkArrayInput(arr)
            self.populateEventsCombo(arr)
            fields = arr.dtype.names
            if 'xPos' not in fields or 'yPos' not in fields:
                raise HelpfulException("Array input to Spatial correlator needs to have the following fields: 'xPos', 'yPos'")
        elif arr is None:
            self.data = None
            return
        
        self.data = np.zeros(len(arr), dtype=arr.dtype.descr + [('prob', float)])
        self.data[:] = arr
        
        if 'numOfPreEvents' in fields and 'PreRegionLen' in fields:
            self.calculateSpontRate()
        if 'PostRegionLen' in fields:
            self.ctrl.deltaTSpin.setValue(self.data['PostRegionLen'][0])
        
        self.process()
        
    def calculateSpontRate(self):
        spontRate = float(self.data['numOfPreEvents'].sum())/self.data['PreRegionLen'].sum()
        self.ctrl.spontSpin.setValue(spontRate)
    
    def paramChanged(self, *args):
        self.process()
    
    def process(self):
        #print "process called."
        if self.ctrl.disableChk.isChecked():
            return
        if self.data is None:
            return
        
        #print "calculating Probs"
        fn.bendelsSpatialCorrelationAlgorithm(self.data, self.ctrl.radiusSpin.value(), self.ctrl.spontSpin.value(), self.ctrl.deltaTSpin.value(), printProcess=False, eventsKey=str(self.ctrl.eventCombo.currentText()))
        #print "probs calculated"
        self.data['prob'] = 1-self.data['prob'] ## give probability that events are not spontaneous
        
        if self.ctrl.probabilityRadio.isChecked():
            self.emitOutputChanged(self.data)
        elif self.ctrl.thresholdRadio.isChecked():
            arr = self.data['prob']
            arr[1-arr < self.ctrl.thresholdSpin.value()] = 1
            arr[(1-arr > self.ctrl.thresholdSpin.value())*(arr!=1)] = 0
            self.data['prob'] = arr
            self.emitOutputChanged(self.data)
        #spacing = 5e-6
        #arr = fn.convertPtsToSparseImage(self.data, ['prob'], spacing)
        #arr = arr['prob']
        #arr[1-arr < self.ctrl.significanceSpin.value()] = 1
        #arr[(1-arr > self.ctrl.significanceSpin.value())*(arr!=1)] = 0
        #arr = scipy.ndimage.gaussian_filter(arr, 45e-6/spacing)
        
        #curve = pg.IsocurveItem(arr, 0.2)
        #spots = self.data[(1-self.data['prob'] < self.ctrl.significanceSpin.value())*(self.data['prob'] != 0)]
        #if 'spotSize' in self.data.dtype.names:
            #self.outline.setRadius(self.data[1]['spotSize']/2.)
        #self.outline.setData(spots)
        
    def emitOutputChanged(self, obj):
        self.sigOutputChanged.emit(obj)
    
    #@staticmethod
    def checkArrayInput(self, arr):
        fields = arr.dtype.names
        if 'xPos' not in fields or 'yPos' not in fields or 'numOfPostEvents' not in fields:
            raise HelpfulException("Array input needs to have the following fields: 'xPos', 'yPos', 'numOfPostEvents'. Current fields are: %s" %str(fields))  
        else:
            return True    
    
    #@staticmethod    
    #def bendelsSpatialCorrelationAlgorithm(data, radius, spontRate, timeWindow):
        #SpatialCorrelator.checkArrayInput(data) ## check that data has 'xPos', 'yPos' and 'numOfPostEvents'
        
        ### add 'prob' field to data array
        #if 'prob' not in data.dtype.names:
            #arr = np.zeros(len(data), dtype=data.dtype.descr + [('prob', float)])
            #arr[:] = data     
            #data = arr
        #else:
            #data['prob']=0
            
    
        
        ### spatial correlation algorithm from :
        ### Bendels, MHK; Beed, P; Schmitz, D; Johenning, FW; and Leibold C. Etection of input sites in 
        ### scanning photostimulation data based on spatial correlations. 2010. Journal of Neuroscience Methods.
        
        ### calculate probability of seeing a spontaneous event in time window
        #p = 1-np.exp(-spontRate*timeWindow)
        
        ### for each spot, calculate the probability of having the events in nearby spots occur randomly
        #for x in data:
            #spots = data[(np.sqrt((data['xPos']-x['xPos'])**2+(data['yPos']-x['yPos'])**2)) < radius]
            #nSpots = len(spots)
            #nEventSpots = len(spots[spots['numOfPostEvents'] > 0])
            
            #prob = 0
            #for j in range(nEventSpots, nSpots+1):
                #prob += ((p**j)*((1-p)**(nSpots-j))*math.factorial(nEventSpots))/(math.factorial(j)*math.factorial(nSpots-j))
            ##j = arange(nEventSponts, nSpots+1)
            ##prob = (((p**j)*((1-p)**(nSpots-j))*np.factorial(nEventSpots))/(np.factorial(j)*np.factorial(nSpots-j))).sum() ## need a factorial function that works on arrays
                
            #x['prob'] = prob
        
        #return data
    


#class SpatialOutline(pg.GraphicsObject):
    
    #def __init__(self, parent=None, pen=None, spots=None, radius=25e-6):
        #pg.GraphicsObject.__init__(self, parent)
        
        #if pen is None:
            #pen = (255, 255, 255)
        #self.setPen(pen)   
        
        #self.path = Qt.QPainterPath()
        #self.spots = spots
        #self.radius = radius
        #if spots is not None:
            #self.makePath()
            
    #def setData(self, spots):
        #self.spots = spots
        #self.makePath()
        #self.update(self.boundingRect())
        
    #def setRadius(self, radius):
        #self.radius = radius
        #self.makePath()
        #self.update(self.boundingRect())
        
        
    #def setPen(self, pen):
        #self.pen = pg.mkPen(pen)
        #self.currentPen = self.pen
        #self.update()    
        
    #def makePath(self):
        #if self.spots is None:
            #return
        #path = Qt.QPainterPath()
        #for s in self.spots:
            #path.addEllipse(s['xPos'], s['yPos'], self.radius, self.radius)
            
        ##pps = Qt.QPainterPathStroker()
        
        ##self.path = pps.createStroke(path)
        #self.path=path
    
    #def boundingRect(self):
        #if self.spots is None:
            #return Qt.QRectF()
        ##x = self.spots['xPos'].min()
        ##y = self.spots['yPos'].min()
        ##return Qt.QRectF(x,y , self.spots['xPos'].max()-x, self.spots['yPos'].max()-y)
        ##print "outline.boundingRect: ", self.path.boundingRect()
        #return self.path.boundingRect()

    #def paint(self, p, *args):
        #p.setRenderHint(Qt.QPainter.Antialiasing)
        ##path = self.shape()
        #p.setPen(self.currentPen)
        #p.drawPath(self.path)
        ##p.setPen(Qt.QPen(Qt.QColor(255,0,0)))
        ##p.drawPath(self.shape())
        #p.setPen(Qt.QPen(Qt.QColor(0,0,255)))
        #p.drawRect(self.boundingRect())    