# -*- coding: utf-8 -*-
"""
pbm_ImageAnalysis is an analysis module for ACQ4.
This module provides:
    1. Bleaching correction of image stacks
    2. Normalization of image stacks
    3. ROI's on Z-stacks (or T-stacks), including saving and retrieving the ROI files
        (the format is the same as in PyImageAnalysis - simple text file)
    4. Display of simultaneously recorded physiology:
        simple spike detection (on cell, intracellular)
    5. Cross-correlation of ROI signals in the imaging data (pairwise), and some
        display of the results
    To be done:
    6. Cross-correlation of ROI and spike trains.
    
    Fall, 2011
    Jan, 2012.
    Paul B. Manis, Ph.D.
    UNC Chapel Hill
    Supported by NIH/NIDCD Grants:
        DC004551 (Cellular mechanisms of auditory information processing)
        DC000425 (Physiology of the Dorsal Cochlear Nucleus Molecular Layer)
        DC009809 (Auditory Cortex: Synaptic organization and plasticity)

"""

from PyQt4 import QtGui, QtCore
from lib.analysis.AnalysisModule import AnalysisModule
from collections import OrderedDict
import os, shutil
import operator
import pyqtgraph as pg
import PIL as Image
from metaarray import MetaArray
import numpy
import scipy
import ctrlTemplate
import ctrlTemplateAnalysis
import ctrlTemplatePhysiology
from lib.analysis.tools import Utility
from lib.analysis.tools import Fitting
from lib.analysis.tools import PlotHelpers as PH # matlab plotting helpers
from lib.util import functions as FN

# import ImageP # avaialable as part of the STXMPy package


#import smc as SMC # Vogelstein's OOPSI analysis for calcium transients

import pylab as PL
""" 
We use matplotlib/pylab for *some* figure generation.

"""
class pbm_ImageAnalysis(AnalysisModule):
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        # per-instance parameters:
        self.currentDataDirectory = None # currently selected data directory (if valid)
        self.refImage = None # Reference image data used for ratio calculations
                                # This image may come from a separate file or a calculation on the present file
        self.physData = None # physiology data associated with the current image
        self.dataStruct = 'flat' # 'flat' or 'interleaved' are valid at present.
        self.imageInfo = []
        self.ignoreFirst = False # ImagePhys_ignoreFirst
        self.rectSelect = True #
        self.tStart = 0.0 # baseline time start = applies to the image: ImagePhys_BaseStart
        self.tEnd = 50.0 # baseline time end (msec) : ImagePhys_BaseEnd
        self.imageLPF = 0.0 # low pass filter of the image data, Hz: ImagePhys_ImgLPF
        self.physLPF = 0.0 # low pass filter of the physiology data, Hz (0 = no filtering): ImagePhys_PhysLPF
        self.physLPFChanged = False # flag in case the physiology LPF changes (avoid recalculation)
        self.physSign = 0.0 # ImagePhys_PhysSign (detection sign for events)
        self.physThresh = -50.0 # ImagePhys_PhysThresh (threshold in pA to detect events)
        self.physThreshLine = None
        self.ratioImages = False # only set true once a ratio (reference) image is loaded 
        self.ROIfig = None
        self.baseImage=[]
        self.viewFlag = False # false if viewing movie, true if viewing fixed image
        self.referenceImage = []
        self.AllRois = []
        self.nROI = 0 # count of ROI's in the window
        self.rois = []
        self.currentRoi = None
        self.imageData = [] # Image Data array, information about the data is in the dataState dictionary
        self.lastROITouched=[]
        self.spikesFound = None
        self.burstsFound = None
        self.spikeTimes = []
        self.burstTimes = []
        
        self.spikesFoundpk = None
        self.withinBurstsFound = None
        self.FData = []
        self.MPLFig = None # We keep one instance of a matplotlib figure, create and destroy as needed
        
        self.ctrlWidget = QtGui.QWidget()
        self.ctrl = ctrlTemplate.Ui_Form()
        self.ctrl.setupUi(self.ctrlWidget)
        
        self.ctrlImageFuncWidget = QtGui.QWidget()
        self.ctrlImageFunc = ctrlTemplateAnalysis.Ui_Form()
        self.ctrlImageFunc.setupUi(self.ctrlImageFuncWidget)
        
        self.ctrlPhysFuncWidget = QtGui.QWidget()
        self.ctrlPhysFunc = ctrlTemplatePhysiology.Ui_Form()
        self.ctrlPhysFunc.setupUi(self.ctrlPhysFuncWidget)
        
        self.initDataState()
        self.RGB = Utility.makeRGB()
        
        ## Setup basic GUI
        self._elements_ = OrderedDict([
            ('File Loader', {'type': 'fileInput', 'size': (150, 300), 'host': self, 'showFileTree': True}),
            ('Image',       {'type': 'imageView', 'pos': ('right', 'File Loader'), 'size': (500, 500)}),
            ('Analysis',    {'type': 'ctrl', 'object': self.ctrlImageFuncWidget, 'host': self, 'size': (150,300)}),
            ('Physiology',  {'type': 'ctrl', 'object': self.ctrlPhysFuncWidget, 'pos' : ('above', 'Analysis'), 'size': (150,300)}),
            ('Imaging Parameters',  {'type': 'ctrl', 'object': self.ctrlWidget, 'pos' : ('above', 'Physiology'), 'size': (150,300)}), 
            ('ROI Plot',   {'type': 'plot',  'pos': ('right', 'Imaging Parameters'),'size': (1000, 300)}),
            ('Phys Plot',   {'type': 'plot',  'pos': ('bottom', 'ROI Plot'),'size': (1000, 300)}),
            ('Trial Plot',  {'type': 'plot', 'size': (1000, 300)}),
#            ('Line Scan',   {'type': 'imageView', 'size': (1000, 300)}),
            #('Data Table',  {'type': 'table', 'pos': ('below', 'Time Plot')}),
        ])
        self.initializeElements()
        self.ctrl.ImagePhys_RectSelect.stateChanged.connect(self.updateRectSelect)
        self.ctrl.ImagePhys_Update.clicked.connect(self.updateAnalysis)
        self.ROI_Plot = self.getElement('ROI Plot', create=True)
        self.trialPlot = self.getElement('Trial Plot', create=True)
        self.physPlot = self.getElement('Phys Plot', create = True)
        self.lr = pg.LinearRegionItem([0, 1])
        # self.ROI_Plot.addItem(self.lr)
        self.updateRectSelect()    
        self.ROI_Plot.plotItem.vb.setXLink('Phys Plot') # not sure - this seems to be at the wrong level in the window manager
        self.imageView = self.getElement('Image', create=True)
        self.imageItem = self.imageView.imageItem      

        # Plots are updated when the selected region changes
        self.lr.sigRegionChanged.connect(self.updateAnalysis)
        self.imageView.sigProcessingChanged.connect(self.processData)
        
        # main image processing buttons
        self.ctrl.ImagePhys_addRoi.clicked.connect(self.addOneROI)
        self.ctrl.ImagePhys_clearRoi.clicked.connect(self.clearAllROI)
        self.ctrl.ImagePhys_getRatio.clicked.connect(self.loadRatioImage)
        self.ctrl.ImagePhys_ImgNormalize.clicked.connect(self.doNormalize)
        self.ctrl.ImagePhys_UnBleach.clicked.connect(self.unbleachImage)
        self.ctrl.ImagePhys_View.currentIndexChanged.connect(self.changeView)
        self.ctrl.ImagePhys_RetrieveROI.clicked.connect(self.restoreROI)
        self.ctrl.ImagePhys_SaveROI.clicked.connect(self.saveROI)
        self.ctrl.ImagePhys_CorrTool_BL1.clicked.connect(self.Baseline1)
        self.ctrl.ImagePhys_CorrTool_HPF.clicked.connect(self.BaselineHPF)
 #       self.ctrl.ImagePhys_CorrTool_:PF.clicked.connect(self.SignalLPF)
        self.ctrl.ImagePhys_ExportTiff.clicked.connect(self.ExportTiff)
        
        # Physiology analysis buttons and controls
        self.ctrlPhysFunc.ImagePhys_DetectSpikes.clicked.connect(self.detectSpikes)
        self.ctrlPhysFunc.ImagePhys_PhysThresh.valueChanged.connect(self.showPhysTrigger) 
        #self.ctrlPhysFunc.ImagePhysFuncs_RevSTA.clicked.connect(self.RevSTA)
        self.ctrlPhysFunc.ImagePhys_STA.clicked.connect(self.computeSTA)
        self.ctrlPhysFunc.ImagePhys_BTA.clicked.connect(self.computeBTA)
        self.ctrlPhysFunc.ImagePhys_PhysLPF.valueChanged.connect(self.physLPF_valueChanged)
        
        #
        # Imaging analysis buttons
        #
        self.ctrlImageFunc.IAFuncs_Distance.clicked.connect(self.ROIDistances)
        self.ctrlImageFunc.IAFuncs_DistanceStrength.clicked.connect(self.ROIDistStrength)
        self.ctrlImageFunc.IAFuncs_NetworkGraph.clicked.connect(self.NetworkGraph)
        self.ctrlImageFunc.IAFuncs_Analysis_AXCorr_Individual.clicked.connect(self.Analog_Xcorr_Individual)
        self.ctrlImageFunc.IAFuncs_Analysis_AXCorr.clicked.connect(self.Analog_Xcorr)
        self.ctrlImageFunc.IAFuncs_Analysis_UnbiasedXC.clicked.connect(self.Analog_Xcorr_unbiased)
        self.ctrlImageFunc.IAFuncs_DistanceStrengthPrint.clicked.connect(self.printDistStrength)

    def initDataState(self):
        self.dataState = {'Loaded': False, 'bleachCorrection': False, 'Normalized': False,
                        'NType' : None, 'Structure': 'Flat', 'NTrials': 0}
        self.ctrl.ImagePhys_BleachInfo.setText('None')
        self.ctrl.ImagePhys_NormInfo.setText('None')
        self.IXC_Strength = []
        self.ROIDistanceMap = []

        
    def updateRectSelect(self):
        self.rectSelect = self.ctrl.ImagePhys_RectSelect.isChecked()
        if self.rectSelect:
            self.ROI_Plot.plotItem.vb.setLeftButtonAction(mode='rect') # use the rubber band box instead
            self.physPlot.plotItem.vb.setLeftButtonAction(mode='rect') # use the rubber band box instead
        else:
            self.ROI_Plot.plotItem.vb.setLeftButtonAction(mode='pan') # use the standard pan mode instead
            self.physPlot.plotItem.vb.setLeftButtonAction(mode='pan') # use the standard pan modeinstead
        
    def changeView(self):
        if self.dataState['Loaded'] is False:
            return # no data - so skip this.
        view = self.ctrl.ImagePhys_View.currentText()
        if view == 'Reference Image': 
            self.imageView.setImage(self.baseImage)
            self.viewFlag = True
        if view == 'Std Image':
            self.imageView.setImage(self.stdImage)
        if view == 'Movie':
            self.imageView.setImage(self.imageData)
            self.viewFlag = False

    def processData(self):
        self.normData = []
        self.imageData = []
        print 'in processData...'
        for img in self.rawData:
            print 'doing image processdata'
            n = numpy.empty(img.shape, dtype=img.dtype)
            for i in range(img.shape[0]):
                n[i] = self.imageView.normalize(img[i])
            self.normData.append(n)
            
            imgSet = {'procMean': n.mean(axis=0), 'procStd': n.std(axis=0)}
            print 'appending...'
            self.imageData.append(imgSet)
            
    def updateAnalysis(self):
        self.getDataStruct()
        roi = self.currentRoi
        plot = self.getElement('Trial Plot')
        plot.clearPlots()
        print 'LPF Changed?: ', self.physLPFChanged
        if self.physLPFChanged: # only update if the LPF filter has changed
            self.readPhysiology(self.currentDataDirectory) # re-read in case LPF has changed
        c = 0
        print 'Roi in update: ', roi
        if self.currentRoi is None:
            return
        for img in self.normData: # pull from all the normalized data arrays (in a list)
            #img = img.mean(axis=1)
            rgn = self.lr.getRegion()
            img = img[:, rgn[0]:rgn[1]].mean(axis=1)
            data = roi.getArrayRegion(img, self.imageItem, axes=(1,2))
            m = data.mean(axis=1).mean(axis=1)
            #data = roi.getArrayRegion(img, self.view.imageView, axes=(1,2))
            #s = data.mean(axis=1).mean(axis=1)
            plot.plot(m, pen=pg.hsvColor(c*0.2, 1.0, 1.0))
            #self.plot.plot(m-s, pen=pg.hsvColor(c*0.2, 1.0, 0.4))
            #self.plot.plot(m+s, pen=pg.hsvColor(c*0.2, 1.0, 0.4))
            c += 1
            
            #if c == 1:
                #self.getElement('Line Scan').setImage(data.mean(axis=2))
        #if self.traces is None:
            #return
        #rgn = self.lr.getRegion()
        #data = self.traces['Time': rgn[0]:rgn[1]]
        #self.plot2.plot(data.mean(axis=1), clear=True)
        #self.plot2.plot(data.max(axis=1))
        #self.plot2.plot(data.min(axis=1))


    def loadFileRequested(self, dh):
        """Called by file loader when a file load is requested.
        In this case, we request a directory, corresponding to a sample run,
        which may contain both physiology and image data"""
        
        self.downSample = int(self.ctrl.ImagePhys_Downsample.currentText())
        if self.downSample <= 0:
            self.downSample = 1 # same as "none"
        self.initDataState()
        
        self.shiftFlag = False # eventually, but at the moment it does NOT work
        
        if len(dh) != 1:
            QtGui.QMessageBox.warning(self,
                                      "pbm_ImageAnalysis: loadFileRequested Error",
                                      "Can only load one data set/run at a time.")
            return False
            # raise Exception("Can only load one data set/run at a time.")
        dh = dh[0]
        self.currentFileName = dh.name()
        self.imageScaleUnit = 'pixels'
        if dh.isFile(): # direct file "video....ma" read
            if self.downSample == 1:
                img = dh.read() # read the image stack
            else:
                (img, info) = self.tryDownSample(dh)
            if img == []:
                return False
            if self.ignoreFirst:
                fi = 1
            else:
                fi = 0
            self.clearPhysiologyInfo() # clear the physiology data currently in memory to avoid confusion
            self.imageData = img.view(numpy.ndarray) # load into rawData, clipping the first image if needed
            self.rawData = self.imageData.copy()[fi:] # save the raw data.
            self.imageData = self.imageData[fi:]
            self.baseImage = self.imageData[0] # save first image in series to show after processing...
            if self.downSample > 1:
                self.imageTimes = info[0]['values']
                self.imageTimes = self.imageTimes[fi:]
                self.imageTimes = self.imageTimes[::self.downSample]
                nFrames = numpy.shape(self.imageData)[0]
                print 'frames: %d   imageTimes: %d' % (nFrames, len(self.imageTimes))
                self.imageTimes = self.imageTimes[:nFrames] # sometimes these don't match when downsampling
                print 'imageTime: %d' % (len(self.imageTimes))
                self.imageInfo = info
            else:
                self.imageTimes = img.infoCopy()[0].values()[1]
                self.imageTimes = self.imageTimes[fi:]
                self.imageInfo = img.infoCopy()
