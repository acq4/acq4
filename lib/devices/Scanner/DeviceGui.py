# -*- coding: utf-8 -*-
from DeviceTemplate import Ui_Form
import time, os, sys
from PyQt4 import QtCore, QtGui
from lib.util.MetaArray import MetaArray
from lib.util.qtgraph.graphicsItems import ImageItem
import lib.Manager
from lib.util.imageAnalysis import *
from lib.util.debug import *

class ScannerDeviceGui(QtGui.QWidget):
    def __init__(self, dev):
        QtGui.QWidget.__init__(self)
        self.dev = dev
        self.ui = Ui_Form()
        self.ui.setupUi(self)

        ## Populate Device lists
        defCam = None
        if 'defaultCamera' in self.dev.config:
            defCam = self.dev.config['defaultCamera']
        defLaser = None
        if 'defaultLaser' in self.dev.config:
            defLaser = self.dev.config['defaultLaser']

        devs = self.dev.dm.listDevices()
        for d in devs:
            self.ui.cameraCombo.addItem(d)
            self.ui.laserCombo.addItem(d)
            if d == defCam:
                self.ui.cameraCombo.setCurrentIndex(self.ui.cameraCombo.count()-1)
            if d == defLaser:
                self.ui.laserCombo.setCurrentIndex(self.ui.laserCombo.count()-1)
            

        
        ## Populate list of calibrations
        self.updateCalibrationList()
        
        ## create graphics scene
        self.image = ImageItem()
        self.scene = QtGui.QGraphicsScene()
        self.ui.view.setScene(self.scene)
        self.scene.addItem(self.image)
        self.ui.view.setAspectLocked(True)
        self.ui.view.invertY()

        QtCore.QObject.connect(self.ui.calibrateBtn, QtCore.SIGNAL('clicked()'), self.calibrateClicked)
        QtCore.QObject.connect(self.ui.testBtn, QtCore.SIGNAL('clicked()'), self.testClicked)
        QtCore.QObject.connect(self.ui.deleteBtn, QtCore.SIGNAL('clicked()'), self.deleteClicked)
        
        
    def updateCalibrationList(self):
        self.ui.calibrationList.clear()
        
        ## Populate calibration lists
        index = self.dev.getCalibrationIndex()
        for cam in index:
            for laser in index[cam]:
                for obj in index[cam][laser]:
                    cal = index[cam][laser][obj]
                    spot = '%0.0f, %0.1f um' % (cal['spot'][0], cal['spot'][1]*1e6)
                    date = cal['date']
                    item = QtGui.QTreeWidgetItem([cam, obj, laser, str(spot), date])
                    self.ui.calibrationList.addTopLevelItem(item)
        
        
    def calibrateClicked(self):
        cam = str(self.ui.cameraCombo.currentText())
        laser = str(self.ui.laserCombo.currentText())
        obj = self.dev.getObjective(cam)
        
        ## Run calibration
        (cal, spot) = self.runCalibration()
        #cal = MetaArray((512, 512, 2))
        #spot = 100e-6
        date = time.strftime('%Y.%m.%d %H:%M', time.localtime())
        
        #fileName = cam + '_' + laser + '_' + obj + '.ma'
        index = self.dev.getCalibrationIndex()
        
        if cam not in index:
            index[cam] = {}
        if laser not in index[cam]:
            index[cam][laser] = {}
        index[cam][laser][obj] = {'spot': spot, 'date': date, 'params': cal}

        self.dev.writeCalibrationIndex(index)
        #cal.write(os.path.join(self.dev.config['calibrationDir'], fileName))
        
        self.updateCalibrationList()

    def testClicked(self):
        pass

    def deleteClicked(self):
        cur = self.ui.calibrationList.currentItem()
        cam = str(cur.text(0))
        obj = str(cur.text(1))
        laser = str(cur.text(2))
        
        index = self.dev.getCalibrationIndex()
        
        cal = index[cam][laser][obj]
        del index[cam][laser][obj]
        #fileName = cal['fileName']
        #calDir = self.dev.config['calibrationDir']
        #fileName = os.path.join(calDir, fileName)
        #try:
            #os.remove(fileName)
        #except:
            #print "Error while removing file %s:" % fileName
            #sys.excepthook(*sys.exc_info())
        self.dev.writeCalibrationIndex(index)
        
        self.updateCalibrationList()

    def runCalibration(self):
        camera = str(self.ui.cameraCombo.currentText())
        laser = str(self.ui.laserCombo.currentText())
        blurRadius = 5
        
        ## Do fast scan of entire allowed command range
        (background, origFrames, positions) = self.scan()

        ## Do background subtraction
        frames = origFrames - background

        ## Find a frame with a spot close to the center
        cx = frames.shape[1] / 2
        cy = frames.shape[2] / 2
        maxIndex = argmax(frames[:, cx, cy])
        maxFrame = frames[maxIndex]

        ## Determine spot intensity and width
        mfBlur = blur(maxFrame, blurRadius)
        amp = mfBlur.max() - median(mfBlur)  # guess intensity of spot
        (x, y) = argwhere(mfBlur == mfBlur.max())[0]   # guess location of spot
        fit = fitGaussian2D(maxFrame, [amp, x, y, maxFrame.shape[0] / 10, 0.])[0]  ## gaussian fit to locate spot exactly
        info = origFrames.infoCopy()[-1]
        pixelSize = info['pixelSize'][0]
        region = info['region']
        binning = info['binning']
        spotHeight = fit[0]
        spotWidth = fit[3] * pixelSize
        size = self.spotSize(mfBlur)
        center = info['centerPosition']
        
        ## Determine location of spot within each frame, 
        ## ignoring frames where the spot is too dim or too close to the frame edge
        spotLocations = []
        spotCommands = []
        spotFrames = []
        margin = fit[3]
        for i in range(frames.shape[0]):
            frame = frames[i]
            fBlur = blur(frame, blurRadius)
            mx = fBlur.max()
            diff = mx - fBlur.min()
            if self.spotSize(fBlur) < size * 0.5:
                continue
            (x, y) = argwhere(fBlur == mx)[0]   # guess location of spot
            if x < margin or x > frame.shape[0] - margin:
                continue
            if y < margin or y > frame.shape[1] - margin:
                continue
            
            ## x,y are currently in sensor coords, now convert to absolute scale relative to center
            #print "======="
            #print x, y, region
            x = (x - (region[2]*0.5 / binning)) * info['pixelSize'][0]
            y = (y - (region[3]*0.5 / binning)) * info['pixelSize'][1]
            #print x, y
            
            spotLocations.append([x, y])
            spotCommands.append(positions[i])
            spotFrames.append(frame[newaxis])
        
        for i in range(len(spotLocations)):
            print spotLocations[i], spotCommands[i]
        spotFrameMax = concatenate(spotFrames).max(axis=0)
        self.image.updateImage(spotFrameMax, autoRange=True)
        self.ui.view.setRange(self.image.boundingRect())
        
        
        ## Fit all data to a map function
        mapParams = self.generateMap(array(spotLocations), array(spotCommands))
        print 
        print "Map parameters:", mapParams
        return (mapParams, (spotHeight, spotWidth))

    def generateMap(self, loc, cmd):
        """Generates parameters for functions that map image locations to command values.
        We assume that command values can be approximated by planar functions:
          Cmd.X  =  A  +  B * Loc.X  +  C * Loc.Y  +  D * Loc.X^2  +  E * Loc.Y^2
          Cmd.Y  =  F  +  G * Loc.X  +  H * Loc.Y  +  I * Loc.X^2  +  J * Loc.Y^2
        Returns [[A, B, C, D, E], [F, G, H, I, J]]
        """
        def fn(v, loc):
            return v[0] + v[1] * loc[:, 0] + v[2] * loc[:, 1] + v[3] * loc[:, 0]**2 + v[4] * loc[:, 1]**2
            
        def erf(v, loc, cmd):
            return fn(v, loc) - cmd
            
        xFit = leastsq(erf, [0, 1, 1, 0, 0], (loc, cmd[:,0]))[0]
        yFit = leastsq(erf, [0, 1, 1, 0, 0], (loc, cmd[:,1]))[0]
        return (list(xFit), list(yFit))

    def spotSize(self, frame):
        med = median(frame)
        fr1 = frame - ((frame.max()-med) / e) - med
        fr1 = fr1 * (fr1 > 0)
        return fr1.sum()

    def scan(self):
        """Scan over x and y ranges in a nPts x nPts grid, return the image recorded at each location."""
        camera = str(self.ui.cameraCombo.currentText())
        laser = str(self.ui.laserCombo.currentText())
        
        duration = 4.0
        rate = 10000
        nPts = int(rate * duration)
        sweeps = 20

        cameraTrigger = ones(nPts, dtype=byte)

        (cmdMin, cmdMax) = self.dev.config['commandLimits']
        cmdRange = cmdMax - cmdMin
        xCommand = fromfunction(lambda i: cmdMin + ((cmdRange * i * float(sweeps) / nPts) % cmdRange), (nPts,), dtype=float)
        xCommand[-1] = 0.0
        yCommand = empty((nPts,), dtype=float)
        start = 0
        for i in range(sweeps):
            stop = start + (nPts / sweeps)
            yCommand[start:stop] = cmdMin + cmdRange * (float(i)/(sweeps-1))
            start = stop
        yCommand[-1] = 0.0
        daqName = self.dev.config['XAxis'][0]

        ## Record 10 camera frames with the shutter closed 
        cmd = {
            'protocol': {'duration': 0.0},
            camera: {'record': True, 'minFrames': 10},
            laser: {'Shutter': {'preset': 0, 'holding': 0}}
        }
        task = lib.Manager.getManager().createTask(cmd)
        task.execute()
        result = task.getResult()
        ## pull result, convert to ndarray float, take average over all frames
        background = result[camera]['frames'].view(ndarray).astype(float).mean(axis=0)
        
        ## Record full scan.
        cmd = {
            'protocol': {'duration': duration},
            camera: {'record': True, 'triggerMode': 'Trigger First', 'recordExposeChannel': True, 'channels': {
                'exposure': {'record': True}, 
                'trigger': {'preset': 0, 'command': cameraTrigger}}},
            laser: {'Shutter': {'preset': 1, 'holding': 0}},
            #'CameraTrigger': {'Command': {'preset': 0, 'command': cameraTrigger, 'holding': 0}},
            self.dev.name: {'xCommand': xCommand, 'yCommand': yCommand},
            daqName: {'numPts': nPts, 'rate': rate}
        }

        task = lib.Manager.getManager().createTask(cmd)
        task.execute()
        result = task.getResult()

        ## Pull frames, subtract background, and display
        frames = result[camera]['frames']
        #self.image.updateImage((frames - background).max(axis=0), autoRange=True)
        #self.ui.view.setRange(self.image.boundingRect())
        
        ## Generate a list of the scanner command values for each frame
        positions = []
        for i in range(frames.shape[0]):
            t = frames.xvals('Time')[i]
            ind = int((t/duration) * nPts)
            positions.append([xCommand[ind], yCommand[ind]])
        return (background, frames, positions)
        

    #def measureSpotSize(self, camera, laser):
        ### Record a background frame
        #cmd = {
            #'protocol': {'duration': 0.0},             ## duration will be determined by camera
            #camera: {'record': True, 'minFrames': 2, 'forceStop': True},  ## Record frames (need at least 2; first frame can have variable exposure)
            #self.dev.name: {'command': [0.0, 0.0]}     ## Set scan mirror command to 0, 0
        #}
        #task = lib.Manager.getManager().createTask(cmd)
        #task.execute()
        #result1 = task.getResult()

        ### take another frame with the laser on
        #cmd[laser] = {'Shutter': {'preset': 1, 'holding': 0}}  ## Open shutter before, close shutter after

        #task = lib.Manager.getManager().createTask(cmd)
        #task.execute()
        #result2 = task.getResult()


        ### compute difference
        #im1 = result1[camera]['frames'][1]
        #im2 = result2[camera]['frames'][1]
        #diff = im2.astype(int) - im1.astype(int)

        ### display image
        #self.image.updateImage(diff, autoRange=True)
        #self.ui.view.setRange(self.image.boundingRect())

        ### fit 2D gaussian
        ##from numpy import median
        #diffSmooth = blur(diff, 10)
        #amp = diffSmooth.max() - diffSmooth.min()
        #(x, y) = argwhere(diffSmooth == diffSmooth.max())[0]
        #fit = fitGaussian2D(diff, [amp, x, y, 40., 0.])[0]
        #pixelSize = im1.infoCopy()[-1]['pixelSize'][0]


        #return (fit[0], fit[3]*pixelSize)
