from PyQt4 import QtCore, QtGui
import lib.Manager
import pyqtgraph as pg
import numpy as np
import functions as fn

man = lib.Manager.getManager() 
db = man.getModule('Data Manager').currentDatabase()
mod = man.dataModel

## update DB field to reflect dir meta info
#for i in db.select('Cell', ['rowid']):                                                                                                          
    #d = db.getDir('Cell', i[0])
    #typ = d.info().get('type', '')
    #db.update('Cell', {'type': typ}, rowid=i[0])
    #print d, typ

##Make DB view linking photostim_sites -> ProtocolSequence -> Cell
#db('CREATE VIEW "sites" AS select * from photostim_sites inner join ProtocolSequence on photostim_sites.sourceDir = ProtocolSequence.rowid inner join Cell on ProtocolSequence.source = Cell.rowid')


##Make DB view linking events -> ProtocolSequence -> Cell
#db('CREATE VIEW "events" AS select * from photostim_events inner join ProtocolSequence on photostim_events.sourceDir = ProtocolSequence.rowid inner join Cell on ProtocolSequence.source = Cell.rowid')

## Get events
firstRun = False
if 'ev' not in locals():
    firstRun = True

    win = QtGui.QMainWindow()
    cw = QtGui.QWidget()
    layout = QtGui.QGridLayout()
    layout.setContentsMargins(0,0,0,0)
    layout.setSpacing(0)
    cw.setLayout(layout)
    win.setCentralWidget(cw)

    cellSpin = QtGui.QSpinBox()
    layout.addWidget(cellSpin, 0, 0)
    
    separateCheck = QtGui.QCheckBox("color pre/post")
    layout.addWidget(separateCheck, 0, 1)
    
    colorCheck = QtGui.QCheckBox("color y position")
    layout.addWidget(colorCheck, 0, 2)

    spl1 = QtGui.QSplitter()
    spl1.setOrientation(QtCore.Qt.Vertical)
    layout.addWidget(spl1, 1, 0, 1, 3)

    pw1 = pg.PlotWidget()
    spl1.addWidget(pw1)
    pw1.setLabel('left', 'Amplitude', 'A')
    pw1.setLabel('bottom', 'Decay Tau', 's')

    spl2 = QtGui.QSplitter()
    spl2.setOrientation(QtCore.Qt.Horizontal)
    spl1.addWidget(spl2)

    pw2 = pg.PlotWidget()
    gv = pg.GraphicsView()
    gv.setBackgroundBrush(pg.mkBrush('w'))
    image = pg.ImageItem()
    gv.addItem(image)
    gv.enableMouse()
    gv.setAspectLocked(True)
    spl2.addWidget(pw2)
    spl2.addWidget(gv)

    win.show()
    win.resize(1000,800)

    sp1 = pw1.scatterPlot([], pen=pg.mkPen(None), brush=(200,200,255,70), identical=True, size=8)
    sp2 = pw1.scatterPlot([], pen=pg.mkPen(None), brush=(255,200,200,70), identical=True, size=8)
    sp3 = pw1.scatterPlot([], pen=pg.mkPen(None), brush=(100,255,100,70), identical=True, size=8)
    sp4 = pw1.scatterPlot([], pen=pg.mkPen(None), size=8)



    print "Loading events..."
    
    import os, pickle
    md = os.path.abspath(os.path.split(__file__)[0])
    cacheFile = os.path.join(md, 'eventCache.p')
    if os.path.isfile(cacheFile):
        print "Read from cache..."
        ev = pickle.load(open(cacheFile, 'r'))
    else:
        ev = db.select('events', ['sourceDir', 'SourceFile', 'fitAmplitude', 'fitTime', 'fitDecayTau', 'userTransform', 'type', 'Source'], toArray=True)


        ## insert holding levels
        print "Reading holding levels..."
        holding = np.empty(ev.shape)
        hvals = {}
        for i in range(len(ev)):
            sd = ev[i]['sourceDir']
            if sd not in hvals:
                cf = db.getDir('ProtocolSequence', sd)[ev[i]['SourceFile']]
                hvals[sd] = mod.getClampHoldingLevel(cf)
                #print hvals[sd], cf
            holding[i] = hvals[sd]
            
        ## insert positions
        pos = np.empty(ev.shape, dtype=[('x', float), ('y', float)])

        print "Reading event positions..."
        pcache = {}
        tcache = {}
        for i in range(len(ev)):
            if i%1000 == 0:
                print i
            key = (ev[i]['sourceDir'], ev[i]['SourceFile'])
            if key not in pcache:
                try:
                    dh = db.getDir('ProtocolSequence', key[0])[key[1]].parent()
                    p1 = pg.Point(dh.info()['Scanner']['position'])
                    if key[0] not in tcache:
                        tr = pg.Transform()
                        tr.restoreState(dh.parent().info()['userTransform'])
                        tcache[key[0]] = tr
                    trans = tcache[key[0]]
                    p2 = trans.map(p1)
                    pcache[key] = (p2.x(),p2.y())
                except:
                    print key
                    raise
            pos[i] = pcache[key]

        ev = fn.concatenateColumns([ev, ('holding', holding.dtype, holding), pos])   
        pickle.dump(ev, cacheFile)
    cells = list(set(ev['Source']))
    cellSpin.setMaximum(len(cells)-1)
    print "Done."

