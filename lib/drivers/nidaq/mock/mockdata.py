#!/usr/bin/python -i
from helpers import *
from numpy.random import normal, random, poisson, exponential

dataFiles = {
    'cam': 'mock_camera.dat',
    'cell': 'mock_cell.dat'
}

data = None

def getMockData(name):
    global data, dataFiles
    
    if data is None:
        useCache = True
        for f in dataFiles:
            dataFiles[f] = os.path.join(os.path.split(__file__)[0], dataFiles[f])
            if not os.path.isfile(dataFiles[f]):
                useCache = False
        if useCache:
            print "Loading cached data for", name
            data = {
                'cam':  MetaArray(file=dataFiles['cam']).view(ndarray),
                'cell': MetaArray(file=dataFiles['cell']).view(ndarray)
            }
        else:
            print "Generating data for", name
            (cell, cam) = getData()
            data = {
                'cam': (cam*2**12).astype(uint16),
                'cell': cell
            }
            MetaArray(data['cam']).write(dataFiles['cam'])
            MetaArray(cell).write(dataFiles['cell'])
    else:
        print "Returning pre-generated data", name
    return data[name]



def getData():
    recordTime = 20
    sampleRate = 20000
    pspTau = 1.0e-3
    caDecayTau = 0.2
    numCells = 20
    connectRate = 0.2
    interconnectRate = 0.00
    visibility = 0.5
    cellNoise = 1e-3
    pspStrength = 10e-3
    spontRate = 3.
    cellSize = 6.
    
    width = 160
    expTime = 0.01
    frameRate = 25
    imageNoise = 0.003
    
    
    class Cell:
        def __init__(self):
            self.spontRate = 0.
            self.connected = False
            self.pspStrength = 0
            self.cells = []
            self.spikes = []
            self.mpot = -60e-3
            self.visible = False
            self.trace = zeros((sampleRate*recordTime,), dtype=float32)
            self.caTrace = zeros((sampleRate*recordTime,), dtype=float32)
            self.caSignal = 0.03
    
    # decide on network topology, cell properties
    
    print "Generating network..."
    cells = []
    
    totVis = int(numCells * visibility)
    totConn = int(numCells * connectRate)
    totVisConn = int(clip(normal(loc=numCells*connectRate*visibility, scale=1.0), 3.0, 7.0))
    #totVisConn = 1
    #totConn = 1
    #totVis = 5
    print totVis, totConn, totVisConn
    
    for i in range(0, numCells):
        cell = Cell()
        cell.spontRate = abs(normal(loc=spontRate, scale=spontRate))
        cell.connected = cell.visible = False
        if i < totConn or i < totVisConn:
            cell.connected = True
        if (i < totVisConn) or (i >= totConn and i < totConn + totVis): 
            cell.visible = True
        cell.pos = (random(), random())
        cell.pspStrength = normal(loc=pspStrength, scale=pspStrength)
        if random() < 0.5:
            cell.pspStrength *= -1.0
        cell.caSignal = 1.0
        cell.caDS = 1.02 + (random() * 0.04)
        cell.size = normal(cellSize)
        cell.image = generateSphere(cell.size)
        if cell.visible:
            cell.x = cell.pos[0]*(width-cell.image.shape[0])
            cell.y = cell.pos[1]*(width-cell.image.shape[1])
        cells.append(cell)
    
    #ind = 0
    #while totVis < 3:
        #if not cells[ind].visible:
            #cells[ind].visible = True
            #totVis += 1
    
    
    for i in range(0, numCells):
        for j in range(0, numCells):
            if random() < interconnectRate:
                cells[i].cells.append(cells[j])
    
    
    # circle connected neurons
    print "Cell connections:"
    conCells = []
    for cell in cells:
        if cell.connected:
            if cell.visible:
                if cell.pspStrength > 0:
                    print "  %d: visible excitatory at (%f, %f), strength=%f, SR=%f, CS=%f" % (len(conCells), cell.x, cell.y, cell.pspStrength, cell.spontRate, cell.caDS)
                    conCells.append(cell)
                    #pen = QtGui.QPen(QtGui.QColor(100, 255, 100))
                else:
                    print "  %d: visible inhibitory at (%f, %f), strength=%f, SR=%f, CS=%f" % (len(conCells), cell.x, cell.y, cell.pspStrength, cell.spontRate, cell.caDS)
                    conCells.append(cell)
                    #pen = QtGui.QPen(QtGui.QColor(100, 100, 255))
                #e = imgWin.scene.addEllipse(cell.x, cell.y, cell.image.shape[0], cell.image.shape[1], pen)
                #e.setZValue(1)
            else:
                if cell.pspStrength > 0:
                    print "  %d: invisible excitatory, strength=%f, SR=%f" % (len(conCells), cell.pspStrength, cell.spontRate)
                    conCells.append(cell)
                else:
                    print "  %d: invisible inhibitory, strength=%f, SR=%f" % (len(conCells), cell.pspStrength, cell.spontRate)
                    conCells.append(cell)
    
    
    # generate list of AP times for each cell
    
    print "Generating spike trains... (%d samples)" % (sampleRate * recordTime)
    t = 0.0
    dt = 1.0 / sampleRate
    for i in range(0, sampleRate * recordTime):
        if i % 1000 == 0:
            print i
        for c in range(0, numCells):
            cells[c].spike = False
            if cells[c].mpot > 0.:
                cells[c].mpot = -90e-3
            #cells[c].prob += (1.0 - cells[c].prob) * 100. * dt
            cells[c].mpot += (-60e-3 - cells[c].mpot) * 100. * dt
            cells[c].caSignal += (1.0-cells[c].caSignal) * (dt / caDecayTau) 
            cells[c].mpot += normal(scale=cellNoise)
            prob = (cells[c].spontRate * dt)
            prob += (1.0-prob)  / (1.0 + exp(-4000 * (cells[c].mpot + 30e-3)))
            if random() < prob:
                cells[c].spikes.append(t)
                cells[c].mpot = 20e-3
                cells[c].caSignal *= cells[c].caDS
                cells[c].spike = True
            cells[c].trace[i] = cells[c].mpot
            cells[c].caTrace[i] = cells[c].caSignal
            
        for c in range(0, numCells):
            if cells[c].spike:
                for cell in cells[c].cells:
                    cell.mpot += cells[c].pspStrength
        t += dt
    
    # generate recording traces
    print "Generating traces..."
    
    vcTrace = zeros((2,sampleRate*recordTime), dtype=float32)
    #cameraTrace = zeros((2,sampleRate*recordTime), dtype=float32)
    image = zeros(((frameRate*recordTime) - 1, width, width), dtype=float32)
    
    t = 0.0
    dt = 1.0 / sampleRate
    v = 0
    lastShutter = 0.
    frame = 0
    intFrames = 0
    tau = 1.0e-3
    tSize = tau * 10 * sampleRate
    template = empty((tSize,), dtype=float)
    for i in range(0, int(tSize)):
        template[i] = alpha(i*dt, tau)
    
    vcTrace[0, :] = -65e-3
    
    
    for cell in cells:
        if cell.connected:
            for spike in cell.spikes:
                t = spike * sampleRate
                x = vcTrace[0, t:t+tSize]
                x += template[0:x.shape[0]] * cell.pspStrength
            
    for i in range(0, sampleRate * recordTime):
        #v += - v * 100. * dt
        vcTrace[0,i] += normal(scale=cellNoise)
        #for cell in cells:
            #if cell.connected:
                #for spike in cell.spikes:
                    #if spike > t-dt and spike <= t:
                        #v += cell.pspStrength
        #vcTrace[0,i] = v
        #vcTrace[1,i] = t
        #cameraTrace[1,i] = t
        
        if t-lastShutter > 1.0/frameRate:
            lastShutter = t
            if frame < image.shape[0]:
                image[frame] /= intFrames
            intFrames = 0
            frame += 1
        elif t-lastShutter > expTime:
            vcTrace[1,i] = 0.0
        elif frame < image.shape[0]:
            vcTrace[1,i] = 1.0
            for cell in cells:
                if cell.visible:
                    #cell.x = cell.pos[0]*(width-cell.image.shape[0])
                    #cell.y = cell.pos[1]*(width-cell.image.shape[1])
                    image[frame, cell.x:cell.x+cell.image.shape[0], cell.y:cell.y+cell.image.shape[1]] += cell.image * (cell.caTrace[i]-0.99)
                    intFrames += 1
        t += dt
        
    vcTrace[1,0] = 0.0
        
    if frame < image.shape[0]:
        image[frame] /= intFrames
        
    bg = blur(abs(normal(size=(1, image.shape[1], image.shape[2]))), [0, 15, 15])
    bg -= bg.min() * 0.9
    image2 = (blur(image, (0, 2, 2)) + 1.) * bg
    image2 *= normal(loc=1.0, scale=imageNoise, size=image.shape)
    
    #imgWin = showImg(image2, title="Raw data")
    #images[0].trace()
    #vcPlot = showPlot(vcTrace[0], title="Physiology")
    #vcPlot.addPlot(vcTrace[1] * 0.5 * vcTrace[0].max())
    

    return (vcTrace, image2)