#            if self.shiftFlag:
#                imean = numpy.mean(numpy.mean(numpy.mean(self.imageData, axis=1), axis=1), axis=0)
#                self.imageData = self.AlignStack(self.imageData, fi, verbose=True)
            self.imageView.setImage(self.imageData)
            self.dataState['Loaded'] = True
            self.dataState['Structure'] = 'Flat'
            self.background = self.rawData.mean(axis=2).mean(axis=1)
            self.backgroundmean = self.background.mean(axis=0)

#            QtGui.QMessageBox.warning(self,
#                                      "pbm_ImageAnalysis: loadFileRequested Error",
#                                      "Select a Directory containing the data, not the data file itself")
#            return
#            raise Exception("Select a Directory containing the data, not the data file itself")

        elif self.dataStruct is 'flat':
            #print 'getting Flat data structure!'
            self.rawData = []
            self.readPhysiology(dh)
            img = dh['Camera/frames.ma'].read() # read the image stack
            if self.ignoreFirst:
                fi = 1
            else:
                fi = 0
            self.imageData = img.view(numpy.ndarray) # load into rawData, clipping the first image if needed
            self.rawData = self.imageData.copy()[fi:] # save the raw data.
            self.imageData = self.imageData[fi:]
            self.baseImage = self.imageData[0] # just to show after processing...
            self.imageTimes = img.infoCopy()[0].values()[1]
            self.imageTimes = self.imageTimes[fi:]
            self.imageInfo = img.infoCopy()
            self.imageView.setImage(self.imageData)
            self.dataState['Loaded'] = True
            self.dataState['Structure'] = 'Flat'
            self.background = self.rawData.mean(axis=2).mean(axis=1)
            self.backgroundmean = self.background.mean(axis=0)

            #self.processData()

        else: # interleaved data structure (Deepti Rao's calcium imaging data)
            dirs = dh.subDirs() # find out what kind of data we 
            images = [[],[],[],[]]
            ## Iterate over sequence
            minFrames = None
            for d in dirs: # each of the directories contains a data set
                d = dh[d]
                try:
                    ind = d.info()[('Clamp1', 'amp')]
                except:
                    print d
                    print d.info()
                    raise
                img = d['Camera/frames.ma'].read()
                images[ind].append(img)
                
                if minFrames is None or img.shape[0] < minFrames:
                    minFrames = img.shape[0]
                
            self.rawData = []
            self.imageData = []
            print "len images: %d " % (len(images))
            while len(images) > 0:
                imgs = images.pop(0)
                img = np.concatenate([i[np.newaxis,:minFrames,...] for i in imgs], axis=0)
                self.rawData.append(img.astype(np.float32))
                #img /= self.background
            
            ## remove bleaching curve from first two axes
            ctrlMean = self.rawData[0].mean(axis=2).mean(axis=2)
            trialCurve = ctrlMean.mean(axis=1)[:,np.newaxis,np.newaxis,np.newaxis]
            timeCurve = ctrlMean.mean(axis=0)[np.newaxis,:,np.newaxis,np.newaxis]
            del ctrlMean
            for img in self.rawData:
                img /= trialCurve
                img /= timeCurve

            #for img in self.rawData:
                #m = img.mean(axis=0)
                #s = img.std(axis=0)
                #if self.background is not None:
                    #m = m.astype(np.float32)
                    #m /= self.background
                    #s = s.astype(np.float32)
                    #s /= self.background
                #imgSet = {'mean': m, 'std': s}
                #self.data.append(imgSet)
                #self.imgMeans.append(m)
                #self.imgStds.append(s)
        
            self.imageItem.setImage(self.rawData[1].mean(axis=0))
            self.processData()
        
            ## set up the selection region correctly and prepare IV curves
            #if len(dirs) > 0:
                #end = cmd.xvals('Time')[-1]
                #self.lr.setRegion([end *0.5, end * 0.6])
                #self.updateAnalysis()
                #info = [
                    #{'name': 'Command', 'units': cmd.axisUnits(-1), 'values': np.array(values)},
                    #data.infoCopy('Time'), 
                    #data.infoCopy(-1)]
                #self.traces = MetaArray(np.vstack(traces), info=info)
            self.imageData = self.rawData
        self.ROI_Plot.clearPlots()
        self.getDataStruct()
        self.currentDataDirectory = dh
        self.updateAvgStdImage()
        self.updateThisROI(self.lastROITouched)    
        return True

    def updateAvgStdImage(self):
        """ update the reference image types and then make sure display agrees.
        """
        self.aveImage = numpy.mean(self.imageData, axis=0)
        self.stdImage = numpy.std(self.imageData, axis=0)
        self.changeView()
        
    def getImageScaling(self):
        """ retrieve scaling factor and set imageScaleUnit from the info on the image file
            In the case where the information is missing, we just set pixels.
        """
        if 'pixelSize' in self.imageInfo[3]:
            print self.imageInfo[3]
            pixelsize = self.imageInfo[3]['pixelSize']
            region = self.imageInfo[3]['region']
            binning = self.imageInfo[3]['binning']
            self.imageScaleUnit = 'um'
            sf = 1.0e6
        else:
            print 'Old File without full scaling information on image, setting to defaults of pixels.'
            sh = self.imageData.shape
            region = [0, 0, sh[1], sh[2]] # make region from image data directly [x0,y0,y1,y1]
            px = [1.0, 1.0] # scaling is now in pixels directly
            self.imageScaleUnit = 'pixels'
            sf = 1.0
            pixelsize = [1.0, 1.0]
        sx = region[2]-region[0]
        sy = region[3]-region[1]
        px = [0, 0]
        px[0] = pixelsize[0] * sf
        px[1] = pixelsize[1] * sf
        sx = sx*px[0]
        sy = sy*px[1]
        print "sx, sy, px", sx, sy, px
        return(sx, sy, px)

    def getfileSize(self, fileName, msg=False):
        """ Measure the dimensions of an image MetaArray file."""
        try:
            im = MetaArray(file = fileName, subset=(slice(None), slice(0,1), slice(0,1)))
            info = im.infoCopy()
            sh = im.shape
            nframes = sh[0]
            im = MetaArray(file = fileName, subset=(slice(0,1), slice(None), slice(None)))
            sh = im.shape
            xdim = sh[1]
            ydim = sh[2]
            if msg:
                print "File %s has %d frames, of %d x %d pixels" % (fileName,nframes, xdim, ydim)
                return((nframes, xdim, ydim), info)
        except:
            return((),[])

    def tryDownSample(self, dh):
        print "Trying downsampling file at %d" % (self.downSample)
        (sh, info) = self.getfileSize(dh.name(), msg=True) # get the file length
        block_size = self.downSample*100
        totframes = int(sh[0]/self.downSample)
        block_loop = int(sh[0]/block_size)
        leftover = sh[0] - block_loop*block_size
        if leftover > 0:
            block_loop = block_loop + 1
            leftover = self.downSample*int(leftover/self.downSample)
        print "block loops: %d  leftover: %d, totframes: %d" % (block_loop, leftover, totframes)
        im = []
        ind = 0
        frame = 0
        for bl in range(block_loop):
            block_pos = bl * block_size
            if bl == (block_loop - 1) and leftover > 0:
                block_size = leftover
            print "block_pos: %d  block: %d, block_size: %d" % (block_pos, bl, block_size)
            imt = MetaArray(file=dh.name(), subset=(slice(block_pos,block_pos+block_size),slice(None), slice(None)))
            if im == []:
                im = numpy.zeros((totframes,sh[1], sh[2]))
            print imt.shape
            print im.shape
            for fr in range(0, block_size, self.downSample):
               # print "frame: %d ind: %d" % (fr, ind)
                im[ind] = numpy.mean(imt[fr:(fr+self.downSample),:,:], axis=0)
                ind = ind + 1
        return(im, info)
