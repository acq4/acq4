from PyQt4 import QtGui, QtCore
import SpatialCorrelatorCtrlTemplate
import math
from HelpfulException import HelpfulException
import numpy as np
import pyqtgraph as pg




class SpatialCorrelator(QtGui.QWidget):
    
    def __init__(self):
        QtGui.QWidget.__init__(self)
        
        self.ctrl = SpatialCorrelatorCtrlTemplate.Ui_Form()
        self.ctrl.setupUi(self)
        
        self.ctrl.deltaTSpin.setOpts(suffix='s', value=50e-3, dec=True, step=0.1, siPrefix=True)
        self.ctrl.radiusSpin.setOpts(suffix='m', value=80e-6, dec=True, step=0.1, siPrefix=True)
        self.ctrl.spontSpin.setOpts(suffix='Hz', value=0, step=0.1, siPrefix=True)
        self.ctrl.significanceSpin.setOpts(value=0.05)
        
        self.outline = SpatialOutline()
        self.data = None ## will be a record array with 1 row per stimulation - needs to contain fields xpos, ypos, numOfPostEvents, significance
        
        self.ctrl.processBtn.clicked.connect(self.process)
        
    def getOutline(self):
        return self.outline
    
    def setData(self, arr=None, xPos=None, yPos=None, numOfPostEvents=None):
        if arr is not None:
            self.checkArrayInput(arr)
            fields = arr.dtype.names
            if 'xPos' not in fields or 'yPos' not in fields or 'numOfPostEvents' not in fields:
                raise HelpfulException("Array input to Spatial correlator needs to have the following fields: 'xPos', 'yPos', 'numOfPostEvents'")
        elif arr is None:
            self.data = None
            return
        
        self.data = np.zeros(len(arr), dtype=arr.dtype.descr + [('prob', float)])
        self.data[:] = arr
        
        if 'numOfPreEvents' in fields and 'PreRegionLen' in fields:
            self.calculateSpontRate()
        self.process()
        
    @staticmethod
    def checkArrayInput(arr):
        fields = arr.dtype.names
        if 'xPos' not in fields or 'yPos' not in fields or 'numOfPostEvents' not in fields:
            raise HelpfulException("Array input needs to have the following fields: 'xPos', 'yPos', 'numOfPostEvents'. Current fields are: %s" %str(fields))  
        else:
            return True
    
    def process(self):
        if self.ctrl.disableChk.isChecked():
            return
        SpatialCorrelator.bendelsSpatialCorrelationAlgorithm(self.data, self.ctrl.radiusSpin.value(), self.ctrl.spontSpin.value(), self.ctrl.deltaTSpin.value())
        spots = self.data[(1-self.data['prob'] < self.ctrl.significanceSpin.value())*(self.data['prob'] != 0)]
        if 'spotSize' in self.data.dtype.names:
            self.outline.setRadius(self.data[1]['spotSize']/2.)
        self.outline.setData(spots)
    
    @staticmethod    
    def bendelsSpatialCorrelationAlgorithm(data, radius, spontRate, timeWindow):
        SpatialCorrelator.checkArrayInput(data) ## check that data has 'xPos', 'yPos' and 'numOfPostEvents'
        
        ## add 'prob' field to data array
        if 'prob' not in data.dtype.names:
            arr = np.zeros(len(data), dtype=data.dtype.descr + [('prob', float)])
            arr[:] = data     
            data = arr
        else:
            data['prob']=0
            
    
        
        ## spatial correlation algorithm from :
        ## Bendels, MHK; Beed, P; Schmitz, D; Johenning, FW; and Leibold C. Etection of input sites in 
        ## scanning photostimulation data based on spatial correlations. 2010. Journal of Neuroscience Methods.
        
        ## calculate probability of seeing a spontaneous event in time window
        p = 1-np.exp(-spontRate*timeWindow)
        
        ## for each spot, calculate the probability of having the events in nearby spots occur randomly
        for x in data:
            spots = data[(np.sqrt((data['xPos']-x['xPos'])**2+(data['yPos']-x['yPos'])**2)) < radius]
            nSpots = len(spots)
            nEventSpots = len(spots[spots['numOfPostEvents'] > 0])
            
            prob = 0
            for j in range(nEventSpots, nSpots+1):
                prob += ((p**j)*((1-p)**(nSpots-j))*math.factorial(nEventSpots))/(math.factorial(j)*math.factorial(nSpots-j))
            #j = arange(nEventSponts, nSpots+1)
            #prob = (((p**j)*((1-p)**(nSpots-j))*np.factorial(nEventSpots))/(np.factorial(j)*np.factorial(nSpots-j))).sum() ## need a factorial function that works on arrays
                
            x['prob'] = prob
        
        return data
    
    def calculateSpontRate(self):
        spontRate = float(self.data['numOfPreEvents'].sum())/self.data['PreRegionLen'].sum()
        self.ctrl.spontSpin.setValue(spontRate)
        

class SpatialOutline(pg.GraphicsObject):
    
    def __init__(self, parent=None, pen=None, spots=None, radius=25e-6):
        pg.GraphicsObject.__init__(self, parent)
        
        if pen is None:
            pen = (255, 255, 255)
        self.setPen(pen)   
        
        self.path = QtGui.QPainterPath()
        self.spots = spots
        self.radius = radius
        if spots is not None:
            self.makePath()
            
    def setData(self, spots):
        self.spots = spots
        self.makePath()
        self.update(self.boundingRect())
        
    def setRadius(self, radius):
        self.radius = radius
        self.makePath()
        self.update(self.boundingRect())
        
        
    def setPen(self, pen):
        self.pen = pg.mkPen(pen)
        self.currentPen = self.pen
        self.update()    
        
    def makePath(self):
        if self.spots is None:
            return
        path = QtGui.QPainterPath()
        for s in self.spots:
            path.addEllipse(s['xPos'], s['yPos'], self.radius, self.radius)
            
        #pps = QtGui.QPainterPathStroker()
        
        #self.path = pps.createStroke(path)
        self.path=path
    
    def boundingRect(self):
        if self.spots is None:
            return QtCore.QRectF()
        #x = self.spots['xPos'].min()
        #y = self.spots['yPos'].min()
        #return QtCore.QRectF(x,y , self.spots['xPos'].max()-x, self.spots['yPos'].max()-y)
        #print "outline.boundingRect: ", self.path.boundingRect()
        return self.path.boundingRect()

    def paint(self, p, *args):
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        #path = self.shape()
        p.setPen(self.currentPen)
        p.drawPath(self.path)
        #p.setPen(QtGui.QPen(QtGui.QColor(255,0,0)))
        #p.drawPath(self.shape())
        p.setPen(QtGui.QPen(QtGui.QColor(0,0,255)))
        p.drawRect(self.boundingRect())    