# -*- coding: utf-8 -*-
from __future__ import division
from acq4.modules.TaskRunner.analysisModules import AnalysisModule
from acq4.Manager import getManager
from PyQt4 import QtCore, QtGui
from imagingTemplate import Ui_Form
import numpy as np
import acq4.pyqtgraph as pg
import acq4.util.functions as fn
import acq4.util.metaarray as metaarray
from acq4.util.HelpfulException import HelpfulException
# import acq4.devices.Scanner.ScanUtilityFuncs as SUFA
from acq4.devices.Scanner.ScanProgram.rect import RectScan
from acq4.pyqtgraph.parametertree import ParameterTree, Parameter

class ImagingModule(AnalysisModule):
    def __init__(self, *args):
        AnalysisModule.__init__(self, *args)
        # self.ui = Ui_Form()
        # self.ui.setupUi(self)
        self.layout = QtGui.QGridLayout()
        self.setLayout(self.layout)
        self.splitter = QtGui.QSplitter()
        self.layout.addWidget(self.splitter)
        self.ptree = ParameterTree()
        self.splitter.addWidget(self.ptree)
        self.imageView = pg.ImageView()
        self.splitter.addWidget(self.imageView)

        # self.postGuiInit()

        self.params = Parameter(name='imager', children=[
            dict(name='scanner', type='interface', interfaceTypes=['scanner']),
            dict(name='detectors', type='group', addText="Add detector.."),
            dict(name='decomb', type='float', value=20e-6, suffix='s', siPrefix=True, bounds=[0, 1e-3], step=1e-6, children=[
                dict(name='auto', type='bool', value=True),
                dict(name='subpixel', type='bool', value=False),
                ]),
            dict(name='downsample', type='int', value=1, suffix='x', bounds=[1,None]),
            dict(name='display', type='bool', value=True),
            ])
        self.ptree.setParameters(self.params, showTop=False)
        self.params.sigTreeStateChanged.connect(self.update)
        self.params.child('detectors').sigAddNew.connect(self.addDetectorClicked)

        self.man = getManager()
        self.lastFrame = None
        # self.SUF = SUFA.ScannerUtilities()
        # self.ui.alphaSlider.valueChanged.connect(self.imageAlphaAdjust)        
        self.img = pg.ImageItem()  ## image shown in camera module
        self.img.setLookupTable(self.imageView.ui.histogram.getLookupTable)  # image fetches LUT from the ImageView
        self.imageView.ui.histogram.sigLevelsChanged.connect(self._updateCamModImage)
        self.imageView.imageItem.setAutoDownsample(True)
        # self.ui.scannerComboBox.setTypes('scanner')
        # self.ui.detectorComboBox.setTypes('daqChannelGroup')

    def addDetectorClicked(self):
        self.addNewDetector()

    def addNewDetector(self, name='detector', value=None):
        self.params.child('detectors').addChild(
            dict(name=name, type='interface', interfaceTypes=['daqChannelGroup'], value=value),
            autoIncrementName=True)
                
    def quit(self):
        self.clear()
        AnalysisModule.quit(self)
        
    def saveState(self):
        return self.params.saveState(filter='user')

    def restoreState(self, state):
        detectors = {}

        # for backward compat:
        det = state['children'].pop('detector', None)
        if det is not None:
            detectors['detector'] = det['value']
        # current format:
        dets = state['children'].pop('detectors', {})
        for name, data in dets.get('children', {}).items():
            detectors[name] = data['value']

        self.params.restoreState(state, removeChildren=False)
        for name, det in detectors.items():
            self.addNewDetector(name, det)

    def taskSequenceStarted(self, *args):
        pass
    
    def taskFinished(self):
        pass
        
    def newFrame(self, frame):
        """
        Called when task is finished (truly completes, no errors/abort)
        frame contains all of the data returned from all devices
        """
        self.lastFrame = frame
        self.update()  # updates image

        # Store image if requested
        storeFlag = frame['cmd']['protocol']['storeData'] # get flag 
        if storeFlag and len(self.lastResult) > 0:
            result = self.lastResult[0]  # for now we only handle single-component programs

            dirhandle = frame['cmd']['protocol']['storageDir'] # grab storage directory
            
                       
            # to line below, add x, y for the camera (look at camera video output)

            info = [dict(name='Time', units='s', values=result['scanParams'].frameTimes()), 
                    dict(name='X'), dict(name='Y'), {
                        'transform': result['transform'],
                        'imageProcessing': result['params'],
                    }]
            ma = metaarray.MetaArray(result['image'], info=info)
            fh = dirhandle.writeFile(ma, 'Imaging.ma')
            fh.setInfo(transform=result['transform'])

    def update(self):
        self.lastResult = []
        frame = self.lastFrame
        if frame is None:
            self.clear()
            return
        # imageDownSample = self.ui.downSampling.value() # this is the "image" downsample,
        # get the downsample for the daq. This is far more complicated than it should be...

        # Get PMT signal(s)
        pmtdata = []
        for detector in self.params.param('detectors'):
            data = frame['result'][detector.value()]["Channel":'Input']
            t = data.xvals('Time')
            pmtdata.append(data.asarray())
        
        if len(pmtdata) == 0:
            return

        # parse program options
        progs = frame['cmd'][self.params['scanner']]['program']
        if len(progs) == 0:
            self.image.setImage(np.zeros((1,1)))
            return

        # For now, we only support single-component scan programs.
        prog = progs[0]
        
        if prog['type'] == 'rect':
            # keep track of some analysis in case it should be stored later
            result = {'params': self.params.saveState(filter='user')['children']}
            self.lastResult.append(result)

            rs = RectScan()
            rs.restoreState(prog['scanInfo'])
            result['scanParams'] = rs

            # Determine decomb duration
            auto = self.params['decomb', 'auto']
            if auto:
                (decombed, lag) = rs.measureMirrorLag(pmtdata[0])
                self.params['decomb'] = lag
            decomb = self.params['decomb']
            
            # Extract from PMT array
            imageData = []
            for chan in pmtdata:
                chanImage = rs.extractImage(chan, offset=decomb, subpixel=self.params['decomb', 'subpixel'])
                imageData.append(chanImage.reshape(chanImage.shape + (1,)))
                
            if len(imageData) == 1:
                imageData = imageData[0]
                levelMode = 'mono'
            else:
                if len(imageData) == 2:
                    imageData.append(np.zeros(imageData[0].shape, dtype=imageData[0].dtype))
                imageData = np.concatenate(imageData, axis=-1)
                levelMode = 'rgba'

            if imageData.size == 0:
                self.clear()
                raise Exception('image Data has zero size')

            # Downsample
            ds = self.params['downsample']
            if ds > 1:
                imageData = pg.downsample(imageData, ds, axis=2)

            # Collected as (frame, row, col) but pg prefers images like (frame, col, row)
            imageData = imageData.transpose((0, 2, 1, 3)[:imageData.ndim])
            result['image'] = imageData

            # compute global transform
            tr = rs.imageTransform()
            st = pg.QtGui.QTransform()
            st.scale(self.params['downsample'], 1)
            tr = st * tr
            result['transform'] = pg.SRTTransform3D(tr)

            # Display image locally
            self.imageView.setImage(imageData, levelMode=levelMode)
            self.imageView.getView().setAspectLocked(True)
