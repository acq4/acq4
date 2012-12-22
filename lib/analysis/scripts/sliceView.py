import pyqtgraph as pg
import numpy as np
import pyqtgraph.opengl as gl 
import lib.Manager
import lib.analysis.atlas.CochlearNucleus as cn

man = lib.Manager.getManager()
initialized = False

def __reload__(old):  ## re-use existing objects if module is reloaded
    global initialized, w, v, atlas
    initialized = True
    w = old['w']
    v = old['v']
    atlas = old['atlas']

if not initialized:
    atlas = cn.CochlearNucleus()
    w = pg.GraphicsWindow()
    w.setBackground(pg.mkColor('w'))
    v = w.addViewBox()
    v.setAspectLocked()
    v.invertY()
    w.show()
    initialized = True

def show():
    """
    Display a graphic of the currently selected slice / cell
    """
    
    global v, g, atlas
    v.clear()
    if 'cell' in man.currentFile.shortName().lower():
        cd = man.currentFile
        sd = cd.parent()
    else:
        sd = man.currentFile
        cd = None
    atlas.loadState(sd)
    g = atlas.schematicGraphicsItems()
    v.addItem(g)
    
    if cd is not None:
        imgf = cd['morphology.png']
        imgd = pg.colorToAlpha(imgf.read(), np.array([255,255,255]))
        mimg1 = pg.ImageItem(imgd)
        tr = pg.SRTTransform(imgf.info()['userTransform'])
        mimg1.setTransform(tr)
        mimg1.setParentItem(g.sliceGroup)
        g.cellImg1 = mimg1
        
        cellScale = 30.
        mimg2 = pg.ImageItem(imgd)
        mimg2.setTransform(tr * g.sliceGroup.transform())
        mimg2.scale(cellScale, cellScale)
        g.cellImg2 = mimg2
        
        b1 = g.atlasGroup.mapRectToParent(g.atlasGroup.childrenBoundingRect())
        b2 = g.sliceGroup.mapRectToParent(g.sliceGroup.childrenBoundingRect())
        bounds = b1 | b2
        print bounds
        mimg2.setParentItem(g)
        imgBounds = g.mapRectFromItem(mimg2, mimg2.boundingRect())
        print imgBounds
        pos = pg.Point(bounds.center().x() - imgBounds.center().x(), bounds.top()-imgBounds.bottom()) 
        mimg2.setPos(pos)
        
        ## add scale bar
        sbLength = 100e-6
        g.cellScale = pg.QtGui.QGraphicsLineItem(0.0, 0.0, sbLength * cellScale, 0.0)
        g.cellScale.setPen(pg.mkPen(color=0.0, width=100e-6, cosmetic=False))
        g.cellScale.setParentItem(g)
        g.cellScale.setZValue(10)
        g.cellScale.text = pg.TextItem("100 um", anchor=(0.5, 1), color=(0,0,0))
        g.cellScale.text.setParentItem(g.cellScale)
        g.cellScale.text.setPos(sbLength*0.5*cellScale, -50e-6)
        g.cellScale.setPos(0, bounds.top())