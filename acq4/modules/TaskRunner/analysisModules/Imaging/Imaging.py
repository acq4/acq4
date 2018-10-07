# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import division
from acq4.modules.TaskRunner.analysisModules import AnalysisModule
from acq4.Manager import getManager
from acq4.util import Qt
from .imagingTemplate import Ui_Form
import numpy as np
import acq4.pyqtgraph as pg
import acq4.util.functions as fn
import acq4.util.metaarray as metaarray
from acq4.devices.Microscope import Microscope
from acq4.util.HelpfulException import HelpfulException
# import acq4.devices.Scanner.ScanUtilityFuncs as SUFA
from acq4.devices.Scanner.scan_program.rect import RectScan
from acq4.pyqtgraph.parametertree import ParameterTree, Parameter

class ImagingModule(AnalysisModule):
    def __init__(self, *args):
        AnalysisModule.__init__(self, *args)
        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)
        self.splitter = Qt.QSplitter()
        self.layout.addWidget(self.splitter)
        self.ptree = ParameterTree()
        self.splitter.addWidget(self.ptree)
        self.imageView = pg.ImageView()
        self.splitter.addWidget(self.imageView)
        
        self.params = Parameter(name='imager', children=[
            dict(name='scanner', type='interface', interfaceTypes=['scanner']),
            dict(name='detectors', type='group', addText="Add detector.."),
            dict(name='decomb', type='float', readonly=False, value=20e-6, suffix='s', siPrefix=True, bounds=[0, 1e-3], step=1e-6, decimals=5, children=[
                dict(name='auto', type='action'),
                dict(name='subpixel', type='bool', value=False),
                ]),
            dict(name='downsample', type='int', value=1, suffix='x', bounds=[1,None]),
            dict(name='display', type='bool', value=True),
            dict(name='scanProgram', type='list', values=[]),
            dict(name='Objective', type='str', value='Unknown', readonly=True),
            dict(name='Filter', type='str', value='Unknown', readonly=True),
            ])
        self.ptree.setParameters(self.params, showTop=False)
        self.params.sigTreeStateChanged.connect(self.update)
        self.params.child('detectors').sigAddNew.connect(self.addDetectorClicked)
        self.params.child('decomb', 'auto').sigActivated.connect(self.autoDecomb)

        self.man = getManager()
        self.scannerDev = self.man.getDevice(self.params['scanner'])
        # find first scope device that is parent of scanner
        dev = self.scannerDev
        while dev is not None and not isinstance(dev, Microscope):
            dev = dev.parentDevice()
        self.scopeDev = dev
                
        self.lastFrame = None
        # self.SUF = SUFA.ScannerUtilities()
        # self.ui.alphaSlider.valueChanged.connect(self.imageAlphaAdjust)        
        self.img = pg.ImageItem()  ## image shown in camera module
        self.img.setLookupTable(self.imageView.ui.histogram.getLookupTable)  # image fetches LUT from the ImageView
        self.imageView.ui.histogram.sigLevelsChanged.connect(self._updateCamModImage)
        self.imageView.imageItem.setAutoDownsample(True)
        # self.ui.scannerComboBox.setTypes('scanner')
        # self.ui.detectorComboBox.setTypes('daqChannelGroup')

    def opticsUpdate(self, reset=False):
        self.params['Objective'] = self.scopeDev.currentObjective.name()
        if self.filterDevice is not None:
            self.params['Filter'] = self.filterDevice.currentFilter.name()
        
    def addDetectorClicked(self):
        self.addNewDetector()

    def addNewDetector(self, name='detector', value=None):
        self.params.child('detectors').addChild(
            dict(name=name, type='interface', interfaceTypes=['daqChannelGroup'], value=value, removable=True),
            autoIncrementName=True)
        
        for detector in self.params.param('detectors') :
            det = self.man.getDevice(detector.value())
            filt = det.getFilterDevice()
            if filt is not None:
                self.filterDevice =  self.man.getDevice(filt)
            else:
                self.filterDevice = None

        if self.filterDevice is not None:
            self.filterDevice.sigFilterChanged.connect(self.opticsUpdate)
        
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
        dets = state['children'].get('detectors', {}).pop('children', {})
        for name, data in dets.items():
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

    def autoDecomb(self):
        # Determine decomb duration
        rs = self.lastResult[0]['scanParams']
        pmtdata = self.lastResult[0]['pmtdata']
        lag = rs.measureMirrorLag(pmtdata[0], subpixel=self.params['decomb', 'subpixel'])
        self.params['decomb'] = lag

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
        scanCmd = frame['cmd'][self.params['scanner']]
        if 'program' not in scanCmd:
            return
        progs = scanCmd['program']
        if len(progs) == 0:
            self.image.setImage(np.zeros((1,1)))
            return

        # Update list so user can select program component
        supportedTypes = ['rect']
        progs = dict([(prog['name'], prog) for prog in progs if prog['type'] in supportedTypes])
        self.params.child('scanProgram').setLimits(list(progs.keys()))
        selectedProg = self.params['scanProgram']
        if selectedProg not in progs:
            return
        prog = progs[selectedProg]
        
        if prog['type'] == 'rect':
            # keep track of some analysis in case it should be stored later
            result = {
                'params': self.params.saveState(filter='user')['children'],
                'pmtdata': pmtdata,
            }
            self.lastResult.append(result)

            rs = RectScan()
            rs.restoreState(prog['scanInfo'])
            result['scanParams'] = rs

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
            st = Qt.QTransform()
            st.scale(self.params['downsample'], 1)
            tr = st * tr
            result['transform'] = pg.SRTTransform3D(tr)

            frameTimes = rs.frameTimes()

            # Display image locally
            self.imageView.setImage(imageData, xvals=frameTimes, levelMode=levelMode)
            self.imageView.getView().setAspectLocked(True)
#            self.imageView.imageItem.setRect(Qt.QRectF(0., 0., rs.width, rs.height))  # TODO: rs.width and rs.height might not be correct!
            self.imageView.imageItem.resetTransform()
            self.imageView.imageItem.scale((rs.width/rs.height)/(imageData.shape[1]/imageData.shape[2]), 1.0)
            self.imageView.autoRange()

            # Display image remotely (in the same camera module as used by the scanner device)
            if self.params['display']:
                self.img.setVisible(True)
                sd = self.pr.getDevice(self.params['scanner'])
                camMod = sd.cameraModule().window()
                camMod.addItem(self.img, z=1000)
                self.img.setImage(imageData.mean(axis=0))
                self.img.setTransform(tr)
            else:
                self.img.setVisible(False)
        else:
            raise Exception("Imaging module only supports rect scans (not %s)." % prog['type'])
        
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
