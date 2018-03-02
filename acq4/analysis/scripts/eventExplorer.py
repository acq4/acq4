from __future__ import print_function
from acq4.util import Qt
import acq4.Manager
import acq4.pyqtgraph as pg
import acq4.pyqtgraph.opengl as gl

import numpy as np
import acq4.util.functions as fn
import re
man = acq4.Manager.getManager() 

## update DB field to reflect dir meta info
#for i in db.select('Cell', ['rowid']):                                                                                                          
    #d = db.getDir('Cell', i[0])
    #typ = d.info().get('type', '')
    #db.update('Cell', {'type': typ}, rowid=i[0])
    #print d, typ

global eventView, siteView, cells
eventView = 'events_view'
siteView = 'sites_view'


firstRun = False
if 'events' not in locals():
    global events
    events = {}
    firstRun = True

    win = Qt.QMainWindow()
    #cw = Qt.QWidget()
    layout = pg.LayoutWidget()
    #layout = Qt.QGridLayout()
    #layout.setContentsMargins(0,0,0,0)
    #layout.setSpacing(0)
    #cw.setLayout(layout)
    win.setCentralWidget(layout)

    cellCombo = Qt.QComboBox()
    cellCombo.setSizeAdjustPolicy(cellCombo.AdjustToContents)
    layout.addWidget(cellCombo)
    
    reloadBtn = Qt.QPushButton('reload')
    layout.addWidget(reloadBtn)
    
    separateCheck = Qt.QCheckBox("color pre/post")
    layout.addWidget(separateCheck)
    
    colorCheck = Qt.QCheckBox("color y position")
    layout.addWidget(colorCheck)
    
    errLimitSpin = pg.SpinBox(value=0.7, step=0.1)
    layout.addWidget(errLimitSpin)

    lengthRatioLimitSpin = pg.SpinBox(value=1.5, step=0.1)
    layout.addWidget(lengthRatioLimitSpin)

    postRgnStartSpin = pg.SpinBox(value=0.500, step=0.01, siPrefix=True, suffix='s')
    layout.addWidget(postRgnStartSpin)

    postRgnStopSpin = pg.SpinBox(value=0.700, step=0.01, siPrefix=True, suffix='s')
    layout.addWidget(postRgnStopSpin)

    spl1 = Qt.QSplitter()
    spl1.setOrientation(Qt.Qt.Vertical)
    layout.addWidget(spl1, row=1, col=0, rowspan=1, colspan=8)

    pw1 = pg.PlotWidget()
    spl1.addWidget(pw1)
    pw1.setLabel('left', 'Amplitude', 'A')
    pw1.setLabel('bottom', 'Decay Tau', 's')

    spl2 = Qt.QSplitter()
    spl2.setOrientation(Qt.Qt.Horizontal)
    spl1.addWidget(spl2)

    pw2 = pg.PlotWidget(labels={'bottom': ('time', 's')})
    spl2.addWidget(pw2)
    
    tab = Qt.QTabWidget()
    spl2.addWidget(tab)
    
    
    ## For viewing cell morphology
    gv = pg.GraphicsView()
    gv.setBackgroundBrush(pg.mkBrush('w'))
    image = pg.ImageItem()
    gv.addItem(image)
    gv.enableMouse()
    gv.setAspectLocked(True)
    tab.addTab(gv, 'Morphology')

    ## 3D atlas
    import acq4.analysis.atlas.CochlearNucleus as CN
    atlas = CN.CNAtlasDisplayWidget()
    atlas.showLabel('DCN')
    atlas.showLabel('AVCN')
    atlas.showLabel('PVCN')
    tab.addTab(atlas, 'Atlas')
    
    atlasPoints = gl.GLScatterPlotItem()
    atlas.addItem(atlasPoints)
    
    win.show()
    win.resize(1000,800)

    sp1 = pw1.scatterPlot([], pen=pg.mkPen(None), brush=(200,200,255,70), identical=True, size=8)
    sp2 = pw1.scatterPlot([], pen=pg.mkPen(None), brush=(255,200,200,70), identical=True, size=8)
    sp3 = pw1.scatterPlot([], pen=pg.mkPen(None), brush=(100,255,100,70), identical=True, size=8)
    sp4 = pw1.scatterPlot([], pen=pg.mkPen(None), size=8)

    


    print("Reading cell list...")
    
    #import os, pickle
    #md = os.path.abspath(os.path.split(__file__)[0])
    #cacheFile = os.path.join(md, 'eventCache.p')
    #if os.path.isfile(cacheFile):
        #print "Read from cache..."
        #ev = pickle.load(open(cacheFile, 'r'))
    #else:
    
    
    
        #pickle.dump(ev, open(cacheFile, 'w'))
    ## create views that link cell information to events/sites
    db = man.getModule('Data Manager').currentDatabase()
    if not db.hasTable(siteView):
        print("Creating DB views.")
        db.createView(siteView, ['photostim_sites', 'DirTable_Protocol', 'DirTable_Cell'])  ## seems to be unused.
    if not db.hasTable(eventView):
        db.createView(eventView, ['photostim_events', 'DirTable_Protocol', 'DirTable_Cell'])
        
    cells = db.select(siteView, ['CellDir'], distinct=True)
    cells = [c['CellDir'] for c in cells]
    cells.sort(lambda a,b: cmp(a.name(), b.name()))
    
    cellCombo.addItem('')
    for c in cells:
        cellCombo.addItem(c.name(relativeTo=man.baseDir))
    #cellSpin.setMaximum(len(cells)-1)
    print("Done.")

    
    
