# -*- coding: utf-8 -*-
#import CtrlTemplate
#import acq4.pyqtgraph.WidgetGroup
#import acq4.util.advancedTypes as advancedTypes
from __future__ import print_function
import collections
import acq4.analysis.atlas.Atlas as Atlas
import os
from acq4.util import Qt
import acq4.util.DataManager as DataManager
from acq4.analysis.atlas.AuditoryCortex.CortexROI import CortexROI
import numpy as np
import acq4.pyqtgraph as pg
import scipy
from acq4.util.debug import Profiler



class AuditoryCortex(Atlas.Atlas):
    
    DBIdentity = "AuditoryCortexAtlas" ## owner key used for asking DB which tables are safe to use
    
    def __init__(self, state=None):
        Atlas.Atlas.__init__(self, state=None)
        self._ctrl = None
        #self.setState(state)  
        self.state = state

    def mapToAtlas(self, pos):
        """Maps obj into atlas coordinates."""
        matrix = self.getMatrix(pos)
        mapped = np.dot(matrix, [pos[0]*pos[1], pos[0], pos[1], 1])
        return mapped
        
    def getMatrix(self, pos):
        """Return the transformMatrix to use for the given pos."""
        quads = self.state['quadrilaterals']
        ind=None
        for i, q in enumerate(quads):
            if Qt.QPolygonF([Qt.QPointF(*x) for x in q]).containsPoint(Qt.QPointF(pos), Qt.Qt.OddEvenFill):
                ind = i
        if ind == None: ## in case pos is outside the quadrilaterals
            bestMin = 1000
            for i, q in enumerate(quads):
                dist = [pg.Point(x-pos).length() for x in q]
                minDist = min(dist)
                dist.remove(minDist)
                minDist += min(dist)
                if minDist < bestMin:
                    bestMin = minDist
                    ind = i    
            
        m = self.state['transformMatrices'][ind]
        return np.array([m[0], m[1]])
      
    def setState(self, state):
        #self._matrix = None
        self.state = state
    
    def solveBilinearTransform(self, points1, points2):
        """
        Find a bilinear transformation matrix (2x4) that maps points1 onto points2
        points must be specified as a list of 4 Vector, Point, QPointF, etc.
        
        To use this matrix to map a point [x,y]::
        
            mapped = np.dot(matrix, [x*y, x, y, 1])
        """
        ## A is 4 rows (points) x 4 columns (xy, x, y, 1)
        ## B is 4 rows (points) x 2 columns (x, y)
        A = np.array([[points1[i].x()*points1[i].y(), points1[i].x(), points1[i].y(), 1] for i in range(4)])
        B = np.array([[points2[i].x(), points2[i].y()] for i in range(4)])
        
        ## solve 2 sets of linear equations to determine transformation matrix elements
        matrix = np.zeros((2,4))
        for i in range(2):
            matrix[i] = scipy.linalg.solve(A, B[:,i])  ## solve Ax = B; x is one row of the desired transformation matrix
        
        return matrix    
    
    def getState(self):
        raise Exception("Must be reimplemented in subclass.")

    def restoreState(self, state):
        raise Exception("Must be reimplemented in subclass.")
        
    def name(self):
        return "AuditoryCortexAtlas"
        
    def ctrlWidget(self, host=None):
        if self._ctrl is None:
            if host is None:
                raise Exception("To initialize an A1AtlasCtrlWidget a host must be specified.")
            self._ctrl = A1AtlasCtrlWidget(self, host)
        return self._ctrl
    
    
