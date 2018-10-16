# -*- coding: utf-8 -*-
from __future__ import print_function
from .DeviceTemplate import Ui_Form
import time, os, sys, gc
from acq4.util import Qt
#from acq4.pyqtgraph.graphicsItems import ImageItem
import acq4.Manager
from acq4.util.imageAnalysis import *
from acq4.util.debug import *
import numpy as np
import acq4.pyqtgraph as pg
#import acq4.pyqtgraph.WidgetGroup as WidgetGroup
#from acq4.pyqtgraph.ProgressDialog import ProgressDialog
from acq4.util.HelpfulException import HelpfulException

class ScannerDeviceGui(Qt.QWidget):
    
    
    def __init__(self, dev, win):
        Qt.QWidget.__init__(self)
        self.dev = dev
        self.win = win
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.stateGroup = pg.WidgetGroup({
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

        #devs = self.dev.dm.listDevices()
        #for d in devs:
            #self.ui.cameraCombo.addItem(d)
            #self.ui.laserCombo.addItem(d)
            #if d == defCam:
                #self.ui.cameraCombo.setCurrentIndex(self.ui.cameraCombo.count()-1)
            #if d == defLaser:
                #self.ui.laserCombo.setCurrentIndex(self.ui.laserCombo.count()-1)
        self.ui.cameraCombo.setTypes('camera')
        self.ui.laserCombo.setTypes('laser')
        
        self.spots = []
        
        ## Populate list of calibrations
        self.updateCalibrationList()
        
        ## load default config
        state = self.dev.loadCalibrationDefaults()
        if state is not None:
            self.stateGroup.setState(state)
        
        ## create graphics scene
        #self.image = ImageItem()
        #self.scene = self.ui.view.scene
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
        for laser in index:
            for obj in index[laser]:
                cal = index[laser][obj]
                spot = '%0.0f, %0.1f um' % (cal['spot'][0], cal['spot'][1]*1e6)
                date = cal['date']
                item = Qt.QTreeWidgetItem([', '.join(obj), laser, str(spot), date])
                item.opticState = obj
                self.ui.calibrationList.addTopLevelItem(item)
        
        
    def storeCamConf(self):
        cam = str(self.ui.cameraCombo.currentText())
        self.dev.storeCameraConfig(cam)
        
    def calibrateClicked(self):
        self.ui.calibrateBtn.setEnabled(False)
        self.ui.calibrateBtn.setChecked(True)
        self.ui.calibrateBtn.setText('Calibrating...')
        try:
            cam = str(self.ui.cameraCombo.currentText())
            laser = str(self.ui.laserCombo.currentText())
            #obj = self.dev.getObjective()
            opticState = self.dev.getDeviceStateKey()
            
            ## Run calibration
            (cal, spot) = self.runCalibration()
            #gc.collect() ## a lot of memory is used in running calibration, make sure we collect all the leftovers now
            #cal = MetaArray((512, 512, 2))
            #spot = 100e-6
            date = time.strftime('%Y.%m.%d %H:%M', time.localtime())
            
            #fileName = cam + '_' + laser + '_' + obj + '.ma'
            index = self.dev.getCalibrationIndex()
            
            if laser not in index:
                index[laser] = {}
            index[laser][opticState] = {'spot': spot, 'date': date, 'params': cal}

            self.dev.writeCalibrationIndex(index)
            
            self.dev.writeCalibrationDefaults(self.stateGroup.state())
            #cal.write(os.path.join(self.dev.config['calibrationDir'], fileName))
            
            self.updateCalibrationList()
        finally:
            self.ui.calibrateBtn.setEnabled(True)
            self.ui.calibrateBtn.setChecked(False)
            self.ui.calibrateBtn.setText('Calibrate')

    def deleteClicked(self):
        cur = self.ui.calibrationList.currentItem()
        optState = cur.opticState
        laser = str(cur.text(1))
        index = self.dev.getCalibrationIndex()
        del index[laser][optState]
        self.dev.writeCalibrationIndex(index)
        self.updateCalibrationList()


    def addSpot(self, pos, size):
        """Add a circle to the image"""
        s2 = size/2.0
        s = Qt.QGraphicsEllipseItem(0, 0, 1, 1)
        s.scale(size, size)
        s.setPos(pos[0]-s2, pos[1]-s2)
        s.setPen(Qt.QPen(Qt.QColor(100, 255, 100, 70)))
        self.ui.view.addItem(s)
        s.setZValue(100)
        self.spots.append(s)
        
        
    def clearSpots(self):
        """Clear all circles from the image"""
        for s in self.spots:
            self.ui.view.removeItem(s)
        self.spots = []
        

    def runCalibration(self):
        """The scanner calibration routine:
            1) Measure background frame, then scan mirrors 
               while collecting frames as fast as possible (self.scan())
            2) Locate spot in every frame using gaussian fit
            3) Map image spot locations to coordinate system of Scanner device's parent
            3) Do parabolic fit to determine mapping between voltage and position
        """
        camera = str(self.ui.cameraCombo.currentText())
        laser = str(self.ui.laserCombo.currentText())
        blurRadius = 5
        
        ## Do fast scan of entire allowed command range
        (background, cameraResult, positions) = self.scan()
        #self.calibrationResult = {'bg': background, 'frames': cameraResult, 'pos': positions}

        with pg.ProgressDialog("Calibrating scanner: Computing spot positions...", 0, 100) as dlg:
            dlg.show()
            dlg.raise_()  # Not sure why this is needed here..

            ## Forget first 2 frames since some cameras can't seem to get these right.
            frames = cameraResult.asArray()
            frames = frames[2:]
            positions = positions[2:]
            
            ## Do background subtraction
            ## take out half the data until it can do the calculation without having a MemoryError.
            finished = False
            gc.collect()
            while not finished:
                try:
                    frames = frames.astype(np.float32)
                    frames -= background.astype(np.float32)
                    finished=True
                except MemoryError:
                    frames = frames[::2,:,:]
                    positions = positions[::2]
                    finished = False
                
            ## Find a frame with a spot close to the center (within center 1/3)
            cx = frames.shape[1] / 3
            cy = frames.shape[2] / 3
            centerSlice = blur(frames[:, cx:cx*2, cy:cy*2], (0, 5, 5)).max(axis=1).max(axis=1)
            maxIndex = argmax(centerSlice)
            maxFrame = frames[maxIndex]
            dlg.setValue(5)

            ## Determine spot intensity and width
            mfBlur = blur(maxFrame, blurRadius)
            amp = mfBlur.max() - median(mfBlur)  ## guess intensity of spot
            (x, y) = argwhere(mfBlur == mfBlur.max())[0]   ## guess location of spot
            fit = fitGaussian2D(maxFrame, [amp, x, y, maxFrame.shape[0] / 10, 0.])[0]  ## gaussian fit to locate spot exactly
            # convert sigma to full width at 1/e
            fit[3] = abs(2 * (2 ** 0.5) * fit[3]) ## sometimes the fit for width comes out negative. *shrug*
            someFrame = cameraResult.frames()[0]
            frameTransform = pg.SRTTransform(someFrame.globalTransform())
            pixelSize = someFrame.info()['pixelSize'][0]
            spotAmplitude = fit[0]
            spotWidth = abs(fit[3] * pixelSize)
            size = self.spotSize(mfBlur)
            dlg.setValue(50)

            ## Determine location of spot within each frame, 
            ## ignoring frames where the spot is too dim or too close to the frame edge
            spotLocations = []
            globalSpotLocations = []
            spotCommands = []
            spotFrames = []
            margin = fit[3]
            
            for i in range(len(positions)):
                dlg.setValue(50. + 50. * i / frames.shape[0])
                if dlg.wasCanceled():
                    raise HelpfulException('Calibration canceled by user.', msgType='warning')

                frame = frames[i]
                fBlur = blur(frame.astype(np.float32), blurRadius)
    
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
                
                ## convert pixel location to coordinate system of scanner's parent
                globalPos = frameTransform.map(pg.Point(x, y))  ## Map from frame pixel location to global coordinates
                localPos = self.dev.mapGlobalToParent(globalPos)  ## map from global to parent coordinate system. This is the position we calibrate to.
                #print (x, y), (globalPos.x(), globalPos.y()), (localPos.x(), localPos.y())
                
                spotLocations.append([localPos.x(), localPos.y()])
                globalSpotLocations.append([globalPos.x(), globalPos.y()])
                spotCommands.append(positions[i])
                spotFrames.append(frame[newaxis])
        
        ## sanity check on spot frame
        if len(spotFrames) == 0:
            self.ui.view.setImage(frames)
            raise HelpfulException('Calibration never detected laser spot!  Looking for spots that are %f pixels wide.'% fit[3], reasons=['shutter is disabled', 'mirrors are disabled', 'objective is not clean', 'spot is not visible or not bright enough when shutter is open'])

        spotFrameMax = concatenate(spotFrames).max(axis=0)
        self.ui.view.setImage(spotFrameMax, transform=frameTransform)
        
        self.clearSpots()
        for sl in globalSpotLocations:
            #self.addSpot(sl, fit[3]*binning[0])
            self.addSpot(sl, spotWidth)
        self.ui.view.autoRange()
        
        if len(spotFrames) < 10:
            raise HelpfulException('Calibration detected only %d frames with laser spot; need minimum of 10.' % len(spotFrames), reasons=['spot is too dim for camera sensitivity', 'objective is not clean', 'mirrors are scanning too quickly', 'mirror scanning region is not within the camera\'s view'])
        
        ## Fit all data to a map function
        mapParams = self.generateMap(array(spotLocations), array(spotCommands))
        #print 
        #print "Map parameters:", mapParams
        
        if spotWidth < 0:
            raise Exception()
        return (mapParams, (spotAmplitude, spotWidth))

    def generateMap(self, loc, cmd):
        """Generates parameters for functions that map spot locations (Loc) to command values (Cmd).
        We assume that command values can be approximated by parabolic functions:
          Cmd.X  =  A  +  B * Loc.X  +  C * Loc.Y  +  D * Loc.X^2  +  E * Loc.Y^2
          Cmd.Y  =  F  +  G * Loc.X  +  H * Loc.Y  +  I * Loc.X^2  +  J * Loc.Y^2
        Returns [[A, B, C, D, E], [F, G, H, I, J]]
        """
#        print "==========="
#        print loc
#        print "============"
#        print cmd
        #for i in range(loc.shape[0]):
            #print tuple(loc[i]),  tuple(cmd[i])
        
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
        #xFit = leastsq(erf2, list(xFit)+[0, 0], (loc, cmd[:,0]))[0]
        #yFit = leastsq(erf2, list(yFit)+[0, 0], (loc, cmd[:,1]))[0]
        
        # 2nd stage disabled -- we can bring this back when we have a good method
        # for optimization with constraints.
        xFit = list(xFit)+[0,0]
        yFit = list(yFit)+[0,0]
        #print "fit stage 2:", xFit, yFit
        
        ## compute fit error
        errx = abs(erf2(xFit,  loc,  cmd[:, 0])).mean()
        erry = abs(erf2(yFit,  loc,  cmd[:, 1])).mean()
        print("Fit error:",  errx,  erry)
        self.dev.lastCalData = (loc,  cmd)
        return (list(xFit), list(yFit))

    def spotSize(self, frame):
        """Return the normalized integral of all values in the frame that are between max and max/e"""
        med = median(frame)
        fr1 = frame - med   ## subtract median value so baseline is at 0
        mask = fr1 > (fr1.max() / np.e)  ## find all values > max/e
        ss = (fr1 * mask).sum() / mask.sum()  ## integrate values within mask, divide by mask area
        assert(not np.isnan(ss))
        return ss

    def scan(self):
        """Scan over x and y ranges in a nPts x nPts grid, return the image recorded at each location."""
        camera = str(self.ui.cameraCombo.currentText())
        laser = str(self.ui.laserCombo.currentText())
        
        ## Camera settings to use during scan
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
        daqName = self.dev.config['XAxis']['device']

        ## Record 10 camera frames with the shutter closed 
        #print "parameters:", camParams
        cmd = {
            'protocol': {'duration': 0.0, 'timeout': 5.0},
            camera: {'record': True, 'minFrames': 10, 'params': camParams, 'pushState': 'scanProt'}, 
            #laser: {'Shutter': {'preset': 0, 'holding': 0}}
        }
        #print "\n\n====> Record background\n"
        task = acq4.Manager.getManager().createTask(cmd)
        task.execute()
        result = task.getResult()
        ## pull result, convert to ndarray float, take average over all frames
        background = result[camera].asArray().astype(float).mean(axis=0)
        #print "Background shape:", result[camera]['frames'].shape
        
        ## Record full scan.
        cmd = {
            'protocol': {'duration': duration, 'timeout': duration+5.0},
            camera: {'record': True, 'triggerProtocol': True, 'params': camParams, 'channels': {
                'exposure': {'record': True}, 
                },
                'popState': 'scanProt'},
            #laser: {'shutter': {'preset': 0, 'holding': 0, 'command': np.ones(len(xCommand), dtype=byte)}},
            laser: {'alignMode': True},
            self.dev.name(): {'xCommand': xCommand, 'yCommand': yCommand},
            daqName: {'numPts': nPts, 'rate': rate, 'triggerDevice': camera}
        }
        #print "\n\n====> Scan\n"
        task = acq4.Manager.getManager().createTask(cmd)
        task.execute(block=False)
        with pg.ProgressDialog("Calibrating scanner: Running scan protocol..", 0, 100) as dlg:
            while not task.isDone():
                dlg.setValue(100.*task.runTime()/task.duration())
                if dlg.wasCanceled():
                    task.abort()
                    raise HelpfulException('Calibration canceled by user.', msgType='warning')
                time.sleep(0.2)
        
        result = task.getResult()
        
        frames = result[camera].asMetaArray()
        if frames._info[-1]['preciseTiming'] is not True:
            raise HelpfulException("Calibration could not accurately measure camera frame timing.",
                                   reasons=["The exposure signal from the camera was not recorded by the DAQ."])
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
        
        return (background, result[camera], positions)
        