#        except:
#            print "Unable to read file downsampled at %d" % (self.downSample)
#            #error = 1
#            return([])

                    
    def clearPhysiologyInfo(self):
        self.physPlot.clearPlots()
        self.physData = []
        self.physThreshLine = None
        self.spikesFound = None
        self.spikeFoundpk = None
        self.burstsFound = None
        self.withinBurstsFound = None
        self.makeSpikePointers() # prepare the graph
        
    def readPhysiology(self, dh):
        """ call to read the physiology from the primary data channel
        dh is thehandle to the directory where the data is stored (not the file itself)
        """
        if dh is None:
            return
        self.clearPhysiologyInfo()
        data = self.dataModel.getClampFile(dh).read() # retrieve the physiology traces
        self.physData = self.dataModel.getClampPrimary(data)
        self.physData = self.physData * 1e12 # convert to pA
        info1 = data.infoCopy()
        self.samplefreq = info1[2]['DAQ']['primary']['rate']
        if self.physLPF > 250.0 and self.physLPF < 0.5*self.samplefreq: # respect Nyquist, just minimally
            #print self.physData.shape
            self.physData =  Utility.SignalFilter_LPFBessel(self.physData, self.physLPF, self.samplefreq, NPole = 8)
            #print self.physData.shape
        self.physLPFChanged = False # we have updated now, so flag is reset
        maxplotpts=50000
        shdat = self.physData.shape
        decimate_factor = 1
        if shdat[0] > maxplotpts:
            decimate_factor = int(numpy.floor(shdat[0]/maxplotpts))
            if decimate_factor < 1:
                decimate_factor = 1
        else:
            pass
            # store primary channel data and read command amplitude
        #print 'decimate factor: %d' % (decimate_factor)
        #print 'Number of points in original data set: ', shdat
        tdat = data.infoCopy()[1]['values']
        tdat = tdat[::decimate_factor]
        self.physPlot.plot(tdat, self.physData[::decimate_factor], pen=pg.mkPen('w')) # , decimate=decimate_factor)
        self.tdat = data.infoCopy()[1]['values']
        self.showPhysTrigger()
        self.detectSpikes()
        
    def loadRatioImage(self):
        pass # not implemented yet...
        self.background = dh.read()[np.newaxis,...].astype(float)
        self.background /= self.background.max()
        return

    def getDataStruct(self):
        ds = self.ctrl.ImagePhys_DataStruct.currentIndex()
        if ds == 0:
            self.dataStruct = 'flat'
        else:
            self.dataStruct = 'interleaved'
        ifimg = self.ctrl.ImagePhys_ignoreFirst.isChecked()
        if ifimg is True:
            self.ignoreFirst = True
        else:
            self.ignoreFirst = False
        lpf = self.ctrlPhysFunc.ImagePhys_PhysLPF.value()
        if lpf == 0.0:
            self.physLPF = 0.0
        else:
            self.physLPF = lpf
        #print "data struct = %s" % self.dataStruct
        #print "ignore First: ", self.ignoreFirst
        #print "lpf: %8.1f" % self.physLPF

    def physLPF_valueChanged(self):
        self.physLPFChanged = True # just note that it has changed
    
    def doNormalize(self):
        method = self.ctrl.ImagePhys_ImgMethod.currentIndex()
        if method == 0: # (F-Fo)/Fo
            self.StandarddFFImage()
        if method == 1:
            self.MediandFFImage() # median 
        if method == 2:
            self.normalizeImage() # other normalization
        if method == 3: # g/r ratio  - future: requires image to be loaded (hooks in place, no code yet)
            pass
        self.updateAvgStdImage()
        self.calculateROIs()
        
    def ExportTiff(self):
        """ Take the current image data and make a directory with individual TIFF files
            for the frames, using PIL.
            Useful for making movies (read the tiffs into ImageJ, export QT or QVI file)
        """
        # self.ImageData
        tiffpath = '../TiffStacks/'
        if not os.path.isdir(tiffpath):
            os.makedirs(tiffpath)
        else: # overwrite the directory - by deleting existing files first
            if os.path.isdir(tiffpath): # keep the working directory clean.
                for root, dirs, files in os.walk(tiffpath):
                    for f in files:
                        os.unlink(os.path.join(root, f))
                    for d in dirs:
                        shutil.rmtree(os.path.join(root, d))
            
        image_sh = self.imageData.shape
        nframes = image_sh[0]
        xsize = image_sh[1]
        ysize = image_sh[2]
        print 'Writing tiff images to %s\n' % (tiffpath)
        for i in range(0, nframes):
            ai = Image.fromarray(self.imageData[i,:,:]*8192.0)
            fn = tiffpath + 'acq4_ImageAnalysis_%05d.tiff' % (i)
            ai.save(fn)
#
#---------baseline correction routines --------------------
#
    def Baseline1(self):       
    ### data correction routine to smooth out the baseline
    ###
        self.BFData = numpy.array(self.FData)
        self.FilterKernel = 11
        self.FilterOrder = 3
        thr = 2.0 # self.ui.CorrTool_Threshold.value()
        dds = self.BFData[:,0:-1].copy()
        for roi in range(0, self.nROI):
            d = self.BFData[roi,:].copy().T
            ds = Utility.savitzky_golay(d, kernel = 31, order = 5) # smooth data
            dds[roi,:] = numpy.diff(ds) # take derivative of smoothed data
            stdev = numpy.std(dds[roi,:])
            pts = numpy.where(numpy.abs(dds[roi,:]) < thr*stdev) # get subset of points to fit
            dds2 = numpy.diff(numpy.diff(ds))
            stdev2 = numpy.std(dds2)
            pts2 = numpy.where(numpy.abs(dds2) < thr*stdev2)
            s0 = set(numpy.transpose(pts).flat)
            s1 = set(numpy.transpose(pts2).flat)
            ptsok = list(s1.intersection(s0))

            if len(ptsok) == 0:
                return
            tf = self.imageTimes[ptsok]
            df = d[ptsok]
            p = numpy.polyfit(tf, df, 5)
            bd = numpy.polyval(p, self.imageTimes)
            dm = numpy.mean(d[0:10])
            self.BFData[roi,:] = Utility.savitzky_golay(d/bd, kernel = self.FilterKernel,
                                                      order = self.FilterOrder)
            self.FData[roi, :] = self.BFData[roi,:]
            #self.plotdata(self.times, 100*(self.BFData-1.0), datacolor = 'blue', erase = True,
            #          background = False, scaleReset=False, yMinorTicks=0, yMajorTicks=3,
            #          yLabel = u'\u0394F/F<sub>ROI %d</sub>')
        self.makeROIDataFigure(clear=False, gcolor='g')

    def BaselineHPF(self): 
        ### data correction
        ### try to remove baseline drift by high-pass filtering the data.
        
        print self.FData
        self.BFData = numpy.array(self.FData)
        print self.BFData.shape
        HPF = self.ctrl.ImagePhys_ImgHPF.value()
        LPF = self.ctrl.ImagePhys_ImgLPF.value() # 100.0
        if LPF < 4*HPF:
            print "please make lpf/hpf further apart in frequency"
            return

        dt = numpy.mean(numpy.diff(self.imageTimes))
        samplefreq = 1.0/dt
        if (LPF > 0.5*samplefreq):
            LPF = 0.5*samplefreq

        dds = self.BFData[:,0:-1].copy()
        for roi in range(0, self.nROI):
            d = self.BFData[roi,:].copy().T
            self.BFData[roi,:] = Utility.SignalFilter(d, LPF, HPF, samplefreq)
            self.FData[roi,:] = self.BFData[roi,:]
        #self.plotdata(self.times, 100*(self.BFData-1.0), datacolor = 'red', erase = True,
        #              background = False, scaleReset=False, yMinorTicks=0, yMajorTicks=3,
        #              yLabel = u'\u0394F/F<sub>ROI %d</sub>')
        self.makeROIDataFigure(clear=False, gcolor='r')

#
# detect spikes in physiology trace
#

    def showPhysTrigger(self):
        thr = self.ctrlPhysFunc.ImagePhys_PhysThresh.value()
        sign = self.ctrlPhysFunc.ImagePhys_PhysSign.currentIndex()
        if sign == 0:
            ysign = 1.0
        else:
            ysign = -1.0
        if self.physThreshLine is None:
            self.physThreshLine = self.physPlot.plot(x=numpy.array([self.tdat[0], self.tdat[-1]]),
                y=numpy.array([ysign*thr, ysign*thr]), pen=pg.mkPen('r'), clear=False)
        else:
            self.physThreshLine.setData(x=numpy.array([self.tdat[0], self.tdat[-1]]), 
                y=numpy.array([ysign*thr, ysign*thr]))

    def detectSpikes(self, burstMark = None):
        spikescale = 1.0 # or 1e-12...
        thr = spikescale*self.ctrlPhysFunc.ImagePhys_PhysThresh.value()
        sign = self.ctrlPhysFunc.ImagePhys_PhysSign.currentIndex()
        if sign == 0:
            ysign = 1.0
        else:
            ysign = -1.0
        (sptimes, sppts) = Utility.findspikes(self.tdat, ysign*self.physData, thr*spikescale, t0=None, t1= None, 
            dt = 1.0/self.samplefreq, mode='peak', interpolate=False, debug=False)
        self.SpikeTimes = sptimes
        if len(sptimes) <= 1:
            return
        yspmarks=ysign*thr*spikescale
        bList = self.defineSpikeBursts()
        self.burstTimes = bList
        yburstMarks = ysign*thr*0.9*spikescale
        ywithinBurstMarks = ysign*thr*0.8*spikescale
        self.makeSpikePointers(spikes=(sptimes, yspmarks), spikespk=(sptimes, self.physData[sppts]),
            bursts = (bList, yburstMarks, ywithinBurstMarks))
        print 'spikes detected: %d' % (len(sptimes))

    def makeSpikePointers(self, spikes = None, spikespk = None, bursts=None):
        # add scatterplot items to physiology trace  - these start out empty, but we can replace
        # the points in the arrays later.
        if spikes is not None and len(spikes[0]) > 0:
            if self.spikesFound is None:
                    self.spikesFound = pg.ScatterPlotItem(size=6, pen=pg.mkPen('g'), brush=pg.mkBrush(0, 255, 0, 200), 
                    symbol = 't', identical=True)
                    #self.clearPhysiologyInfosetPoints(x=[], y=spikes[1])
                    self.physPlot.addItem(self.spikesFound)
            else:
                self.spikesFound.setPoints(x=spikes[0], y=spikes[1]*numpy.ones(len(spikes[0])))
            
        if spikespk is not None and len(spikespk[0]) > 0:
            if self.spikesFoundpk is None:
                self.spikesFoundpk = pg.ScatterPlotItem(size=4, pen=pg.mkPen('r'), brush=pg.mkBrush(0, 255, 0, 200), 
                    symbol = 'o', identical=True)
                #self.spikesFoundpk.setPoints(x=spikespk[0], y=spikespk[1])
                self.physPlot.addItem(self.spikesFoundpk)
            else:
                self.spikesFoundpk.setPoints(x=spikespk[0], y=spikespk[1]*numpy.ones(len(spikespk[0])))
            
        if bursts is not None and len(bursts[0]) > 0:
            if self.burstsFound is None:
                self.burstsFound = pg.ScatterPlotItem(size=7, pen=pg.mkPen('y'), brush=pg.mkBrush(255, 255, 0, 200),
                    symbol = 's', identical = True)
                #self.burstsFound.setPoints(x=bursts[0], y = bursts[1])
                self.physPlot.addItem(self.burstsFound)
            if self.withinBurstsFound is None:
                self.withinBurstsFound = pg.ScatterPlotItem(size=7, pen=pg.mkPen('b'), brush=pg.mkBrush(0, 0, 255, 200),
                    symbol = 'o', identical = True)
                #self.withinBurstsFound.addPoints(x=withinbursts[0], y = withinbursts[1])
                self.physPlot.addItem(self.withinBurstsFound)
            onsetSpikes = []
            burstSpikes= []
            for b in range(len(bursts[0])):
                bdat = bursts[0][b]
                onsetSpikes.append(bdat[0])
                burstSpikes.extend(bdat[1:].tolist())
            self.burstsFound.setPoints(x=onsetSpikes, y = [bursts[1] for x in range(len(onsetSpikes))])
            self.withinBurstsFound.setPoints(x=burstSpikes, y = [bursts[2] for x in range(len(burstSpikes))])
                
    def checkMPL(self):
        if self.MPLFig is not None:
            PL.close()
            self.MPLFig = None
            
        
    def RevSTA(self):
        pass
        
    def computeSTA(self):
        """
        Compute the spike-triggered average of the ROI signals, given the spike train. 
        This one is just the basic spike-triggered average
        """
        self.computeBTA(singleSpike=True)

    def computeBTA(self, singleSpike=False):
        """
        Compute the spike-triggered average of the ROI signals, given the spike train. 
        The following criteria are avaiable to select from within the spike train:
        1. minimum time before a spike
        2. minimum rate AFTER the spike (for the next N spikes)
        3. minimum # of spikes (N) for minimum rate determination (define burst)
        """
        if not singleSpike: # normal processing is to do bursts, using first spike of burst
            if self.burstTimes == []:
                bList = self.defineSpikeBursts()
                self.burstTimes = bList
            onsetSpikes = []
            burstSpikes= []
            bList = self.burstTimes
            for b in range(len(bList)):
                bdat = bList[b]
                onsetSpikes.append(bdat[0])
                burstSpikes.extend(bdat[1:].tolist())
            plotTitle = 'Burst-Onset-Triggered Fluorescence'
        else: # but we can also handle just regular spike trains...
            onsetSpikes = self.SpikeTimes
            plotTitle = 'All-Spikes-Triggered Fluorescence'
        self.calculateROIs()
        N = len(onsetSpikes)
        avCaF = [[0]*N for i in xrange(self.nROI)]
        avCaT = [[0]*N for i in xrange(self.nROI)]

        for roi in range(0, self.nROI):
            i = 0
            for onSp in onsetSpikes:
                (x, y) = Utility.clipdata(self.FData[roi], self.imageTimes, onSp-0.1, onSp+0.5)
                avCaF[roi][i] = y
                avCaT[roi][i] = (x.tolist()-onSp)
                i = i + 1
        self.checkMPL()
        (self.MPLFig, self.MPL_plots) = PL.subplots(num = "Image Analysis", nrows = self.nROI+1, ncols=2, 
                    sharex = False, sharey = False)
        self.MPLFig.suptitle('%s:\n %s' % (plotTitle, self.currentFileName), fontsize=11)
        dt = numpy.mean(numpy.diff(self.imageTimes))/2.
        tbase = numpy.arange(-0.1, 0.5, dt)
        axmin = 1e6
        axmax = -1e6
        ave = [[]]*self.nROI
        std = [[]]*self.nROI
        CaAmin = 1e6
        CaAmax = -1e6
        for roi in range(0, self.nROI):
            self.MPL_plots[self.nROI][0].plot(self.imageTimes, self.FData[roi])
            interCaF = numpy.zeros((N, len(tbase)))
            for i in range(0, len(onsetSpikes)):
            #sp = self.MPL_plots.scatter(avCaT, avCaF, s=15, color='tomato')
                self.MPL_plots[roi][0].plot(avCaT[roi][i], avCaF[roi][i]*100., color = 'k', linestyle = '-')
                f_int = scipy.interpolate.interp1d(avCaT[roi][i], avCaF[roi][i]*100., bounds_error = False)
                interCaF[i, :] = f_int(tbase)
                CaAmin = numpy.nanmin([numpy.nanmin(avCaF[roi][i]), CaAmin])
                CaAmax = numpy.nanmax([numpy.nanmax(avCaF[roi][i]), CaAmax])
            #    self.MPL_plots[roi][1].plot(tbase, interCaF[roi,i,:], 'r')
            ave[roi] = scipy.stats.nanmean(interCaF, axis = 0)
            std[roi] = scipy.stats.nanstd(interCaF, axis = 0)
            self.MPL_plots[roi][1].errorbar(tbase, ave[roi]*100., yerr=std[roi]*100., color='r')
            self.MPL_plots[roi][0].set_xlabel('T (sec)')
            self.MPL_plots[roi][0].set_ylabel('dF/F (%)')
            axmin = numpy.nanmin([numpy.nanmin(ave[roi]-std[roi]), axmin])
            axmax = numpy.nanmax([numpy.nanmax(ave[roi]+std[roi]), axmax])
        for roi in range(0, self.nROI):
            self.MPL_plots[roi][1].set_ylim((axmin*100., axmax*100.))
            self.MPL_plots[roi][0].set_ylim((CaAmin*100., CaAmax*100.))
