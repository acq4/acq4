# -*- coding: utf-8 -*-
import CtrlTemplate
import WidgetGroup
import advancedTypes
import lib.analysis.atlas.Atlas as Atlas
#import DataManager
import os
from PyQt4 import QtCore, QtGui
import DataManager

class AuditoryCortex(Atlas.Atlas):
    def __init__(self, canvas=None, state=None):
        ## define slice planes and the atlas images to use for each
        scale = 3.78e-6
        #scale = 5.5e-6
        #pos = (-676*scale/2., -577*scale/2.)
        pos = (-681*scale/2., -231e-6)
        #pos = (0.0, 0.0)
        self.slicePlanes = advancedTypes.OrderedDict([
            ('Thalamocortical', [('ThalamocorticalMarker.svg', scale, pos)]),
            ('Coronal', []),
        ])
        
        self.ctrl = None
        self.canvas = canvas
        if canvas is not None:
            atlasDir = os.path.split(os.path.abspath(__file__))[0]
            #fh = DataManager.getHandle(os.path.join(atlasDir, 'CN_coronal.png'))
            #self.image = canvas.addImage(fh, pos=pos, scale=(scale, scale))
            #self.image.setMovable(False)
            self.images = []
            self.ctrl = QtGui.QWidget()
            self.ui = CtrlTemplate.Ui_Form()
            self.ui.setupUi(self.ctrl)
            self.stateGroup = WidgetGroup.WidgetGroup(self.ctrl)
            self.ui.slicePlaneCombo.clear()
            for sp in self.slicePlanes:
                self.ui.slicePlaneCombo.addItem(sp)
            #self.ui.slicePlaneCombo.currentIndexChanged.connect(self.slicePlaneChanged)
            #self.ui.hemisphereCombo.currentIndexChanged.connect(self.hemisphereChanged)
            #self.ui.photoCheck.stateChanged.connect(self.photoCheckChanged)
            #self.ui.drawingCheck.stateChanged.connect(self.drawingCheckChanged)
            #self.ui.thicknessSpin.valueChanged.connect(self.thicknessSpinChanged)
            self.stateGroup.sigChanged.connect(self.uiChanged)
            #self.ui.reAlignAtlasBtn.clicked.connect(self.reAlignAtlas)
            #self.connect(canvas, QtCore.SIGNAL('itemTransformChangeFinished'), self.itemMoved) ## old style
            self.canvas.sigItemTransformChangeFinished.connect(self.itemMoved) ## new style
            
        Atlas.Atlas.__init__(self, canvas, state)
        
    def ctrlWidget(self):
        return self.ctrl
        
    def saveState(self):
        return self.state.copy()
        
    def restoreState(self, state):
        self.state.update(state)
        self.update()
        
    def update(self):
        if self.ctrl is not None:
            self.stateGroup.setState(self.state)
            
            
    def uiChanged(self):
        for item in self.images:
            self.canvas.removeItem(item)
        self.images = []
        
        state = self.stateGroup.state()
        slice = state['slicePlaneCombo']
        hem = state['hemisphereCombo']
        #flip = state['flipCheck']
        
        imgs = self.slicePlanes[slice]
        atlasDir = os.path.split(os.path.abspath(__file__))[0]
        
        for imgFile, scale, pos in imgs:
            fh = DataManager.getHandle(os.path.join(atlasDir, 'images', imgFile))
            item = self.canvas.addFile(fh, pos=pos, scale=[scale,scale], index=0, movable=False, z=10000)
            self.images.append(item)
        
            
    def close(self):
        for item in self.images:
            self.canvas.removeItem(item)
        self.images = []
    
    def itemMoved(self, canvas, item):
        """Save an item's transformation if the user has moved it. 
        This is saved in the 'userTransform' attribute; the original position data is not affected."""
        if item not in self.images:
            return
        #fh = self.items[item]
        fh = item.handle()
        trans = item.saveTransform()
        fh.setInfo(userTransform=trans)
        #print "saved", fh.shortName()
        
    #def reAlignAtlas(self):
        
        #file, scale, pos = self.slicePlanes[self.stateGroup.state()['slicePlaneCombo']]:
        
        #trans = self.images[0].saveTransform()
        
        
        
        
    
    