def loadCell(cell, reloadData=False):
    global events
    if reloadData:
        events.pop(cell, None)
    if cell in events:
        return
    db = man.getModule('Data Manager').currentDatabase()
    mod = man.dataModel
    
    allEvents = []
    hvals = {}
    nEv = 0
    positionCache = {}
    tcache = {}
    print("Loading all events for cell", cell)
    tot = db.select(eventView, 'count()', where={'CellDir': cell})[0]['count()']
    print(tot, "total events..")
    
    with pg.ProgressDialog('Loading event data...', maximum=tot, wait=0) as dlg:
        for ev in db.iterSelect(eventView, ['ProtocolSequenceDir', 'SourceFile', 'fitAmplitude', 'fitTime', 'fitDecayTau', 'fitRiseTau', 'fitTimeToPeak', 'fitLengthOverDecay', 'fitFractionalError', 'userTransform', 'CellType', 'CellDir', 'ProtocolDir'], where={'CellDir': cell}, toArray=True, chunkSize=200):
            extra = np.empty(ev.shape, dtype=[('right', float), ('anterior', float), ('dorsal', float), ('holding', float)])
            
            ## insert holding levels
            for i in range(len(ev)):
                sd = ev[i]['ProtocolSequenceDir']
                if sd not in hvals:
                    cf = ev[i]['SourceFile']
                    hvals[sd] = mod.getClampHoldingLevel(cf)
                    #print hvals[sd], cf
                extra[i]['holding'] = hvals[sd]
                
            ## insert positions
    
            for i in range(len(ev)):
                protoDir = ev[i]['SourceFile'].parent()
                key = protoDir
                #key = (ev[i]['ProtocolSequenceDir'], ev[i]['SourceFile'])
                if key not in positionCache:
                    #try:
                        #dh = ev[i]['ProtocolDir']
                        #p1 = pg.Point(dh.info()['Scanner']['position'])
                        #if key[0] not in tcache:
                            #tr = pg.SRTTransform()
                            #tr.restoreState(dh.parent().info()['userTransform'])
                            #tcache[key[0]] = tr
                        #trans = tcache[key[0]]
                        #p2 = trans.map(p1)
                        #pcache[key] = (p2.x(),p2.y())
                    #except:
                        #print key
                        #raise
                    rec = db.select('CochlearNucleus_Protocol', where={'ProtocolDir': protoDir})
                    if len(rec) == 0:
                        pos = (None, None, None)
                    elif len(rec) == 1:
                        pos = (rec[0]['right'], rec[0]['anterior'], rec[0]['dorsal'])
                    elif len(rec) == 2:
                        raise Exception("Multiple position records for %s!" % str(protoDir))
                    positionCache[key] = pos
                extra[i]['right'] = positionCache[key][0]
                extra[i]['anterior'] = positionCache[key][1]
                extra[i]['dorsal'] = positionCache[key][2]
            
                
            ev = fn.concatenateColumns([ev, extra])
            allEvents.append(ev)
            nEv += len(ev)
            dlg.setValue(nEv)
            if dlg.wasCanceled():
                raise Exception('Canceled by user.')
    ev = np.concatenate(allEvents)
    
    numExSites = 0
    numInSites = 0
    for site in db.select(siteView, 'ProtocolSequenceDir', where={'CellDir': cell}):
        h = hvals.get(site['ProtocolSequenceDir'],None)
        if h is None:
            continue
        if h > -0.02:
            numInSites += 1
        elif h < -0.04:
            numExSites += 1
    
    events[cell] = (ev, numExSites, numInSites)
    
    
    
    