#            self.MPL_plots[roi][1].errorbar(tbase, ave[roi], yerr=std[roi], color='r')
        
        PL.show()
        
    def defineSpikeBursts(self):
        """
        The following criteria are avaiable to select from within the spike train:
        1. minimum time before a spike
        2. minimum rate AFTER the spike (for the next N spikes)
        3. minimum # of spikes (N) for minimum rate determination (define burst length)
        The return arrays are the times of first spikes
        2 Feb 2012 P. B. Manis (working version)
        """
        
        #minTime = 0.100 # in milliseconds
        #maxInterval = 0.040 # maximum time between spikes to be counted in a burst
        #minNspikes = 3 # minimum number of spikes for event to count as a burst
        minTime = self.ctrlPhysFunc.ImagePhys_burstISI.value()/1000.0
        maxInterval = self.ctrlPhysFunc.ImagePhys_withinBurstISI.value()/1000.0
        minNspikes = self.ctrlPhysFunc.ImagePhys_minBurstSpikes.value()
        # first we find the indices of all events that meet the above criteria:
        if len(self.SpikeTimes) < 3:
            return([], [])
        isis = numpy.diff(self.SpikeTimes)
        burstOnsetCandidates = numpy.where(isis > minTime)[0].tolist()
        burstOnsetCandidates = [x + 1 for x in burstOnsetCandidates] 
        # those are candidate events...
        allBurstList = []
        burstOnsetList = []
        for i in burstOnsetCandidates:
            tempWithinBurst = [i] # list of spike times that follow this one
            for j in range(i,len(self.SpikeTimes)-1):
                if isis[j] <= maxInterval: # if interspike interval is long, we terminate
                    tempWithinBurst.append(j+1) # keep track of spikes that are "within" a burst
                else: # if isi is too long, terminate burst
                    break
            if len(tempWithinBurst) >= (minNspikes-1) and i not in burstOnsetList: # note, tempWithinBurst does not include the first spike.
                burstOnsetList.append(i)
                allBurstList.append(tempWithinBurst)
        burstTList = []
        for j in range(len(allBurstList)):
            burstTList.append(self.SpikeTimes[allBurstList[j]])
        return(burstTList)
                
    def ROIDistStrength(self):
        """
        Create a plot of the strength of the cross correlation (peak value) versus the distance
        between the (center) of all pairs of ROIs
        """
        if self.ROIDistanceMap == []:
            self.ROIDistances() # make sure we ahve valid distance information
        print self.IXC_Strength
        if self.IXC_Strength == []:
            self.Analog_Xcorr_Individual(plottype = None)
        self.checkMPL()
        (self.MPLFig, self.MPL_plots) = PL.subplots(num = "Image Analysis", nrows = 1, ncols=1, 
                    sharex = True, sharey = True)
        self.MPLFig.suptitle('Analog XCorr: %s' % self.currentFileName, fontsize=11)
        threshold = self.ctrlImageFunc.IAFuncs_XCorrThreshold.value()
        x0 = numpy.nanmin(numpy.nanmin(self.ROIDistanceMap))
        x1 = numpy.nanmax(numpy.nanmax(self.ROIDistanceMap))
        thrliney = [threshold, threshold]
        thrlinex = [x0, x1]
        sp = self.MPL_plots.scatter(self.ROIDistanceMap, self.IXC_Strength, s=15, color='tomato')
        self.MPL_plots.plot(thrlinex, thrliney)
        self.MPL_plots.set_xlabel('Distance (%s)' % self.imageScaleUnit)
        self.MPL_plots.set_ylabel('Correlation (R)')
        self.MPL_plots.set_ylim((0,1))
        PL.show()

    def printDistStrength(self):
        print '\n\n----------------------------------\nROI Distance Map\nFile: %s '% self.currentFileName
        print 'roi1\troi2\td (um)\t R'
        sh = self.ROIDistanceMap.shape
        for i in range(0, sh[0]):
            for j in range(i+1, sh[1]):
                print '%d\t%d\t%8.0f\t%6.3f' % (i,j,self.ROIDistanceMap[i,j], self.IXC_Strength[i,j])
        print '-------------------------------\n'
        
    def NetworkGraph(self):
        """
        Create a graph showing the network. Each node is an ROI, and the lines connecting
        the nodes have a thickness that corresponds to the strength of the cross correlation.
        """
        if self.ROIDistanceMap == []:
            self.ROIDistances() # make sure we ahve valid distance information
        if self.IXC_Strength == []:
            self.Analog_Xcorr_Individual(plottype = None)
        self.checkMPL()
        (self.MPLFig, self.MPL_plots) = PL.subplots(num = "Network Graph", nrows = 1, ncols=1, 
                    sharex = True, sharey = True)
        self.MPLFig.suptitle('Network Graph: %s' % self.currentFileName, fontsize=11)
        (sx, sy, px) = self.getImageScaling()
        maxStr = numpy.nanmax(self.IXC_Strength)
        minStr = numpy.nanmin(self.IXC_Strength)
        maxline = 4096.0
        minline = 0.25
        threshold = self.ctrlImageFunc.IAFuncs_XCorrThreshold.value()
        nd = len(self.AllRois)
        print px
        for i in range(0, nd):
            wpos1 = [self.AllRois[i].pos().x(), self.AllRois[i].pos().y(),
                            self.AllRois[i].boundingRect().width(), self.AllRois[i].boundingRect().height()]
            x1 = (wpos1[0]+0.5*wpos1[2])*px[0]
            y1 = (wpos1[1]+0.5*wpos1[3])*px[1]                
            for j in range(i+1, nd):
                wpos2 = [self.AllRois[j].pos().x(), self.AllRois[j].pos().y(),
                            self.AllRois[j].boundingRect().width(), self.AllRois[j].boundingRect().height()]
                x2 = (wpos2[0]+0.5*wpos2[2])*px[0]
                y2 = (wpos2[1]+0.5*wpos2[3])*px[1]
                if self.IXC_Strength[i,j] < threshold:
                    self.MPL_plots.plot([x1, x2], [y1, y2], 
                    linestyle = '', color='tomato', marker='o')
                else:
                    lw = maxline*(self.IXC_Strength[i,j]-threshold)/(maxStr-threshold)+minline
                    if lw < 0:
                        lw = 0
                    self.MPL_plots.plot([x1, x2], [y1, y2], linewidth=lw, 
                    linestyle = '-', color='tomato', marker='o')
        self.MPL_plots.set_xlim((0, sx))
        self.MPL_plots.set_ylim((sy, 0))
        self.MPL_plots.set_xlabel('X (%s)' % self.imageScaleUnit)
        self.MPL_plots.set_ylabel('Y (%s)' % self.imageScaleUnit)
        PL.show()
        
#--------------- From PyImageAnalysis3.py: -----------------------------
#---------------- ROI routines on Images  ------------------------------

    def clearAllROI(self):
        """ remove all rois and all references to the rois """
        for roi in self.AllRois:
            roi.hide()
            del roi
        self.AllRois=[]
        self.nROI = 0
        self.FData=[]
        self.BFData =[]
        rois=[]
        self.lastROITouched = []
        self.ROI_Plot.clear()
        #self.clearPlots()

    def deleteLastTouchedROI(self):
        """ remove the currently (last) selected roi and all references to it,
        then select and display a new ROI """
        ourWidget = self.lastROITouched
        if ourWidget in self.AllRois:
            id = ourWidget.ID # get the id of the roi
            self.AllRois.remove(ourWidget)  # remove it from our list
            ourWidget.hide()
            del ourWidget
        else:
            QtGui.QMessageBox.warning(self,
                                      Qt.QString("Delete ROI - Error"),
                                      "Last ROI was not in ROI list?")
        self.nROI = len(rois)
        for roi in self.AllRois:
            roi.ID = rois.index(roi) # renumber the roi list.
        #print '# Rois after delete: %d' % len(rois)
        if id < 0:
            id = rois[0].ID # pick first
        if id > self.nROI:
            id = self.AllRois[-1].ID # pick last
        #self.clearPlots() # need to redraw the plot list
        self.FData=[]
        self.BFData =[]
        for roi in self.AllRois: # navigate the list one more time
            self.plotImageROIs(roi)
            if id == roi.ID:
                self.updateThisROI(roi) # display the next chosen ROI in the box below the image
        # now update the overall ROI plot
        self.plotdata(yMinorTicks = 0, yMajorTicks = 3,
                      yLabel = u'F0<sub>ROI %d</sub>')

    def addOneROI(self, pos=[0 ,0], hw=[5, 5]):
        """ append one roi to the self.AllRois list, put it on the screen (scene), and
        make sure it is actively connected to code. The return value lets us
        handle the rois when we restore them """
        roi = pg.RectROI(pos, hw, scaleSnap=True, translateSnap=True)
