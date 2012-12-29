# -*- coding: utf-8 -*-
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
    w.setRenderHints(pg.QtGui.QPainter.Antialiasing | pg.QtGui.QPainter.TextAntialiasing | pg.QtGui.QPainter.SmoothPixmapTransform)
    w.setBackground(pg.mkColor('w'))
    v = w.addViewBox()
    v.setAspectLocked()
    v.invertY()
    w.show()
    initialized = True

def show(dh=None):
    """
    Display a graphic of the currently selected slice / cell
    """
    
    global v, g, atlas
    if dh is None:
        dh = man.currentFile
    v.clear()
    
    if 'cell' in dh.shortName().lower():
        cd = dh
        sd = cd.parent()
    else:
        sd = dh
        cd = None
    atlas.loadState(sd)
    g = atlas.schematicGraphicsItems()
    v.addItem(g)
    
    if cd is not None:
        ## small image to go over slice schematic
        imgf = cd['morphology.png']
        imgd = pg.colorToAlpha(imgf.read(), np.array([255,255,255]))
        mimg1 = pg.ImageItem(imgd)
        tr = pg.SRTTransform(imgf.info()['userTransform'])
        mimg1.setTransform(tr)
        mimg1.setParentItem(g.sliceGroup)
        g.cellImg1 = mimg1
        
        ## larger image to be displayed above
        cellGroup = pg.ItemGroup()
        g.cellGroup = cellGroup
        mimg2 = pg.ImageItem(imgd)
        mimg2.setParentItem(cellGroup)
        mimg2.setTransform(tr * g.sliceGroup.transform())
        mimg2.scale(1.0 / g.sliceScaleFactor, 1.0 / g.sliceScaleFactor)
        #angle = pg.SRTTransform(g.sliceGroup.transform()).getRotation()
        #mimg2.rotate(angle)
        cellScale = 50.
        cellGroup.scale(cellScale, cellScale)
        g.cellImg2 = mimg2
        
        ## reposition image above slice schematic
        b1 = g.atlasGroup.mapRectToParent(g.atlasGroup.childrenBoundingRect())
        b2 = g.sliceClip.mapRectToParent(g.sliceClip.boundingRect())
        bounds = b1 | b2
        cellGroup.setParentItem(g)
        imgBounds = g.mapRectFromItem(mimg2, mimg2.boundingRect())
        pos = pg.Point(bounds.center().x() - imgBounds.center().x(), bounds.top()-imgBounds.bottom()) 
        cellGroup.setPos(pos)
        
        ## add scale bar
        sbLength = 25e-6
        g.cellScale = pg.QtGui.QGraphicsLineItem(0.0, 0.0, sbLength, 0.0)
        g.cellScale.setPen(pg.mkPen(color=0.0, width=100e-6/cellScale, cosmetic=False))
        g.cellScale.setParentItem(cellGroup)
        g.cellScale.setZValue(10)
        g.cellScale.text = pg.TextItem(u"25 µm", anchor=(0.5, 1), color=(0,0,0))
        g.cellScale.text.setParentItem(g.cellScale)
        g.cellScale.text.setPos(sbLength*0.5, -50e-6/cellScale)
        corner = mimg2.mapToParent(mimg2.boundingRect()).boundingRect().bottomRight()
        g.cellScale.setPos(corner + pg.Point(-sbLength/2., -sbLength/3.))
        
        cell = dh
        sl = cell.parent()
        day = sl.parent()
        name = day.shortName() + "_" + sl.shortName() + "_" + cell.shortName()
        g.cellName = pg.TextItem(name, color=(0,0,0))
        g.cellName.setParentItem(cellGroup)
        g.cellName.setPos(corner + pg.Point(-sbLength*4,-sbLength/4.))
        ## auto-range the view
        #bounds = bounds | g.mapFromItem(mimg2, mimg2.boundingRect()).boundingRect()
        #v.setRange(bounds)
        
def exportAll():
    global v
    with pg.ProgressDialog("exporting all..", 0, 1000) as dlg:
        for day in man.baseDir.ls():
            day = man.baseDir[day]
            for sl in day.ls():
                if 'slice' not in sl:
                    continue
                sl = day[sl]
                for cell in sl.ls():
                    if 'cell' not in cell:
                        continue
                    cell = sl[cell]
                    try:
                        m = cell['morphology.png']
                    except:
                        continue
                    
                    show(cell)
                    pg.QtGui.QApplication.processEvents()
                    pg.QtGui.QApplication.processEvents()
                    
                    name = day.shortName() + "_" + sl.shortName() + "_" + cell.shortName() + ".svg"
                    ex = pg.exporters.SVGExporter.SVGExporter(v.scene())
                    ex.export(name)
                    print name
                    
                    if dlg.wasCanceled():
                        raise Exception("export cancelled")