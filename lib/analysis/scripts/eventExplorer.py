from PyQt4 import QtCore, QtGui
import lib.Manager
import pyqtgraph as pg
import numpy as np
import functions as fn

man = lib.Manager.getManager() 

## update DB field to reflect dir meta info
#for i in db.select('Cell', ['rowid']):                                                                                                          
    #d = db.getDir('Cell', i[0])
    #typ = d.info().get('type', '')
    #db.update('Cell', {'type': typ}, rowid=i[0])
    #print d, typ

global eventView, siteView, cells
eventView = 'events_view'
siteView = 'sites_view'


## Get events
firstRun = False
if 'events' not in locals():
    global events
    events = {}
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

    


    print "Reading cell list..."
    
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
        print "Creating DB views."
        db.createView(siteView, ['photostim_sites', 'DirTable_Protocol', 'DirTable_Cell'])  ## seems to be unused.
    if not db.hasTable(eventView):
        db.createView(eventView, ['photostim_events', 'DirTable_Protocol', 'DirTable_Cell'])
        
    cells = db.select(siteView, ['CellDir'], distinct=True)
    cells = [c['CellDir'] for c in cells]
    #for c in cells:
        #print c, db.getDir('Cell', c)
    #cells.sort(lambda a,b: cmp(db.getDir('DirType_Cell', a).name(), db.getDir('DirType_Cell', b).name()))
    cells.sort(lambda a,b: cmp(a.name(), b.name()))
    cellSpin.setMaximum(len(cells)-1)
    print "Done."

def loadCell(cell):
    global events
    if cell in events:
        return
    db = man.getModule('Data Manager').currentDatabase()
    mod = man.dataModel
    
    allEvents = []
    hvals = {}
    nEv = 0
    pcache = {}
    tcache = {}
    print "Loading all events for cell", cell
    tot = db.tableLength(eventView)
    for ev in db.iterSelect(eventView, ['ProtocolSequenceDir', 'SourceFile', 'fitAmplitude', 'fitTime', 'fitDecayTau', 'fitRiseTau', 'userTransform', 'type', 'CellDir', 'ProtocolDir'], where={'CellDir': cell}, toArray=True):
        extra = np.empty(ev.shape, dtype=[('x', float), ('y', float), ('holding', float)])
        
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
            key = (ev[i]['ProtocolSequenceDir'], ev[i]['SourceFile'])
            if key not in pcache:
                try:
                    dh = ev[i]['ProtocolDir']
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
            extra[i]['x'] = pcache[key][0]
            extra[i]['y'] = pcache[key][1]
        ev = fn.concatenateColumns([ev, extra])
        allEvents.append(ev)
        nEv += len(ev)
        print "    Loaded %d / %d events" % (nEv, tot)
    ev = np.concatenate(allEvents)
    events[cell] = ev
    
    
def init():
    if not firstRun:
        return
    cellSpin.valueChanged.connect(showCell)
    separateCheck.toggled.connect(showCell)
    colorCheck.toggled.connect(showCell)
    for s in [sp1, sp2, sp3, sp4]:
        s.sigPointsClicked.connect(plotClicked)

def plotClicked(plt, pts):
    pt = pts[0]
    #(id, fn, time) = pt.data
    
    #[['SourceFile', 'ProtocolSequenceDir', 'fitTime']]
    #fh = db.getDir('ProtocolSequence', id)[fn]
    fh = pt.data['SourceFile']
    id = pt.data['ProtocolSequenceDir']
    time = pt.data['fitTime']
    
    data = fh.read()['Channel':'primary']
    p = pw2.plot(data, clear=True)
    pos = time / data.xvals('Time')[-1]
    arrow = pg.CurveArrow(p, pos=pos)
    xr = pw2.viewRect().left(), pw2.viewRect().right()
    if time < xr[0] or time > xr[1]:
        w = xr[1]-xr[0]
        pw2.setXRange(time-w/5., time+4*w/5., padding=0)
    
    x = np.linspace(time, time+pt.data['fitDecayTau']*5, 1000)
    v = [pt.data['fitAmplitude'], pt.data['fitTime'], pt.data['fitRiseTau'], pt.data['fitDecayTau']]
    y = fn.pspFunc(v, x, risePower=1.0) + data[np.argwhere(data.xvals('Time')>time)[0]]
    pw2.plot(x, y, pen='b')
    #plot.addItem(arrow)


def select(ev, ex=True):
    #if source is not None:
        #ev = ev[ev['CellDir']==source]
    if ex:
        ev = ev[ev['holding'] < -0.04]         # excitatory events
        ev = ev[(ev['fitAmplitude'] < 0) * (ev['fitAmplitude'] > -2e-10)]
    else:
        ev = ev[(ev['holding'] >= -0.01) * (ev['holding'] <= 0.01)]  ## inhibitory events
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
    
    dh = cell #db.getDir('Cell', cell)
    loadCell(dh)
    
    try:
        image.setImage(dh['morphology.png'].read())
        gv.setRange(image.sceneBoundingRect())
    except:
        image.setImage(np.zeros((2,2)))
        pass
    
    ev = events[cell]
    
    ev2 = select(ev, ex=True)
    ev3 = select(ev, ex=False)
    
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
                'data': ev4[i]
            })
        sp4.setData(pts)
        
    else:
        sp1.show()
        sp2.show()
        #sp3.show()
        sp4.hide()
        
        ## excitatory
        if separateCheck.isChecked():
            pre = ev2[ev2['fitTime']< 0.498]
            post = ev2[(ev2['fitTime'] > 0.502) * (ev2['fitTime'] < 0.7)]
        else:
            pre = ev2
        
        sp1.setData(x=pre['fitDecayTau'], y=pre['fitAmplitude'], data=pre);
        #print "Cell ", cell
        #print "  excitatory:", np.median(ev2['fitDecayTau']), np.median(ev2['fitAmplitude'])
        
        ## inhibitory
        if separateCheck.isChecked():
            pre = ev3[ev3['fitTime']< 0.498]
            post2 = ev3[(ev3['fitTime'] > 0.502) * (ev3['fitTime'] < 0.7)]
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
        typ = ev2[0]['type']
    except:
        typ = ev3[0]['type']
        
    sr = spontRate(ev2)
        
    pw1.setTitle(
        "%s -- %s --- <span style='color: #99F;'>ex:</span> %s %s %0.1fHz --- <span style='color: #F99;'>in:</span> %s %s" % (
        dh.name(relativeTo=dh.parent().parent().parent()), 
        typ,
        pg.siFormat(np.median(ev2['fitDecayTau']), space=False, suffix='s'),
        pg.siFormat(np.median(ev2['fitAmplitude']), space=False, suffix='A'),
        sr,
        pg.siFormat(np.median(ev3['fitDecayTau']), space=False, suffix='s'),
        pg.siFormat(np.median(ev3['fitAmplitude']), space=False, suffix='A'),
    ))

def spontRate(ev):
    ev = ev[ev['fitTime'] < 0.498]
    count = {}
    for i in range(len(ev)):
        key = (ev[i]['ProtocolSequenceDir'], ev[i]['SourceFile'])
        if key not in count:
            count[key] = 0
        count[key] += 1
    sr = np.mean([v/0.498 for v in count.itervalues()])
    return sr

init()