#       roi = qtgraph.widgets.EllipseROI(pos, hw, scaleSnap=True, translateSnap=True)
#       roi = qtgraph.widgets.MultiLineROI([[0,0], [5,5], [10,10]], 3, scaleSnap=True, translateSnap=True)
        roi.ID = self.nROI # give each ROI a unique identification number
        rgb = self.RGB[self.nROI]
        self.nROI = self.nROI + 1
        roi.setPen(QtGui.QPen(QtGui.QColor(rgb[0], rgb[1], rgb[2])))
        roi.color = rgb
        self.AllRois.append(roi)
        self.imageView.addItem(roi)
        self.updateThisROI(self.AllRois[-1])
        roi.sigRegionChanged.connect(self.updateThisROI)
        roi.sigHoverEvent.connect(self.updateThisROI)
        return (roi)

    def plotImageROIs(self, ourWidget):
        """ plot the ROIs in the image - as an initial instantiation. Every known
            roi gets plotted with the routine 
        """
        if ourWidget in self.AllRois: # must be in the list of our rois - ignore other widgets
            tr = ourWidget.getArrayRegion(self.imageData, self.imageItem, axes=(1,2))
            tr = tr.mean(axis=2).mean(axis=1) # compute average over the ROI against time
            if self.datatype == 'int16':
                tr = tr / ourWidget.getArrayRegion(self.im_filt, self.imageItem, axes=(0,1)).mean(axis=1).mean(axis=0)
            sh = numpy.shape(self.FData)
            if sh[0] is 0:
                self.FData = atleast_2d(tr) # create a new trace in this place
                #sh = shape(self.FData)
            if sh[0] > ourWidget.ID: # did we move an existing widget?
                self.FData[ourWidget.ID,:] =numpy.array(tr) # then replace the trace
            else: # the widget is not in the list yet...
                self.FData = append(self.FData, atleast_2d(tr), 0)
            self.plotdata(roiUpdate=[ourWidget.ID], showplot=False, datacolor = ourWidget.color)

    def roiChanged(self, roi):
        if isinstance(roi, int):
            roi = self.currentRoi
        if roi is None:
            return
        self.ROI_Plot.clearPlots()
        lineScans = []
        for imgSet in self.imageData:
            data = roi.getArrayRegion(imgSet['procMean'], self.imageItem, axes=(1,2))
            m = data.mean(axis=1).mean(axis=1)
            lineScans.append(data.mean(axis=2))
            spacer = np.empty((lineScans[-1].shape[0], 1), dtype = lineScans[-1].dtype)
            spacer[:] = lineScans[-1].min()
            lineScans.append(spacer)
            data = roi.getArrayRegion(imgSet['procStd'], self.imageItem, axes=(1,2))
            s = data.mean(axis=1).mean(axis=1)
            self.ROI_Plot.plot(m, pen=pg.hsvColor(c*0.2, 1.0, 1.0))
            self.ROI_Plot.plot(m-s, pen=pg.hsvColor(c*0.2, 1.0, 0.4))
            self.ROI_Plot.plot(m+s, pen=pg.hsvColor(c*0.2, 1.0, 0.4))            

        lineScan = np.hstack(lineScans)
        self.getElement('Line Scan').setImage(lineScan)
        self.currentRoi = roi
        
    def updateThisROI(self, roi, livePlot=True):
        """ called when we need to update the ROI result plot for a particular ROI widget 
        """
        if roi in self.AllRois:
            tr = roi.getArrayRegion(self.rawData, self.imageView.imageItem, axes=(1,2))
            tr = tr.mean(axis=2).mean(axis=1) # compute average over the ROI against time
            trm = tr.mean(axis=0)
            tr = tr/(self.background*trm/self.backgroundmean)
            # bk = self.background/self.backgroundmean
            tr[0] = tr[1]
            if livePlot is True:
                self.ROI_Plot.plot(self.imageTimes, tr, pen=pg.mkPen('r'), clear=True)
                # self.ROI_Plot.plot(self.imageTimes, bk, pen=pg.mkPen('b'))
            if self.lastROITouched == []:
                self.lastROITouched = roi
                roi.pen().setWidth(0.12) # just bump up the width
            if roi != self.lastROITouched:
                self.lastROITouched.pen.setWidth(0.12)
                roi.pen().setWidthF(0.25)
                self.lastROITouched = roi # save the most recent one
            return(tr)

    def calculateROIs(self):
        i = 0
        self.FData = []
        currentROI = self.lastROITouched
        for ourWidget in self.AllRois:
            tr = self.updateThisROI(ourWidget, livePlot=False)
            sh = numpy.shape(self.FData)
            if sh[0] == 0:
                self.FData = numpy.atleast_2d(tr) # create a new trace in this place
            if sh[0] > ourWidget.ID: # did we move an existing widget?
                self.FData[ourWidget.ID,:] =numpy.array(tr) # then replace the trace
            else: # the widget is not in the list yet...
                self.FData = numpy.append(self.FData, numpy.atleast_2d(tr), 0)
        self.updateThisROI(currentROI) # just update the latest plot with the new format.
      

    def optimizeAll(self):
        for roi in self.AllRois:
            self.optimizeThisROI(roi)

    def optimizeOne(self):
        if self.lastROITouched in self.AllRois:
            self.optimizeThisROI(self.lastROITouched)

    def optimizeThisROI(self, ourWidget, livePlot=True):
        """ This routine determines the best (largest) signal in a region in and
            around the current ROI, by moving (dithering) the ROI. The ROI is left
            positioned at the "best" location
        """
#        ditherX = self.ui.ditherX.value()
#        ditherY = self.ui.ditherY.value()
#        ditherMode = self.ui.ditherMode.currentIndex()
        ditherX = 2
        ditherY = 2
        ditherMode = 0
        if ourWidget in self.AllRois:
            (tr_test, trDither) = self.__measDither(ditherMode, ourWidget)
            wpos = ourWidget.state['pos']
            tr_best = 0.0
            tr_X = wpos[0]
            tr_Y = wpos[1]
            for x in range(-ditherX, ditherX):
                for y in range(-ditherY, ditherY):
                    px = wpos[0]+x
                    py = wpos[1]+y
                    ourWidget.setPos([px, py])
                    (tr_test, trDither) = self.__measDither(ditherMode, ourWidget)
                    if tr_test > tr_best:
                        tr_X = px
                        tr_Y = py
                        tr_best = tr_test
                        tr = trDither # save peak signal
            ourWidget.setPos([tr_X, tr_Y])
            sh = numpy.shape(tr)
 #           if livePlot:
 #               MPlots.updatePlot(self.ui.liveROIPlot, range(0, sh[0]), tr, 'liveROI',
 #                                 color=self.RGB[ourWidget.ID-1])
            return(tr)

    def __measDither(self, ditherMode, ourWidget):
        """Compute the value that we are optimizing for the dithering."""
        trDither = ourWidget.getArrayRegion(self.normData[0], self.imageItem, axes=(1,2))
        trDither = trDither.mean(axis=2).mean(axis=1) # compute average over the ROI against time
        if ditherMode is 0: # peak to peak
            tr_test = numpy.amax(trDither) - numpy.amin(trDither)
        if ditherMode is 1: # baseline to peak
            tr_test = numpy.amax(trDither)
        if ditherMode is 2: # standard deviation
            tr_test = numpy.std(trDither)
        return(tr_test, trDither)

    def ROIDistances(self):
        """
        measure the distances between all possible pairs of ROIs, store result in matrix...
        The distances are scaled into microns or pixels.
        """
        print 'Calculating ROI to ROI distances'
        nd = len(self.AllRois)
        self.ROIDistanceMap = numpy.empty((nd, nd)) # could go sparse, but this is simple...
        self.ROIDistanceMap.fill(numpy.nan)
        (sx, sy, px) = self.getImageScaling()
        for i in range(0, nd):
            wpos1 = [self.AllRois[i].pos().x(), self.AllRois[i].pos().y(),
                            self.AllRois[i].boundingRect().width(), self.AllRois[i].boundingRect().height()]
            x1 = (wpos1[0]+0.5*wpos1[2])*px[0]
            y1 = (wpos1[1]+0.5*wpos1[3])*px[1]
            for j in range(i+1, nd):
                wpos2 = [self.AllRois[j].pos().x(), self.AllRois[j].pos().y(),
                            self.AllRois[j].boundingRect().width(), self.AllRois[j].boundingRect().height()]
                x2 = (wpos2[0]+0.5*wpos2[2])*px[0]
                y2 = (wpos2[1]+0.5*wpos2[3])*px[1]                
                self.ROIDistanceMap[i,j] = numpy.sqrt((x1-x2)**2+(y1-y2)**2)
        
        