#            self.imageView.imageItem.setRect(QtCore.QRectF(0., 0., rs.width, rs.height))  # TODO: rs.width and rs.height might not be correct!
            self.imageView.imageItem.resetTransform()
            self.imageView.imageItem.scale((rs.width/rs.height)/(imageData.shape[1]/imageData.shape[2]), 1.0)
            self.imageView.autoRange()

            # Display image remotely (in the same camera module as used by the scanner device)
            if self.params['display']:
                self.img.setVisible(True)
                sd = self.pr.getDevice(self.params['scanner'])
                camMod = sd.cameraModule().window()
                camMod.addItem(self.img)
                self.img.setImage(imageData.mean(axis=0))
                self.img.setTransform(tr)
            else:
                self.img.setVisible(False)

           
        if prog['type'] == 'multipleLineScan': 
            totSamps = int(np.sum(prog['scanPointList'])) # samples per scan, before downsampling
            imageData = pmtdata[prog['startStopIndices'][0]:prog['startStopIndices'][0]+int((nscans*totSamps))].copy()           
            imageData = imageData.reshape(nscans, totSamps)
            csum = np.cumsum(prog['scanPointList'])
            for i in xrange(0, len(csum), 2):
                    imageData[:,csum[i]:csum[i+1]] = 0

            #imageData = imageData[:,0:prog['samplesPerScan']] # trim off the pause data
            imageData = fn.downsample(imageData, imageDownSample, axis=1)
            self.ui.plotWidget.setImage(imageData)
            self.ui.plotWidget.getView().setAspectLocked(False)
            self.ui.plotWidget.imageItem.setRect(QtCore.QRectF(startT, 0.0, totSamps*dt*nscans, dist ))
            self.ui.plotWidget.autoRange()
            storeFlag = frame['cmd']['protocol']['storeData'] # get flag 
            if storeFlag:
                dirhandle = frame['cmd']['protocol']['storageDir'] # grab directory
                self.info={'detector': self.detectorDevice(), 'scanner': self.scannerDevice(), 'indices': prog['startStopIndices'], 
                           'scanPointList': prog['scanPointList'], 'nscans': prog['nScans'], 
                           'positions': prog['points'],
                           'downSample': imageDownSample, 'daqDownSample': daqDownSample}
                info = [dict(name='Time', units='s', 
                             values=t[prog['startStopIndices'][0]:prog['startStopIndices'][1]-int(totSamps):int(totSamps)]), 
                        dict(name='Distance'), self.info]
                ma = metaarray.MetaArray(imageData, info=info)
                dirhandle.writeFile(ma, 'Imaging.ma')

        if prog['type'] == 'rectScan':
            samplesPerScan = prog['imageSize'][0]*prog['imageSize'][1]
            getManager().data = prog, pmtdata
            imageData = pmtdata[prog['startStopIndices'][0]:prog['startStopIndices'][0] + nscans*samplesPerScan]
            imageData=imageData.reshape(nscans, prog['imageSize'][1], prog['imageSize'][0])
            imageData = imageData.transpose(0,2,1)
            imageAve = np.mean(imageData, axis=0)
            #print prog['scanParameters']
            self.SUF.setScannerParameters(prog['scanParameters']) # load up information for Scanner calculations
            self.SUF.setScanInfo(prog['scanInfo'])
            imageAve, bestShift = self.SUF.adjustBidirectional(imageAve, True, 0.)
            #print 'bestShift: ', bestShift, ' microseconds'
            bestShift = 200e-6
            for i in range(nscans):
                (decombedImage, shift) = self.SUF.adjustBidirectional(imageData[i], False, bestShift)
                roImage = self.SUF.removeOverscan(decombedImage)
                if i == 0:
                    newImage = np.zeros((nscans, roImage.shape[0], roImage.shape[1]))
                newImage[i] = roImage
            #print imageAve.shape
            #print newImage.shape
            imageData = newImage
            

            # imageData = fn.downsample(imageData, imageDownSample, axis=0)
            if imageData.size == 0:
                raise Exception('image Data has zero size')
            self.ui.plotWidget.setImage(imageData)
            pts = prog['points']
            floatpoints =[ (float(x[0]), float(x[1])) for x in pts]
            width  = (pts[1] -pts[0]).length() # width is x in M
            height = (pts[2]- pts[0]).length() # heigh in M
            self.ui.plotWidget.getView().setAspectLocked(True)
            self.ui.plotWidget.imageItem.setRect(QtCore.QRectF(0., 0., width, height))
            self.ui.plotWidget.autoRange()
           # self.ui.histogram.imageChanged(autoLevel=True)
            #print 'rectscan - nscans, samplesperscan: ', prog['nScans'], samplesPerScan
            sd = self.pr.getDevice(self.scannerDevice())
            camMod = sd.cameraModule().window()
            if self.img is not None:
                camMod.removeItem(self.img)
                self.img = None
            self.img = pg.ImageItem(imageData.mean(axis=0))
            camMod.addItem(self.img)
            w = imageData.shape[1]
            h = imageData.shape[2]
            localPts = map(pg.Vector, [[0,0], [w,0], [0,h], [0,0,1]]) # w and h of data of image in pixels.
            globalPts = prog['points'] # sort of. - 
            m = pg.solve3DTransform(localPts, map(pg.Vector, globalPts+[[0,0,1]]))
            m[:,2] = m[:,3]
            m[2] = m[3]
            m[2,2] = 1
            tr = QtGui.QTransform(*m[:3,:3].transpose().reshape(9))
            self.img.setTransform(tr)
            storeFlag = frame['cmd']['protocol']['storeData'] # get flag 
           # print 'srttransform: ', pg.SRTTransform3D(tr)
            if storeFlag:
                dirhandle = frame['cmd']['protocol']['storageDir'] # grab directory
                self.info={'detector': self.detectorDevice(), 'scanner': self.scannerDevice(), 'indices': prog['startStopIndices'], 
                           'samplesPerScan': samplesPerScan, 'nscans': prog['nScans'], 
                           'positions': floatpoints, # prog['points'],
                           'downSample': imageDownSample,
                           'transform': pg.SRTTransform3D(tr),
                           }
                           
                # to line below, add x, y for the camera (look at camera video output)
                info = [dict(name='Time', units='s', 
                             values=t[prog['startStopIndices'][0]:prog['startStopIndices'][0]+nscans*samplesPerScan:samplesPerScan]), 
                        dict(name='Distance'), self.info]
                print self.info
                print info
                ma = metaarray.MetaArray(imageData, info=info)
                
                dirhandle.writeFile(ma, 'Imaging.ma')
        
    def clear(self):
        self.imageView.clear()
        scene = self.img.scene()
        if scene is not None:
            scene.removeItem(self.img)

    def imageAlphaAdjust(self):
        if self.img is None:
            return
        alpha = self.ui.alphaSlider.value()
        self.img.setImage(opacity=float(alpha/100.))
        
        
    def _updateCamModImage(self):
        # update image levels
        self.img.setLevels(self.imageView.ui.histogram.getLevels())