class A1AtlasCtrlWidget(Atlas.AtlasCtrlWidget):
    
    def __init__(self, atlas, host):
        Atlas.AtlasCtrlWidget.__init__(self, atlas, host)
        
        self.atlasDir = os.path.split(os.path.abspath(__file__))[0]
        
        ## add ThalamocorticalMarker to canvas
        fh = DataManager.getHandle(os.path.join(self.atlasDir, 'images', 'ThalamocorticalMarker.svg'))
        self.canvas.addFile(fh, pos=(-0.001283, -0.000205), scale=[3.78e-6, 3.78e-6], index=0, movable=False, z=10000)        
     
        ## add CortexROI
        self.roi = CortexROI([-1e-3, 0])
        self.canvas.addGraphicsItem(self.roi, pos=(-1e-3, 1e-3), scale=[1e-3, 1e-3], name='CortexROI', movable=False)
        self.roi.sigRegionChangeFinished.connect(self.roiChanged)
        
    def loadState(self):
        if self.sliceDir is None:
            return
            
        state = self.sliceDir.info()['atlas'][self.atlas.name()]      
        self.roi.setState(state['cortexROI'])
        self.atlas.setState(state)
        
    def saveState(self):
        ## Saves the position/configuration of the cortexROI, as well as transforms for mapping to atlas coordinates
        
        if self.sliceDir is None:
            return       
       
        ## get state of ROI
        cortexROI = self.roi.saveState()
        quads = self.roi.getQuadrilaterals()
        newQuads = []
        for q in quads:
            newQuads.append([(p.x(), p.y()) for p in q])
        rects = self.roi.getNormalizedRects()
        matrices = []
        for i, q in enumerate(quads):
            matrix = self.atlas.solveBilinearTransform([pg.Point(x) for x in q], [pg.Point(x) for x in rects[i]])
            matrices.append([list(matrix[0]), list(matrix[1])])
        
        state = {
            'cortexROI':cortexROI,
            'quadrilaterals':newQuads,
            'normalizedRects': rects,
            'transformMatrices': matrices
        }
        
        ## write to slice directory meta-info
        atlasInfo = self.sliceDir.info().get('atlas', {}).deepcopy()
        atlasInfo[self.atlas.name()] = state
        self.sliceDir.setInfo(atlas=atlasInfo)
        
        ## set state for atlas object
        self.atlas.setState(state)       
        
    def generateDataArray(self, positions, dirType):
        prof = Profiler("A1Atlas.generateDataArray", disabled=True)
        
        if self.atlas.state is None:
            self.saveState()
        prof.mark('saved atlas state')
        
        dirColumn = dirType + 'Dir'
        if dirType == 'Protocol':
            data = np.empty(len(positions), dtype=[('SliceDir', object), 
                                                   (dirColumn, object), 
                                                   #('layer', float),
                                                   #('depth', float), 
                                                   ('yPosSlice', float),
                                                   ('yPosCell', float),
                                                   ('percentDepth', float), 
                                                   ('xPosSlice', float), 
                                                   ('xPosCell', float), 
                                                   ('modXPosSlice', float), 
                                                   ('modXPosCell', float)])
            fields = collections.OrderedDict([
                           ('SliceDir', 'directory:Slice'),
                           (dirColumn, 'directory:'+dirType),
                           ('yPosSlice', 'real'),
                           ('yPosCell', 'real'),
                           ('percentDepth', 'real'),
                           ('xPosSlice', 'real'),
                           ('xPosCell', 'real'),
                           ('modXPosSlice', 'real'),
                           ('modXPosCell', 'real')])            
            prof.mark("defined Protocol data array")
            
            for i in range(len(positions)):
                dh, pos = positions[i]
                cellPos = self.dataModel.getCellInfo(dh)['userTransform']['pos']
                mapped = self.atlas.mapToAtlas(pg.Point(pos)) ## needs to return %depth and modXPosSlice 
                #data[i] = (self.sliceDir, dh, mapped.x(), mapped.y(), mapped.z())
                data[i]['SliceDir'] = self.sliceDir
                data[i][dirColumn] = dh
                data[i]['yPosSlice'] = pos[1]
                data[i]['yPosCell'] = pos[1]-cellPos[1]
                data[i]['percentDepth'] = mapped[1]
                data[i]['xPosSlice'] = pos[0]
                data[i]['xPosCell'] = pos[0]-cellPos[0]
                data[i]['modXPosSlice'] = mapped[0]
                data[i]['modXPosCell'] = mapped[0]-self.atlas.mapToAtlas(pg.Point(cellPos))[0]   
            prof.mark("filled protocol data array")
            
        elif dirType == 'Cell':
            data = np.empty(len(positions), dtype=[('SliceDir', object), 
                                                    (dirColumn, object), 
                                                    #('layer', float),
                                                    #('depth', float), 
                                                    ('yPosSlice', float),
                                                    #('yPosCell', float),
                                                    ('percentDepth', float), 
                                                    ('xPosSlice', float), 
                                                    #('xPosCell', float), 
                                                    ('modXPosSlice', float), 
                                                    #('modXPosCell', float)
                                                    ]) 
            fields = collections.OrderedDict([
                ('SliceDir', 'directory:Slice'),
                (dirColumn, 'directory:'+dirType),
                ('yPosSlice', 'real'),
                ('percentDepth', 'real'),
                ('xPosSlice', 'real'),
                ('modXPosSlice', 'real')])
            prof.mark("defined cell data array")
            for i in range(len(positions)):
                dh, pos = positions[i]
                #cellPos = self.dataModel.getCellInfo(dh)['pos']
                mapped = self.atlas.mapToAtlas(pg.Point(pos)) ## needs to return %depth and modXPosSlice 
                #data[i] = (self.sliceDir, dh, mapped.x(), mapped.y(), mapped.z())
                data[i]['SliceDir'] = self.sliceDir
                data[i][dirColumn] = dh
                data[i]['yPosSlice'] = pos[1]
                #data['yPosCell'] = pos[1]-cellPos[1]
                data[i]['percentDepth'] = mapped[1]
                data[i]['xPosSlice'] = pos[0]
                #data['xPosCell'] = pos[0]-cellPos[0]
                data[i]['modXPosSlice'] = mapped[0]
                #data['modXPosCell'] = mapped[0]-self.atlas.mapToAtlas(pg.Point(cellPos))[0]   
            prof.mark("filled cell data array")
        else:
            prof.finish()
            raise Exception("Not sure how to structure data array for dirType=%s"%dirType)
        
        prof.finish()
        return data, fields
                
    def roiChanged(self):
        self.saveState()
            
            
            
class PreviousAuditoryCortex(Atlas.Atlas):
    def __init__(self, canvas=None, state=None):
        ## define slice planes and the atlas images to use for each
        scale = 3.78e-6
        #scale = 5.5e-6
        #pos = (-676*scale/2., -577*scale/2.)
        #pos = (-681*scale/2., -231e-6)
        #pos = (-681*scale/2., -231*scale/2.)
        pos = (-0.001283, -0.000205)
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
            self.ctrl = Qt.QWidget()
            self.ui = CtrlTemplate.Ui_Form()
            self.ui.setupUi(self.ctrl)
            self.stateGroup = pyqtgraph.WidgetGroup(self.ctrl)
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
            #self.connect(canvas, Qt.SIGNAL('itemTransformChangeFinished'), self.itemMoved) ## old style
            self.canvas.sigItemTransformChangeFinished.connect(self.itemMoved) ## new style
            
        Atlas.Atlas.__init__(self, state)
        self.uiChanged()
        
    def ctrlWidget(self, **args):
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
            #item = self.canvas.addFile(fh, index=0, movable=False)
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
        
        
        
        
    
    