#    def getROI(self, roi):
#        for ourwidget in self.AllRois:
#            if ourwidget.ID == roi:
#                return ourwidget
#        return(None)


    # """
    # The original code for the next subroutine is pulled form the xanesP.py source
    # (for x-ray spectroscopy data)
    # The original was by Tamás Haraszti tamas.haraszti@uni-heidelberg.de
    # http://www.biomedcentral.com/1752-153X/4/11
    # PMID: 20525317 [PubMed] PMCID: PMC2891742 
    # 
    # """
    # 
    # def AlignStack(self, imgstack, imgi, thresh = 0.0,
    #         invert=True, cut=True, ROI=None, verbose = False):
    #     """ Align a stack to one of its images using a convolution filter.
    #         First the images are convolved to a reference image, and the
    #         maximum of the convolution is taken. Standard precision is at 
    #         single pixel level.
    #         Then a shift is applied using the ImageP.shift routine.
    # 
    #         In this algorithm no subpixel shifting is used in order to
    #         preserve the original statistics of the data points.
    #     
    #         Parameters:
    #         imgstack:   a list containing images
    #         imgi:       index of the position image inside imgstack
    #         thresh:     threshold to use on the reference image; if it is
    #                     zero, then use the ImageP.graythresh algorithm
    #         invert:     if True, invert the reference image
    #         cut:        if True, cut to the common area after shift
    #         ROI:        i list or tuple of ndices i0,i1,j0,j1 so that the 
    #                     subimage: img[i0:i1,j0:j1] shall be used for the
    #                     alignment.
    #         verbose:    plot actual convolution image
    # 
    #         Return:
    #         an list of the aligned images
    #     """
    # 
    #     N = len(imgstack)
    #     (newWin1, view1, imgwin1) = self.newpgImageWindow(title = 'original')
    #     for img in imgstack:
    #         imgwin1.setImage(img, autoLevels = True)
    #         imgwin1.updateImage()
    #         
    #     if imgi < 0 or imgi >= N:
    #         print "Invalid index: %d not in 0 - %d" %(imgi, N)
    #         return None
    #     #end if
    # 
    #     a = imgstack[imgi].copy()
    # 
    #     if ROI is True:
    #         if len(ROI) != 4 :
    #             print "ROI should be 4 indices long"
    #         else:
    #             try:
    #                 atmp = a[ROI[0]:ROI[1],ROI[2]:ROI[3]]
    #             except:
    #                 print "Invalid ROI!"
    #             else:
    #                 a = atmp
    #             #end try
    #         #end if
    #     #end if
    # 
    #     if invert is True:
    #         a = a.max() - a
    #     else :
    #         a = a - a.min()
    #     #end if
    #     sh = a.shape
    #     if thresh == 0.0 :
    #         #the a*100 is a residue from problems with images
    #         #where min and max were between 0-1 and graythresh 
    #         #returned strange results or error:
    #         thresh = ImageP.graythresh(a*100.0) * a.max()
    # 
    #         if verbose:
    #             print "threshold is set to: %.3f" %thresh
    #         #end if
    #     #end if
    # 
    #     #initialize result stack:
    #     outstack = []
    #     indx = numpy.zeros( imgstack[0].shape, dtype='bool') + True
    # 
    #     # if verbose :
    #     # #initiate two figure frames
    #     #     emptyarr = numpy.random.normal(size=sh)
    #     #     (newWin1, view1, imgwin1) = self.newpgImageWindow(title = 'original')
    #     #     imgwin1.setImage(a)
    #     #     (newWin2, view2, imgwin2) = self.newpgImageWindow(title= 'img2')
    #     #     imgwin2.setImage(emptyarr)
    #     #     imgwin1.updateImage()
    #     #     imgwin2.updateImage()
    #     #             
    #     for img in imgstack:
    #         if invert is True:
    #             #invert the image as well (a is already inverted):
    #             c = ImageP.ConvFilter(a > thresh, img.max() - img)
    #         else :
    #             c = ImageP.ConvFilter(a > thresh, img)
    #         #end if
    # 
    #         # overkill: 
    #         #res = ImageP.PeakFind(c)
    # 
    #         # we could also use ImageP.PeakFind on convolve(a,a) as reference.
    #         # indexing goes 0 - N-1, then N/2-1 is the center:
    #         #x = res['X'][0] - (c.shape[0]/2 - 1)
    #         #y = res['Y'][0] - (c.shape[1]/2 - 1)
    # 
    #         #we stick to the first maximum. If there are more than one,
    #         #anyway we have a problem. That shold be handled by adjusting the
    #         #image parameters prior the alignment.
    #         x,y = (c == c.max()).nonzero()
    #         x = x[0] - (c.shape[0]/2 -1)
    #         y = y[0] - (c.shape[1]/2 -1)
    #         print 'max of c: ', c.max().max()
    #         #now do the alignment:
    #         #shift is creating a new array
    #         img2 = ImageP.shift(img, x, y)
    #        # print img2[0:10,0:10]
    #     #    print img[0:10,0:10]
    #         print 'shift: x %d y %d' % (x, y)
    #      #   print 'img2: ', img2.shape
    #      #   print 'img:  ', img.shape
    #         outstack.append(img2)
    #         indx = indx * (img2 > 0)
    # 
    #         # imgwin1.setImage(img, autoLevels = True)
    #         # imgwin1.updateImage()
    #         # imgwin2.setImage(img2, autoLevels = True)
    #         # imgwin2.updateImage()
    # 
    #     if cut is True:
    #         ix, iy = indx.nonzero()
    #         i0 = ix.min()
    #         #+1 for the indexing limit...
    #         i1 = ix.max()+1
    #         j0 = iy.min()
    #         j1 = iy.max()+1
    #     
    #         print "Common boundaries:",i0,i1,j0,j1
    # 
    #         #cut the list elements:
    #         for i in xrange(N):
    #             outstack[i] = outstack[i][i0:i1,j0:j1]
    # 
    #     return numpy.atleast_2d(outstack)
    # #end of AlignStack

    def RegisterStack(self, imgstack, imgi, thresh = 0.0,
            invert=True, cut=True, ROI=None, verbose = False):
        """ Align a stack to one of its images using recursiveRegisterImages
            from util/functions.py
            
            Parameters:
            imgstack:   a list containing images
            imgi:       index of the standard position image inside imgstack
            thresh:     not used :threshold to use on the reference image; if it is
                        zero, then use the ImageP.graythresh algorithm
            invert:     note used: if True, invert the reference image
            cut:        if True, cut to the common area after shift
            ROI:        list or tuple of ndices i0,i1,j0,j1 so that the 
                        subimage: img[i0:i1,j0:j1] shall be used for the
                        alignment.
            verbose:    plot actual convolution image
    
            Return:
            a list of the aligned images
        """
    
        N = len(imgstack)
        (newWin1, view1, imgwin1) = self.newpgImageWindow(title = 'original')
        for img in imgstack:
            imgwin1.setImage(img, autoLevels = True)
            imgwin1.updateImage()
            
        if imgi < 0 or imgi >= N:
            print "Invalid index: %d not in 0 - %d" %(imgi, N)
            return None
        #end if
    
        a = imgstack[imgi].copy()
    
        if ROI is True:
            if len(ROI) != 4 :
                print "ROI should be 4 indices long"
            else:
                try:
                    atmp = a[ROI[0]:ROI[1],ROI[2]:ROI[3]]
                except:
                    print "Invalid ROI!"
                else:
                    a = atmp
                #end try
            #end if
        #end if
    
        if invert is True:
            a = a.max() - a
        else :
            a = a - a.min()
        #end if
        sh = a.shape
        if thresh == 0.0 :
            #the a*100 is a residue from problems with images
            #where min and max were between 0-1 and graythresh 
            #returned strange results or error:
            thresh = ImageP.graythresh(a*100.0) * a.max()
    
            if verbose:
                print "threshold is set to: %.3f" %thresh
            #end if
        #end if
    
        #initialize result stack:
        outstack = []
        indx = numpy.zeros( imgstack[0].shape, dtype='bool') + True
    
        # if verbose :
        # #initiate two figure frames
        #     emptyarr = numpy.random.normal(size=sh)
        #     (newWin1, view1, imgwin1) = self.newpgImageWindow(title = 'original')
        #     imgwin1.setImage(a)
        #     (newWin2, view2, imgwin2) = self.newpgImageWindow(title= 'img2')
        #     imgwin2.setImage(emptyarr)
        #     imgwin1.updateImage()
        #     imgwin2.updateImage()
        #             
        for img, imgN in imgstack:
            x = 0
            y = 0
            if imgN != imgi:
                if invert is True:
                    img = img.max() - img
                c = FN.recursiveRegisterImages(img, imgstack[imgi], maxDist=10)
                print 'C: ' , c
            continue
            img2 = ImageP.shift(img, x, y)
           # print img2[0:10,0:10]
        #    print img[0:10,0:10]
            print 'shift: x %d y %d' % (x, y)
         #   print 'img2: ', img2.shape
         #   print 'img:  ', img.shape
            outstack.append(img2)
            indx = indx * (img2 > 0)
    
            # imgwin1.setImage(img, autoLevels = True)
            # imgwin1.updateImage()
            # imgwin2.setImage(img2, autoLevels = True)
            # imgwin2.updateImage()
    
        if cut is True:
            ix, iy = indx.nonzero()
            i0 = ix.min()
            #+1 for the indexing limit...
            i1 = ix.max()+1
            j0 = iy.min()
            j1 = iy.max()+1
        
            print "Common boundaries:",i0,i1,j0,j1
    
            #cut the list elements:
            for i in xrange(N):
                outstack[i] = outstack[i][i0:i1,j0:j1]
    
        return numpy.atleast_2d(outstack)
    #end of registerStack

    def newpgImageWindow(self, title = '', border = 'w'):
        newWin = pyqtgrwindow(title = title)
        view = pg.GraphicsView()
        newWin.setCentralWidget(view)
        newWin.show()
        img = pg.ImageItem(border=border)
        view.scene().addItem(img)
        view.setRange(QtCore.QRectF(0, 0, 500, 500))
        return(newWin, view, img)
                
############################

    def saveROI(self, fileName = None):
        """Save the ROI information (locations) to a disk file."""
        self.calculateROIs()
        if self.FData == []:
            print 'self.FData is empty!'
            return
        sh = numpy.shape(self.FData)
        data = numpy.empty([sh[0]+1, sh[1]])
        data[0] = numpy.arange(0,sh[1])
        roiData = []
        for i in range(0, sh[0]):
            data[i+1] = self.FData[i]
            roiData.append([self.AllRois[i].pos().x(), self.AllRois[i].pos().y(),
                            self.AllRois[i].boundingRect().height(), self.AllRois[i].boundingRect().width()])
        data = data.T
        if fileName is None or fileName is False:
            fileName= QtGui.QFileDialog.getSaveFileName(None, "Save ROI as csv file", "", 
                self.tr("CSV Files (*.csv)"))
            if not fileName:
                return
        fname = fileName
        if "." not in fileName:
            fileName = fileName + '.csv'
        file = open(fileName, 'w')
        stringVals=''
        for col in range(0, data.shape[1]): # write a header for our formatting.
            if col is 0:
                file.write('time,')
            else:
                stringVals = ['R%03d' % x for x in range(0, col)]
        file.write(",".join(stringVals) + "\n")
        for row in range(0, data.shape[0]):
            stringVals = ["%f" % x for x in data[row]]
            file.write(",".join(stringVals) + "\n")
        file.close()
        fd = open(fname + '.roi', 'w')
        for rd in roiData:
            fd.write(' '.join(map(str, rd)) + '\n')
        fd.close()
    
    def restoreROI(self, fileName = None):
        """Retrieve the ROI locations from a file, plot them on the image, and compute the traces."""
        self.clearAllROI() # always start with a clean slate.
        if fileName is False or fileName is None:
            fileName = QtGui.QFileDialog.getOpenFileName(None, u'Retrieve ROI data', u'', u'ROIs (*.roi)')
        self.RData = []
        self.nROI = 0
        if fileName:
            fd = open(fileName, 'r')
            for line in fd:
                roixy = numpy.fromstring(line, sep=' ')
                roi = self.addOneROI(pos=[roixy[0], roixy[1]], hw=[roixy[2], roixy[3]])
                tr = self.updateThisROI(roi, livePlot=False)
                lcount = len (tr)
                self.RData.append(tr)
            #self.times = arange(0, len(tr))
            self.nROI = len(self.RData)
            self.FData =numpy.array(self.RData)# .reshape(lcount, self.nROI).T
            self.BFData = [] # 'baseline corrected'
            #self.plotdata(yMinorTicks = 0, yMajorTicks = 3,
            #              yLabel = u'F0<sub>ROI %d</sub>')
        self.makeROIDataFigure(clear=True)


    def makeROIDataFigure(self, clear = False, gcolor = 'k'):
        self.checkMPL()
        (self.MPLFig, self.MPL_plots) = PL.subplots(num="ROI Data", nrows = self.nROI, ncols=1, 
        sharex = True)
        self.MPLFig.suptitle('Analog XCorr: %s' % self.currentFileName, fontsize=10)
        for i, plr in enumerate(self.MPL_plots):
            plr.plot(self.imageTimes, self.FData[i,:], color = gcolor)
            plr.hold(True)
        PL.show()

#----------------------Stack Ops (math on images) ---------------------------------

    def stackOp_absmax(self): # absolute maximum
        """Make an image that is the maximum of each pixel across the image stack."""
        self.clearAllROI()
        sh = numpy.shape(self.imageData);
        if len(sh) == 4:
            self.image = numpy.amax(self.imageData[:,1,:,:], axis = 0).astype(float32)
        elif len(sh) == 3:
            self.image = numpy.amax(self.imageData[:,:,:], axis = 0).astype(float32)
        self.paintImage(image=self.image, focus=False)

    def stackOp_normmax(self): # normalized maximum
        """Make an image that is the maximum of each pixel, normalized within each image, across the image stack."""
        self.clearAllROI()
        levindex = self.ui.stackOp_levels.currentIndex()
        levels = [8., 16., 256., 4096., 65536.]
        id_shape = numpy.shape(self.imageData)
        id = numpy.zeros(id_shape)
        self.imageLevels = levels[-1]
        if len(id_shape) == 4:
            plane = 1
            amaxd = numpy.amax(self.imageData[:,plane,:,:], axis=0).astype(float32)
            amind = numpy.amin(self.imageData[:,plane,:,:], axis=0).astype(float32)
            id = numpy.floor((levels[levindex]/amaxd)*(self.imageData[:,plane,:,:].astype(float32)-amind))
        elif len(id_shape) == 3:
            amaxd = numpy.amax(self.imageData[:,:,:], axis=0).astype(float32)
            amind = numpy.amin(self.imageData[:,:,:], axis=0).astype(float32)
            id = numpy.floor((levels[levindex]/amaxd)*(self.imageData[:,:,:].astype(float32)-amind))
        self.image = numpy.amax(id, axis = 0)
        id=[]
        self.paintImage(image=self.image, focus=False)

    def stackOp_std(self):
        """Make an image that is the standard deviation of each pixel across the image stack."""
        self.clearAllROI()
        sh = numpy.shape(self.imageData);
        if len(sh) == 4:
            self.image = numpy.std(self.imageData[:,1,:,:], axis = 0)
        elif len(sh) == 3:
            self.image = numpy.std(self.imageData[:,:,:], axis = 0)
        self.paintImage(image=self.image, focus=False)

    def stackOp_mean(self):
        """Make an image that is the mean of each pixel across the image stack."""
        sh = numpy.shape(self.imageData);
        self.clearAllROI()
        if len(sh) == 4:
            self.image = numpy.mean(self.imageData[:,1,:,:], axis = 0)
        elif len(sh) == 3:
            self.image = numpy.mean(self.imageData[:,:,:], axis = 0)
        self.paintImage(image=self.image, focus=False)

    def stackOp_restore(self):
        """Redraw the original image stack."""
        self.paintImage(updateTools = True, focus=True) # return to the original imagedata

#----------------------Image Processing methods ----------------
# Includes bleach correction, filtering (median and gaussian), and deltaF/F calculation

    def unbleachImage(self):
        if self.dataState['bleachCorrection'] is True:
            return # already did unbleaching, can't do it twice!
        if self.dataState['Normalized'] is True:
            return # shouldn't do bleaching correction on normalized data