def init():
    if not firstRun:
        return
    cellCombo.currentIndexChanged.connect(showCell)
    separateCheck.toggled.connect(showCell)
    colorCheck.toggled.connect(showCell)
    errLimitSpin.valueChanged.connect(showCell)
    lengthRatioLimitSpin.valueChanged.connect(showCell)
    reloadBtn.clicked.connect(reloadCell)
    for s in [sp1, sp2, sp3, sp4]:
        s.sigPointsClicked.connect(plotClicked)

def plotClicked(plt, pts):
    pt = pts[0]
    #(id, fn, time) = pt.data
    
    #[['SourceFile', 'ProtocolSequenceDir', 'fitTime']]
    #fh = db.getDir('ProtocolSequence', id)[fn]
    fh = pt.data()['SourceFile']
    id = pt.data()['ProtocolSequenceDir']
    time = pt.data()['fitTime']
    
    data = fh.read()['Channel':'primary']
    data = fn.besselFilter(data, 8e3)
    p = pw2.plot(data, clear=True)
    pos = time / data.xvals('Time')[-1]
    arrow = pg.CurveArrow(p, pos=pos)
    xr = pw2.viewRect().left(), pw2.viewRect().right()
    if time < xr[0] or time > xr[1]:
        w = xr[1]-xr[0]
        pw2.setXRange(time-w/5., time+4*w/5., padding=0)
    
    fitLen = pt.data()['fitDecayTau']*pt.data()['fitLengthOverDecay']
    x = np.linspace(time, time+fitLen, fitLen * 50e3)
    v = [pt.data()['fitAmplitude'], pt.data()['fitTime'], pt.data()['fitRiseTau'], pt.data()['fitDecayTau']]
    y = fn.pspFunc(v, x, risePower=2.0) + data[np.argwhere(data.xvals('Time')>time)[0]-1]
    pw2.plot(x, y, pen='b')
    #plot.addItem(arrow)


def select(ev, ex=True):
    #if source is not None:
        #ev = ev[ev['CellDir']==source]
    if ex:
        ev = ev[ev['holding'] < -0.04]         # excitatory events
        ev = ev[(ev['fitAmplitude'] < 0) * (ev['fitAmplitude'] > -2e-10)]
    else:
        ev = ev[(ev['holding'] >= -0.02) * (ev['holding'] <= 0.01)]  ## inhibitory events
        ev = ev[(ev['fitAmplitude'] > 0) * (ev['fitAmplitude'] < 2e-10)]
    ev = ev[(0 < ev['fitDecayTau']) * (ev['fitDecayTau'] < 0.2)]   # select decay region
    
    ev = ev[ev['fitFractionalError'] < errLimitSpin.value()]
    ev = ev[ev['fitLengthOverDecay'] > lengthRatioLimitSpin.value()]
    return ev
    
def reloadCell():
    showCell(reloadData=True)

