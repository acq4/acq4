# -*- coding: utf-8 -*-
from __future__ import print_function
import acq4.util.Qt as Qt
import acq4.pyqtgraph as pg
import numpy as np
import acq4.pyqtgraph.opengl as gl 
import acq4.Manager
import acq4.analysis.atlas.CochlearNucleus as cn

man = acq4.Manager.getManager()
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
    w.setRenderHints(Qt.QPainter.Antialiasing | Qt.QPainter.TextAntialiasing | Qt.QPainter.SmoothPixmapTransform)
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
        g.cellScale = Qt.QGraphicsLineItem(0.0, 0.0, sbLength, 0.0)
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
        
def showMap(dh=None):
    """
    Display a graphic of an input map for the currently selected cell
    """
    
    global v, g, atlas
    if dh is None:
        dh = man.currentFile
    db = man.getModule('Data Manager').currentDatabase()
    v.clear()
    
    cd = dh
    sd = cd.parent()
    atlas.loadState(sd)
    
    g = atlas.schematicGraphicsItems(contours=False, sliceScale=10, cellDir=cd)
    v.addItem(g)
    
    cellGroup = pg.ItemGroup()
    g.cellGroup = cellGroup
    cellScale = 10.
    cellGroup.scale(cellScale, cellScale)
    cellGroup.setParentItem(g)
    
    g.atlasScale.hide()
    g.arrowGroup.hide()
    
    ## reposition/rescale atlas group
    b1 = g.atlasGroup.mapRectToParent(g.atlasGroup.childrenBoundingRect())
    b2 = g.sliceClip.mapRectToParent(g.sliceClip.boundingRect())
    g.atlasGroup.setPos(b2.right()-b1.left()+0.001, b2.top()-b1.top())
    
    b1 = g.atlasGroup.mapRectToParent(g.atlasGroup.childrenBoundingRect())    
    bounds = b1 | b2
    
    if cd.exists('morphology.png'):
        ## small image to go over slice schematic
        imgf = cd['morphology.png']
        imgd = pg.colorToAlpha(imgf.read(), np.array([255,255,255]))
        mimg1 = pg.ImageItem(imgd)
        tr = pg.SRTTransform(imgf.info()['userTransform'])
        mimg1.setTransform(tr)
        mimg1.setParentItem(g.sliceGroup)
        mimg1.setZValue(100)
        g.cellImg1 = mimg1
        
        ## larger image to be displayed above
        mimg2 = pg.ImageItem(imgd)
        mimg2.setParentItem(cellGroup)
        mimg2.setTransform(tr * g.sliceGroup.transform())
        mimg2.scale(1.0 / g.sliceScaleFactor, 1.0 / g.sliceScaleFactor)
        #angle = pg.SRTTransform(g.sliceGroup.transform()).getRotation()
        #mimg2.rotate(angle)
        g.cellImg2 = mimg2
        cellGroup.scale(5,5)
        
        ## reposition next to slice schematic
        imgBounds = g.mapRectFromItem(mimg2, mimg2.boundingRect())
        pos = pg.Point(bounds.right()-imgBounds.left(), bounds.bottom()-imgBounds.bottom()) 
        cellGroup.setPos(pos)
    
        ## add scale bar
        sbLength = 50e-6
        g.cellScale = Qt.QGraphicsLineItem(0.0, 0.0, sbLength, 0.0)
        g.cellScale.setPen(pg.mkPen(color=0.0, width=5))
        g.cellScale.setZValue(10)
        g.cellScale.text = pg.TextItem(u"%d µm" % int(sbLength*1e6), anchor=(0.5, 1), color=(0,0,0))
        g.cellScale.text.setParentItem(g.cellScale)
        g.cellScale.text.setPos(sbLength*0.5, -50e-6/cellScale)
        #g.cellScale = pg.ScaleBar(sbLength)
        g.cellScale.setParentItem(cellGroup)
        corner = mimg2.mapToParent(mimg2.boundingRect()).boundingRect().bottomRight()
        g.cellScale.setPos(corner + pg.Point(-sbLength/2., -sbLength/3.))
    pos = pg.SRTTransform(cd.info()['userTransform']).map(pg.Point(0,0))
    size = pg.Point(30e-6, 30e-6)
    g.cellMarker = Qt.QGraphicsEllipseItem(Qt.QRectF(pos-size, pos+size))
    g.cellMarker.setBrush(pg.mkBrush(100,100,255,150))
    g.cellMarker.setPen(pg.mkPen('k', width=0.5))
    g.cellMarker.setParentItem(g.sliceGroup)
    g.cellMarker.setZValue(90)
        
    sites = db.select('map_site_view', ['ProtocolDir', 'HasInput'], where={'CellDir': cd})
    if len(sites) > 0:
        tr = sites[0]['ProtocolDir'].parent().info().get('userTransform', None)
        if tr is None:
            tr = pg.SRTTransform()
        else:
            tr = pg.SRTTransform(tr)
            
        pos = []
        size = sites[0]['ProtocolDir'].info()['Scanner']['spotSize']
        brushes = []
        for site in sites:
            pd = site['ProtocolDir']
            x,y = pd.info()['Scanner']['position']
            p2 = tr.map(pg.Point(x,y))
            pos.append((p2.x(), p2.y()))
            if site['HasInput']:
                brushes.append(pg.mkBrush('w'))
            else:
                brushes.append(pg.mkBrush(None))
        inputMap = pg.ScatterPlotItem(pos=np.array(pos), size=size, brush=brushes, pen=(0,0,0,50), pxMode=False, antialias=True)
        g.sliceGroup.addItem(inputMap)
        g.inputMap = inputMap
        inputMap.setZValue(50)
    
    
    cell = dh
    sl = cell.parent()
    day = sl.parent()
    name = day.shortName() + "_" + sl.shortName() + "_" + cell.shortName()
    rec = db.select('DirTable_Cell', '*', where={'Dir': cd})[0]
    
    name += "\nType: " + str(rec['CellType']) + "   Temp: " + str(rec['Temperature']) + "   Internal: " + str(rec['Internal']) + "   Age:" + str(rec['Age']) + "   Raccess: " + str(rec['AccessResistance'])
    name += "\nDirect Area: %s>0pA %s>20pA %s>100pA" % (str(rec['DirectAreaGt0']), str(rec['DirectAreaGt20']), str(rec['DirectAreaGt100']))
    name += "   Direct n spikes: " + str(rec['DirectNSpikes'])
    name += "\nSpont Ex Decay: %s   Spont In Decay: %s" % (str(rec['SpontExDecay1']), str(rec['SpontInDecay']))
    name += "\nExcitatory input" if (rec['EvokedExDecay'] is not None or rec['EvokedExAmp'] is not None) else ""
    print(rec)
    #name += '\nDirect Slow Decay: %s %s' % (str(rec['DirectAreaGT0']), str(rec['DirectAreaGT0']))
    
    
    
    g.cellName = pg.TextItem(name, color=(0,0,0))
    g.cellName.setParentItem(g)
    g.cellName.setPos(0, bounds.bottom())
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
                    Qt.QApplication.processEvents()
                    Qt.QApplication.processEvents()
                    
                    name = day.shortName() + "_" + sl.shortName() + "_" + cell.shortName() + ".svg"
                    ex = pg.exporters.SVGExporter.SVGExporter(v.scene())
                    ex.export(name)
                    print(name)
                    
                    if dlg.wasCanceled():
                        raise Exception("export cancelled")
                    
                    
def exportAllMaps():
    global v
    db = man.getModule('Data Manager').currentDatabase()
    cells = db.select('DirTable_Cell', ['Dir'], where={'MapOK': 1})
    cells.sort(key=lambda c: c['Dir'].name())
    with pg.ProgressDialog("exporting all..", 0, 1000) as dlg:
        for rec in cells:
            cell = rec['Dir']
            sl = cell.parent()
            day = sl.parent()
            
            showMap(cell)
            Qt.QApplication.processEvents()
            Qt.QApplication.processEvents()
            
            name = 'map_' + day.shortName() + "_" + sl.shortName() + "_" + cell.shortName() + ".svg"
            ex = pg.exporters.SVGExporter.SVGExporter(v.scene())
            ex.export(name)
            print(name)
            
            if dlg.wasCanceled():
                raise Exception("export cancelled")