#        self.clearAllROI()
        imshape = numpy.shape(self.imageData)
        tc_bleach = numpy.zeros(imshape[0])
        Fits = Fitting.Fitting()
        for k in range(0, imshape[0]):
            tc_bleach[k] = numpy.median(self.imageData[k,:,:])

        # replace tc_bleach with a smoothed version - 4th order polynomial
        fitx = numpy.arange(0, numpy.shape(tc_bleach)[0])
        #(fpar, xf, yf, names) = Fits.FitRegion([0], 0, fitx, tc_bleach, 0.0, numpy.amax(fitx),
        #                                    fitFunc = 'poly2', fitPars = [0.1, 0.2, 0.3, 0.4, 0.0],
        #                                    plotInstance = None)
        (a0, a1, tau) = Fits.expfit(fitx, tc_bleach)
        print("fit result = a0: %f   a1: %f   tau: %f\n", (a0, a1, tau))

        tc_bleach = (a0 + a1*numpy.exp(-fitx/tau))/a0 # convert start value to 1.0, take it from there
        BleachPct = 100.0*(tc_bleach[-1]-tc_bleach[0])/tc_bleach[0]
        for k in range(0, len(self.imageData)):
            self.imageData[k,:,:] = self.imageData[k,:,:] / tc_bleach[k]
        self.ctrl.ImagePhys_BleachInfo.setText('B=%6.2f%%' % BleachPct)
        self.paintImage(focus = False)
        print 'mean: bl: ', numpy.mean(self.imageData[0])

    def normalizeImage(self):
        """
        Each image is normalized to the mean of the whole series
        """
        if self.dataState['Normalized'] is True: # should not normalize twice!
            return
#        self.clearAllROI()
        meanimage = numpy.mean(self.imageData, axis=0)
        #meanimage = scipy.ndimage.filters.gaussian_filter(meanimage, (3,3))
        sh = meanimage.shape
        print 'mean image shape: ', sh
        for i in range(len(self.imageData)):
            self.imageData[i,:,:] = self.imageData[i,:,:] - meanimage
            self.imageData[i,:,:] = self.imageData[i,:,:] / numpy.mean(numpy.mean(self.imageData[i,:,:], axis=0), axis=0)
#        self.imageData = numpy.array(self.imageData) / self.im_filt
        self.dataState['Normalized'] = True
        self.dataState['NType'] = 'norm'
        self.paintImage(focus = False)
        self.ctrl.ImagePhys_NormInfo.setText('Norm')
        print 'norm: ', numpy.mean(self.imageData[1])

    def MediandFFImage(self, data=None):
        if self.dataState['Normalized'] is True: # should not normalize twice!
            return
#        self.clearAllROI()
        sh = self.imageData.shape
        imm = numpy.median(numpy.median(self.imageData, axis=2), axis=1)
        samplefreq = 1.0/numpy.mean(numpy.diff(self.imageTimes))
        if samplefreq < 100.0:
            lpf = samplefreq/3.0
        else:
            lpf = 33.0
        imm = Utility.SignalFilter_LPFButter(imm, lpf, samplefreq, NPole = 8)
        for i in range(len(self.imageData)):
            self.imageData[i,:,:] = self.imageData[i,:,:] - imm[i]
        self.trialPlot.plot(y=imm, x=self.imageTimes, clear=True)
        self.dataState['Normalized'] = True
        self.dataState['NType'] = 'median'
        self.ctrl.ImagePhys_NormInfo.setText('Median')
        self.paintImage()

    def StandarddFFImage(self):
        if self.dataState['Normalized'] is True: # should not normalize twice!
            return
#        self.clearAllROI()
    # bwin = self.ui.baselineFrames.value()
    # baseline = self.imageData[0:bwin]
        print 'std dff'
        self.normData = []
        im_filt = numpy.mean(self.imageData[0:1], axis=0) # save the reference
        im_filt = scipy.ndimage.filters.gaussian_filter(im_filt, (3,3))
        self.imageData = (self.imageData - im_filt) / im_filt # do NOT replot!
        self.imageData = scipy.ndimage.filters.gaussian_filter(self.imageData, (0,3,3))
        self.dataState['Normalized'] = True
        self.dataState['NType'] = 'dF/F'
        self.ctrl.ImagePhys_NormInfo.setText('(F-Fo)/Fo')
        self.paintImage()
        print 'dff: ', numpy.mean(self.imageData[1])

    def smoothImage(self):
        self.imageData = scipy.ndimage.filters.gaussian_filter(self.imageData, (3,3,3))
        self.paintImage()
        
    def paintImage(self, image = None, updateTools = True, focus=True):
        if image == None:
            pImage = self.imageData
        else:
            pImage = image
        pImage = numpy.squeeze(pImage)
        #self.initImage(len(pImage))
        self.imageView.setImage(pImage)

    def ccf(self, x, y, axis=None):
        """Computes the cross-correlation function of two series `x` and `y`.
        Note that the computations are performed on anomalies (deviations from
        average).
        Returns the values of the cross-correlation at different lags.
        Lags are given as [0,1,2,...,n,n-1,n-2,...,-2,-1] (not any more)
        :Parameters:
            `x` : 1D MaskedArray
                Time series.
            `y` : 1D MaskedArray
                Time series.
            `axis` : integer *[None]*
                Axis along which to compute (0 for rows, 1 for cols).
                If `None`, the array is flattened first.
        """
        assert x.ndim == y.ndim, "Inconsistent shape !"
    #    assert(x.shape == y.shape, "Inconsistent shape !")
        if axis is None:
            if x.ndim > 1:
                x = x.ravel()
                y = y.ravel()
            npad = x.size + y.size
            xanom = (x - x.mean(axis=None))
            yanom = (y - y.mean(axis=None))
            Fx = numpy.fft.fft(xanom, npad, )
            Fy = numpy.fft.fft(yanom, npad, )
            iFxy = numpy.fft.ifft(Fx.conj()*Fy).real
            varxy = numpy.sqrt(numpy.inner(xanom,xanom) * numpy.inner(yanom,yanom))
        else:
            npad = x.shape[axis] + y.shape[axis]
            if axis == 1:
                if x.shape[0] != y.shape[0]:
                    raise ValueError, "Arrays should have the same length!"
                xanom = (x - x.mean(axis=1)[:,None])
                yanom = (y - y.mean(axis=1)[:,None])
                varxy = numpy.sqrt((xanom*xanom).sum(1) * (yanom*yanom).sum(1))[:,None]
            else:
                if x.shape[1] != y.shape[1]:
                    raise ValueError, "Arrays should have the same width!"
                xanom = (x - x.mean(axis=0))
                yanom = (y - y.mean(axis=0))
                varxy = numpy.sqrt((xanom*xanom).sum(0) * (yanom*yanom).sum(0))
            Fx = numpy.fft.fft(xanom, npad, axis=axis)
            Fy = numpy.fft.fft(yanom, npad, axis=axis)
            iFxy = numpy.fft.ifft(Fx.conj()*Fy,n=npad,axis=axis).real
        # We juste turn the lags into correct positions:
        iFxy = numpy.concatenate((iFxy[len(iFxy)/2:len(iFxy)],iFxy[0:len(iFxy)/2]))
        return iFxy/varxy

#
#------------- cross correlation calculations -----------------
#
    def Analog_Xcorr(self, FData = None, dt = None):
        """Average cross correlation of all traces"""
        self.calculateROIs()
        if not FData:
            FData = self.FData
        if dt is None:
            if self.imageTimes is []:
                dt = 1
            else:
                dt = numpy.mean(numpy.diff(self.imageTimes))
        self.use_MPL = self.ctrlImageFunc.IAFuncs_MatplotlibCheckBox.checkState()
        if not self.use_MPL:
            self.avgXcorrWindow = pyqtgrwindow(title = 'Analog_Xcorr_Average')
            self.mpwavg = pg.GraphicsLayoutWidget()
            self.avgXcorrWindow.setCentralWidget(self.mpwavg)
            self.avgXcorrWindow.show()
        else:
            self.checkMPL()
            (self.MPLFig, self.MPL_plots) = PL.subplots(num = "Average XCorr", nrows = 1, ncols=1, 
                        sharex = True, sharey = True)
            self.MPLFig.suptitle('Average XCorr: %s' % self.currentFileName, fontsize=11)
            
        nxc = 0
        self.xcorr = []
        for roi1 in range(0, len(FData)-1):
            for roi2 in range(roi1+1, len(FData)):
                (a1, b1) = numpy.polyfit(self.imageTimes, FData[roi1,:], 1)
                (a2, b2) = numpy.polyfit(self.imageTimes, FData[roi2,:], 1)
                y1 = numpy.polyval([a1, b1], self.imageTimes)
                y2 = numpy.polyval([a2, b2], self.imageTimes)
                sc = self.ccf(FData[roi1,:]-y1, FData[roi2,:]-y2)
                if nxc == 0:
                    self.xcorr = sc
                else:
                    self.xcorr = self.xcorr + sc
                nxc = nxc + 1
        self.xcorr = self.xcorr/nxc
        s = numpy.shape(self.xcorr)
        self.lags = dt*(numpy.arange(0, s[0])-s[0]/2.0)
        if not self.use_MPL:
            p = self.mpwavg.addPlot(0,0)
            p.plot(self.lags,self.xcorr)
            p.setXRange(numpy.min(self.lags), numpy.max(self.lags))
        else:
            self.MPL_plots.plot(self.lags, self.xcorr)
            self.MPL_plots.plot(self.lags,numpy.zeros(self.lags.shape), color = '0.5')
            self.MPL_plots.plot([0,0], [-0.5, 1.0], color = '0.5')
            self.MPL_plots.set_title('Average XCorr', fontsize=10)
            self.MPL_plots.set_xlabel('T (sec)', fontsize=10)
            self.MPL_plots.set_ylabel('Corr (R)', fontsize=10)
            PH.cleanAxes(self.MPL_plots)
            PL.show()
            

    def Analog_Xcorr_unbiased(self, FData = None, dt = None):
        self.oldROIs = self.AllRois
        self.clearAllROI()
        img_sh = self.rawData.shape
        img_x = img_sh[1]
        img_y = img_sh[2]
        nx = 10
        ny = 10
        dx = int(img_x/nx)
        dy = int(img_y/ny)
        print dx, dy
        for i in range(0, nx):
            for j in range(0, ny):
                self.addOneROI(pos=[i*dx, j*dy], hw=[dx, dy])
        self.Analog_Xcorr_Individual(plottype = 'image')
        
    def Analog_Xcorr_Individual(self, FData = None, dt = None, plottype = 'traces'):
        """ compute and display the individual cross correlations between pairs of traces
            in the data set"""
        print 'Calculating cross-correlations between all ROIs'
        self.use_MPL = self.ctrlImageFunc.IAFuncs_MatplotlibCheckBox.checkState()
        self.calculateROIs()
        if self.ROIDistanceMap == []:
            self.ROIDistances()
        if not FData:
            FData = self.FData
            nROI = self.nROI
        else:
            nROI = len(FData)
        if dt is None:
            if self.imageTimes is []:
                dt = 1
            else:
                dt = numpy.mean(numpy.diff(self.imageTimes))
        
        nxc = 0
        rows = nROI-1
        cols = rows
        self.IXC_corr =  [[]]*(sum(range(1,nROI)))
        self.IXC_plots = [[]]*(sum(range(1,nROI)))
        self.IXC_Strength = numpy.empty((nROI, nROI))
        self.IXC_Strength.fill(numpy.nan)
        xtrace  = 0
        yMinorTicks = 0
        bLegend = self.ctrlImageFunc.IAFuncs_checkbox_TraceLabels.isChecked()
        gridFlag = True

        if self.nROI > 8:
            gridFlag = False
        if not self.use_MPL:
            self.newWindow = pyqtgrwindow(title = 'Analog_Xcorr_Individual')
            self.pgwin = pg.GraphicsLayoutWidget()
            self.newWindow.setCentralWidget(self.pgwin)
            self.newWindow.show()
        else:
            self.checkMPL()
            if plottype == 'traces':
                (self.MPLFig, self.IXC_plots) = PL.subplots(num="Individual ROI Cross Correlations", 
                    nrows = self.nROI-1, ncols=self.nROI-1, 
                    sharex = True, sharey = True)
                self.MPLFig.suptitle('XCorr: %s' % self.currentFileName, fontsize=11)
            else:
                self.MPLFig = PL.subplot(111)
        for xtrace1 in range(0, nROI-1):
            a1 = numpy.polyfit(self.imageTimes, FData[xtrace1,:], 2)
            y1 = numpy.polyval(a1, self.imageTimes)
            for xtrace2 in range(xtrace1+1, nROI):
                if bLegend:
                    legend = legend=('%d vs %d' % (xtrace1, xtrace2))
                else:
                    legend = None
                a2 = numpy.polyfit(self.imageTimes, FData[xtrace2,:], 2)
                y2 = numpy.polyval(a2, self.imageTimes)
                sc = self.ccf(FData[xtrace1,:]-y1, FData[xtrace2,:]-y2)
                #sc = self.ccf(FData[xtrace1,:], FData[xtrace2,:])
                self.IXC_corr[xtrace] = sc
                self.IXC_Strength[xtrace1, xtrace2] = sc.max()
                s = numpy.shape(sc)
                self.lags = dt*(numpy.arange(0, s[0])-s[0]/2.0)
                #MPlots.PlotLine(self.IXC_plots[xtrace], self.lags, 0*self.IXC_corr[xtrace],
                #                color = 'lightgray', linestyle='Dash', dataID=('ref_%d_%d' % (xtrace1, xtrace2)))
                #MPlots.PlotLine(self.IXC_plots[xtrace], self.lags, self.IXC_corr[xtrace],
                #                color = 'k', dataID = ('Xcorr_%d_%d' % (xtrace1, xtrace2)))
                if plottype == 'traces':
                    if not self.use_MPL:
                        self.IXC_plots[xtrace] = self.pgwin.addPlot(xtrace1, xtrace2)
                        self.IXC_plots[xtrace].plot(self.lags, self.IXC_corr[xtrace])
                        if xtrace == 0:
                            self.IXC_plots[0].registerPlot(name='xcorr_%03d' % xtrace)
                        if xtrace > 0:
                            self.IXC_plots[xtrace].vb.setXLink('xcorr_000') # not sure - this seems to be at the wrong level in the window manager
                    else: # pylab
                        plx = self.IXC_plots[xtrace1, xtrace2-1]
                        plx.plot(self.lags,self.IXC_corr[xtrace])
                        plx.hold = True
                        plx.plot(self.lags,numpy.zeros(self.lags.shape), color = '0.5')
                        plx.plot([0,0], [-0.5, 1.0], color = '0.5')
                        plx.set_title('ROIs: %d, %d' % (xtrace1, xtrace2), fontsize=10)
                        plx.set_xlabel('T (sec)', fontsize=10)
                        plx.set_ylabel('Corr (R)', fontsize=10)
                        PH.cleanAxes(plx) 
                        
                xtrace = xtrace + 1
        # now rescale all the plot Y axes by getting the min/max "viewRange" across all, then setting them all the same

        if not self.use_MPL and plottype == 'traces':
            ymin = 0
            ymax = 0
            bmin = []
            bmax = []
            for i in range(0, xtrace):
                bmin.append(numpy.amin(self.IXC_plots[i].vb.viewRange()[1]))
                bmax.append(numpy.amax(self.IXC_plots[i].vb.viewRange()[1]))
            ymin = numpy.amin(bmin)
            ymax = numpy.amax(bmax)
            self.IXC_plots[i].setXRange(numpy.min(self.lags), numpy.max(self.lags))
            for i in range(0, xtrace):
                self.IXC_plots[i].setYRange(ymin, ymax) # remember, all are linked to the 0'th plot
                self.IXC_plots[i].setLabel('left', text="R")
                self.IXC_plots[i].setLabel('bottom', text="Time (s)")
                if i == 0:
                    pass
                    #self.IXC_plots[i].setYlabel("R")
                    #self.IXC_plots[i].setXlabel("Time (s)")
                if i > 0:
                    self.IXC_plots[i].hideAxis('left')
                    self.IXC_plots[i].hideAxis('bottom')
                 #   self.IXC_plots[i].hideButtons()
        elif plottype == 'traces':
            for xtrace1 in range(0, nROI-1):
                for xtrace2 in range(0, xtrace1):
                    plx = self.IXC_plots[xtrace1-1, xtrace2]
                    plx.set_xlabel('T (sec)', fontsize=10)
                    plx.set_ylabel('Corr (R)', fontsize=10)
                    PH.cleanAxes(self.IXC_plots[xtrace1, xtrace2])
            PL.show()
        elif plottype == 'image':
