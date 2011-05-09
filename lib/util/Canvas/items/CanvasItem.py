# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore, QtSvg
from pyqtgraph import widgets
import pyqtgraph as pg

class SelectBox(widgets.ROI):
    def __init__(self, scalable=False):
        #QtGui.QGraphicsRectItem.__init__(self, 0, 0, size[0], size[1])
        widgets.ROI.__init__(self, [0,0], [1,1])
        center = [0.5, 0.5]
            
        if scalable:
            self.addScaleHandle([1, 1], center, lockAspect=True)
            self.addScaleHandle([0, 0], center, lockAspect=True)
        self.addRotateHandle([0, 1], center)
        self.addRotateHandle([1, 0], center)

class CanvasItem(QtCore.QObject):
    
    sigResetUserTransform = QtCore.Signal(object)
    sigTransformChangeFinished = QtCore.Signal(object)
    sigTransformChanged = QtCore.Signal(object)
    
    """CanvasItem takes care of managing an item's state--alpha, visibility, z-value, transformations, etc. and
    provides a control widget"""
    
    sigVisibilityChanged = QtCore.Signal(object)
    transformCopyBuffer = None
    
    def __init__(self, item, **opts):
        defOpts = {'name': None, 'z': None, 'movable': True, 'scalable': False, 'handle': None, 'visible': True, 'parent':None} #'pos': [0,0], 'scale': [1,1], 'angle':0,
        defOpts.update(opts)
        self.opts = defOpts
        self.selectedAlone = False  ## whether this item is the only one selected
        
        QtCore.QObject.__init__(self)
        self.canvas = None
        self._graphicsItem = item
        
        z = self.opts['z']
        if z is not None:
            item.setZValue(z)

        self.ctrl = QtGui.QWidget()
        self.layout = QtGui.QGridLayout()
        self.layout.setSpacing(0)
        self.ctrl.setLayout(self.layout)
        
        self.alphaLabel = QtGui.QLabel("Alpha")
        self.alphaSlider = QtGui.QSlider()
        self.alphaSlider.setMaximum(1023)
        self.alphaSlider.setOrientation(QtCore.Qt.Horizontal)
        self.alphaSlider.setValue(1023)
        self.layout.addWidget(self.alphaLabel, 0, 0)
        self.layout.addWidget(self.alphaSlider, 0, 1)
        self.resetTransformBtn = QtGui.QPushButton('Reset Transform')
        self.copyBtn = QtGui.QPushButton('Copy')
        self.pasteBtn = QtGui.QPushButton('Paste')
        self.layout.addWidget(self.resetTransformBtn, 1, 0, 1, 2)
        self.layout.addWidget(self.copyBtn, 2, 0, 1, 1)
        self.layout.addWidget(self.pasteBtn, 2, 1, 1, 1)
        self.alphaSlider.valueChanged.connect(self.alphaChanged)
        self.alphaSlider.sliderPressed.connect(self.alphaPressed)
        self.alphaSlider.sliderReleased.connect(self.alphaReleased)
        #self.canvas.sigSelectionChanged.connect(self.selectionChanged)
        self.resetTransformBtn.clicked.connect(self.resetTransformClicked)
        self.copyBtn.clicked.connect(self.copyClicked)
        self.pasteBtn.clicked.connect(self.pasteClicked)
        
        if 'transform' in self.opts:
            self.baseTransform = self.opts['transform']
        else:
            self.baseTransform = pg.Transform()
            if 'pos' in self.opts:
                self.baseTransform.translate(self.opts['pos'])
            if 'angle' in self.opts:
                self.baseTransform.rotate(self.opts['angle'])
            if 'scale' in self.opts:
                self.baseTransform.scale(self.opts['scale'])

        ## create selection box (only visible when selected)
        tr = self.baseTransform.saveState()
        if 'scalable' not in opts and tr['scale'] == (1,1):
            self.opts['scalable'] = True
            
        ## every CanvasItem implements its own individual selection box 
        ## so that subclasses are free to make their own.
        self.selectBox = SelectBox(scalable=self.opts['scalable'])
        #self.canvas.scene().addItem(self.selectBox)
        self.selectBox.hide()
        self.selectBox.setZValue(1e6)
        self.selectBox.sigRegionChanged.connect(self.selectBoxChanged)  ## calls selectBoxMoved
        self.selectBox.sigRegionChangeFinished.connect(self.selectBoxChangeFinished)

        ## set up the transformations that will be applied to the item
        ## (It is not safe to use item.setTransform, since the item might count on that not changing)
        self.itemRotation = QtGui.QGraphicsRotation()
        self.itemScale = QtGui.QGraphicsScale()
        self._graphicsItem.setTransformations([self.itemRotation, self.itemScale])
        
        self.tempTransform = pg.Transform() ## holds the additional transform that happens during a move - gets added to the userTransform when move is done.
        self.userTransform = pg.Transform() ## stores the total transform of the object
        self.resetUserTransform() 
        self.selectBoxBase = self.selectBox.getState().copy()
        
        ## reload user transform from disk if possible
        if self.opts['handle'] is not None:
            trans = self.opts['handle'].info().get('userTransform', None)
            if trans is not None:
                self.restoreTransform(trans)
                
        #print "Created canvas item", self
        #print "  base:", self.baseTransform
        #print "  user:", self.userTransform
        #print "  temp:", self.tempTransform
        #print "  bounds:", self.item.sceneBoundingRect()

    def setCanvas(self, canvas):
        ## Called by canvas whenever the item is added.
        ## It is our responsibility to add all graphicsItems to the canvas's scene
        ## The canvas will automatically add our graphicsitem, 
        ## so we just need to take care of the selectbox.
        if canvas is self.canvas:
            return
            
        if canvas is None:
            self.canvas.removeFromScene(self._graphicsItem)
            self.canvas.removeFromScene(self.selectBox)
        else:
            canvas.addToScene(self._graphicsItem)
            canvas.addToScene(self.selectBox)
        self.canvas = canvas

    def graphicsItem(self):
        """Return the graphicsItem for this canvasItem."""
        return self._graphicsItem

    #def name(self):
        #return self.opts['name']
    def handle(self):
        """Return the file handle for this item, if any exists."""
        return self.opts['handle']
                             
    def copyClicked(self):
        CanvasItem.transformCopyBuffer = self.saveTransform()
        
    def pasteClicked(self):
        t = CanvasItem.transformCopyBuffer
        if t is None:
            return
        else:
            self.restoreTransform(t)

    def hasUserTransform(self):
        #print self.userRotate, self.userTranslate
        return not self.userTransform.isIdentity()

    def ctrlWidget(self):
        return self.ctrl
        
    def alphaChanged(self, val):
        alpha = val / 1023.
        self._graphicsItem.setOpacity(alpha)
        
    def isMovable(self):
        return self.opts['movable']
        
    def setMovable(self, m):
        self.opts['movable'] = m
        
    def selectBoxMoved(self):
        """The selection box has moved; get its transformation information and pass to the graphics item"""
        self.userTransform = self.selectBox.getGlobalTransform(relativeTo=self.selectBoxBase)
        self.updateTransform()
        
    def setTemporaryTransform(self, transform):
        self.tempTransform = transform
        self.updateTransform()
    
    def applyTemporaryTransform(self):
        """Collapses tempTransform into UserTransform, resets tempTransform"""
        self.userTransform = self.userTransform * self.tempTransform ## order is important!
        self.resetTemporaryTransform()
        self.selectBoxFromUser()  ## update the selection box to match the new userTransform
    
    def resetTemporaryTransform(self):
        self.tempTransform = pg.Transform()  ## don't use Transform.reset()--this transform might be used elsewhere.
        self.updateTransform()
        
    def transform(self): 
        return self._graphicsItem.transform()

    def updateTransform(self):
        """Regenerate the item position from the base, user, and temp transforms"""
        transform = self.baseTransform * self.userTransform * self.tempTransform ## order is important
        
        s = transform.saveState()
        self._graphicsItem.setPos(*s['pos'])
        
        self.itemRotation.setAngle(s['angle'])
        self.itemScale.setXScale(s['scale'][0])
        self.itemScale.setYScale(s['scale'][1])
        
    def resetUserTransform(self):
        #self.userRotate = 0
        #self.userTranslate = pg.Point(0,0)
        self.userTransform.reset()
        self.updateTransform()
        
        self.selectBox.blockSignals(True)
        self.selectBoxToItem()
        self.selectBox.blockSignals(False)
        self.sigTransformChanged.emit(self)
        self.sigTransformChangeFinished.emit(self)
        
    def resetTransformClicked(self):
        self.resetUserTransform()
        self.sigResetUserTransform.emit(self)
        
    def restoreTransform(self, tr):
        try:
            #self.userTranslate = pg.Point(tr['trans'])
            #self.userRotate = tr['rot']
            self.userTransform = pg.Transform(tr)
            
            self.selectBoxFromUser() ## move select box to match
            self.updateTransform()
            self.sigTransformChanged.emit(self)
            self.sigTransformChangeFinished.emit(self)
        except:
            #self.userTranslate = pg.Point([0,0])
            #self.userRotate = 0
            self.userTransform = pg.Transform()
            debug.printExc("Failed to load transform:")
        #print "set transform", self, self.userTranslate
        
    def saveTransform(self):
        #print "save transform", self, self.userTranslate
        #return {'trans': list(self.userTranslate), 'rot': self.userRotate}
        return self.userTransform.saveState()
    
    def selectBoxFromUser(self):
        """Move the selection box to match the current userTransform"""
        ## user transform
        #trans = QtGui.QTransform()
        #trans.translate(*self.userTranslate)
        #trans.rotate(-self.userRotate)
        
        #x2, y2 = trans.map(*self.selectBoxBase['pos'])
        
        self.selectBox.blockSignals(True)
        self.selectBox.setState(self.selectBoxBase)
        self.selectBox.applyGlobalTransform(self.userTransform)
        #self.selectBox.setAngle(self.userRotate)
        #self.selectBox.setPos([x2, y2])
        self.selectBox.blockSignals(False)
        

    def selectBoxToItem(self):
        """Move/scale the selection box so it fits the item's bounding rect. (assumes item is not rotated)"""
        rect = self._graphicsItem.sceneBoundingRect()
        self.itemRect = self._graphicsItem.boundingRect()
        self.selectBox.blockSignals(True)
        self.selectBox.setPos([rect.x(), rect.y()])
        self.selectBox.setSize(rect.size())
        self.selectBox.setAngle(0)
        self.selectBox.blockSignals(False)

    def zValue(self):
        return self.opts['z']
        
    def setZValue(self, z):
        self.opts['z'] = z
        if z is not None:
            self._graphicsItem.setZValue(z)
        
    #def selectionChanged(self, canvas, items):
        #self.selected = len(items) == 1 and (items[0] is self) 
        #self.showSelectBox()
           
           
    def selectionChanged(self, sel, multi):
        """
        Inform the item that its selection state has changed. 
        Arguments:
            sel: bool, whether the item is currently selected
            multi: bool, whether there are multiple items currently selected
        """
        self.selectedAlone = sel and not multi
        self.showSelectBox()
        
    def showSelectBox(self):
        """Display the selection box around this item if it is selected and movable"""
        if self.selectedAlone and self.isMovable() and self.isVisible():  #and len(self.canvas.itemList.selectedItems())==1:
            self.selectBox.show()
        else:
            self.selectBox.hide()
        
    def hideSelectBox(self):
        self.selectBox.hide()
        
                
    def selectBoxChanged(self):
        self.selectBoxMoved()
        #self.updateTransform(self.selectBox)
        #self.emit(QtCore.SIGNAL('transformChanged'), self)
        self.sigTransformChanged.emit(self)
        
    def selectBoxChangeFinished(self):
        #self.emit(QtCore.SIGNAL('transformChangeFinished'), self)
        self.sigTransformChangeFinished.emit(self)

    def alphaPressed(self):
        """Hide selection box while slider is moving"""
        self.hideSelectBox()
        
    def alphaReleased(self):
        self.showSelectBox()
        
    def show(self):
        if self.opts['visible']:
            return
        self.opts['visible'] = True
        self._graphicsItem.show()
        self.showSelectBox()
        self.sigVisibilityChanged.emit(self)
        
    def hide(self):
        if not self.opts['visible']:
            return
        self.opts['visible'] = False
        self._graphicsItem.hide()
        self.hideSelectBox()
        self.sigVisibilityChanged.emit(self)

    def setVisible(self, vis):
        if vis:
            self.show()
        else:
            self.hide()

    def isVisible(self):
        return self.opts['visible']