def init():
    if not firstRun:
        return
    cellSpin.valueChanged.connect(showCell)
    separateCheck.toggled.connect(showCell)
    colorCheck.toggled.connect(showCell)
    for s in [sp1, sp2, sp3, sp4]:
        s.sigClicked.connect(plotClicked)

def plotClicked(plt, pts):
    pt = pts[0]
    (id, fn, time) = pt.data
    fh = db.getDir('ProtocolSequence', id)[fn]
    data = fh.read()['Channel':'primary']
    p = pw2.plot(data, clear=True)
    pos = time / data.xvals('Time')[-1]
    arrow = pg.CurveArrow(p, pos=pos)
    #plot.addItem(arrow)


def select(ev, source=None, ex=True):
    if source is not None:
        ev = ev[ev['Source']==source]
    if ex:
        ev = ev[ev['holding'] < -0.04]         # excitatory events
        ev = ev[(ev['fitAmplitude'] < 0) * (ev['fitAmplitude'] > -2e-10)]
    else:
        ev = ev[ev['holding'] >= 0.0]
        ev = ev[(ev['fitAmplitude'] > 0) * (ev['fitAmplitude'] < 2e-10)]
    ev = ev[(0 < ev['fitDecayTau']) * (ev['fitDecayTau'] < 0.2)]   # select decay region
    return ev
    

def showCell():
    pw2.clear()
    #global lock
    #if lock:
        #return
    #lock = True
    QtGui.QApplication.processEvents() ## prevents double-spin
    #lock = False
    cell = cells[cellSpin.value()]
    
    dh = db.getDir('Cell', cell)
    try:
        image.updateImage(dh['morphology.png'].read())
        gv.setRange(image.sceneBoundingRect())
    except:
        image.updateImage(np.zeros((2,2)))
        pass
    
    ev2 = select(ev, source=cell)
    ev3 = select(ev, source=cell, ex=False)
    
    if colorCheck.isChecked():
        sp1.hide()
        sp2.hide()
        sp3.hide()
        sp4.show()
        
        ev2 = ev2[(ev2['fitTime']>0.502) * (ev2['fitTime']<0.7)]
        ev3 = ev3[(ev3['fitTime']>0.502) * (ev3['fitTime']<0.7)]
        ev4 = np.concatenate([ev2, ev3])
        
        yMax = ev4['y'].max()
        yMin = ev4['y'].min()
        
        pts = []
        for i in range(len(ev4)):
            hue = 0.6*((ev4[i]['y']-yMin) / (yMax-yMin))
            pts.append({
                'pos': (ev4[i]['fitDecayTau'], ev4[i]['fitAmplitude']),
                'brush': pg.hsvColor(hue, 1, 1, 0.3),
                'data': (ev4[i]['sourceDir'], ev4[i]['SourceFile'], ev4[i]['fitTime'])
            })
        sp4.setPoints(pts)
        
    else:
        sp1.show()
        sp2.show()
        #sp3.show()
        sp4.hide()
        if separateCheck.isChecked():
            pre = ev2[ev2['fitTime']< 0.498]
            post = ev2[(ev2['fitTime'] > 0.502) * (ev2['fitTime'] < 0.7)]
        else:
            pre = ev2
        
        sp1.setPoints(x=pre['fitDecayTau'], y=pre['fitAmplitude'], data=pre[['SourceFile', 'sourceDir', 'fitTime']]);
        #print "Cell ", cell
        #print "  excitatory:", np.median(ev2['fitDecayTau']), np.median(ev2['fitAmplitude'])
        
        
        if separateCheck.isChecked():
            pre = ev3[ev3['fitTime']< 0.498]
            post2 = ev3[(ev3['fitTime'] > 0.502) * (ev3['fitTime'] < 0.7)]
            post = np.concatenate([post, post2])
        else:
            pre = ev3
        sp2.setPoints(x=pre['fitDecayTau'], y=pre['fitAmplitude'], data=pre[['SourceFile', 'sourceDir', 'fitTime']]);
        #print "  inhibitory:", np.median(ev2['fitDecayTau']), np.median(ev2['fitAmplitude'])
        
        if separateCheck.isChecked():
            sp3.setPoints(x=post['fitDecayTau'], y=post['fitAmplitude'], data=post[['SourceFile', 'sourceDir', 'fitTime']])
            sp3.show()
        else:
            sp3.hide()
    
    try:
        typ = ev2[0]['type']
    except:
        typ = ev3[0]['type']
        
    sr = spontRate(ev2)
        
    pw1.setTitle(
        "%s -- %s --- <span style='color: #99F;'>ex:</span> %s %s %0.1fHz --- <span style='color: #F99;'>in:</span> %s %s" % (
        dh.name(relativeTo=dh.parent().parent().parent()), 
        typ,
        fn.siFormat(np.median(ev2['fitDecayTau']), space=False, suffix='s'),
        fn.siFormat(np.median(ev2['fitAmplitude']), space=False, suffix='A'),
        sr,
        fn.siFormat(np.median(ev3['fitDecayTau']), space=False, suffix='s'),
        fn.siFormat(np.median(ev3['fitAmplitude']), space=False, suffix='A'),
    ))

def spontRate(ev):
    ev = ev[ev['fitTime'] < 0.498]
    count = {}
    for i in range(len(ev)):
        key = (ev[i]['sourceDir'], ev[i]['SourceFile'])
        if key not in count:
            count[key] = 0
        count[key] += 1
    sr = np.median([v/0.498 for v in count.itervalues()])
    return sr

init()