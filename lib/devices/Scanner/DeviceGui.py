# -*- coding: utf-8 -*-
from DeviceTemplate import Ui_Form
import time, os, sys
from PyQt4 import QtCore, QtGui
from pyqtgraph.graphicsItems import ImageItem
import lib.Manager
from imageAnalysis import *
from debug import *
import numpy as np
import pyqtgraph.WidgetGroup as WidgetGroup
from ProgressDialog import ProgressDialog

class ScannerDeviceGui(QtGui.QWidget):
    
    
    def __init__(self, dev, win):
        QtGui.QWidget.__init__(self)
        self.dev = dev
        self.win = win
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.stateGroup = WidgetGroup.WidgetGroup({
            'duration': self.ui.scanDurationSpin,
            'xMin': self.ui.xMinSpin,
            'xMax': self.ui.xMaxSpin,
            'yMin': self.ui.yMinSpin,
            'yMax': self.ui.yMaxSpin,
            'splitter': self.ui.splitter,
        })
        
        spos = dev.getShutterVals()
        if spos is None:
            self.ui.shutterGroup.hide()
        else:
            self.shutterChanged()
            self.ui.shutterXSpin.setValue(spos[0])
            self.ui.shutterYSpin.setValue(spos[1])
        
        
        ## Populate Device lists
        #defCam = None
        #if 'defaultCamera' in self.dev.config:
            #defCam = self.dev.config['defaultCamera']
        defCam = self.dev.config.get('defaultCamera', None)
        #defLaser = None
        #if 'defaultLaser' in self.dev.config:
            #defLaser = self.dev.config['defaultLaser']
        defLaser = self.dev.config.get('defaultLaser', None)

        devs = self.dev.dm.listDevices()
        for d in devs:
            self.ui.cameraCombo.addItem(d)
            self.ui.laserCombo.addItem(d)
            if d == defCam:
                self.ui.cameraCombo.setCurrentIndex(self.ui.cameraCombo.count()-1)
            if d == defLaser:
                self.ui.laserCombo.setCurrentIndex(self.ui.laserCombo.count()-1)
            
        self.spots = []
        
        ## Populate list of calibrations
        self.updateCalibrationList()
        
        ## load default config
        state = self.dev.loadCalibrationDefaults()
        if state is not None:
            self.stateGroup.setState(state)
        
        ## create graphics scene
        #self.image = ImageItem()
        self.scene = self.ui.view.scene
        #self.ui.view.enableMouse()
        #self.scene.addItem(self.image)
        #self.ui.view.setAspectLocked(True)
        #self.ui.view.invertY()

        self.ui.calibrateBtn.clicked.connect(self.calibrateClicked)
        self.ui.storeCamConfBtn.clicked.connect(self.storeCamConf)
        self.ui.deleteBtn.clicked.connect(self.deleteClicked)
        self.ui.shutterBtn.clicked.connect(self.shutterClicked)
        self.dev.sigShutterChanged.connect(self.shutterChanged)

    def shutterClicked(self):
        self.dev.setShutterOpen(not self.lastShutterState)
        
    def shutterChanged(self):
        sh = self.dev.getShutterOpen()
        self.lastShutterState = sh
        if sh:
            self.ui.shutterBtn.setText('Close Shutter')
        else:
            self.ui.shutterBtn.setText('Open Shutter')
            

            
            
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
        
        
    def storeCamConf(self):
        cam = str(self.ui.cameraCombo.currentText())
        self.dev.storeCameraConfig(cam)
        
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
        
        self.dev.writeCalibrationDefaults(self.stateGroup.state())
        #cal.write(os.path.join(self.dev.config['calibrationDir'], fileName))
        
        self.updateCalibrationList()

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


    def addSpot(self, pos, size):
        """Add a circle to the image"""
        s2 = size/2.
        s = QtGui.QGraphicsEllipseItem(0, 0, 1, 1)
        s.scale(size, size)
        s.setPos(pos[0]-s2, pos[1]-s2)
        s.setPen(QtGui.QPen(QtGui.QColor(100, 255, 100, 70)))
        self.scene.addItem(s)
        s.setZValue(100)
        self.spots.append(s)
        
        
    def clearSpots(self):
        """Clear all circles from the image"""
        for s in self.spots:
            self.scene.removeItem(s)
        self.spots = []
        

    def runCalibration(self):
        """Wraps around runCalibrationInner, adds progress dialog and error reporting"""
        with ProgressDialog("Calibrating scanner: Running protocol..", 0, 100) as self.progressDlg:
            #self.progressDlg.setWindowModality(QtCore.Qt.WindowModal)
            #self.progressDlg.setMinimumDuration(0)
        
            try:
                self.updatePrgDlg(0)
                return self.runCalibrationInner()
            except:
                #print "SHOW ERROR"
                self.win.showMessage("Error during scanner calibration, see console.", 30000)
                raise
            #finally:
                #self.progressDlg.setValue(100)

    def updatePrgDlg(self, val=None, text=None):
        if text is not None:
            self.progressDlg.setLabelText(text)
        if val is not None:
            self.progressDlg.setValue(val)
        QtGui.QApplication.instance().processEvents()
        if self.progressDlg.wasCanceled():
            self.progressDlg.setValue(100)
            raise Exception('Calibration canceled by user.')

    def runCalibrationInner(self):
        """The scanner calibration routine:
            1) Measure background frame, then scan mirrors 
               while collecting frames as fast as possible (self.scan())
            2) Locate spot in every frame using gaussian fit
            3) Do parabolic fit to determine mapping between voltage and position
        """
        camera = str(self.ui.cameraCombo.currentText())
        laser = str(self.ui.laserCombo.currentText())
        blurRadius = 5
        
        ## Do fast scan of entire allowed command range
        (background, origFrames, positions) = self.scan()

        self.updatePrgDlg(25, "Calibrating scanner: Computing spot size...")
        
        ## Forget first 2 frames since some cameras can't seem to get these right.
        origFrames = origFrames[2:]
        positions = positions[2:]
        
        ## Do background subtraction
        frames = origFrames.astype(np.int32) - background.astype(np.int32)

        ## Find a frame with a spot close to the center (within center 1/3)
        cx = frames.shape[1] / 3
        cy = frames.shape[2] / 3
        centerSlice = frames[:, cx:cx*2, cy:cy*2].mean(axis=1).mean(axis=1)
        maxIndex = argmax(centerSlice)
        maxFrame = frames[maxIndex]

        ## Determine spot intensity and width
        mfBlur = blur(maxFrame, blurRadius)
        amp = mfBlur.max() - median(mfBlur)  ## guess intensity of spot
        (x, y) = argwhere(mfBlur == mfBlur.max())[0]   ## guess location of spot
        fit = fitGaussian2D(maxFrame, [amp, x, y, maxFrame.shape[0] / 10, 0.])[0]  ## gaussian fit to locate spot exactly
        fit[3] = abs(fit[3]) ## sometimes the fit for width comes out negative. *shrug*
        info = origFrames.infoCopy()[-1]
        pixelSize = info['pixelSize'][0]
        region = info['region']
        binning = info['binning']
        spotHeight = fit[0]
        spotWidth = fit[3] * pixelSize
        size = self.spotSize(mfBlur)
        center = info['centerPosition']

        self.updatePrgDlg(40, "Calibrating scanner: Computing spot positions...")


        ## Determine location of spot within each frame, 
        ## ignoring frames where the spot is too dim or too close to the frame edge
        spotLocations = []
        spotCommands = []
        spotFrames = []
        margin = fit[3]
        #sensorSize = lib.Manager.getManager().getDevice(camera).getParam('sensorSize')
        #print "Spot size is %f x %g (%f px)" % (size, spotWidth, fit[3])
        for i in range(len(positions)):
            frame = frames[i]
            fBlur = blur(frame, blurRadius)
            mx = fBlur.max()
            diff = mx - fBlur.min()
            ss = self.spotSize(fBlur)
            if ss < size * 0.6:
                #print "Ignoring spot:", ss
                continue
            #else:
                #print "Keeping spot:", ss
                
            (x, y) = argwhere(fBlur == mx)[0]   # guess location of spot
            if x < margin or x > frame.shape[0] - margin:
                #print "   ..skipping; too close to edge", x, y
                continue
            if y < margin or y > frame.shape[1] - margin:
                #print "   ..skipping; too close to edge", x, y
                continue
            
            frame[x,y] = -1  ## mark location of peak in image
            #print "  ..spot is at", x, y
            
            ## x,y are currently in sensor coords, now convert to absolute scale relative to center
            ### No, let's calibrate into sensor coords.
            #print "======="
            ##print x, y, region
            #print "Image location:", x, y
            #x = (x - (region[2]/ (2*binning[0]))) * info['pixelSize'][0]
            #y = (y - (region[3]/ (2*binning[1]))) * info['pixelSize'][1]
            ##print x, y
            #print "Camera region:", region, binning
            #print "Real location:", x, y
            
            ## convert image location to absolute sensor pixel
            x = region[0] + (x+0.5) * binning[0]
            y = region[1] + (y+0.5) * binning[1]
            
            spotLocations.append([x, y])
            spotCommands.append(positions[i])
            spotFrames.append(frame[newaxis])
            self.updatePrgDlg(40 + 60 * i / frames.shape[0])
        
        #for i in range(len(spotLocations)):
            #print spotLocations[i], spotCommands[i]
        
        ## sanity check on spot frame
        if len(spotFrames) == 0:
            #self.image.updateImage(frames.max(axis=0))
            self.ui.view.setImage(frames)
            print "frames shape:", frames.shape
            raise Exception('Calibration never detected laser spot!\n  Looking for spots that are %f pixels wide.\n  (Check: 1. shutter is closed, 2. mirrors on, 3. objective is clean, 4. spot visible (and bright enough) when shutter is open)' % fit[3])

        spotFrameMax = concatenate(spotFrames).max(axis=0)
        #self.image.updateImage(maxFrame, autoRange=True)
        #self.image.updateImage(spotFrameMax, autoRange=True)
        #self.image.resetTransform()
        #impos = info['imagePosition']
        #self.ui.view.setImage(spotFrameMax, scale=[pixelSize, pixelSize], pos=[impos[0]-center[0], impos[1]-center[1]])
        self.ui.view.setImage(spotFrameMax, scale=binning, pos=region[:2])
        #self.image.scale(pixelSize, pixelSize)
        #self.image.setPos(impos[0]-center[0], impos[1]-center[1])
        #self.ui.view.setRange(self.image.mapRectToScene(self.image.boundingRect()))
        
        self.clearSpots()
        for sl in spotLocations:
            #self.addSpot(sl, spotWidth)
            self.addSpot(sl, fit[3]*binning[0])
        
        if len(spotFrames) <= 10:
            raise Exception('Calibration detected only %d frames with laser spot; need minimum of 10.' % len(spotFrames))

        self.updatePrgDlg(90, "Calibrating scanner: Doing linear regression..")
        
        ## Fit all data to a map function
        mapParams = self.generateMap(array(spotLocations), array(spotCommands))
        #print 
        #print "Map parameters:", mapParams
        
        return (mapParams, (spotHeight, spotWidth))

    def generateMap(self, loc, cmd):
        """Generates parameters for functions that map image locations (Loc) to command values (Cmd).
        We assume that command values can be approximated by parabolic functions:
          Cmd.X  =  A  +  B * Loc.X  +  C * Loc.Y  +  D * Loc.X^2  +  E * Loc.Y^2
          Cmd.Y  =  F  +  G * Loc.X  +  H * Loc.Y  +  I * Loc.X^2  +  J * Loc.Y^2
        Returns [[A, B, C, D, E], [F, G, H, I, J]]
        """
        
        ## do a two-stage fit, using only linear parameters first.
        ## this is to make sure the second-order parameters do no interfere with the first-order fit.
        def fn1(v, loc):
            return v[0] + v[1] * loc[:, 0] + v[2] * loc[:, 1]
        def fn2(v, loc):
            return v[0] + v[1] * loc[:, 0] + v[2] * loc[:, 1] + v[3] * loc[:, 0]**2 + v[4] * loc[:, 1]**2
            
        def erf1(v, loc, cmd):
            return fn1(v, loc) - cmd
        def erf2(v, loc, cmd):
            return fn2(v, loc) - cmd
            
        ### sanity checks here on loc and cmd
        if loc.shape[0] < 6:
            raise Exception("Calibration only detected %d spots; this is not enough." % loc.shape[0])

        ## fit linear parameters first
        xFit = leastsq(erf1, [0, 0, 0], (loc, cmd[:,0]))[0]
        yFit = leastsq(erf1, [0, 0, 0], (loc, cmd[:,1]))[0]
        #print "fit stage 1:", xFit, yFit
        
        ## then fit the parabolic equations, using the linear fit as the seed
        xFit = leastsq(erf2, list(xFit)+[0, 0], (loc, cmd[:,0]))[0]
        yFit = leastsq(erf2, list(yFit)+[0, 0], (loc, cmd[:,1]))[0]
        #print "fit stage 2:", xFit, yFit
        #xFit = list(xFit)+[0,0]
        #yFit = list(yFit)+[0,0]
        
        return (list(xFit), list(yFit))

    def spotSize(self, frame):
        """Return the normalized integral of all values in the frame that are between max and max/e"""
        med = median(frame)
        fr1 = frame - med   ## subtract median value so baseline is at 0
        mask = fr1 > (fr1.max() / e)  ## find all values > max/e
        return (fr1 * mask).sum() / mask.sum()  ## integrate values within mask, divide by mask area

    def scan(self):
        """Scan over x and y ranges in a nPts x nPts grid, return the image recorded at each location."""
        
        ## Camera settings to use during scan
        binning = (2, 2)
        exposure = 0.003
        
        camera = str(self.ui.cameraCombo.currentText())
        laser = str(self.ui.laserCombo.currentText())
        
        camParams = self.dev.getCameraConfig(camera)        
        
        duration = self.ui.scanDurationSpin.value()
        rate = 10000
        nPts = int(rate * duration)
        sweeps = 20

        #cameraTrigger = ones(nPts, dtype=byte)

        ##(cmdMin, cmdMax) = self.dev.config['commandLimits']
        xRange = (self.ui.xMinSpin.value(), self.ui.xMaxSpin.value())
        yRange = (self.ui.yMinSpin.value(), self.ui.yMaxSpin.value())
        xDiff = xRange[1] - xRange[0]
        yDiff = yRange[1] - yRange[0]
        
        xCommand = np.fromfunction(lambda i: xRange[0] + ((xDiff * i * float(sweeps) / nPts) % xDiff), (nPts,), dtype=float)
        xCommand[-1] = 0.0
        yCommand = np.empty((nPts,), dtype=float)
        start = 0
        for i in range(sweeps):
            stop = start + (nPts / sweeps)
            yCommand[start:stop] = yRange[0] + yDiff * (float(i)/(sweeps-1))
            start = stop
        yCommand[-1] = 0.0
        daqName = self.dev.config['XAxis'][0]

        ## Record 10 camera frames with the shutter closed 
        #print "parameters:", camParams
        cmd = {
            'protocol': {'duration': 0.0, 'timeout': 5.0},
            camera: {'record': True, 'minFrames': 10, 'params': camParams, 'pushState': 'scanProt'}, 
            laser: {'Shutter': {'preset': 0, 'holding': 0}}
        }
        #print "\n\n====> Record background\n"
        task = lib.Manager.getManager().createTask(cmd)
        task.execute()
        result = task.getResult()
        ## pull result, convert to ndarray float, take average over all frames
        background = result[camera]['frames'].view(np.ndarray).astype(float).mean(axis=0)
        #print "Background shape:", result[camera]['frames'].shape
        
        ## Record full scan.
        cmd = {
            'protocol': {'duration': duration, 'timeout': duration+5.0},
            camera: {'record': True, 'triggerProtocol': True, 'params': camParams, 'channels': {
                'exposure': {'record': True}, 
                #'trigger': {'preset': 0, 'command': cameraTrigger}
                },
                #'binning': binning, 'exposure': exposure, 'CLEAR_MODE': 'Clear Pre-Exposure', 'GAIN_INDEX': 3, 
                'popState': 'scanProt'},
            laser: {'Shutter': {'preset': 0, 'holding': 0, 'command': np.ones(len(xCommand), dtype=byte)}},
            #'CameraTrigger': {'Command': {'preset': 0, 'command': cameraTrigger, 'holding': 0}},
            self.dev.name: {'xCommand': xCommand, 'yCommand': yCommand},
            daqName: {'numPts': nPts, 'rate': rate, 'triggerDevice': camera}
        }
        #print "\n\n====> Scan\n"
        task = lib.Manager.getManager().createTask(cmd)
        task.execute()
        result = task.getResult()

        frames = result[camera]['frames']
        #print "scan shape:", frames.shape
        #print "parameters:", camParams
        
        ## Generate a list of the scanner command values for each frame
        positions = []
        for i in range(frames.shape[0]):
            t = frames.xvals('Time')[i]
            ind = int((t/duration) * nPts)
            if ind >= len(xCommand):
                break
            positions.append([xCommand[ind], yCommand[ind]])
            
        if frames.ndim != 3 or frames.shape[0] < 5:
            raise Exception("Camera did not collect enough frames (data shape is %s)" % str(frames.shape))
            
        if background.shape != frames.shape[1:]:
            raise Exception("Background measurement frame has different shape %s from scan frames %s" % (str(background.shape), str(frames.shape[1:])))
        
        return (background, frames, positions)
        