def showCell(**kwds):
    pw2.clear()
    reloadData = kwds.get('reloadData', False)
    #global lock
    #if lock:
        #return
    #lock = True
    Qt.QApplication.processEvents() ## prevents double-spin
    #lock = False
    cell = cells[cellCombo.currentIndex()-1]
    
    dh = cell #db.getDir('Cell', cell)
    loadCell(dh, reloadData=reloadData)
    
    try:
        image.setImage(dh['morphology.png'].read())
        gv.setRange(image.sceneBoundingRect())
    except:
        image.setImage(np.zeros((2,2)))
        pass
    
    ev, numExSites, numInSites = events[cell]
    
    ev2 = select(ev, ex=True)
    ev3 = select(ev, ex=False)
    
    if colorCheck.isChecked():
        sp1.hide()
        sp2.hide()
        sp3.hide()
        sp4.show()
        
        start = postRgnStart()
        stop = postRgnStop()
        ev2post = ev2[(ev2['fitTime']>start) * (ev2['fitTime']<stop)]
        ev3post = ev3[(ev3['fitTime']>start) * (ev3['fitTime']<stop)]
        ev4 = np.concatenate([ev2post, ev3post])
        
        yMax = ev4['dorsal'].max()
        yMin = ev4['dorsal'].min()
        brushes = []
        for i in range(len(ev4)):
            hue = 0.6*((ev4[i]['dorsal']-yMin) / (yMax-yMin))
            brushes.append(pg.hsvColor(hue, 1.0, 1.0, 0.3))
            #pts.append({
                #'pos': (ev4[i]['fitDecayTau'], ev4[i]['fitAmplitude']),
                #'brush': pg.hsvColor(hue, 1, 1, 0.3),
                #'data': ev4[i]
            #})
            
        sp4.setData(x=ev4['fitDecayTau'], y=ev4['fitAmplitude'], symbolBrush=brushes, data=ev4)
        
    else:
        sp1.show()
        sp2.show()
        #sp3.show()
        sp4.hide()
        
        ## excitatory
        if separateCheck.isChecked():
            pre = ev2[ev2['fitTime']< preRgnStop()]
            post = ev2[(ev2['fitTime'] > postRgnStart()) * (ev2['fitTime'] < postRgnStop())]
        else:
            pre = ev2
        
        sp1.setData(x=pre['fitDecayTau'], y=pre['fitAmplitude'], data=pre);
        #print "Cell ", cell
        #print "  excitatory:", np.median(ev2['fitDecayTau']), np.median(ev2['fitAmplitude'])
        
        ## inhibitory
        if separateCheck.isChecked():
            pre = ev3[ev3['fitTime']< preRgnStop()]
            post2 = ev3[(ev3['fitTime'] > postRgnStart()) * (ev3['fitTime'] < postRgnStop())]
            post = np.concatenate([post, post2])
        else:
            pre = ev3
        sp2.setData(x=pre['fitDecayTau'], y=pre['fitAmplitude'], data=pre);
        #print "  inhibitory:", np.median(ev2['fitDecayTau']), np.median(ev2['fitAmplitude'])
        
        if separateCheck.isChecked():
            sp3.setData(x=post['fitDecayTau'], y=post['fitAmplitude'], data=post)
            sp3.show()
        else:
            sp3.hide()
    
    try:
        typ = ev2[0]['CellType']
    except:
        typ = ev3[0]['CellType']
        
    sr = spontRate(ev2, numExSites)
    sri = spontRate(ev3, numInSites)
        
    title = "%s -- %s --- <span style='color: #99F;'>ex:</span> %s %s %s %0.1fHz --- <span style='color: #F99;'>in:</span> %s %s %s %0.1fHz" % (
        dh.name(relativeTo=dh.parent().parent().parent()), 
        typ,
        pg.siFormat(np.median(ev2['fitTimeToPeak']), error=np.std(ev2['fitTimeToPeak']), space=False, suffix='s'),
        pg.siFormat(np.median(ev2['fitDecayTau']), error=np.std(ev2['fitDecayTau']), space=False, suffix='s'),
        pg.siFormat(np.median(ev2['fitAmplitude']), error=np.std(ev2['fitAmplitude']), space=False, suffix='A'),
        sr,
        pg.siFormat(np.median(ev3['fitTimeToPeak']), error=np.std(ev3['fitTimeToPeak']), space=False, suffix='s'),
        pg.siFormat(np.median(ev3['fitDecayTau']), error=np.std(ev3['fitDecayTau']), space=False, suffix='s'),
        pg.siFormat(np.median(ev3['fitAmplitude']), error=np.std(ev3['fitAmplitude']), space=False, suffix='A'),
        sri)
    print(re.sub(r'<[^>]+>', '', title))
    
    pw1.setTitle(title)

    
    ### show cell in atlas
    #rec = db.select('CochlearNucleus_Cell', where={'CellDir': cell})
    #pts = []
    #if len(rec) > 0:
        #pos = (rec[0]['right'], rec[0]['anterior'], rec[0]['dorsal'])
        #pts = [{'pos': pos, 'size': 100e-6, 'color': (0.7, 0.7, 1.0, 1.0)}]
        
    ### show event positions
    evSpots = {}
    for rec in ev:
        p = (rec['right'], rec['anterior'], rec['dorsal'])
        evSpots[p] = None
        
    pos = np.array(list(evSpots.keys()))
    atlasPoints.setData(pos=pos, )
    
    
def spontRate(ev, n):
    ## This is broken. It does not take into account recordings that had no events.
    ev = ev[ev['fitTime'] < preRgnStop()]
    #count = {}
    #dirs = set()
    #for i in range(len(ev)):
        #key = (ev[i]['ProtocolSequenceDir'], ev[i]['SourceFile'])
        #dirs.add(set)
        #if key not in count:
            #count[key] = 0
        #count[key] += 1
    #sr = np.mean([v/(preRgnStop()) for v in count.itervalues()])
    if n == 0:
        return 0
    return len(ev) / (preRgnStop() * n)

def preRgnStop():
    return postRgnStartSpin.value() - 0.002
    
def postRgnStart():
    return postRgnStartSpin.value() + 0.002
    
def postRgnStop():
    return postRgnStopSpin.value()
    
init()