#            print self.IXC_Strength.shape
            self.MPLFig.imshow(self.IXC_Strength)
            PL.show()
        
        #MPlots.sameScale(self.IXC_plots)
        #MPlots.PlotReset(self.IXC_plots[xtrace-1], xAxisOn=True, yAxisOn=True, xlabel='Lag', unitsX='s',
        #                 ylabel='C', xMinorTicks=0, yMinorTicks=0, clearFlag = False,)
        #self.IXC_plots[xtrace-1].replot()
        #self.selectIndividualXcorrTab()
    #  print self.IXC_strength
        #self.MPLAxes.clear()
        #self.MPLAxes.hold=False
#         imagey = 96
#         for i in range(0, self.nROI):
#             self.MPLAxes.plot(rois[i].pos().x(), imagey-rois[i].pos().y(), 'ro')
#             self.MPLAxes.hold=True 
#             self.MPLAxes.text(rois[i].pos().x()+1, imagey-rois[i].pos().y(), ("%d" % (i) ))
#         scmax = self.IXC_strength.max().max()
#         widmax = 5.0/scmax # scale width by peak strength of correlation
# #        print scmax
# #        print widmax
#         for xtrace1 in range(0, self.nROI-1):
#             for xtrace2 in range(xtrace1+1, self.nROI):
#                 if self.IXC_strength[xtrace1, xtrace2] > 0.25:
#                     self.MPLAxes.plot([rois[xtrace1].pos().x(), rois[xtrace2].pos().x()], 
#                                       [imagey-rois[xtrace1].pos().y(), imagey-rois[xtrace2].pos().y()], 'b-', 
#                                       linewidth=widmax*self.IXC_strength[xtrace1, xtrace2])
#                    print "xt: %d yt: %d lw: %f" % (xtrace1, xtrace2, widmax*self.IXC_strength[xtrace1, xtrace2])

#----------------Fourier Map (reports phase)----------------------------
    def Analog_AFFT(self):
        pass

    def Analog_AFFT_Individual(self):
        pass

    def Analysis_FourierMap(self):
        # print "times: ", self.times # self.times has the actual frame times in it. 
        # first squeeze the image to 3d if it is 4d
        sh = numpy.shape(self.imageData);
        if len(sh) == 4:
            self.imageData = numpy.squeeze(self.imageData)
            sh = numpy.shape(self.imageData)
        print '**********************************\nImage shape: ', sh
        self.imagePeriod = 6.0 # image period in seconds.
        w = 2.0 * numpy.pi * self.imagePeriod
        # identify an interpolation for the image for one cycle of time
        dt = numpy.mean(numpy.diff(self.imageTimes)) # get the mean dt
        maxt = numpy.amax(self.imageTimes) # find last image time
        n_period = int(numpy.floor(maxt/self.imagePeriod)) # how many full periods in the image set?
        n_cycle = int(numpy.floor(self.imagePeriod/dt)); # estimate image points in a stimulus cycle
        ndt = self.imagePeriod/n_cycle
        i_times = numpy.arange(0, n_period*n_cycle*ndt, ndt) # interpolation times
        n_times = numpy.arange(0, n_cycle*ndt, ndt) # just one cycle
        print "dt: %f maxt: %f # images %d" % (dt, maxt, len(self.imageTimes))
        print "# full per: %d  pts/cycle: %d  ndt: %f #i_times: %d" % (n_period, n_cycle, ndt, len(i_times))
        B = numpy.zeros([sh[1], sh[2], n_period, n_cycle])
        #for i in range(0, sh[1]):
#            for j in range(0, sh[2]):
#                B[i,j,:] = numpy.interp(i_times, self.times, self.imageData[:,i,j])
        B = self.imageData[range(0, n_period*n_cycle),:,:]
        print 'new image shape: ', numpy.shape(self.imageData)
        print "B shape: ", numpy.shape(B)
        C = numpy.reshape(B, (n_cycle, n_period, sh[1], sh[2]))
        print 'C: ', numpy.shape(C)
        D = numpy.mean(C, axis=1)
        print "D: ", numpy.shape(D)
        sh = numpy.shape(D)
        A = numpy.zeros((sh[0], 2), float)
        print "A: ", numpy.shape(A)
        A[:,0] = numpy.sin(w*n_times)
        A[:,1] = numpy.cos(w*n_times)
        sparse = 1

        self.phaseImage = numpy.zeros((sh[1], sh[2]))
        self.amplitudeImage = numpy.zeros((sh[1], sh[2]))
        for i in range(0, sh[1], sparse):
            for j in range(0, sh[2], sparse):
                (p, residulas, rank, s) = numpy.linalg.lstsq(A, D[:,i,j])
                self.amplitudeImage[i,j] = numpy.hypot(p[0],p[1])
                self.phaseImage[i, j] = numpy.arctan2(p[1],p[0]) 
        f = open('img_phase.dat', 'w')
        pickle.dump(self.phaseImage, f)
        f.close()
        f = open('img_amplitude.dat', 'w')
        pickle.dump(self.amplitudeImage, f)
        f.close()

#        pylab.figure()
#        pylab.imshow(self.phaseImage)
#        pylab.show()
#
# ---------------SMC (oopsi, Vogelstein method) detection of calcium events in ROIs----------------

    def Analysis_smcAnalyze(self):
        self.smc_A = self.ctrlAnalysis.smc_Amplitude.value()
        self.smc_Kd = self.ctrlAnalysis.smc_Kd.value()
        self.smc_C0 = self.ctrlAnalysis.smc_C0.value()
        self.smc_TCa = self.ctrlAnalysis.smc_TCa.value()
        if self.imageTimes is []:
            dt = 1.0/30.0 # fake it... 30 frames per second
        else:
            dt = numpy.mean(numpy.diff(self.imageTimes))
        print "Mean time between frames: %9.4f" % (dt)
        if self.BFData is []:
            print "No baseline corrected data to use!!!"
            return
        dataIDString = 'smc_'
        for roi in range(0, self.nROI):
            print "ROI: %d" % (roi)
            # normalized the data:
            ndat = (self.BFData[roi,:] - numpy.min(self.BFData[roi,:]))/numpy.max(self.BFData[roi,:])
            self.smc_V = SMC.Variables(ndat, dt)
            self.smc_P = SMC.Parameters(self.smc_V, A=self.smc_A, k_d=self.smc_Kd, C_0=self.smc_C0, tau_c =self.smc_TCa)
            self.smc_S = SMC.forward(self.smc_V, self.smc_P)
            cbar = numpy.zeros(self.smc_P.V.T)
            nbar = numpy.zeros(self.smc_P.V.T)    
            for t in xrange(self.smc_P.V.T):
                for i in xrange(self.smc_P.V.Nparticles):
                    weight = self.smc_S.w_f[i,t]
                    cbar[t] += weight * self.smc_S.C[i,t]
                    nbar[t] += weight * self.smc_S.n[i,t]
            print "ROI: %d cbar: " % (roi)
            print cbar
            print "ROI: %dnbar: " % (roi)
            print nbar
            MPlots.PlotLine(self.plots[roi], self.imageTimes, cbar, color = 'black',
                            dataID = ('%s%d' % (dataIDString, roi)))
        print "finis"

# Use matlab to do the analysis with J. Vogelstein's code, store result on disk
    def smc_AnalyzeMatlab(self):
        subprocess.call(['/Applications/MATLAB_R2010b.app/bin/matlab', '-r', 'FigSimNoisy.m'], bufsize = 1)

    def Analysis_SpikeXCorr(self):
        pass        

class pyqtgrwindow(QtGui.QMainWindow):
    def __init__(self, parent=None, title = '', size=(500,500)):
        super(pyqtgrwindow, self).__init__(parent)
        self.setWindowTitle(title)
        self.setCentralWidget(QtGui.QWidget(self))
        self.resize(size[0], size[1])
        self.show()
        