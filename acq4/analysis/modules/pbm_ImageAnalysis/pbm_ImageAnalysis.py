# -*- coding: utf-8 -*-
from __future__ import print_function
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
    6. Cross-correlation of ROI and spike trains.
    
    Fall, 2011
    Jan, 2012.
    Paul B. Manis, Ph.D.
    UNC Chapel Hill
    Supported by NIH/NIDCD Grants:
        DC004551 (Cellular mechanisms of auditory information processing)
        DC000425 (Physiology of the Dorsal Cochlear Nucleus Molecular Layer)
        DC009809 (Auditory Cortex: Synaptic organization and plasticity)
    Has potential dependency on openCV for some functions.
"""

from acq4.util import Qt
from acq4.analysis.AnalysisModule import AnalysisModule
from collections import OrderedDict
import os
import shutil
import csv
import os.path
import pickle
import acq4.pyqtgraph as pg
import acq4.pyqtgraph.debug as debug
import acq4.util.DatabaseGui as DatabaseGui
import PIL as Image
from acq4.util.metaarray import MetaArray
import numpy as np
import scipy
from . import ctrlTemplate
import ctrlROIsTemplate
import ctrlAnalysisTemplate
import ctrlPhysiologyTemplate
from acq4.analysis.tools import Utility
from acq4.analysis.tools import Fitting
from acq4.analysis.tools import PlotHelpers as PH  # matlab plotting helpers
from acq4.util import functions as FN
from acq4.util.HelpfulException import HelpfulException
from acq4.devices.Scanner.scan_program import rect
from six.moves import range

try:
    import cv2
    #import cv2.cv as cv
    openCVInstalled = True
except:
    openCVInstalled = False
    
#import smc as SMC # Vogelstein's OOPSI analysis for calcium transients

import pylab as PL
#from mpl_toolkits.axes_grid1 import AxesGrid

#
# We use matplotlib/pylab for *some* figure generation.
#

class pbm_ImageAnalysis(AnalysisModule):
    def __init__(self, host, flowchartDir=None, dbIdentity="ImageAnalysis"):
        AnalysisModule.__init__(self, host)
        
        self.dbIdentity = dbIdentity

        # per-instance parameters:
        self.currentDataDirectory = None  # currently selected data directory (if valid)
        self.refImage = None  # Reference image data used for ratio calculations
                                # This image may come from a separate file or a calculation on the present file
        self.physData = None  # physiology data associated with the current image
        self.dataStruct = 'flat'  # 'flat' or 'interleaved' are valid at present.
        self.imageInfo = []
        self.ignoreFirst = 1  # ImagePhys_ignoreFirst # note this is a number of images, not T/F
        self.rectSelect = True  #
        self.tStart = 0.0  # baseline time start = applies to the image: ImagePhys_BaseStart
        self.tEnd = 50.0  # baseline time end (msec) : ImagePhys_BaseEnd
        self.imageLPF = 0.0  # low pass filter of the image data, Hz: ImagePhys_ImgLPF
        self.physLPF = 0.0  # low pass filter of the physiology data, Hz (0 = no filtering): ImagePhys_PhysLPF
        self.physLPFChanged = False  # flag in case the physiology LPF changes (avoid recalculation)
#        self.physSign = 0.0  # ImagePhys_PhysSign (detection sign for events)
        self.physThresh = -50.0  # ImagePhys_PhysThresh (threshold in pA to detect events)
        self.physThreshLine = None
        self.ratioImages = False  # only set true once a ratio (reference) image is loaded
        self.ROIfig = None
        self.baseImages = []
        self.viewFlag = False  # false if viewing movie, true if viewing fixed image
        self.referenceImage = []
        self.ratioImage = None
        self.useRatio = False
        self.AllRois = []
        self.nROI = 0  # count of ROI's in the window
        self.rois = []
        self.currentRoi = None
        self.imageData = np.array(None)  # Image Data array, information about the data is in the dataState dictionary
        self.lastROITouched=[]
        self.spikesFound = None
        self.burstsFound = None
        self.spikeTimes = []
        self.burstTimes = []
        self.specImage = []
        self.specImageCalcFlag = False
        self.stdImage = []
        self.avgImage = []
        self.imageType = 'camera'  # frames for camera (all pixels simultaneous); scanner for scanner (need scan timing)
        
        self.analogMode = True  # if false, we are using digital mode.
        self.csvFileName = None
        self.csvData = None
                
        self.spikesFoundpk = None
        self.withinBurstsFound = None
        self.FData = []
        self.MPLFig = None  # We keep one instance of a matplotlib figure, create and destroy as needed
        self.floatingWindow = None  # one instance of a pyqtgraph window that floats.
        self.pgwin = None

        # ------ Graphical Elements ------
        self._sizeHint = (1280, 900)   # try to establish size of window

        self.ctrlWidget = Qt.QWidget()
        self.ctrl = ctrlTemplate.Ui_Form()
        self.ctrl.setupUi(self.ctrlWidget)
        
        self.ctrlROIFuncWidget = Qt.QWidget()
        self.ctrlROIFunc = ctrlROIsTemplate.Ui_Form()
        self.ctrlROIFunc.setupUi(self.ctrlROIFuncWidget)

        self.ctrlImageFuncWidget = Qt.QWidget()
        self.ctrlImageFunc = ctrlAnalysisTemplate.Ui_Form()
        self.ctrlImageFunc.setupUi(self.ctrlImageFuncWidget)
        
        self.ctrlPhysFuncWidget = Qt.QWidget()
        self.ctrlPhysFunc = ctrlPhysiologyTemplate.Ui_Form()
        self.ctrlPhysFunc.setupUi(self.ctrlPhysFuncWidget)
        
        self.initDataState()
        self.RGB = Utility.makeRGB()

        ## Setup basic GUI
        self._elements_ = OrderedDict([
            ('File Loader', {'type': 'fileInput', 'size': (150, 300), 'host': self, 'showFileTree': True}),
            ('Image',       {'type': 'imageView', 'pos': ('right', 'File Loader'), 'size': (500, 500)}),
            ('Analysis',    {'type': 'ctrl', 'object': self.ctrlImageFuncWidget, 'host': self, 'size': (150,300)}),
            ('Physiology',  {'type': 'ctrl', 'object': self.ctrlPhysFuncWidget, 'pos' : ('above', 'Analysis'), 'size': (150,300)}),
            ('ROI',  {'type': 'ctrl', 'object': self.ctrlROIFuncWidget, 'pos' : ('above', 'Physiology'), 'size': (150,300)}),
            ('Imaging Parameters',  {'type': 'ctrl', 'object': self.ctrlWidget, 'pos' : ('above', 'ROI'), 'size': (150,300)}),
            ('Background Plot',  {'type': 'plot', 'pos': ('right', 'Imaging Parameters'),'size': (1000, 100)}),
            ('ROI Plot',   {'type': 'plot',  'pos': ('bottom', 'Background Plot'),'size': (1000, 300)}),
            ('Phys Plot',   {'type': 'plot',  'pos': ('bottom', 'ROI Plot'),'size': (1000, 300)}),
            
#            ('Line Scan',   {'type': 'imageView', 'size': (1000, 300)}),
            #('Data Table',  {'type': 'table', 'pos': ('below', 'Time Plot')}),
        ])
        self.initializeElements()
        self.ctrl.ImagePhys_RectSelect.stateChanged.connect(self.updateRectSelect)
        self.ctrl.ImagePhys_Update.clicked.connect(self.updateAnalysis)
        self.ROI_Plot = self.getElement('ROI Plot', create=True)
        self.backgroundPlot = self.getElement('Background Plot', create=True)
        self.physPlot = self.getElement('Phys Plot', create = True)
        self.lr = pg.LinearRegionItem([0, 1])
        # self.ROI_Plot.addItem(self.lr)
        self.updateRectSelect()    
        self.ROI_Plot.plotItem.vb.setXLink('Phys Plot') # not sure - this seems to be at the wrong level in the window manager
        self.imageView = self.getElement('Image', create=True)
        self.imageItem = self.imageView.imageItem
        self.fileLoaderInstance = self.getElement('File Loader', create=True)

        # Plots are updated when the selected region changes
        self.lr.sigRegionChanged.connect(self.updateAnalysis)
        self.imageView.sigProcessingChanged.connect(self.processData)
        
        # main image processing buttons
        self.ctrl.ImagePhys_getRatio.clicked.connect(self.loadRatioImage)
        self.ctrl.ImagePhys_clearRatio.clicked.connect(self.clearRatioImage)
        self.ctrl.ImagePhys_ImgNormalize.clicked.connect(self.doNormalize)
        self.ctrl.ImagePhys_View.currentIndexChanged.connect(self.changeView)
        self.ctrl.ImagePhys_GetFileInfo.clicked.connect(self.getFileInfo)
        self.ctrl.ImagePhys_RegisterStack.clicked.connect(self.RegisterStack)
        self.ctrl.ImagePhys_DisplayTraces.clicked.connect(self.makeROIDataFigure)
        self.ctrl.ImagePhys_ExportTiff.clicked.connect(self.ExportTiff)
        self.ctrl.ImagePhys_PhysROIPlot.toggled.connect(self.setupPhysROIPlot)
        # PMT scan data adjustments
        self.ctrl.ImagePhys_Restore_decomb.clicked.connect(self.restoreDecomb)
        self.ctrl.ImagePhys_PMT_decomb.valueChanged.connect(self.processPMT)
        self.ctrl.ImagePhys_PMT_autoButton.clicked.connect(self.processPMT)

        # ROI function buttons and controls
        self.ctrlROIFunc.ImagePhys_addRoi.clicked.connect(self.addOneROI)
        self.ctrlROIFunc.ImagePhys_clearRoi.clicked.connect(self.clearAllROI)
        self.ctrlROIFunc.ImagePhys_UnBleach.clicked.connect(self.unbleachImage)
        self.ctrlROIFunc.ImagePhys_SpecCalc.clicked.connect(self.spectrumCalc)
        self.ctrlROIFunc.ImagePhys_RecalculateROIs.clicked.connect(self.calculateAllROIs)
        self.ctrlROIFunc.ImagePhys_RetrieveROI.clicked.connect(self.restoreROI)
        self.ctrlROIFunc.ImagePhys_SaveROI.clicked.connect(self.saveROI)
        self.ctrlROIFunc.ImagePhys_findROIs.clicked.connect(self.findROIs)
#        self.ctrl.ImagePhys_CorrTool_BL1.clicked.connect(self.Baseline1) # these are checkboxes now...
        self.ctrlROIFunc.ImagePhys_CorrTool_HPF.stateChanged.connect(self.refilterCurrentROI) # corr tool is the checkbox
        self.ctrlROIFunc.ImagePhys_CorrTool_LPF.stateChanged.connect(self.refilterCurrentROI)
        self.ctrlROIFunc.ImagePhys_ImgHPF.editingFinished.connect(self.refilterCurrentROI) # ImgHPF is the is the spinbox
        self.ctrlROIFunc.ImagePhys_ImgLPF.editingFinished.connect(self.refilterCurrentROI)

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
        self.ctrlImageFunc.IAFuncs_AnalogRadioBtn.clicked.connect(self.setAnalogMode)
        self.ctrlImageFunc.IAFuncs_DigitalRadioBtn.clicked.connect(self.setDigitalMode)
        self.ctrlImageFunc.IAFuncs_GetCSVFile.clicked.connect(self.getCSVFile)
        

    def initDataState(self):
        """
        Create clean data State (self.dataState) for new files
        :return nothing:
        """
        self.dataState = {'Loaded': False, 'bleachCorrection': False, 'Normalized': False,
                        'NType' : None, 'Structure': 'Flat', 'NTrials': 0, 'ratioLoaded': False}
        self.ctrlROIFunc.ImagePhys_BleachInfo.setText('None')
        self.ctrl.ImagePhys_NormInfo.setText('None')
        self.IXC_Strength = []
        self.ROIDistanceMap = []
        self.tc_bleach = []

    def setAnalogMode(self):
        """

        :return:
        """
        self.analogMode = True
        self.ctrlImageFunc.IA_Funcs.AnalogRadioBtn.checked(True)
        self.ctrlImageFunc.IA_Funcs.DigitalRadioBtn.checked(False)
    
    def setDigitalMode(self):
        self.digitalMode = False
        self.ctrlImageFunc.IA_Funcs.AnalogRadioBtn.checked(False)
        self.ctrlImageFunc.IA_Funcs.DigitalRadioBtn.checked(True)
        
    def updateRectSelect(self):
        self.rectSelect = self.ctrl.ImagePhys_RectSelect.isChecked()
        if self.rectSelect:
            self.ROI_Plot.plotItem.vb.setLeftButtonAction(mode='rect')  # use the rubber band box instead
            self.physPlot.plotItem.vb.setLeftButtonAction(mode='rect')  # use the rubber band box instead
        else:
            self.ROI_Plot.plotItem.vb.setLeftButtonAction(mode='pan')  # use the standard pan mode instead
            self.physPlot.plotItem.vb.setLeftButtonAction(mode='pan')  # use the standard pan modeinstead
        
    def changeView(self):
        view = self.ctrl.ImagePhys_View.currentText()
        if self.dataState['ratioLoaded'] is True:
            if view == 'Ratio Image':
                self.imageView.setImage(self.ratioImage)
                self.viewFlag = True

        if self.dataState['Loaded'] is False:
            return  # no data - so skip this.
        if view == 'Reference Image':
            self.imageView.setImage(np.mean(self.imageData[self.baseImages, :, :], axis=0))
            self.viewFlag = True
        if view == 'Average Image':
            self.imageView.setImage(self.aveImage)
        if view == 'Std Image':
            self.imageView.setImage(self.stdImage)
        if view == 'Spectrum Image':
            self.imageView.setImage(self.specImageDisplay)
        if view == 'Movie':
            self.imageView.setImage(self.imageData)
            self.viewFlag = False

    def processData(self):
        self.normData = []
        self.imageData = []
        print('in processData...')
        for img in self.rawData:
            print('doing image processdata')
            n = np.empty(img.shape, dtype=img.dtype)
            for i in range(img.shape[0]):
                n[i] = self.imageView.normalize(img[i])
            self.normData.append(n)
            
            imgSet = {'procMean': n.mean(axis=0), 'procStd': n.std(axis=0)}
            print('appending...')
            self.imageData.append(imgSet)
            
    def updateAnalysis(self):
        self.getDataStruct()
        roi = self.currentRoi
        plot = self.getElement('Background Plot')
        plot.clearPlots()
#        print 'LPF Changed?: ', self.physLPFChanged
        if self.physLPFChanged:  # only update if the LPF filter has changed
            self.readPhysiology(self.currentDataDirectory)  # re-read in case LPF has changed
        c = 0
        if self.currentRoi is None:
            return
        for img in self.normData:  # pull from all the normalized data arrays (in a list)
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
        which may contain both physiology and image data.
        If multiple files are selected, this routine will be called for each one...
        
        """
        
#        ds = self.dataModel.isSequence(dh[0])
        #dirtype = self.dataModel.dirType(dh[0])
        # if dirtype == 'ProtocolSequence':
        #     dsp = self.dataModel.listSequenceParams(dh[0])
        dlh = self.fileLoaderInstance.selectedFiles()
        if self.ctrl.ImagePhys_PhysROIPlot.isChecked():
            print('multiple file load, for # of files: ', len(dlh))
            self.makePhysROIPlot(dh, dlh)
        else:
            if len(dlh) > 1:
                raise HelpfulException("pbm_ImageAnalysis: loadFileRequested Error\nCan only load from single file", msgType='status')
            else:
                self.loadSingleFile(dh[0])
    
    def setupPhysROIPlot(self):
        if self.ctrl.ImagePhys_PhysROIPlot.isChecked():
            self.checkMPL()
            self.firstPlot = False
            self.plotCount = 0

    def makePhysROIPlot(self, dh, dlh):
        if type(dh) is list:
            dh = dh[0]
        fname = dh.name()
        (head, tail) = os.path.split(fname)
        self.MPRncolumns = 2
        self.MPRnrows = len(dlh)
        if len(dlh) % 2 == 1:
            self.MPRnrows += 2
        if self.firstPlot is False:
            (self.MPLFig, self.MPPhysPlots) = PL.subplots(num="Physiology-Fluor comparison", 
                    nrows=self.MPRnrows, ncols=self.MPRncolumns, sharex=True, sharey=False)
            self.MPLFig.suptitle('Dataset: %s' % (head) , fontsize=10)

            self.nPhysPlots = len(dlh)
            c = 0
            r = 0
            for i in range(0, self.MPRnrows*self.MPRncolumns, 2):
                self.MPPhysPlots[r, c].sharey = True
                r = r + 2
                if r >= self.MPRnrows:
                    r = 0
                    c += 1
                
        self.firstPlot = True
        try:
            self.loadSingleFile(dh)
        except:
            print('problem loading data... skipping')
            self.plotCount += 1
            return
        self.unbleachImage()
        self.calculateAllROIs()

        c = 0
        r = self.plotCount*2
        if r >= self.MPRnrows-1:
            c += 1
            r = self.plotCount*2 % self.MPRnrows
        self.MPPhysPlots[r+1, c].plot(self.tdat, self.physData, 'k-', linewidth=0.5)
        self.MPPhysPlots[r+1, c].set_title(tail)

        for i in range(self.nROI):
            ndpt = len(self.FData[i, :])
            self.MPPhysPlots[r, c].plot(self.imageTimes[0:ndpt], (self.FData[i, :]-1.0)*100.)
        self.plotCount += 1
        PL.draw()
        if self.plotCount >= self.nPhysPlots:
            PL.show()
            self.ctrl.ImagePhys_PhysROIPlot.setCheckState(False)  # turn off now - to properly sequence reload
            (d1, s1) = os.path.split(self.currentFileName)
            (d2, s2) = os.path.split(d1)
            (d3, s3) = os.path.split(s2)
            sfn = s3+'-'+s2+'-'+s1
            PL.savefig('/Users/Experimenters/Desktop/ePhysPlots/%s.png' % (sfn), dpi=600, format='png')

    def readDataTypes(self):
        requestType = []
        if self.ctrl.ImagePhys_Camera_check.isChecked():
            requestType.append('camera')
        if self.ctrl.ImagePhys_PMT_check.isChecked():
            requestType.append('PMT')
        if self.ctrl.ImagePhys_Image_check.isChecked():
            requestType.append('imaging')
        return requestType

    def clearImageTypes(self):
        self.ctrl.ImagePhys_Camera_check.setText('Camera')
        self.ctrl.ImagePhys_PMT_check.setText('PMT')
        self.ctrl.ImagePhys_Image_check.setText('Imaging')

    def loadSingleFile(self, dh):
        """

        :param dh:
        :return:
        """
        self.imageView.setFocus()
        self.downSample = int(self.ctrl.ImagePhys_Downsample.currentText())
        if self.downSample <= 0:
            self.downSample = 1  # same as "none"
        self.initDataState()

        self.shiftFlag = False  # eventually, but at the moment it does NOT work
        self.getDataStruct()

        if type(dh) is list:
            dh = dh[0]
        self.currentFileName = dh.name()
        self.imageScaleUnit = 'pixels'
        self.imageTimes = np.array(None)
        self.imageType =  None  # 'camera' for camera (all pixels simultaneous); imaging for scanner (need scan timing); PMT for photomultipler raw data
        self.rs = None
        img = None
        self.clearImageTypes()
        if self.dataStruct is 'flat':
            #print 'getting Flat data structure!'
            if dh.isFile():
                fhandle = dh
            else:
                # test data type for the imaging
                requestType = self.readDataTypes()  # selection of image types for analysis - can exclude imaging for example.
                if os.path.isfile(os.path.join(dh.name(), 'Camera/frames.ma')) and 'camera' in requestType:
                    fhandle = dh['Camera/frames.ma']  # get data from ccd camera
                    self.imageType = 'camera'
                    self.ctrl.ImagePhys_Camera_check.setText(u'Camera \u2713')
                    if self.downSample == 1:
                        imt = MetaArray(file=fhandle.name())
                        self.imageInfo = imt.infoCopy()
                        img = imt.asarray()
                        #img = fhandle.read() # read the image stack directly
                    else:
                        (img, info) = self.tryDownSample(fhandle)
                        self.imageInfo = info
                    self.imageTimes = self.imageInfo[0]['values']
                    self.imageData = img.view(np.ndarray)
                    sh = self.imageData.shape
                    self.scanTimes = np.zeros(sh[1]*sh[2]).reshape((sh[1], sh[2]))
                    self.prepareImages()

                elif os.path.isfile(os.path.join(dh.name(), 'PMT.ma')) and 'PMT' in requestType:
                    fhandle = dh['PMT.ma']  # get data from PMT, as raw trace information
                    self.pmtData = MetaArray(file=fhandle.name())
                    self.imageType = 'PMT'
                    self.ctrl.ImagePhys_PMT_check.setText(u'PMT \u2713')
                    self.rs = rect.RectScan()
                    scanInfo = dh.info()['Scanner']['program'][0]['scanInfo']
                    self.rs.restoreState(scanInfo)
                    decombInfo = dh.info()['protocol']['analysis']['Imaging']['children']['decomb']
                    auto = decombInfo['children']['auto']['value']
                    subpixel = decombInfo['children']['subpixel']['value']
                    self.PMTInfo = {'scanInfo': scanInfo, 'decombInfo': decombInfo, 'auto': auto, 'subpixel': subpixel}
                    self.imageInfo = self.pmtData.infoCopy()
                    self.restoreDecomb()  # restore the original decomb settings and process the image.

                elif os.path.isfile(os.path.join(dh.name(), 'imaging.ma')) and 'imaging' in requestType:
                    fhandle = dh['imaging.ma']  # get data from a pre-processed imaging file of PMT data
                    self.imageType = 'imaging'
                    self.ctrl.ImagePhys_Image_check.setText(u'Imaging \u2713')
                    if self.downSample == 1:
                        imt = MetaArray(file=fhandle.name())
                        self.imageInfo = imt.infoCopy()
                        img = imt.asarray()
                    else:
                        (img, info) = self.tryDownSample(fhandle)
                        self.imageInfo = info
                    self.imageData = img.view(np.ndarray)
                    self.imageTimes = self.imageInfo[0]['values']
                    itdt = (np.max(self.imageTimes)/len(self.imageTimes))  # time between scans (duration)
                    sh = self.imageData.shape
                    self.scanTimes = np.linspace(0., itdt, sh[1]*sh[2]).reshape((sh[1], sh[2]))  # estimated times for each point in the image.
                    self.prepareImages()

                else:
                    raise Exception("No valid imaging data found")
            self.clearPhysiologyInfo()  # clear the physiology data currently in memory to avoid confusion
            if not dh.isFile():
                self.readPhysiology(dh)
            if img is None:
                return False
            #self.processData()

        else:  # interleaved data structure (Deepti Rao's calcium imaging data)
            dirs = dh.subDirs()  # find out what kind of data we
            images = [[], [], [], []]
            ## Iterate over sequence
            minFrames = None
            for d in dirs:  # each of the directories contains a data set
                d = dh[d]
                try:
                    ind = d.info()[('Clamp1', 'amp')]
                except:
                    print('unable to read clamp data from : ', d)
                    print(d.info())
                    raise
                img = d['Camera/frames.ma'].read()
                images[ind].append(img)
                
                if minFrames is None or img.shape[0] < minFrames:
                    minFrames = img.shape[0]
                
            self.rawData = np.array(None)
            self.imageData = np.array(None)
#            print "len images: %d " % (len(images))
            while len(images) > 0:
                imgs = images.pop(0)
                img = np.concatenate([i[np.newaxis, :minFrames, ...] for i in imgs], axis=0)
                self.rawData.append(img.astype(np.float32))
                #img /= self.background
            
            ## remove bleaching curve from first two axes
            ctrlMean = self.rawData[0].mean(axis=2).mean(axis=2)
            trialCurve = ctrlMean.mean(axis=1)[:, np.newaxis, np.newaxis, np.newaxis]
            timeCurve = ctrlMean.mean(axis=0)[np.newaxis,:, np.newaxis, np.newaxis]
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
        self.ctrl.ImagePhys_View.setCurrentIndex(0)  # always set to show the movie
        self.specImageCalcFlag = False  # we need to recalculate the spectrum
        npts = self.imageData.shape[0]/2
        freq = np.fft.fftfreq(npts, d=self.imagedT)
        freq = freq[0:npts/2 + 1]
        self.ctrlROIFunc.ImagePhys_SpecHPF.setMinimum(0.0)
        self.ctrlROIFunc.ImagePhys_SpecHPF.setMaximum(np.max(freq))
        self.ctrlROIFunc.ImagePhys_SpecHPF.setValue(freq[1])
        self.ctrlROIFunc.ImagePhys_SpecLPF.setMinimum(freq[1])
        self.ctrlROIFunc.ImagePhys_SpecLPF.setMaximum(np.max(freq))
        self.ctrlROIFunc.ImagePhys_SpecLPF.setValue(np.max(freq))
        #print dir(self.ctrl.ImagePhys_ImgNormalize)
        self.ctrl.ImagePhys_ImgNormalize.setEnabled(True)
        self.updateAvgStdImage()  # make sure mean and std are properly updated
        self.calculateAllROIs()  # recompute the ROIS
        self.updateThisROI(self.lastROITouched)  # and make sure plot reflects current ROI (not old data)
        return True

    def restoreDecomb(self):
        """
        Retrieve the original decombing value for the file, and reset the image
        :return:
        """
        self.ctrl.ImagePhys_PMT_decomb.setValue(1e6*self.PMTInfo['decombInfo']['value'])
        self.ctrl.ImagePhys_PMT_auto_check.setChecked(self.PMTInfo['auto'])
        self.ctrl.ImagePhys_PMT_decomb_subpixel.setChecked(self.PMTInfo['subpixel'])
        self.processPMT()

    def filterPMT(self, sdt, lpf):
        if self.ctrl.ImagePhys_PMT_LPF_check.isChecked():
            lpf = self.ctrl.ImagePhys_PMT_LPF.value()*1e3  # convert kHz to Hz
#            print sdt, lpf
            if 1./sdt < lpf/2.:   # force nyquist happiness
                lpf = 0.5/sdt
                print('reset lpf to ', lpf)
            filtdata = Utility.SignalFilter_LPFBessel(self.pmtData.asarray()[0], lpf, 1.0/sdt, NPole=4, bidir=True)
            return filtdata
        #    img = self.rs.extractImage(filtdata, offset=lag, subpixel=subpixel)
        else:  # no filtering - just return original array
            return self.pmtData.asarray()[0]
        #img = self.rs.extractImage(self.pmtData.asarray()[0], offset=lag, subpixel=subpixel)

    def processPMT(self):
        """
        read, adjust and set up PMT data for analysis and display.
        Includes decombing for bidirectional scans,
        :return: Nothing
        """
        if self.imageType != 'PMT':
            return
        sdt = self.pmtData.xvals('Time')[1] - self.pmtData.xvals('Time')[0]
        lpf = self.ctrl.ImagePhys_PMT_LPF.value()*1e3  # convert kHz to Hz
        pmt_d = self.filterPMT(sdt, lpf)  # filter data first

        if self.ctrl.ImagePhys_PMT_auto_check.isChecked():
            (decombed, lag) = self.rs.measureMirrorLag(pmt_d, transpose=True, maxShift=100)
            lag *= sdt/2.  # lag from measureMirrorLag is  expressed in pixels - convert to time.
            self.ctrl.ImagePhys_PMT_decomb.setValue(lag*1e6)
        else:
            lag = self.ctrl.ImagePhys_PMT_decomb.value() * 1e-6
        subpixel = self.ctrl.ImagePhys_PMT_decomb_subpixel.isChecked()
#         if self.ctrl.ImagePhys_PMT_LPF_check.isChecked():
# #            print sdt, lpf
#             if 1./sdt < lpf/2.:   # force nyquist happiness
#                 lpf = 0.5/sdt
#                 print 'reset lpf to ', lpf
#             filtdata = Utility.SignalFilter_LPFBessel(self.pmtData.asarray()[0], lpf, 1.0/sdt, NPole=4)
#             img = self.rs.extractImage(filtdata, offset=lag, subpixel=subpixel)
#         else:
#             img = self.rs.extractImage(self.pmtData.asarray()[0], offset=lag, subpixel=subpixel)
        img = self.rs.extractImage(pmt_d, offset=lag, subpixel=subpixel)
        self.imageData = img.view(np.ndarray)
        self.imageData = self.imageData.transpose(0, 2, 1)
       # compute global transform
        tr = self.rs.imageTransform()
        st = Qt.QTransform()
        st.scale(self.downSample, 1)
        tr = st * tr
        self.pmtTransform = pg.SRTTransform3D(tr)
        itx = self.rs.extractImage(self.pmtData.xvals('Time'), offset=lag, subpixel=subpixel)
        self.imageTimes = itx[:,0,0]
        self.scanTimes = itx[0,:,:]  # use times from first scan; will adjust offset later
        self.prepareImages()

    def prepareImages(self):
        """
        set up image data for analysis, and display image.
        :return: Nothing
        """
        fi = self.ignoreFirst
        self.rawData = self.imageData.copy()[fi:]  # save the raw data.
        self.imageData = self.imageData[fi:]
        self.imageTimes = self.imageTimes[fi:]
        self.baseImages = range(1)  # identify which images to show as the "base image"
        if self.downSample > 1:
            self.imageTimes = self.imageTimes[0:-1:self.downSample]
        self.imagedT = np.mean(np.diff(self.imageTimes))
        self.imageView.setImage(self.imageData)
        self.imageView.getView().setAspectLocked(True)
        self.imageView.imageItem.resetTransform()
        if self.imageType == 'PMT':
            self.imageView.imageItem.scale((self.rs.width/self.rs.height)/(float(self.imageData.shape[1])/float(self.imageData.shape[2])), 1.0)
        self.imageView.autoRange()

        self.dataState['Loaded'] = True
        self.dataState['Structure'] = 'Flat'
        self.background = self.rawData.mean(axis=2).mean(axis=1)
        self.backgroundmean = self.background.mean(axis=0)
        # if any ROIs available, update them.
        self.updateAvgStdImage()  # make sure mean and std are properly updated
        self.calculateAllROIs()  # recompute the ROIS
        self.updateThisROI(self.lastROITouched)  # and make sure plot reflects current ROI (not old data)

    def getCSVFile(self):
        """ read the CSV file for the ROI timing data """
        fd = Qt.QFileDialog(self)
        self.fileName = fd.getOpenFileName()
        from os.path import isfile
        allcsvdata = []
        if isfile(self.fileName):
            self.statusBar().showMessage( "Loading: %s..." % (self.fileName) )
            self.show()
            csvfile = csv.reader(open(self.fileName), delimiter=",")
            self.times = []
            self.nROI = 0
            self.bkgd=[]
            self.bkgdpos = None
            self.timepos = 0
            self.roilist = []
            firstline = next(csvfile)
            allcsvdata.append(firstline)
        return allcsvdata

    def updateAvgStdImage(self):
        """ update the reference image types and then make sure display agrees.
        """
        self.aveImage = np.mean(self.imageData, axis=0)
        self.stdImage = np.std(self.imageData, axis=0)
        self.changeView()

    def spectrumCalc(self):
        """
        Calculate the spectrum and display the power across time in a frequency band as the image
        intensity at each point. Useful for finding areas of activity.
        """
#        sh = self.imageData.shape
        if self.specImageCalcFlag is False:  # calculate spectrum info
            self.freim = np.abs(np.fft.fft(self.imageData, axis=0)/self.imageData.shape[0])
            self.specImageCalcFlag = True
            
        npts = self.imageData.shape[0]/2
        freq = np.fft.fftfreq(npts, d=self.imagedT)  # get frequency list
        freq = freq[0:npts/2 + 1]
        hpf = self.ctrlROIFunc.ImagePhys_SpecHPF.value()
        lpf = self.ctrlROIFunc.ImagePhys_SpecLPF.value()
        u = np.where(freq > hpf) # from frequencies, select those from the window
        v = np.where(freq < lpf)
        frl = list(set(u[0]).intersection(set(v[0])))
        if len(frl) == 0: # catch bad selection
            return
        si = self.freim.take(frl, axis=0) # % make selection
        self.specImage = np.mean(si, axis=0) # and get the average across the frequenies selected
        sigma = self.ctrlROIFunc.ImagePhys_FFTSmooth.value()
        self.specImageDisplay = scipy.ndimage.filters.gaussian_filter(self.specImage, sigma) # smooth a bit
        self.ctrl.ImagePhys_View.setCurrentIndex(3)
        self.changeView()

    def getImageScaling(self):
        """ 
            Retrieve scaling factor and set imageScaleUnit from the info on the image file
            In the case where the information is missing, we just set units to pixels.
        """
        if 'pixelSize' in self.imageInfo[3]:
            pixelsize = self.imageInfo[3]['pixelSize']
            region = self.imageInfo[3]['region']
#            binning = self.imageInfo[3]['binning']
            self.imageScaleUnit = 'um'
            sf = 1.0e6
        else:
            print('Old File without full scaling information on image, setting to defaults of pixels.')
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
        #print "sx, sy, px", sx, sy, px
        return(sx, sy, px)
    
    def getFileInfo(self):
        
        dh = self.fileLoaderInstance.selectedFiles()
        dh = dh[0]
        imt = MetaArray(file=dh.name()) # , subset=(slice(block_pos,block_pos+block_size),slice(None), slice(None)))
        sh = imt.shape
        info = imt.infoCopy()
        self.downSample = int(self.ctrl.ImagePhys_Downsample.currentText())
        if self.downSample <= 0:
            self.downSample = 1 # same as "none"
        totframes = int(np.ceil(sh[0]/self.downSample))
        imageTimes = list(info[0].values())[1]
        dt = np.mean(np.diff(imageTimes))
        print('\n')
        print('*'*80)
        print('File %s\n   Contains %d frames of %d x %d' % (dh.name(), sh[0], sh[1], sh[2]))
        print('   (would downsample to %d frames at downsample = %d ' % (totframes, self.downSample))
        print('Frame rate is: %12.5f s per frame or %8.2f Hz' % (dt, 1.0/dt))
        
    def tryDownSample(self, dh):
        imt = MetaArray(file=dh.name()) # , subset=(slice(block_pos,block_pos+block_size),slice(None), slice(None)))
        if imt is None:
            raise HelpfulException("Failed to read file %s in tryDownSample" % dh.name(), msgType='status')
        sh = imt.shape
        info = imt.infoCopy()
        outframes = int(np.ceil(sh[0]/self.downSample))
        bigblock = 1000
        nbigblocks = int(np.floor(sh[0]/bigblock))
        nlastblock = sh[0] - nbigblocks*bigblock
        if nlastblock > 0:
            nbigblocks += 1
        nframesperblock = bigblock/self.downSample
        print('Reducing from %d frames to %d frames, downsample = %d ' % (sh[0], outframes, self.downSample))
        imt_out = np.empty((outframes, sh[1], sh[2]), dtype=np.float32)
        tfr = 0
#        nfr = 0
        with pg.ProgressDialog("Downsampling", 0, outframes) as dlg:
            avgflag = True
            dlg.setLabelText("Reading images...")
            dlg.setValue(0)
            dlg.setMaximum(outframes)
#            bbcount = 0
            for bb in range(nbigblocks):
                img = imt[bb*bigblock:(bb+1)*bigblock, :, :]
                try:
                    img = img.asarray()
                except:
                    pass
                if bb == nbigblocks-1:
                    nframesperblock = int(np.floor(nlastblock/self.downSample))
                    print("reading last block of short...")
                for fr in range(nframesperblock):
                    dlg.setLabelText("Reading block %d of %d" % (tfr, outframes))
                    block_pos = fr * self.downSample
                    #print 'tfr: %d  block: %5d,  frame: %d ' % (tfr, block_pos, nfr)
                    if avgflag:
                        imt_out[tfr] = np.mean(img[block_pos:(block_pos+self.downSample)], axis=0)
    #                    imt_out[fr] = np.mean(imt[block_pos:(block_pos+self.downSample)], axis=0)
                    else:
                        try:
                            imt_out[tfr] = img[block_pos,:,:]
                        except:
                            print('Failing!!! fr: %d   blockpos: %d  bb: %d' % (fr, block_pos, bb))
                    dlg += 1
                    tfr += 1
#                    nfr = tfr*self.downSample
                    if dlg.wasCanceled():
                        raise Exception("Downample input canceled by user.")
                
        return(imt_out, info)

    def clearPhysiologyInfo(self):
        self.physPlot.clearPlots()
        self.physData = []
        self.physThreshLine = None
        self.spikesFound = None
        self.spikeFoundpk = None
        self.burstsFound = None
        self.withinBurstsFound = None
        self.makeSpikePointers()  # prepare the graph
        
    def readPhysiology(self, dh=None):
        """
        call to read the physiology from the primary data channel

        :params dh:  is the handle to the directory where the data is stored (not the file itself)
        "returns: Nothing
        """
        if dh is None:
            return
        self.clearPhysiologyInfo()
        data = self.dataModel.getClampFile(dh).read()  # retrieve the physiology traces
        self.physData = self.dataModel.getClampPrimary(data).asarray()
        if self.dataModel.getClampMode(data) == 'IC':
            self.physData = self.physData * 1e3  # convert to mV
            units = 'mV'
            self.ctrlPhysFunc.ImagePhys_PhysThresh.setSuffix(units)
        else:
            self.physData = self.physData * 1e12  # convert to pA, best for on-cell patches
            units = 'pA'
        info1 = data.infoCopy()
        self.samplefreq = info1[2]['DAQ']['primary']['rate']
        if self.physLPF >= 250.0 and self.physLPF < 0.5*self.samplefreq: # respect Nyquist, just minimally
            self.physData = Utility.SignalFilter_LPFBessel(self.physData, self.physLPF, self.samplefreq, NPole=8)
        self.physLPFChanged = False # we have updated now, so flag is reset
        maxplotpts = 50000
        shdat = self.physData.shape
        decimate_factor = 1
        if shdat[0] > maxplotpts:
            decimate_factor = int(np.floor(shdat[0]/maxplotpts))
            if decimate_factor < 1:
                decimate_factor = 1
        else:
            pass
            # store primary channel data and read command amplitude
        #print 'decimate factor: %d' % (decimate_factor)
        #print 'Number of points in original data set: ', shdat
        tdat = data.infoCopy()[1]['values']
        tdat = tdat[::decimate_factor]
        self.tdat = data.infoCopy()[1]['values']  # / 1000. NOT
        self.physPlot.plot(tdat, self.physData[::decimate_factor], pen=pg.mkPen('w')) # , decimate=decimate_factor)
        self.showPhysTrigger()
        try:
            self.detectSpikes()
        except:
            pass
        
    def loadRatioImage(self):
        print('loading ratio image')
        dh = self.fileLoaderInstance.selectedFiles()
        self.ratioImage = dh[0].read()[np.newaxis,...].astype('float')
        print(self.ratioImage)
        #self.background /= self.background.max()
        if self.ratioImage is None:
            self.dataState['ratioLoaded'] = False
            self.useRatio = False
            view = self.ctrl.ImagePhys_View.currentText()
            if view == 'Ratio Image':
                view = self.ctrl.ImagePhys_View.setCurrentIndex(0)

        else:
            self.useRatio = True
            self.dataState['ratioLoaded'] = True
            view = self.ctrl.ImagePhys_View.setCurrentIndex(4)
            self.changeView()

    def clearRatioImage(self):
        self.ratioImage = None
        self.dataState['ratioLoaded'] = False
        self.useRatio = False
        self.ctrl.ImagePhys_View.setCurrentIndex(0)
        self.changeView()
            
    def getDataStruct(self):
        ds = self.ctrl.ImagePhys_DataStruct.currentIndex()
        if ds == 0:
            self.dataStruct = 'flat'
        else:
            self.dataStruct = 'interleaved'
        self.ignoreFirst = self.ctrl.ImagePhys_ignoreFirst.value()
        lpf = self.ctrlPhysFunc.ImagePhys_PhysLPF.value()
        if lpf == 0.0:
            self.physLPF = 0.0
        else:
            self.physLPF = lpf
        #print "data struct = %s" % self.dataStruct
        #print "ignore First: ", self.ignoreFirst
        #print "lpf: %8.1f" % self.physLPF

    def physLPF_valueChanged(self):
        self.physLPFChanged = True  # just note that it has changed
    
    def doNormalize(self):
        method = self.ctrl.ImagePhys_ImgMethod.currentIndex()
        if method == 0:  # (F-Fo)/Fo # referenced to a baseline of the first image
            self.StandarddFFImage()
        if method == 1: # reference to a baseline of images over a time window
            self.StandarddFFImage(baseline=True)
        if method == 2:
            self.MediandFFImage()  # Referenced to median of each image
        if method == 3:
            self.normalizeImage()  # another normalization
        if method == 4:
            self.slowFilterImage()  # slow filtering normalization: (F-Fslow)/Fslow on pixel basis over time
        print('normalize method: ', method)
        print(self.dataState['ratioLoaded'])
        print(self.useRatio)
        if method == 4:  # g/r ratio  - future: requires image to be loaded (hooks in place, no code yet)
            if self.dataState['ratioLoaded'] and self.useRatio:
                self.GRFFImage() # convert using the ratio
                
        self.updateAvgStdImage()
        self.calculateAllROIs()
        
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
#        xsize = image_sh[1]
#        ysize = image_sh[2]
        print('Writing tiff images to %s\n' % (tiffpath))
        #print dir(Image.Image)
        for i in range(0, nframes):
            ai = Image.Image.fromarray(self.imageData[i, :, :]*8192.0)
            fn = tiffpath + 'acq4_ImageAnalysis_%05d.tiff' % (i)
            ai.save(fn)
#
#---------baseline correction routines --------------------
#
    def Baseline0(self, roi=None):
        if roi is None:
            lrois = range(0, self.nROI)
        else:
            lrois = [roi]
        t0 = self.ctrlROIFunc.ImagePhys_BaseStart.value()
        t1 = self.ctrlROIFunc.ImagePhys_BaseEnd.value()
        dt = np.mean(np.diff(self.imageTimes))
        it0 = int(t0/dt)
        it1 = int(t1/dt)
        for roi in lrois:
            bl = np.mean(self.FData[roi.ID][it0:it1])
            self.BFData[roi.ID] /= bl
                
    def Baseline1(self, roi=None):       
    ### data correction routine to smooth out the baseline
    ###
        self.FilterKernel = 11
        self.FilterOrder = 3
        thr = 2.0 # self.ui.CorrTool_Threshold.value()
        dds = self.BFData[:,0:-1].copy()
        if roi is None:
            lrois = range(0, self.nROI)
        else:
            lrois = [roi]
        for roi in lrois:
            d = self.BFData[roi.ID].copy().T
            ds = Utility.savitzky_golay(d, kernel=31, order=5) # smooth data
            dds[roi.ID] = np.diff(ds) # take derivative of smoothed data
            stdev = np.std(dds[roi.ID])
            pts = np.where(np.abs(dds[roi.ID]) < thr*stdev) # get subset of points to fit
            dds2 = np.diff(np.diff(ds))
            stdev2 = np.std(dds2)
            pts2 = np.where(np.abs(dds2) < thr*stdev2)
            s0 = set(np.transpose(pts).flat)
            s1 = set(np.transpose(pts2).flat)
            ptsok = list(s1.intersection(s0))

            if len(ptsok) == 0:
                return
            tf = self.imageTimes[ptsok]
            df = d[ptsok]
            p = np.polyfit(tf, df, 5)
            bd = np.polyval(p, self.imageTimes)
#            dm = np.mean(d[0:10])
            bl = Utility.savitzky_golay(d/bd, kernel=self.FilterKernel,
                                                      order=self.FilterOrder)
            self.BFData[roi.ID] = bl
        return(self.BFData)
            #self.FData[roi, :] = self.BFData[roi,:]
            #self.plotdata(self.times, 100*(self.BFData-1.0), datacolor = 'blue', erase = True,
            #          background = False, scaleReset=False, yMinorTicks=0, yMajorTicks=3,
            #          yLabel = u'\u0394F/F<sub>ROI %d</sub>')
       # self.makeROIDataFigure(clear=False, gcolor='g')

    def SignalBPF(self, roi):
        """ data correction
        try to decrease baseline drift by high-pass filtering the data.
        """
        #self.BFData = np.array(self.FData).copy()
        HPF = self.ctrlROIFunc.ImagePhys_ImgHPF.value()
        LPF = self.ctrlROIFunc.ImagePhys_ImgLPF.value()  # 100.0
        if LPF < 4.0*HPF:
            print("please make lpf/hpf further apart in frequency")
            return
        dt = np.mean(np.diff(self.imageTimes))
        samplefreq = 1.0/dt
        if (LPF > 0.5*samplefreq):
            LPF = 0.5*samplefreq
        d = self.BFData[roi.ID].copy().T
        return(Utility.SignalFilter(d, LPF, HPF, samplefreq))

    def SignalHPF(self, roi): 
        """ data correction
        try to decrease baseline drift by high-pass filtering the data.
        """
        HPF = self.ctrlROIFunc.ImagePhys_ImgHPF.value()
        dt = np.mean(np.diff(self.imageTimes))
        samplefreq = 1.0/dt
        d = self.BFData[roi.ID].copy().T
        return(Utility.SignalFilter_HPFButter(d, HPF, samplefreq))

    def SignalLPF(self, roi): 
        """ data correction
        Low-pass filter the data.
        """
        LPF = self.ctrlROIFunc.ImagePhys_ImgLPF.value() # 100.0
        dt = np.mean(np.diff(self.imageTimes))
        samplefreq = 1.0/dt
        if (LPF > 0.5*samplefreq):
            LPF = 0.5*samplefreq
        d = self.BFData[roi.ID].copy().T
        return(Utility.SignalFilter_LPFButter(d, LPF, samplefreq))
        
#
# detect spikes in physiology trace
#
    def showPhysTrigger(self):
        thr = self.ctrlPhysFunc.ImagePhys_PhysThresh.value()
        if self.physThreshLine is None:
            self.physThreshLine = self.physPlot.plot(x=np.array([self.tdat[0], self.tdat[-1]]),
                y=np.array([thr, thr]), pen=pg.mkPen('r'), clear=False)
        else:
            self.physThreshLine.setData(x=np.array([self.tdat[0], self.tdat[-1]]), 
                y=np.array([thr, thr]))

    def detectSpikes(self, burstMark=None):
        spikescale = 1.0  # or 1e-12...
        thr = spikescale*self.ctrlPhysFunc.ImagePhys_PhysThresh.value()
        if thr < 0:
            ysign = -1.0
        else:
            ysign = 1.0
        (sptimes, sppts) = Utility.findspikes(self.tdat, ysign*self.physData, np.abs(thr)*spikescale, t0=None, t1=None,
                                              dt=1.0/self.samplefreq, mode='peak', interpolate=False, debug=False)
        self.SpikeTimes = sptimes
        if len(sptimes) <= 1:
            return
        yspmarks = thr*spikescale
        bList = self.defineSpikeBursts()
        self.burstTimes = bList
        yburstMarks = thr*0.9*spikescale
        ywithinBurstMarks = thr*0.8*spikescale
        self.makeSpikePointers(spikes=(sptimes, yspmarks), spikespk=(sptimes, self.physData[sppts]),
            bursts = (bList, yburstMarks, ywithinBurstMarks))
        print('spikes detected: %d' % (len(sptimes)))

    def makeSpikePointers(self, spikes=None, spikespk=None, bursts=None):
        # add scatterplot items to physiology trace  - these start out empty, but we can replace
        # the points in the arrays later.
        if spikes is not None and len(spikes[0]) > 0:
            if self.spikesFound is None:
                    self.spikesFound = pg.ScatterPlotItem(size=6, pen=pg.mkPen('g'), brush=pg.mkBrush(0, 255, 0, 200), 
                    symbol = 't', identical=True)
                    #self.clearPhysiologyInfosetPoints(x=[], y=spikes[1])
                    self.physPlot.addItem(self.spikesFound)
            else:
                self.spikesFound.setPoints(x=spikes[0], y=spikes[1]*np.ones(len(spikes[0])))
            
        if spikespk is not None and len(spikespk[0]) > 0:
            if self.spikesFoundpk is None:
                self.spikesFoundpk = pg.ScatterPlotItem(size=4, pen=pg.mkPen('r'), brush=pg.mkBrush(0, 255, 0, 200), 
                    symbol = 'o', identical=True)
                #self.spikesFoundpk.setPoints(x=spikespk[0], y=spikespk[1])
                self.physPlot.addItem(self.spikesFoundpk)
            else:
                self.spikesFoundpk.setPoints(x=spikespk[0], y=spikespk[1]*np.ones(len(spikespk[0])))
            
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
        The following criteria are available to select from within the spike train:
        1. minimum time before a spike
        2. minimum rate AFTER the spike (for the next N spikes)
        3. minimum # of spikes (N) for minimum rate determination (define burst)
        """
        if not singleSpike: # normal processing is to do bursts, using first spike of burst
            if self.burstTimes == []:
                bList = self.defineSpikeBursts()
                self.burstTimes = bList
            onsetSpikes = []
            burstSpikes = []
            bList = self.burstTimes
            for b in range(len(bList)):
                bdat = bList[b]
                onsetSpikes.append(bdat[0])
                burstSpikes.extend(bdat[1:].tolist())
            plotTitle = 'Burst-Onset-Triggered Fluorescence'
        else:  # but we can also handle just regular spike trains...
            onsetSpikes = self.SpikeTimes
            plotTitle = 'All-Spikes-Triggered Fluorescence'
        self.calculateAllROIs()
        N = len(onsetSpikes)
        avCaF = [[0]*N for i in range(self.nROI)]
        avCaT = [[0]*N for i in range(self.nROI)]

        for roi in range(0, self.nROI):
            i = 0
            for onSp in onsetSpikes:
                (x, y) = Utility.clipdata(self.FData[roi], self.imageTimes, onSp-0.1, onSp+0.5)
                avCaF[roi][i] = y
                avCaT[roi][i] = (x.tolist()-onSp)
                i = i + 1
        self.checkMPL()
        (self.MPLFig, self.MPL_plots) = PL.subplots(num="Image Analysis", nrows=self.nROI+1, ncols=2,
                                                    sharex=False, sharey=False)
        self.MPLFig.suptitle('%s:\n %s' % (plotTitle, self.currentFileName), fontsize=11)
        dt = np.mean(np.diff(self.imageTimes))/2.
        tbase = np.arange(-0.1, 0.5, dt)
        axmin = 1e6
        axmax = -1e6
        ave = [[]]*self.nROI
        std = [[]]*self.nROI
        CaAmin = 1e6
        CaAmax = -1e6
        for roi in range(0, self.nROI):
            self.MPL_plots[self.nROI][0].plot(self.imageTimes, self.BFData[roi])
            interCaF = np.zeros((N, len(tbase)))
            for i in range(0, len(onsetSpikes)):
            #sp = self.MPL_plots.scatter(avCaT, avCaF, s=15, color='tomato')
                self.MPL_plots[roi][0].plot(avCaT[roi][i], avCaF[roi][i]*100., color='k', linestyle='-')
                f_int = scipy.interpolate.interp1d(avCaT[roi][i], avCaF[roi][i]*100., bounds_error=False)
                interCaF[i, :] = f_int(tbase)
                CaAmin = np.nanmin([np.nanmin(avCaF[roi][i]), CaAmin])
                CaAmax = np.nanmax([np.nanmax(avCaF[roi][i]), CaAmax])
            #    self.MPL_plots[roi][1].plot(tbase, interCaF[roi,i,:], 'r')
            ave[roi] = scipy.stats.nanmean(interCaF, axis=0)
            std[roi] = scipy.stats.nanstd(interCaF, axis=0)
            self.MPL_plots[roi][1].errorbar(tbase, ave[roi]*100., yerr=std[roi]*100., color='r')
            self.MPL_plots[roi][0].set_xlabel('T (sec)')
            self.MPL_plots[roi][0].set_ylabel('dF/F (%)')
            axmin = np.nanmin([np.nanmin(ave[roi]-std[roi]), axmin])
            axmax = np.nanmax([np.nanmax(ave[roi]+std[roi]), axmax])
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
        isis = np.diff(self.SpikeTimes)
        burstOnsetCandidates = np.where(isis > minTime)[0].tolist()
        burstOnsetCandidates = [x + 1 for x in burstOnsetCandidates] 
        # those are candidate events...
        allBurstList = []
        burstOnsetList = []
        for i in burstOnsetCandidates:
            tempWithinBurst = [i]  # list of spike times that follow this one
            for j in range(i, len(self.SpikeTimes)-1):
                if isis[j] <= maxInterval:  # if interspike interval is long, we terminate
                    tempWithinBurst.append(j+1)  # keep track of spikes that are "within" a burst
                else:  # if isi is too long, terminate burst
                    break
            if len(tempWithinBurst) >= (minNspikes-1) and i not in burstOnsetList:  # note, tempWithinBurst does not include the first spike.
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
            self.ROIDistances()  # make sure we ahve valid distance information

        if self.IXC_Strength == []:
            self.Analog_Xcorr_Individual(plottype=None)
        threshold = self.ctrlImageFunc.IAFuncs_XCorrThreshold.value()
        x0 = np.nanmin(np.nanmin(self.ROIDistanceMap))
        x1 = np.nanmax(np.nanmax(self.ROIDistanceMap))
        thrliney = [threshold, threshold]
        nthrliney = [-threshold, -threshold]
        thrlinex = [x0, x1]
        self.use_MPL = self.ctrlImageFunc.IAFuncs_MatplotlibCheckBox.checkState()
        mean = scipy.stats.nanmean(self.IXC_Strength.flatten())
        std = scipy.stats.nanstd(self.IXC_Strength.flatten())
        print('Mean XC: %f   std: %f' % (mean, std))
        if self.use_MPL:
            self.checkMPL()
            (self.MPLFig, self.MPL_plots) = PL.subplots(num="Image Analysis", nrows=1, ncols=1,
                    sharex = True, sharey = True)
            self.MPLFig.suptitle('Analog XCorr: %s' % self.currentFileName, fontsize=11)
            self.MPL_plots.scatter(self.ROIDistanceMap, self.IXC_Strength, s=15, color='tomato')
            self.MPL_plots.plot(thrlinex, thrliney)
            self.MPL_plots.set_xlabel('Distance (%s)' % self.imageScaleUnit)
            self.MPL_plots.set_ylabel('Correlation (R)')
            self.MPL_plots.set_ylim((-1,1))
            PL.show()
        else:
            self.floatingDistWin = pyqtgrwindow(title = 'ROI Distance Strength')
            self.floatingDistWin.setWindowTitle('ROI Distance Strength: %s' % self.currentFileName)
            self.floatingDistWin.layout.clear()
            self.floatingDistWin.layout.setWindowTitle("New Title?")
            s1 = pg.ScatterPlotItem(size=7, pen=pg.mkPen(None), brush=pg.mkBrush(255, 0, 0, 255))
            X = np.reshape(self.ROIDistanceMap, -1)
            X = X[~np.isnan(X)]
            Y = np.reshape(self.IXC_Strength, -1)
            Y = Y[~np.isnan(Y)]
            p = self.floatingDistWin.layout.addPlot(0,0)
            s1.addPoints(X, Y)
            p.addItem(s1)
            p.plot(thrlinex, thrliney, pen=pg.mkPen(width=0.75, color='c'))
            p.plot(thrlinex, nthrliney, pen=pg.mkPen(width=0.75, color='c'))
            p.setLabel('bottom', 'Distance (%s)' % self.imageScaleUnit)
            p.setLabel('left', 'Correlation (R)')
            p.setYRange(-1, 1)
            (xm, xn) = self._calcMinMax(X)
            p.setXRange(0., xn);

    def _calcMinMax(self, x, p=0.05):
        '''
        Compute initial min and max axis scaling points.
        Approach:
        a) with buffer:
           reserve a fraction p of the total span of an axis as buffer and
           round to next order of magnitude
        b) strict (p==0):
           just round to the next order of magnitude
        Special cases:
        x_min==x_max : assign symmetric interval or [0,1], if zero.
        From:
        F. Oliver Gathmann (gathmann@scar.utoronto.ca)
        Surface and Groundwater Ecology Research Group
        University of Toronto
        phone: (416) - 287 7420 ; fax: (416) - 287 7423
        web: http://www.scar.utoronto.ca/~gathmann

        '''
        if len(x) > 0:             # not an empty array passed
            x_max, x_min = np.maximum.reduce(x),np.minimum.reduce(x)
            if x_min != x_max:   # esp. not both x_min,x_max equal to zero
                span = x_max - x_min
                buffer = p * span
                if x_min-buffer > 0:    # both (x_min-buffer),(x_max+buffer) > 0
                    x_min = round(x_min - buffer, -int((np.floor(np.log10(buffer) - 1))))
                    x_max = round(x_max + buffer, -int((np.ceil(np.log10(buffer) - 1))))
                elif x_max+buffer < 0:  # both (x_min-buffer),(x_max+buffer) < 0
                    x_min = round(x_min - buffer, -int((np.ceil(np.log10(buffer) - 1))))
                    x_max = round(x_max + buffer, -int((np.floor(np.log10(buffer) - 1))))
                else:  # (x_min-buffer </= 0)and(x_max+buffer >/= 0)
                    try:
                        x_min = round(x_min - buffer, -int((np.ceil(np.log10(buffer) - 1))))
                    except OverflowError:  # buffer == 0
                        x_min = 0
                    try:
                        x_max = round(x_max + buffer, -int((np.ceil(np.log10(buffer) - 1))))
                    except OverflowError:  # buffer == 0
                        x_max = 0
            else:
                if x_min != 0:
                    x_min = x_min - x_min/2.0
                    x_max = x_max + x_max/2.0
                else:
                    x_min = 0
                    x_max = 1
        else:
            x_min = 0
            x_max = 1
        return x_min,x_max


    def printDistStrength(self):
        print('\n\n----------------------------------\nROI Distance Map\nFile: %s  '% self.currentFileName)
        print('roi1\troi2\td (um)\t R')
        sh = self.ROIDistanceMap.shape
        for i in range(0, sh[0]):
            for j in range(i+1, sh[1]):
                print('%d\t%d\t%8.0f\t%6.3f' % (i, j, self.ROIDistanceMap[i, j], self.IXC_Strength[i, j]))
        print('-------------------------------\n')

    def NetworkGraph(self):
        """
        Create a graph showing the network. Each node is an ROI, and the lines connecting
        the nodes have a thickness that corresponds to the strength of the cross correlation.
        """
        if self.ROIDistanceMap == []:
            self.ROIDistances()  # make sure we ahve valid distance information
        if self.IXC_Strength == []:
            self.Analog_Xcorr_Individual(plottype=None)

        self.use_MPL = self.ctrlImageFunc.IAFuncs_MatplotlibCheckBox.checkState()

        if self.use_MPL:
            self.checkMPL()
            (self.MPLFig, self.MPL_plots) = PL.subplots(num="Network Graph", nrows=1, ncols=1,
                        sharex=True, sharey=True)
            self.MPLFig.suptitle('Network Graph: %s' % self.currentFileName, fontsize=11)
            yFlip_flag = False
        else:
            self.floatingDistWin = pyqtgrwindow(title = 'Network Graph')
            self.floatingDistWin.setWindowTitle('Network Graph: %s' % self.currentFileName)
            self.floatingDistWin.layout.clear()
            self.floatingDistWin.layout.setWindowTitle("Network Graph?")
            plt = self.floatingDistWin.layout.addPlot(0,0)
            yFlip_flag = True

        (sx, sy, px) = self.getImageScaling()
        maxStr = np.abs(np.nanmax(self.IXC_Strength))
#        minStr = np.nanmin(self.IXC_Strength)
        maxline = 4.0
        minline = 0.20
        threshold = self.ctrlImageFunc.IAFuncs_XCorrThreshold.value()
        nd = len(self.AllRois)
        X = np.zeros(nd)
        Y = np.zeros(nd)
        for i in range(0, nd):
            wpos1 = [self.AllRois[i].pos().x(), self.AllRois[i].pos().y(),
                            self.AllRois[i].boundingRect().width(), self.AllRois[i].boundingRect().height()]
            x1 = (wpos1[0]+0.5*wpos1[2])*px[0]
            y1 = (wpos1[1]+0.5*wpos1[3])*px[1]
            if yFlip_flag:
                y1 = sy - y1
            X[i] = x1
            Y[i] = y1
            for j in range(i+1, nd):
                wpos2 = [self.AllRois[j].pos().x(), self.AllRois[j].pos().y(),
                            self.AllRois[j].boundingRect().width(), self.AllRois[j].boundingRect().height()]
                x2 = (wpos2[0]+0.5*wpos2[2])*px[0]
                y2 = (wpos2[1]+0.5*wpos2[3])*px[1]
                if yFlip_flag:
                    y2 = sy-y2
                if np.abs(self.IXC_Strength[i,j]) < threshold:
                    pass
                    # if self.use_MPL:
                    #     self.MPL_plots.plot([x1, x2], [y1, y2],
                    #         linestyle = '--', color='grey', marker='o', linewidth=minline)
                    # else:
                    #     pn = pg.mkPen(width=minline, color=[128, 128, 128, 192], style=Qt.Qt.DashLine)
                    #     plt.plot([x1, x2], [y1, y2], pen = pn)
                else:
                    lw = maxline*(abs(self.IXC_Strength[i, j])-threshold)/(maxStr-threshold)+minline
                    if self.IXC_Strength[i, j] >= threshold:
                        pn = pg.mkPen(width=lw, color=[255, 128, 128, 255])
                        mcolor = 'tomato'
                    else:  # self.IXC_Strength[i,j] <= threshold:
                        pn = pg.mkPen(width=lw, color=[128, 128, 255, 255])
                        mcolor = 'blue'

                    if self.use_MPL:
                        self.MPL_plots.plot([x1, x2], [y1, y2], linewidth=lw,
                            linestyle='-', color=mcolor, marker='o')
                    else:
                        plt.plot([x1, x2], [y1, y2], pen=pn)

        if self.use_MPL:
            self.MPL_plots.set_xlim((0, sx))
            self.MPL_plots.set_ylim((sy, 0))
            self.MPL_plots.set_xlabel('X (%s)' % self.imageScaleUnit)
            self.MPL_plots.set_ylabel('Y (%s)' % self.imageScaleUnit)
            PL.show()
        else:
            s1 = pg.ScatterPlotItem(size=7, pen=pg.mkPen(None), brush=pg.mkBrush(255, 0, 0, 255))
            s1.addPoints(X, Y)
            plt.addItem(s1)
            plt.setLabel('bottom', 'X (%s)' % self.imageScaleUnit)
            plt.setLabel('left', 'Y (%s)' % self.imageScaleUnit)
            plt.setXRange(0., sx)
            plt.setYRange(0., sy)

    #--------------- From PyImageAnalysis3.py: -----------------------------
    #---------------- ROI routines on Images  ------------------------------

    def clearAllROI(self):
        """ remove all rois and all references to the rois """
        for i, roi in enumerate(self.AllRois):
            roi.hide()

        self.AllRois = []
        self.nROI = 0
        self.FData = []  # FData is the raw ROI data before any corrections
        self.BFData = []  # ROI data after all corrections
        self.lastROITouched = []
        self.ROI_Plot.clear()
        #self.clearPlots()

    def deleteLastTouchedROI(self):
        """ remove the currently (last) selected roi and all references to it,
        then select and display a new ROI """
        ourWidget = self.lastROITouched
        if ourWidget not in self.AllRois:
            raise Exception("Delete ROI - Error: Last ROI was not in ROI list?")
        id = ourWidget.ID  # get the id of the roi
        self.AllRois.remove(ourWidget)  # remove it from our list
        ourWidget.hide()
        del ourWidget
        self.nROI = len(self.AllRois)
        for roi in self.AllRois:
            roi.ID = self.AllRois.index(roi)  # renumber the roi list.
        if id < 0:
            id = self.AllRois[0].ID  # pick first
        if id > self.nROI:
            id = self.AllRois[-1].ID  # pick last
        self.FData = []
        self.BFData = []
        for roi in self.AllRois:  # navigate the list one more time
            if id == roi.ID:
                self.updateThisROI(roi)  # display the next chosen ROI in the box below the image
        # now update the overall ROI plot
        self.plotdata(yMinorTicks=0, yMajorTicks=3,
                      yLabel=u'F0<sub>ROI %d</sub>')

    def addOneROI(self, pos=(0, 0), hw=None):
        """
        append one roi to the self.AllRois list, put it on the screen (scene), and
        make sure it is actively connected to code.
        :param pos:  Initial roi posistion (tuple, (x, y))
        :param hw:  Initial ROI height and position (tuple (h,w)). If not defined, will get from current roi default
        :return: The roi handle is returned.
        """
        if hw is None:
            dr = self.ctrlROIFunc.ImagePhys_ROISize.value()
            hw = [dr, dr]
        roi = pg.RectROI(pos, hw, scaleSnap=True, translateSnap=True)
        roi.addRotateHandle(pos=(0, 0), center=(0.5, 0.5))  # handle at left top, rotation about center
#       roi = qtgraph.widgets.EllipseROI(pos, hw, scaleSnap=True, translateSnap=True)
#       roi = qtgraph.widgets.MultiLineROI([[0,0], [5,5], [10,10]], 3, scaleSnap=True, translateSnap=True)
        roi.ID = self.nROI  # give each ROI a unique identification number
        rgb = self.RGB[self.nROI]
        self.nROI = self.nROI + 1
        roi.setPen(Qt.QPen(Qt.QColor(rgb[0], rgb[1], rgb[2])))
        roi.color = rgb
        self.AllRois.append(roi)
        self.imageView.addItem(roi)
        self.updateThisROI(self.AllRois[-1])  # compute the new ROI data
        roi.sigRegionChanged.connect(self.updateThisROI)  # if data region changes, update the information
        roi.sigHoverEvent.connect(self.showThisROI)  # a hover just causes the display below to show what is hre already.
        return (roi)

    # def plotImageROIs(self, ourWidget):
    #     """ plots a single ROIs in the image - as an initial instantiation.
    #     """
    #     if ourWidget in self.AllRois: # must be in the list of our rois - ignore other widgets
    #         tr = ourWidget.getArrayRegion(self.imageData, self.imageItem, axes=(1,2))
    #         tr = tr.mean(axis=2).mean(axis=1) # compute average over the ROI against time
    #         if self.datatype == 'int16':
    #             tr = tr / ourWidget.getArrayRegion(self.im_filt, self.imageItem, axes=(0,1)).mean(axis=1).mean(axis=0)
    #         sh = np.shape(self.FData)
    #         if sh[0] is 0:
    #             self.FData = atleast_2d(tr) # create a new trace in this place
    #             #sh = shape(self.FData)
    #         if sh[0] > ourWidget.ID: # did we move an existing widget?
    #             self.FData[ourWidget.ID,:] = np.array(tr) # then replace the trace
    #         else: # the widget is not in the list yet...
    #             self.FData = append(self.FData, atleast_2d(tr), 0)
    #         self.plotdata(roiUpdate=[ourWidget.ID], showplot=False, datacolor = ourWidget.color)

    # def roiChanged(self, roi):
    #     if isinstance(roi, int):
    #         roi = self.currentRoi
    #     if roi is None:
    #         return
    #     self.ROI_Plot.clearPlots()
    #     lineScans = []
    #     for imgSet in self.imageData:
    #         data = roi.getArrayRegion(imgSet['procMean'], self.imageItem, axes=(1,2))
    #         m = data.mean(axis=1).mean(axis=1)
    #         lineScans.append(data.mean(axis=2))
    #         spacer = np.empty((lineScans[-1].shape[0], 1), dtype = lineScans[-1].dtype)
    #         spacer[:] = lineScans[-1].min()
    #         lineScans.append(spacer)
    #         data = roi.getArrayRegion(imgSet['procStd'], self.imageItem, axes=(1,2))
    #         s = data.mean(axis=1).mean(axis=1)
    #         self.ROI_Plot.plot(m, pen=pg.hsvColor(c*0.2, 1.0, 1.0))
    #         self.ROI_Plot.plot(m-s, pen=pg.hsvColor(c*0.2, 1.0, 0.4))
    #         self.ROI_Plot.plot(m+s, pen=pg.hsvColor(c*0.2, 1.0, 0.4))
    #
    #     lineScan = np.hstack(lineScans)
    #     self.getElement('Line Scan').setImage(lineScan)
    #     self.currentRoi = roi

    def updateThisROI(self, roi, livePlot=True):
        """
        called when we need to update the ROI result plot for a particular ROI widget
        :param roi: handle to the ROI
        :param livePlot: flag for live plotting, passed to showThisROI
        """
        if roi in self.AllRois:
            tr = roi.getArrayRegion(self.imageData, self.imageView.imageItem, axes=(1, 2))
            tr = tr.mean(axis=2).mean(axis=1)  # compute average over the ROI against time
#            trx = tr.copy()
            if self.dataState['Normalized'] is False:
#                trm = tr.mean()  # mean value across all time
                tr = tr/tr.mean()  # (self.background[0:tr.shape[0]]*trm/self.backgroundmean)

            self.FData = self.insertFData(self.FData, tr.copy(), roi)
            self.applyROIFilters(roi)
            self.showThisROI(roi, livePlot)
            return(tr)

    def scannerTimes(self, roi):
        """
        compute mean time over the roi from the scanned time information estimates
        :params: roi - the roi information
        :returns: time array with mean roi collection time offset + base image time
        """
        tr = roi.getArrayRegion(self.scanTimes, self.imageView.imageItem, axes=(0, 1))
        tr = tr.mean(axis=1).mean(axis=0)  # compute average over the ROI against time
        times = self.imageTimes[0:len(self.BFData[roi.ID])] + tr
#        print tr
        return times

    def showThisROI(self, roi, livePlot=True):
        """
        Show one ROI, highlighting it and brining it to the top of the traces
        other rois are dimmed and thinned
        If the plot of the roi does not exist, the plot is
        :param roi: the handle to the selected ROI
        :param livePlot: flag to allow update of plot in real time (if livePlot is not set, the roi
            may not be created at this time.  (is this ever used?)
        :return: Nothing
        """
        if roi in self.AllRois:
            if livePlot is True:
                if self.imageType == 'camera':
                    times = self.imageTimes[0:len(self.BFData[roi.ID])]
                elif self.imageType in ['imaging', 'PMT']:
                    times = self.scannerTimes(roi)
                else:
                    raise ValueError('Image type for time array not known: %s', self.imageType)
                try:
                    roi.plot.setData(times, self.BFData[roi.ID],
                                     pen=pg.mkPen(np.append(roi.color[0:3], 255), width=1.0))  #, pen=pg.mkPen(roi.color), clear=True)
                except:
                    roi.plot = self.ROI_Plot.plot(times, self.BFData[roi.ID],
                                                  pen=pg.mkPen(np.append(roi.color[0:3], 255), width=1.0), clear=False)  # pg.mkPen('r'), clear=True)
                c = np.append(roi.color[0:3], 255)
                roi.plot.setPen(pg.mkPen(color=c, width=2.0))
                roi.plot.setZValue(1000)
                roi.show()  # make sure the roi is visible

        for otherroi in self.AllRois:
            if otherroi != roi:
                c = np.append(otherroi.color[0:3], 128)
                otherroi.plot.setPen(pg.mkPen(color=c, width=1.0))
                otherroi.plot.setZValue(500)

    def markROITouched(self, roi):
        """
        Highlight the last touched ROI in the field
        """
        if self.lastROITouched == []:
            self.lastROITouched = roi
            roi.pen.setWidth(0.18) # just bump up the width
        if roi != self.lastROITouched:
            self.lastROITouched.pen.setWidth(0.18)
            roi.pen.setWidthF(0.12)
            self.lastROITouched = roi # save the most recent one

    def calculateAllROIs(self):
        """
        calculateAllROIs forces a fresh recalculation of all ROI values from the current image
        """
        self.FData = []
        self.BFData = []

        currentROI = self.lastROITouched
        for ourWidget in self.AllRois:
            tr = self.updateThisROI(ourWidget, livePlot=False)
            self.FData = self.insertFData(self.FData, tr, ourWidget)
        self.applyROIFilters(self.AllRois)
        self.updateThisROI(currentROI) # just update the latest plot with the new format.

    def refilterCurrentROI(self):
        """
        calculateCurrentROI forces a fresh recalculation of the most recently touched ROI
        """
        roi = self.lastROITouched
        if roi in self.AllRois:
            self.applyROIFilters(roi)
            self.ROI_Plot.plot(self.imageTimes, self.BFData[roi.ID], pen=pg.mkPen('r'), clear=True)

    def insertFData(self, FData, tr, roi):
        sh = np.shape(FData)
        if sh[0] == 0:
            FData = np.atleast_2d(tr)  # create a new trace in this place
        if sh[0] > roi.ID:  # did we move an existing widget?
            FData[roi.ID] = np.array(tr)  # then replace the trace
        else:  # the widget is not in the list yet...
            FData = np.append(FData, np.atleast_2d(tr), 0)
        return(FData)

    def applyROIFilters(self, rois):
        """
        If checked, apply LPF, HPF, and baseline corrections to the resulting ROI data
        """
        if type(rois) is not list:
            rois = [rois]
#        try:
#            l = len(self.BFData)
#        except:
#            self.BFData = []
        for roi in rois:
            self.BFData = self.insertFData(self.BFData, self.FData[roi.ID], roi) # replace current data with raw data
            if self.ctrl.ImagePhys_CorrTool_BL1.isChecked():
                bl = self.Baseline1(roi)
                self.BFData = self.insertFData(self.BFData, bl, roi)
            if self.ctrlROIFunc.ImagePhys_CorrTool_LPF.isChecked() and self.ctrlROIFunc.ImagePhys_CorrTool_HPF.isChecked():
                bpf = self.SignalBPF(roi)
                self.BFData = self.insertFData(self.BFData, bpf, roi)

            else:
                if self.ctrlROIFunc.ImagePhys_CorrTool_LPF.isChecked():
                    lpf = self.SignalLPF(roi)
                    self.BFData = self.insertFData(self.BFData, lpf, roi)
                if self.ctrlROIFunc.ImagePhys_CorrTool_HPF.isChecked():
                    hpf = self.SignalHPF(roi)
                    self.BFData = self.insertFData(self.BFData, hpf, roi)

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
            #(tr_test, trDither) = self.__measDither(ditherMode, ourWidget)
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
                        tr = trDither  # save peak signal
            ourWidget.setPos([tr_X, tr_Y])
 #           if livePlot:
 #               MPlots.updatePlot(self.ui.liveROIPlot, range(0, np.shape(tr)[0]), tr, 'liveROI',
 #                                 color=self.RGB[ourWidget.ID-1])

    def __measDither(self, ditherMode, ourWidget):
        """Compute the value that we are optimizing for the dithering."""
        trDither = ourWidget.getArrayRegion(self.normData[0], self.imageItem, axes=(1,2))
        trDither = trDither.mean(axis=2).mean(axis=1)  # compute average over the ROI against time
        if ditherMode is 0:  # peak to peak
            tr_test = np.amax(trDither) - np.amin(trDither)
        elif ditherMode is 1:  # baseline to peak
            tr_test = np.amax(trDither)
        elif ditherMode is 2:  # standard deviation
            tr_test = np.std(trDither)
        else:
            tr_test = 0.
        return(tr_test, trDither)

    def ROIDistances(self):
        """
        measure the distances between all possible pairs of ROIs, store result in matrix...
        The distances are scaled into microns or pixels.
        """
        print('Calculating ROI to ROI distances')
        nd = len(self.AllRois)
        self.ROIDistanceMap = np.empty((nd, nd))  # could go sparse, but this is simple...
        self.ROIDistanceMap.fill(np.nan)
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
                self.ROIDistanceMap[i,j] = np.sqrt((x1-x2)**2+(y1-y2)**2)

    def newpgImageWindow(self, title='', border='w'):
        newWin = pyqtgrwindow(title=title)
        view = pg.GraphicsView()
        newWin.setCentralWidget(view)
        newWin.show()
        img = pg.ImageItem(border=border)
        view.scene().addItem(img)
        view.setRange(Qt.QRectF(0, 0, 500, 500))
        return(newWin, view, img)

    def saveROI(self, fileName=None):
        """Save the ROI information (locations) to a disk file."""
        self.calculateAllROIs()
        if self.FData == []:
            print('self.FData is empty!')
            return
        sh = np.shape(self.FData)
        data = np.empty((sh[0]+2, sh[1]))
        data[0] = np.arange(0,sh[1])
        data[1] = self.imageTimes.copy()

        roiData = []
        for i in range(0, sh[0]):
            data[i+2] = self.FData[i]
            roiData.append([self.AllRois[i].pos().x(), self.AllRois[i].pos().y(),
                            self.AllRois[i].boundingRect().height(), self.AllRois[i].boundingRect().width()])
        data = data.T ## transpose
        if fileName is None or fileName is False:
            fileName= Qt.QFileDialog.getSaveFileName(None, "Save ROI as csv file", "",
                self.tr("CSV Files (*.csv)"))
            if not fileName:
                return
        (fnc, extc) = os.path.splitext(fileName)
        fName = fnc + '.csv'
        fd = open(fName, 'w')
        stringVals=''
        for col in range(0, data.shape[1]): # write a header for our formatting.
            if col is 0:
                fd.write('time(index),')
            elif col is 1:
                fd.write('time(sec),')
        stringVals = ['R%03d' % x for x in range(0, data.shape[1]-2)]
        fd.write(",".join(stringVals) + "\n")
        for row in range(0, data.shape[0]):
            stringVals = ["%f" % x for x in data[row]]
            fd.write(",".join(stringVals) + "\n")
    #        print 'Wrote: %s\n' % (fName)
        fd.close()
        (fnc, extc) = os.path.splitext(fileName)
        fName = fnc + '.roi'
        fd = open(fName, 'w')
        for rd in roiData:
            fd.write(' '.join(map(str, rd)) + '\n')
    #        print 'Wrote: %s\n' % fName
        fd.close()

    def restoreROI(self, fileName=None):
        """Retrieve the ROI locations from a file, plot them on the image, and compute the traces."""
        self.clearAllROI()  # always start with a clean slate.
        if fileName is False or fileName is None:
            fileName = Qt.QFileDialog.getOpenFileName(None, u'Retrieve ROI data', u'', u'ROIs (*.roi)')
        if fileName:
            fd = open(fileName, 'r')
            for line in fd:
                roixy = np.fromstring(line, sep=' ')
                self.addOneROI(pos=[roixy[0], roixy[1]], hw=[roixy[2], roixy[3]])
            fd.close()
            self.calculateAllROIs()
        #self.makeROIDataFigure(clear=True)

    def makeROIDataFigure(self, clear = True, gcolor = 'k'):
        self.checkMPL()
        (self.MPLFig, self.MPL_plots) = PL.subplots(num="ROI Data", nrows = self.nROI, ncols=1,
        sharex = True, sharey=True)
        self.MPLFig.suptitle('ROI Traces: %s' % self.currentFileName, fontsize=10)
        ndpt = len(self.FData[0,])
        for i in range(self.nROI):
            self.MPL_plots[i].plot(self.imageTimes[0:ndpt], self.FData[i,:], color = gcolor)
            #self.MPL_plots[i].hold(True)
        PL.show()

#----------------------Stack Ops (math on images) ---------------------------------

    def stackOp_absmax(self): # absolute maximum
        """Make an image that is the maximum of each pixel across the image stack."""
        self.clearAllROI()
        sh = np.shape(self.imageData)
        if len(sh) == 4:
            self.image = np.amax(self.imageData[:,1,:,:], axis=0).astype('float32')
        elif len(sh) == 3:
            self.image = np.amax(self.imageData[:, :, :], axis=0).astype('float32')
        self.paintImage(image=self.image, focus=False)

    def stackOp_normmax(self):  # normalized maximum
        """
        Make an image that is the maximum of each pixel, normalized within each image, across the image stack.
        """
        self.clearAllROI()
        levindex = self.ui.stackOp_levels.currentIndex()
        levels = [8., 16., 256., 4096., 65536.]
        id_shape = np.shape(self.imageData)
        id = np.zeros(id_shape)
        self.imageLevels = levels[-1]
        if len(id_shape) == 4:
            plane = 1
            amaxd = np.amax(self.imageData[:, plane, :, :], axis=0).astype('float32')
            amind = np.amin(self.imageData[:, plane, :, :], axis=0).astype('float32')
            id = np.floor((levels[levindex]/amaxd)*(self.imageData[:, plane, :, :].astype('float32')-amind))
        elif len(id_shape) == 3:
            amaxd = np.amax(self.imageData[:, :, :], axis=0).astype('float32')
            amind = np.amin(self.imageData[:, :, :], axis=0).astype('float32')
            id = np.floor((levels[levindex]/amaxd)*(self.imageData[:, :, :].astype('float32')-amind))
        self.image = np.amax(id, axis = 0)
        self.paintImage(image=self.image, focus=False)

    def stackOp_std(self):

        """Make an image that is the standard deviation of each pixel across the image stack."""
        self.clearAllROI()
        sh = np.shape(self.imageData);
        if len(sh) == 4:
            self.image = np.std(self.imageData[:,1,:,:], axis = 0)
        elif len(sh) == 3:
            self.image = np.std(self.imageData[:,:,:], axis = 0)
        self.paintImage(image=self.image, focus=False)

    def stackOp_mean(self):
        """Make an image that is the mean of each pixel across the image stack."""
        sh = np.shape(self.imageData);
        self.clearAllROI()
        if len(sh) == 4:
            self.image = np.mean(self.imageData[:,1,:,:], axis = 0)
        elif len(sh) == 3:
            self.image = np.mean(self.imageData[:,:,:], axis = 0)
        self.paintImage(image=self.image, focus=False)

    def stackOp_restore(self):
        """Redraw the original image stack."""
        self.paintImage(updateTools=True, focus=True)  # return to the original imagedata

#----------------------Image Processing methods ----------------
#   Includes bleach correction, filtering (median and gaussian), and deltaF/F calculation

    def unbleachImage(self):
        self.dataState['bleachCorrection'] = False  # reset flag...
        self.imageData = self.rawData.copy()  # starts over, no matter what.
        self.dataState['Normalized'] = False
        bleachmode = '2DPoly'
        imshape = np.shape(self.imageData)
        tc_bleach = np.zeros(imshape[0])
        b_corr = np.zeros(imshape[0])
        Fits = Fitting.Fitting()
        for k in range(0, imshape[0]):
            tc_bleach[k] = np.mean(self.imageData[k, :, :])
        dt  = np.mean(np.diff(self.imageTimes)) # sampling rate, seconds
        endT = np.amax(self.imageTimes)
        mFluor = tc_bleach[0]
        # replace tc_bleach with a smoothed version - 4th order polynomial
        fitx = np.arange(0, np.shape(tc_bleach)[0])
        if bleachmode == 'exp2':
            # use a double exponential fit
            (fpar, xf, yf, names) = Fits.FitRegion([0], 0, fitx, tc_bleach, 0.0, np.amax(fitx),
                                               fitFunc = 'exp2', fitPars=[0.9, 0.5, endT/5.0, 0.5, endT/2.0],
                                               plotInstance = None)
    #        (a0, a1, tau) = Fits.expfit(fitx, tc_bleach)
    #        print("fit result = a0: %f   a1: %f   tau: %f\n", (a0, a1, tau))

#            print fpar
            DC = fpar[0][0]
            A0 = fpar[0][1]
            tau1 = fpar[0][2]
            A1 = fpar[0][3]
            tau2 = fpar[0][4]
            self.tc_bleach = (DC + A0*np.exp(-fitx/tau1) + A1*np.exp(-fitx/tau2)) # convert start value to 1.0, take it from there
        if bleachmode == 'SG':
            windur = endT/5.0
            k = int(windur/dt) # make k the number of points in 2 second window
            if k % 2 == 0:
                k += 1
            self.tc_bleach = Utility.savitzky_golay(tc_bleach, kernel = k, order = 5)
        if bleachmode == '2DPoly':
            import itertools
            def polyfit2d(x, y, z, order=5):
                ncols = (order + 1)**2
                G = np.zeros((x.size, ncols))
                ij = itertools.product(range(order+1), range(order+1))
                for k, (i,j) in enumerate(ij):
                    G[:,k] = x**i * y**j
                m, _, _, _ = np.linalg.lstsq(G, z)
                return m

            def polyval2d(x, y, m):
                order = int(np.sqrt(len(m))) - 1
                ij = itertools.product(range(order+1), range(order+1))
                z = np.zeros_like(x)
                for a, (i,j) in zip(m, ij):
                    z += a * x**i * y**j
                return z
#            x = np.repeat(np.arange(imshape[1]), imshape[2])
#            y = np.tile(np.arange(imshape[1]), imshape[2]) # get array shape
            mi = np.mean(self.imageData, axis=0)
            z = np.reshape(mi, (imshape[1]*imshape[2], 1))
#            nx = int(imshape[1]/10)
#            ny = int(imshape[2]/10)
            blimg = scipy.ndimage.filters.gaussian_filter(mi, 15, order = 0, mode='reflect')
            #m = polyfit2d(x, y, z, order=3)
            #xx, yy = np.meshgrid(np.linspace(x.min(), x.max(), imshape[1]), np.linspace(y.min(), y.max(), imshape[2]))
            #blimg = polyval2d(xx, yy, m)
            #PL.imshow(blimg, extent=(x.min(), y.max(), x.max(), y.min()))
            #PL.show()
            self.tc_offset = np.zeros(imshape[0])
            zz = blimg.reshape(blimg.size, 1)
            self.tc_bleach = np.zeros(imshape[0])
            A = np.vstack([zz.reshape(1, zz.size), np.ones(zz.size)]).T
            for k in range(0, imshape[0]):
                z, u, r, s = np.linalg.lstsq(A, self.imageData[k,:,:].reshape(imshape[1]*imshape[2], 1))
                if k == 0:
                    print(z)
                self.tc_bleach[k] = z[0]
                self.tc_offset[k] = z[1]


        BleachPct = 100.0*(self.tc_bleach[-1]-self.tc_bleach[0])/self.tc_bleach[0]
        scaled_blimg = blimg/np.amax(np.amax(blimg)) # scale to max of 1.0
        self.tc_bleach = self.tc_bleach/self.tc_bleach[0]
        mean_orig = np.mean(tc_bleach)
        for k in range(0, len(self.imageData)):
#            avgint = np.mean(np.mean(self.imageData[k], axis=1), axis=0) # get the corrected value here
            if bleachmode == '2DPoly':  # whole field correction, not just linear with time
               # print np.amax(np.amax(scaled_blimg, 0), 0)*tc_bleach[k], self.tc_offset[k]
                self.imageData[k, :, :] = (self.imageData[k, :, :] - self.tc_offset[k]) / (scaled_blimg*self.tc_bleach[k])
            else:
                self.imageData[k, :, :] = self.imageData[k ,:, :] / (self.tc_bleach[k]/mFluor)
            b_corr[k] = np.mean(self.imageData[k,:,:]) # get the corrected value here
            #    self.rawData[k,:,:] = self.rawData[k,:,:] / self.tc_bleach[k]
        mean_final = np.mean(np.mean(np.mean(self.imageData[k], axis=1), axis=0))

        for k in range(0, len(self.imageData)):
            self.imageData[k, :, :] = self.imageData[k, :, :] * mean_orig/mean_final
            b_corr[k] = np.mean(self.imageData[k, :, :])  # get the corrected value here
        self.ctrlROIFunc.ImagePhys_BleachInfo.setText('B=%6.2f%%' % BleachPct)
        ndl = len(tc_bleach)
        self.backgroundPlot.plot(y=tc_bleach, x=self.imageTimes[0:ndl], pen=pg.mkPen('r'), clear=True)
        #self.backgroundPlot.plot(y=self.tc_bleach, x=self.imageTimes[0:ndl], clear=False, pen=pg.mkPen('b'))
        self.backgroundPlot.plot(y=b_corr, x=self.imageTimes[0:ndl], clear=False, pen=pg.mkPen('g'))
        self.paintImage(focus = False)
        self.updateAvgStdImage()
        self.dataState['bleachCorrection'] = True # now set the flag


#------------------------------------------------------------------------------------
# Helpers for ROI finding, and the ROI finding routine:

    def angle_cos(self, p0, p1, p2):
        d1, d2 = p0-p1, p2-p1
        return abs(np.dot(d1, d2) / np.sqrt(np.dot(d1, d1)*np.dot(d2, d2)))

    def pOpen(self, img, block_size):
        """ consists of Dilation followed by erosion """
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (block_size, block_size))
        dimg = cv2.dilate(img, kernel)
        oimg = cv2.erode(dimg, kernel)
        return(oimg)

    def pClose(self, img, block_size):
        """ consists of Erosion followed by Dilation """
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (block_size, block_size))
        eimg = cv2.erode(img, kernel)
        dimg = cv2.dilate(eimg, kernel)
        return(dimg)

    def ProperOpen(self, img, block_size):
        return(self.pOpen(self.pClose(self.pOpen(img, block_size), block_size), block_size))

    def findROIs(self):
        """ find potential regions of interest in an image series.
            This algorithm does the following:
            1. We use the standard deviation or power spectrum of the image. A series of thresholds
            are then set and contours identified. Each contour includes an area in which
            the standard deviation of the image exceeds the threshold. The contours are checked for
            minimum and maximum area.
            2. Next, for each threshold level:
                for each contour at that threshod, we identify contours at the next thresholded
                level up whose center of mass is inside ours. There are 2 possiblities:
                    a. no contours fall inside the current site. This site is a "peak", and
                        it's center of mass is stored as an ROI location.
                    b. one or more contours have a CM at the next level that falls inside
                        the current site. This means that the peak is higher than the current
                        threshold.
                        i. If we are not at the next to the highest threshod, we do not save this
                        location as a potential ROI (it will be identified when looking at the
                        next threshold level).
                        ii. If we are at the next to the highest threshold, then those locations
                        are saved as candidate ROIs.
            3. We filter candidate ROIs by distances, so that there are no overlapping ROIs.

            """
        if openCVInstalled is False:
            return
        if self.ctrlROIFunc.ImagePhys_StdRB.isChecked():
            imstd = self.stdImage
        else:
            imstd = self.specImage
        dr = 3.0 # Roi size
        dr = self.ctrlROIFunc.ImagePhys_ROISize.value() # get roi size fromthe control
        diag = np.hypot(dr,dr)# note we only accept ROIs that are more than this distance apart - nonoverlapping

        stdmax = np.amax(imstd)
        imstd = 255.0*imstd/stdmax
        imstd = scipy.ndimage.gaussian_filter(imstd, sigma=0.002)
        block_size2 =  int(self.ctrlROIFunc.ImagePhys_ROIKernel.currentText())
        # Note: block_size must be odd, so control has only odd values and no edit.
        stdmax = np.amax(imstd)
        imstd = 255.0*imstd/stdmax
        reconst2 = self.ProperOpen(imstd.astype('uint8'), block_size2)

        maxt = int(np.amax(reconst2))
    #        mint = int(np.amin(reconst2))
        meant = int(np.mean(reconst2))/2.0
    #        sqs = {}
        pols = {}
        thr_low = self.ctrlROIFunc.ImagePhys_ROIThrLow.value()
        thr_high = self.ctrlROIFunc.ImagePhys_ROIThrHigh.value()
        thrlist = np.arange(thr_low, thr_high*1.2, 0.05) # start at lowest and work up
        import matplotlib.colors as mc
        thrcols = list(mc.cnames.keys()) # ['r', 'orange', 'y', 'g', 'teal', 'c', 'b', 'violet', 'gray', '']
        # find countours for each threshold level
        for t in thrlist:
            thr = (maxt-meant)*t
            imctr = reconst2.copy() # cv2 method may modify input argument
            retval, ci = cv2.threshold(imctr.astype('uint8'), thr, maxt, cv2.THRESH_BINARY)
            contours, heirarchy = cv2.findContours(ci, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            oth = []
            m = []
            pols[t] = []
            for cnt in contours:
                cnt_len = cv2.arcLength(cnt, True)
                cnt = cv2.approxPolyDP(cnt, 0.02*cnt_len, True)
                m.append(cv2.minAreaRect(cnt))
                area = cv2.contourArea(cnt)
                if len(cnt) == 4 and area > 2.0 and cv2.isContourConvex(cnt):
                    cnt = cnt.reshape(-1, 2)
                if area > 2.0 and area < 400:
                    cnt = cnt.reshape(-1,2)
                    cnt = np.append(cnt, cnt[0]) # add the first point to the array to make sure it is closed
                    oth.append([cnt, True])
            pols[t] = oth

        # now check for the polygons whose center of mass is inside other polygons
        # if, from lowest threshold upwards,
        savpols = pols.copy()
    #        roi = []
        npolys = 0
        for t in thrlist:
            npolys += len(pols[t])
        regthresh = {} # we save the region threshold [Region: thresh]
        finalregions = {} # and the location [Region: (x,y)]
        nregs = 0
        with pg.ProgressDialog("Searching for ROIs ...", 0, 100) as dlg:
            for i in range(len(thrlist)-1): # work through all thresholds, starting at the bottom
                t = thrlist[i]
               # print '\n\n>>>>>>>>>>testing for threshold = %9.3f<<<<<<<<' % t,
                if len(pols[t]) == 0:
                #    print '   (found no candidates at threshold) ', t
                    continue
                #print '   found %d candidates' % len(pols[t])
                for k1, s1 in enumerate(pols[t]): # for each region at this threshold
                    dlg.setMaximum(len(pols[t]))
                    dlg.setValue(k1)
                    if dlg.wasCanceled():
                        raise HelpfulException("The search for ROIs was canceled by the user.", msgType='status')
                    poly_low = np.array([s1[0].reshape(-1,2)]) # this is needed for cv2.moments to take tha argument.
                    t2 = thrlist[i+1] # examine the next higher threshold
                    oneabove = False
                    m = cv2.moments(poly_low)
                    cm_low = (m['m10']/m['m00'], m['m01']/m['m00']) # compute center of mass of this point
                    for k2, s2 in enumerate(pols[t2]): # for each region identified at the next theshold level:
                        poly_high = np.array([s2[0].reshape(-1,2)])
                        m_high = cv2.moments(poly_high)
                        cm_high = (m_high['m10']/m_high['m00'], m_high['m01']/m_high['m00']) # compute center of mass of this point
                        test = cv2.pointPolygonTest(poly_low, cm_high, False) # is that center of mass
                        if  test >= 0: # a higher threshold  center is definitely INSIDE the polygon of the lower threshold
                            oneabove = True # we just need to find one - there could be more
                            break
                    if oneabove is False: # no CM's were found above us, so save this value
                        finalregions[nregs] = cm_low # Accepte this polygon at this threshold as a candidate.
                        regthresh[nregs] = t
                        nregs += 1
        # finally, also accept all peaks at the highest threshold level - they were "deferred" in the loop above
        t = thrlist[-1]
        for k1, s1 in enumerate(pols[t]):
            poly=np.array([s1[0].reshape(-1,2)])
            m = cv2.moments(poly)
            cm = (m['m10']/m['m00'], m['m01']/m['m00'])
            finalregions[nregs] = cm # all polygons at this level are accepted
            regthresh[nregs] = t
            nregs += 1

        print('Regions detected: %d' % (nregs))

        # clean up the final regions - accept only those whose centers are more than
        # "diag" of an ROI apart.
        # first convert the dictionary to a simple list in order
        fp = []
        for u in finalregions:
            fp.append(finalregions[u])
        tree = scipy.spatial.KDTree(fp) # make a tree
        candidates = {} # isolated
        candidates_n = {} # the neighbors not selected
        excluded = []
        for i, p in enumerate(finalregions.keys()):
            if p in excluded: #  or p in candidates_n:
                continue
            set_close = tree.query(fp[i], k=100, distance_upper_bound=diag) # find all pairs that are close together
            neighbors = []
            allth = [] # get the thresholds for all the neighbors
            for p2 in list(set_close[1]):
                if p2 == len(fp): # return values include self and inf.
                    continue
                if p2 in excluded or p2 in candidates_n:
                    continue
                neighbors.append(p2) # build a list of local friends
                allth.append(regthresh[p2])
            if len(neighbors) == 1: # we are our only neighbor
                candidates[p] = (finalregions[p], regthresh[p]) # no decision to make, this one is isolated
                excluded.append(p)
                continue
            k = int(np.argmax(allth)) # find the one with the highest signal
            candidates[p] = (finalregions[neighbors[k]], allth[k]) # candidates will have only the keys that are picked.
            for n in neighbors:
                excluded.append(n) # add these to the excluded list
        print('Found %d ROIs' % (len(candidates)))

    # next we verify that there are no close ROI pairs left:
    # this may not be needed, but sometimes with the pairwise-comparison, it is
    # possible for a proposed ROI to slip through.
        nc = {}
        for i, c in enumerate(candidates):
            nc[i] = candidates[c] # just copy over with a new key

        cp = []
    #        th = []
        excluded = []
        for i, u in enumerate(nc):
            cp.append(nc[u][0]) # just get the coordinates
        tree = scipy.spatial.KDTree(cp) # make a tree
        for i, p in enumerate(nc.keys()):
            if p in excluded:
                continue
            set_close = tree.query(cp[i], k=10, distance_upper_bound=diag) # find all pairs that are close together
            allth = [] # get the thresholds for all the neighbors
            neighbors=[]
            for j, p1 in enumerate(set_close):
                if set_close[0][j] == np.inf: # return values include self and inf.
                    continue
                p2 = set_close[1][j] # indexed into cp
                if p2 in excluded: # already kicked out
                    continue
                neighbors.append(p2) # build a list of local friends, mapped to main list
                allth.append(nc[p2][1]) # get the threshold
            if len(neighbors) == 1: # we are our only neighbor
                continue
            k = int(np.argmax(allth)) # find the one with the highest signal
            for i, n in enumerate(neighbors):
                if n == p2:
                    continue
                excluded.append(neighbors[i])
                nc.pop(n) # remove the duplicates
        print('Reduced to %d ROIs' % (len(nc)))
        candidates = nc.copy()

        self.oldROIs = self.AllRois
        self.clearAllROI()
        plotContours = False
        if plotContours:
            PL.subplot(111)
            PL.cla()
            PL.imshow(imstd, cmap=PL.cm.gray)
            PL.axis('off')
    #            import matplotlib.cm as cmx
    #            import matplotlib.colors as colors
    #            jet = PL.get_cmap('jet')
    #            cNorm  = colors.normalize(vmin=0, vmax=max(thrlist))
    #            scalarMap = cmx.ScalarMappable(norm=cNorm, cmap=jet)

            for i, t in enumerate(thrlist):
                col = thrcols[i]    # scalarMap.to_rgba(t)
                if len(pols[t]) == 0:
                    continue
                for p in savpols[t]: # for each region identified at this theshold:
                    if  p[1]:
                        sr = p[0].reshape(-1,2)
                        PL.plot(sr[:,0], sr[:,1], color = col, linestyle='-')

        for i, ra in enumerate(candidates):
            rxy = candidates[ra][0]
            if plotContours:
                PL.plot(rxy[0], rxy[1], 'r+')
            self.addOneROI(pos = [rxy[1]-dr/2, rxy[0]-dr/2], hw=[dr, dr])
        if plotContours:
            PL.show()

#-------------------------Corrections and/or Normalization---------------------------------
#
#
    def slowFilterImage(self):
        """ try automated signal extraction
        Mellon and Tuong NeuroImage 47: 1331, 2009 """

        if self.dataState['bleachCorrection'] is False:
            print('No Bleaching done, copy rawdata to image')
            self.imageData = self.rawData.copy() # just copy over without a correction        print 'Normalizing'
        if self.dataState['Normalized'] is True and self.dataState['bleachCorrection'] is True:
            print('Data is already Normalized, type = %s ' % (self.dataState['NType']))
            return
        else:
            self.imageData = self.rawData.copy() # just start over with the raw data...

        sh = self.imageData.shape
        t_delay = 0.2 # secs
        t_targetSmooth = 0.25 # secs
        t_subSmooth = 0.5 # secs
        dt  = np.mean(np.diff(self.imageTimes))
        print(dt)
        n_delay = t_delay/dt
        n_targetSmooth = int(t_targetSmooth/dt)
        n_subSmooth = int(t_subSmooth/dt)
#        j_delay = 0
#        k_delay = 0
        smi = scipy.ndimage.filters.uniform_filter1d(self.imageData, axis = 0, size=n_targetSmooth)
        smd = scipy.ndimage.filters.uniform_filter1d(self.imageData, axis = 0, size=n_subSmooth)
        self.imageData = smi[n_delay:sh[0],:,:] - smd[0:sh[0]-n_delay+1,:,:] # shifted subtraction, reduces data set by the time involved

        imstd = np.std(self.imageData, axis=0)
        imstd = scipy.ndimage.gaussian_filter(imstd, sigma=0.002)
#        isize = 1
#        immax = scipy.ndimage.maximum_filter(imstd, size=isize, mode='constant')
        imm = np.mean(np.mean(self.imageData, axis=2), axis=1)
        ndl = imm.shape[0]
        self.backgroundPlot.plot(y=imm, x=self.imageTimes[0:ndl], clear=True)
        self.paintImage()
        self.dataState['Normalized'] = True
        self.dataState['NType'] = 'Slow Filter'
#        self.ctrl.ImagePhys_NormInfo.setText('Slow Filter')
        # this completes the "normalization for the "slow filtering mode"
        # remainder of code here is for ROI detection.


    def normalizeImage(self):
        """
        Each image is normalized to the mean of the whole series, instead
        of using the starting images as the baseline
        """
        if self.dataState['bleachCorrection'] is False:
            print('No Bleaching done, copy rawdata to image')
            self.imageData = self.rawData.copy() # just copy over without a correction        print 'Normalizing'
        if self.dataState['Normalized'] is True and self.dataState['bleachCorrection'] is True:
            print('Data is already Normalized, type = %s ' % (self.dataState['NType']))
            return
        else:
            self.imageData = self.rawData.copy() # just start over with the raw data...
        meanimage = np.mean(self.imageData, axis=0)
        #meanimage = scipy.ndimage.filters.gaussian_filter(meanimage, (3,3))
        sh = meanimage.shape
        print('mean image shape: ', sh)
        for i in range(len(self.imageData)):
            self.imageData[i,:,:] = 1.0+(self.imageData[i,:,:] - meanimage)/meanimage
#        imstd = np.std(self.imageData, axis=0)
#        imstd = scipy.ndimage.gaussian_filter(imstd, sigma=0.002)
#        isize = 1
#        immax = scipy.ndimage.maximum_filter(imstd, size=isize, mode='constant')
#        imm = np.mean(np.mean(self.imageData, axis=2), axis=1)
#        ndl = imm.shape[0]
#        self.backgroundPlot.plot(y=imm, x=self.imageTimes[0:ndl], clear=True)
        self.dataState['Normalized'] = True
        self.dataState['NType'] = 'norm'
        self.paintImage()
        self.ctrl.ImagePhys_NormInfo.setText('Norm')
        # print 'norm: ', np.mean(self.imageData[1])

    def MediandFFImage(self, data=None):
        if self.dataState['bleachCorrection'] is False:
            print('No Bleaching done, copy rawdata to image')
            self.imageData = self.rawData.copy() # just copy over without a correction        print 'Normalizing'
        if self.dataState['Normalized'] is True and self.dataState['bleachCorrection'] is True:
            print('Data is already Normalized, type = %s ' % (self.dataState['NType']))
            return
        else:
            self.imageData = self.rawData.copy() # just start over with the raw data...
 #       sh = self.imageData.shape
        imm = np.median(np.median(self.imageData, axis=2), axis=1)
        samplefreq = 1.0/np.mean(np.diff(self.imageTimes))
        if samplefreq < 100.0:
            lpf = samplefreq/5.0
        else:
            lpf = 20.0
        imm = Utility.SignalFilter_LPFButter(imm, lpf, samplefreq, NPole = 8)
        print(np.amin(imm), np.amax(imm))
        for i in range(len(self.imageData)):
            self.imageData[i,:,:] = 1.0+(self.imageData[i,:,:] - imm[i])/imm[i]

#        imm = np.median(np.median(self.imageData, axis=2), axis=1)
#        ndl = imm.shape[0]
#        self.backgroundPlot.plot(y=imm, x=self.imageTimes[0:ndl], clear=True)
        self.dataState['Normalized'] = True
        self.dataState['NType'] = 'median'
        self.ctrl.ImagePhys_NormInfo.setText('Median')
        self.paintImage()

    def StandarddFFImage(self, baseline = False):
        if self.dataState['bleachCorrection'] is False:
            print('No Bleach Corrections: copying rawdata to image')
            self.imageData = self.rawData.copy() # just copy over without a correction
        if self.dataState['Normalized'] is True and self.dataState['bleachCorrection'] is True:
            print('Data is already Normalized, type = %s ' % (self.dataState['NType']))
            return
        else:
            self.imageData = self.rawData.copy()  # start over with the raw data...
        if baseline is True:
            t0 = self.ctrlROIFunc.ImagePhys_BaseStart.value()
            t1 = self.ctrlROIFunc.ImagePhys_BaseEnd.value()
            dt = np.mean(np.diff(self.imageTimes))
            it0 = int(t0/dt)
            it1 = int(t1/dt)
            if it1-it0 > 1:
                F0 = np.mean(self.imageData[it0:it1,:,:], axis=0)  # save the reference
                self.ctrl.ImagePhys_NormInfo.setText('(F-Fb)/Fb')
            else:
                self.ctrl.ImagePhys_NormInfo.setText('no Fb')
                raise ValueError('baseline has < 2 points')
        else:
            F0= np.mean(self.imageData[0:1,:,:], axis=0)  # save the reference
            self.ctrl.ImagePhys_NormInfo.setText('(F-F0)/F0')

        self.imageData = (self.imageData - F0) / F0  # do NOT replot!
        self.dataState['Normalized'] = True
        self.dataState['NType'] = 'dF/F'
#        imm = np.mean(np.mean(self.imageData, axis=2), axis=1)
#        ndl = imm.shape[0]
#        self.backgroundPlot.plot(y=imm, x=self.imageTimes[0:ndl], clear=True)
        self.paintImage()

    def GRRatioImage(self):
        print('Doing G/R Ratio calculation')
        if self.dataState['bleachCorrection'] is False:
            print('No Bleaching done, copy rawdata to image')
            self.imageData = self.rawData.copy() # just copy over without a correction        print 'Normalizing'
        if self.dataState['ratioLoaded'] is False:
            print('NO ratio image loaded - so try again')
            return
        if self.dataState['Normalized'] is True and self.dataState['bleachCorrection'] is True:
            print('Data is already Normalized, type = %s ' % (self.dataState['NType']))
            return
        else:
            self.imageData = self.rawData.copy() # just start over with the raw data...
        #F0= np.mean(self.imageData[0:3,:,:], axis=0) # save the reference
        self.imageData = self.imageData/self.ratioImage # do NOT replot!
        self.dataState['Normalized'] = True
        self.dataState['NType'] = 'GRRatio'
        self.ctrl.ImagePhys_NormInfo.setText('G/R')
#        imm = np.mean(np.mean(self.imageData, axis=2), axis=1)
#        ndl = imm.shape[0]
#        self.backgroundPlot.plot(y=imm, x=self.imageTimes[0:ndl], clear=True)
        self.paintImage()

    def smoothImage(self):
        self.imageData = scipy.ndimage.filters.gaussian_filter(self.imageData, (3,3,3))
        self.paintImage()

    def paintImage(self, image = None, updateTools = True, focus=True):
        if image == None:
            pImage = self.imageData
        else:
            pImage = image
        pImage = np.squeeze(pImage)
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
            Fx = np.fft.fft(xanom, npad, )
            Fy = np.fft.fft(yanom, npad, )
            iFxy = np.fft.ifft(Fx.conj()*Fy).real
            varxy = np.sqrt(np.inner(xanom,xanom) * np.inner(yanom,yanom))
        else:
            npad = x.shape[axis] + y.shape[axis]
            if axis == 1:
                if x.shape[0] != y.shape[0]:
                    raise ValueError("Arrays should have the same length!")
                xanom = (x - x.mean(axis=1)[:,None])
                yanom = (y - y.mean(axis=1)[:,None])
                varxy = np.sqrt((xanom*xanom).sum(1) * (yanom*yanom).sum(1))[:,None]
            else:
                if x.shape[1] != y.shape[1]:
                    raise ValueError("Arrays should have the same width!")
                xanom = (x - x.mean(axis=0))
                yanom = (y - y.mean(axis=0))
                varxy = np.sqrt((xanom*xanom).sum(0) * (yanom*yanom).sum(0))
            Fx = np.fft.fft(xanom, npad, axis=axis)
            Fy = np.fft.fft(yanom, npad, axis=axis)
            iFxy = np.fft.ifft(Fx.conj()*Fy,n=npad,axis=axis).real
        # We juste turn the lags into correct positions:
        iFxy = np.concatenate((iFxy[len(iFxy)/2:len(iFxy)],iFxy[0:len(iFxy)/2]))
        return iFxy/varxy

#
#------------- cross correlation calculations -----------------
#
    def Analog_Xcorr(self, FData = None, dt = None):
        """Average cross correlation of all traces"""
        self.calculateAllROIs()
        if not FData:
            FData = self.FData
        if dt is None:
            if self.imageTimes is []:
                dt = 1
            else:
                dt = np.mean(np.diff(self.imageTimes))
        self.calculate_all_xcorr(FData, dt)
        self.use_MPL = self.ctrlImageFunc.IAFuncs_MatplotlibCheckBox.checkState()


        if not self.use_MPL:
            self.floatingWindow = pyqtgrwindow(title = 'Analog_Xcorr_Average')
            self.floatingWindow.setWindowTitle('Average XCorr: %s' % self.currentFileName)
            # print dir(self.floatingWindow)
            # print dir(self.floatingWindow.layout)
            self.floatingWindow.layout.clear()
            self.floatingWindow.layout.setWindowTitle("New Title?")
            p = self.floatingWindow.layout.addPlot(0,0)
            p.plot(self.lags,self.xcorr)
            p.setXRange(np.min(self.lags), np.max(self.lags))
        else:
            self.checkMPL()
            (self.MPLFig, self.MPL_plots) = PL.subplots(num = "Average XCorr", nrows = 1, ncols=1,
                        sharex = True, sharey = True)
            self.MPLFig.suptitle('Average XCorr: %s' % self.currentFileName, fontsize=11)
            self.MPL_plots.plot(self.lags, self.xcorr)
            self.MPL_plots.plot(self.lags,np.zeros(self.lags.shape), color = '0.5')
            self.MPL_plots.plot([0,0], [-0.5, 1.0], color = '0.5')
            self.MPL_plots.set_title('Average XCorr', fontsize=10)
            self.MPL_plots.set_xlabel('T (sec)', fontsize=10)
            self.MPL_plots.set_ylabel('Corr (R)', fontsize=10)
            PH.cleanAxes(self.MPL_plots)
            PL.show()

    def calculate_all_xcorr(self, FData = None, dt = None):
        if FData is None:
            FData = self.FData
            nROI = self.nROI
        else:
            nROI = len(FData)
        if dt is None:
            if self.imageTimes is []:
                dt = 1
            else:
                dt = np.mean(np.diff(self.imageTimes))
        ndl = len(FData[0,:])
        itime = self.imageTimes[0:ndl]
        self.IXC_corr =  [[]]*(sum(range(1,nROI)))
        self.xcorr = []
        xtrace = 0
        for roi1 in range(0, len(FData)-1):
            for roi2 in range(roi1+1, len(FData)):
                (a1, b1) = np.polyfit(itime, FData[roi1,:], 1)
                (a2, b2) = np.polyfit(itime, FData[roi2,:], 1)
                y1 = np.polyval([a1, b1], itime)
                y2 = np.polyval([a2, b2], itime)
                sc = self.ccf(FData[roi1,:]-y1, FData[roi2,:]-y2)
                self.IXC_corr[xtrace] = sc
                if xtrace == 0:
                    self.xcorr = sc
                else:
                    self.xcorr = self.xcorr + sc
                xtrace += 1
        self.xcorr = self.xcorr/xtrace
        s = np.shape(self.xcorr)
        self.lags = dt*(np.arange(0, s[0])-s[0]/2.0)

    def Analog_Xcorr_unbiased(self, FData = None, dt = None):
        """ hijacked -"""
        # baseline
        pass


    # def Analog_Xcorr_unbiased(self, FData = None, dt = None):
    #     self.oldROIs = self.AllRois
    #     self.clearAllROI()
    #     img_sh = self.rawData.shape
    #     img_x = img_sh[1]
    #     img_y = img_sh[2]
    #     nx = 10
    #     ny = 10
    #     dx = int(img_x/nx)
    #     dy = int(img_y/ny)
    #     print dx, dy
    #     for i in range(0, nx):
    #         for j in range(0, ny):
    #             self.addOneROI(pos=[i*dx, j*dy], hw=[dx, dy])
    #     self.Analog_Xcorr_Individual(plottype = 'image')

    def Analog_Xcorr_Individual(self, FData = None, dt = None, plottype = 'traces'):
        """ compute and display the individual cross correlations between pairs of traces
            in the data set"""
        print('Calculating cross-correlations between all ROIs')
        self.use_MPL = self.ctrlImageFunc.IAFuncs_MatplotlibCheckBox.checkState()
        self.calculateAllROIs()
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
                dt = np.mean(np.diff(self.imageTimes))
        self.calculate_all_xcorr(self.FData, dt)
#        nxc = 0
#        rows = nROI-1
#        cols = rows
        self.IXC_plots = [[]]*(sum(range(1,nROI)))
        self.IXC_Strength = np.empty((nROI, nROI))
        self.IXC_Strength_Zero = np.empty((nROI, nROI))

        self.IXC_Strength.fill(np.nan)

        xtrace  = 0
        xtrace = 0
        lag_zero = np.argmin(np.abs(self.lags)) # find lag closest to zero
        for xtrace1 in range(0, nROI-1):
            for xtrace2 in range(xtrace1+1, nROI):
                self.IXC_Strength[xtrace1, xtrace2] = self.IXC_corr[xtrace].max()
                self.IXC_Strength[xtrace1, xtrace2] = self.IXC_corr[xtrace][lag_zero]
                xtrace = xtrace + 1

#        yMinorTicks = 0
#        bLegend = self.ctrlImageFunc.IAFuncs_checkbox_TraceLabels.isChecked()
#        gridFlag = True
        if plottype is None:
            return

#        if self.nROI > 8:
#            gridFlag = False
        if not self.use_MPL:
            #if self.floatingWindow is None:
            self.floatingWindow = pyqtgrwindow(title = 'Analog_Xcorr_Individual')
            self.floatingWindow.layout.clear()
            # self.gview = pg.GraphicsView()
            # if self.pgwin is None:
            #     self.pgwin = pg.GraphicsLayout()
            # self.pgwin.clear()
            xtrace = 0
            for xtrace1 in range(0, nROI-1):
                for xtrace2 in range(xtrace1+1, nROI):
#                    print 'xtrace: ', xtrace
                    self.IXC_plots[xtrace] = self.floatingWindow.layout.addPlot(xtrace1, xtrace2)
                    # if xtrace == 0:
                    #     print dir(self.IXC_plots[xtrace])
                    if xtrace > 0:
                        self.IXC_plots[xtrace].hideButtons()
                    xtrace = xtrace + 1
                self.floatingWindow.layout.nextRow()
        else:
            self.checkMPL()
            if plottype == 'traces':
                (self.MPLFig, self.IXC_plots) = PL.subplots(num="Individual ROI Cross Correlations",
                    nrows = self.nROI-1, ncols=self.nROI-1,
                    sharex = True, sharey = True)
                self.MPLFig.suptitle('XCorr: %s' % self.currentFileName, fontsize=11)
            else:
                self.MPLFig = PL.subplot(111)
#        ndl = len(FData[0,:])
#        itime = self.imageTimes[0:ndl]
        dlg = 0
        xtrace = 0
        with pg.ProgressDialog("Analyzing ROIs...", 0, 100) as dlg:
            for xtrace1 in range(0, nROI-1):
#               dlg.setLabelText("I")
                dlg.setValue(0)
                dlg.setMaximum(nROI)
#                temp_F = FData[xtrace1,:] #-y1
                for xtrace2 in range(xtrace1+1, nROI):

#                    if bLegend:
#                        legend = legend=('%d vs %d' % (xtrace1, xtrace2))
#                    else:
#                        legend = None
                    if plottype == 'traces':
                        if not self.use_MPL: # pyqtgraph
                            self.IXC_plots[xtrace].plot(self.lags, self.IXC_corr[xtrace])
                            if xtrace == 0:
                                self.IXC_plots[0].registerPlot(name='xcorr_%03d' % xtrace)
                            if xtrace > 0:
                                self.IXC_plots[xtrace].vb.setXLink('xcorr_000') # not sure - this seems to be at the wrong level in the window manager
                        else: # pylab
                            plx = self.IXC_plots[xtrace1, xtrace2-1]
                            plx.plot(self.lags,self.IXC_corr[xtrace])
                            plx.hold = True
                            plx.plot(self.lags,np.zeros(self.lags.shape), color = '0.5')
                            plx.plot([0,0], [-0.5, 1.0], color = '0.5')
                            if xtrace1 == 0:
                                plx.set_title('ROI: %d' % (xtrace2), fontsize=8)
                            PH.cleanAxes(plx)
                    xtrace = xtrace + 1
                    dlg += 1
                    if dlg.wasCanceled():
                        raise HelpfulException("Calculation canceled by user.", msgType='status')


        # now rescale all the plot Y axes by getting the min/max "viewRange" across all, then setting them all the same
        if not self.use_MPL and plottype == 'traces':
            ymin = 0
            ymax = 0
            bmin = []
            bmax = []
            for i in range(0, xtrace):
                bmin.append(np.amin(self.IXC_plots[i].vb.viewRange()[1]))
                bmax.append(np.amax(self.IXC_plots[i].vb.viewRange()[1]))
            ymin = np.amin(bmin)
            ymax = np.amax(bmax)
            self.IXC_plots[i].setXRange(np.min(self.lags), np.max(self.lags))
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
                    if xtrace1 == nROI-1:
                        plx.set_xlabel('T (sec)', fontsize=10)
                    if xtrace2 == 0:
                        plx.set_ylabel('R (%d)' % xtrace1, fontsize=10)
                    PH.cleanAxes(self.IXC_plots[xtrace1, xtrace2])
            PL.show()
        elif plottype == 'image':
#            print self.IXC_Strength.shape
            self.MPLFig.imshow(self.IXC_Strength)
            PL.show()

    #----------------Fourier Map (reports phase)----------------------------
    def Analog_AFFT(self):
        pass

    def Analog_AFFT_Individual(self):
        pass

    def Analysis_FourierMap(self):
        # print "times: ", self.times # self.times has the actual frame times in it.
        # first squeeze the image to 3d if it is 4d
        sh = np.shape(self.imageData);
        if len(sh) == 4:
            self.imageData = np.squeeze(self.imageData)
            sh = np.shape(self.imageData)
        print('**********************************\nImage shape: ', sh)
        self.imagePeriod = 6.0  # image period in seconds.
        w = 2.0 * np.pi * self.imagePeriod
        # identify an interpolation for the image for one cycle of time
        dt = np.mean(np.diff(self.imageTimes))  # get the mean dt
        maxt = np.amax(self.imageTimes)  # find last image time
        n_period = int(np.floor(maxt/self.imagePeriod))  # how many full periods in the image set?
        n_cycle = int(np.floor(self.imagePeriod/dt))  # estimate image points in a stimulus cycle
        ndt = self.imagePeriod/n_cycle
        i_times = np.arange(0, n_period*n_cycle*ndt, ndt) # interpolation times
        n_times = np.arange(0, n_cycle*ndt, ndt)  # just one cycle
        print("dt: %f maxt: %f # images %d" % (dt, maxt, len(self.imageTimes)))
        print("# full per: %d  pts/cycle: %d  ndt: %f #i_times: %d" % (n_period, n_cycle, ndt, len(i_times)))
        B = np.zeros([sh[1], sh[2], n_period, n_cycle])
        #for i in range(0, sh[1]):
    #            for j in range(0, sh[2]):
    #                B[i,j,:] = np.interp(i_times, self.times, self.imageData[:,i,j])
        B = self.imageData[range(0, n_period*n_cycle),:,:]
        print('new image shape: ', np.shape(self.imageData))
        print("B shape: ", np.shape(B))
        C = np.reshape(B, (n_cycle, n_period, sh[1], sh[2]))
        print('C: ', np.shape(C))
        D = np.mean(C, axis=1)
        print("D: ", np.shape(D))
        sh = np.shape(D)
        A = np.zeros((sh[0], 2), float)
        print("A: ", np.shape(A))
        A[:, 0] = np.sin(w*n_times)
        A[:, 1] = np.cos(w*n_times)
        sparse = 1

        self.phaseImage = np.zeros((sh[1], sh[2]))
        self.amplitudeImage = np.zeros((sh[1], sh[2]))
        for i in range(0, sh[1], sparse):
            for j in range(0, sh[2], sparse):
                (p, residulas, rank, s) = np.linalg.lstsq(A, D[:,i,j])
                self.amplitudeImage[i,j] = np.hypot(p[0],p[1])
                self.phaseImage[i, j] = np.arctan2(p[1],p[0])
        f = open('img_phase.dat', 'w')
        pickle.dump(self.phaseImage, f)
        f.close()
        f = open('img_amplitude.dat', 'w')
        pickle.dump(self.amplitudeImage, f)
        f.close()

    #        PL.figure()
    #        PL.imshow(self.phaseImage)
    #        PL.show()
    #
    # ---------------SMC (oopsi, Vogelstein method) detection of calcium events in ROIs----------------

    def Analysis_smcAnalyze(self):
        try:
            import SMC
        except:
            raise ImportError ("SMC not importable")
        self.smc_A = self.ctrlAnalysis.smc_Amplitude.value()
        self.smc_Kd = self.ctrlAnalysis.smc_Kd.value()
        self.smc_C0 = self.ctrlAnalysis.smc_C0.value()
        self.smc_TCa = self.ctrlAnalysis.smc_TCa.value()
        if self.imageTimes is []:
            dt = 1.0/30.0 # fake it... 30 frames per second
        else:
            dt = np.mean(np.diff(self.imageTimes))
        print("Mean time between frames: %9.4f" % (dt))
        if self.BFData is []:
            print("No baseline corrected data to use!!!")
            return
#        dataIDString = 'smc_'
        for roi in range(0, self.nROI):
            print("ROI: %d" % (roi))
            # normalized the data:
            ndat = (self.BFData[roi,:] - np.min(self.BFData[roi,:]))/np.max(self.BFData[roi,:])
            self.smc_V = SMC.Variables(ndat, dt)
            self.smc_P = SMC.Parameters(self.smc_V, A=self.smc_A, k_d=self.smc_Kd, C_0=self.smc_C0, tau_c =self.smc_TCa)
            self.smc_S = SMC.forward(self.smc_V, self.smc_P)
            cbar = np.zeros(self.smc_P.V.T)
            nbar = np.zeros(self.smc_P.V.T)
            for t in range(self.smc_P.V.T):
                for i in range(self.smc_P.V.Nparticles):
                    weight = self.smc_S.w_f[i,t]
                    cbar[t] += weight * self.smc_S.C[i,t]
                    nbar[t] += weight * self.smc_S.n[i,t]
            print("ROI: %d cbar: " % (roi))
            print(cbar)
            print("ROI: %dnbar: " % (roi))
            print(nbar)
#            MPlots.PlotLine(self.plots[roi], self.imageTimes, cbar, color = 'black',
#                            dataID = ('%s%d' % (dataIDString, roi)))
        print("finis")

# Use matlab to do the analysis with J. Vogelstein's code, store result on disk
    def smc_AnalyzeMatlab(self):
        import subprocess
        subprocess.call(['/Applications/MATLAB_R2010b.app/bin/matlab', '-r', 'FigSimNoisy.m'], bufsize=1)

    def Analysis_SpikeXCorr(self):
        pass


    def RegisterStack(self):
        """
        Align a stack of images using openCV. We calculate a rigid transform
        referenced to the first image, and transform each subsequent image
        based on that.
        It is fast, and better than nothing, but not perfect.
        """
#        import scipy.ndimage.interpolation
 #       outstack = self.imageData.copy()
        shd = self.imageData.shape
        maximg = np.amax(self.imageData)
        refimg = (255*np.mean(self.imageData, axis=0)/maximg).astype('uint8')
        for i in range(0,shd[0]):
            timage = (255*self.imageData[i,:,:]/maximg).astype('uint8')
            affineMat = cv2.estimateRigidTransform(refimg, timage, False)
            print(timage.shape, self.imageData[i].shape)
            self.imageData[i,:,:] = cv2.warpAffine(timage, affineMat, dsize=timage.shape, borderMode = cv2.BORDER_REPLICATE).astype('float32')*maximg/255.
            #x = scipy.ndimage.interpolation.affine_transform(self.imageData[i,:,:], affineMat[0:2,0:2] )
        self.updateAvgStdImage()



    def RegisterStack2(self):
        """ THIS IS NOT IN USE!!!

        Align a stack to one of its images using recursiveRegisterImages
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
        try:
            from acq4.analysis.tools import ImageP # avaialable as part of the STXMPy package
        except:
            raise ImportError('cann import ImageP for stack registration')

        imgstack = self.imageData
        cut = False
        imgi = 0  # use first image as reference
        N = len(imgstack)
        if imgi < 0 or imgi >= N:
            print("Invalid index: %d not in 0 - %d" %(imgi, N))
            return None
        #end if

        a = imgstack[imgi].copy()

#        sh = a.shape
        thresh = np.mean(a)*1.25
        print("threshold is set to: %.3f" % thresh)

        #initialize result stack:
        outstack = []
        indx = np.zeros(imgstack[0].shape, dtype='bool') + True

        imgN = 0
        #  print imgstack.shape
        for i, img in enumerate(imgstack):
            x = 0.
            y = 0.
            if i != imgi:
                #c = ImageP.ConvFilter(a > thresh, img)
                # print c
                c = FN.recursiveRegisterImages(img, imgstack[imgi], maxDist=10)
                x,y = (c == c.max()).nonzero()
                x = x[0] - (c.shape[0]/2 -1)
                y = y[0] - (c.shape[1]/2 -1)
            img2 = ImageP.shift(img, x, y)
            print('n: %d shift: x %f y %f' % (imgN, x, y))
            outstack.append(img2)
            indx = indx * (img2 > 0)
            imgN = imgN + 1

        if cut is True:
            ix, iy = indx.nonzero()
            i0 = ix.min()
            #+1 for the indexing limit...
            i1 = ix.max()+1
            j0 = iy.min()
            j1 = iy.max()+1

            print("Common boundaries:",i0,i1,j0,j1)

            #cut the list elements:
            for i in range(N):
                outstack[i] = outstack[i][i0:i1,j0:j1]

        for i in range(self.imageData.shape[0]):
            self.imageData[i,:,:] = outstack[i]
        return np.atleast_2d(outstack)
    #end of registerStack

#---------------------Database Operations ----------------------------- #
    def storeToDB(self, data=None):
        p = debug.Profiler("ImageAnalysis.storeToDB", disabled=True)

        if data is None:
            data =  self.flowchart.output()['events']

        if len(data) == 0:
            return

        dbui = self.getElement('Database')
        table = dbui.getTableName(self.dbIdentity)
        db = dbui.getDb()
        if db is None:
            raise Exception("No DB selected")
        p.mark("DB prep done")

        columns = db.describeData(data)
        columns.update({
            'ProtocolSequenceDir': 'directory:ProtocolSequence',
            'ProtocolDir': 'directory:Protocol',
            #'SourceFile': 'file'
        })
        p.mark("field list done")

        ## Make sure target table exists and has correct columns, links to input file
        db.checkTable(table, owner=self.dbIdentity, columns=columns, create=True, addUnknownColumns=True)
        p.mark("data prepared")

        ## collect all protocol/Sequence dirs
        prots = {}
        seqs = {}
        for fh in set(data['SourceFile']):
            prots[fh] = fh.parent()
            seqs[fh] = self.dataModel.getParent(fh, 'ProtocolSequence')

        ## delete all records from table for current input files
        for fh in set(data['SourceFile']):
            db.delete(table, where={'SourceFile': fh})
        p.mark("previous records deleted")

        ## assemble final list of records
        records = {}
        for col in data.dtype.names:
            records[col] = data[col]
        records['ProtocolSequenceDir'] = list(map(seqs.get, data['SourceFile']))
        records['ProtocolDir'] = list(map(prots.get, data['SourceFile']))

        p.mark("record list assembled")

        ## insert all data to DB
        with pg.ProgressDialog("Storing events...", 0, 100) as dlg:
            for n, nmax in db.iterInsert(table, records):
                dlg.setMaximum(nmax)
                dlg.setValue(n)
                if dlg.wasCanceled():
                    raise HelpfulException("Scan store canceled by user.", msgType='status')
        p.mark("records inserted")
        p.finish()

    def readFromDb(self, sequenceDir=None, sourceFile=None):
        """Read events from DB that originate in sequenceDir.
        If sourceFile is specified, only return events that came from that file.
        """

        dbui = self.getElement('Database')
        table = dbui.getTableName(self.dbIdentity)
        db = dbui.getDb()
        if db is None:
            raise Exception("No DB selected")

        #identity = self.dbIdentity+'.events'
        #table = dbui.getTableName(identity)
        if not db.hasTable(table):
            #return None, None
            return None
            #return np.empty(0)

        #pRow = db.getDirRowID(sourceDir)
        #if pRow is None:
            #return None, None

        if sourceFile is not None:
            events = db.select(table, '*', where={'SourceFile': sourceFile}, toArray=True)
        else:
            events = db.select(table, '*', where={'ProtocolSequenceDir': sequenceDir}, toArray=True)

        if events is None:
            ## need to make an empty array with the correct field names
            schema = db.tableSchema(table)
            ## NOTE: dtype MUST be specified as {names: formats: } since the names are unicode objects
            ##  [(name, format), ..] does NOT work.
            events = np.empty(0, dtype={'names': [k for k in schema], 'formats': [object]*len(schema)})

        return events


class DBCtrl(Qt.QWidget):
    def __init__(self, host, identity):
        Qt.QWidget.__init__(self)
        self.host = host

        self.layout = Qt.QVBoxLayout()
        self.setLayout(self.layout)
        self.dbgui = DatabaseGui.DatabaseGui(dm=host.dataManager(), tables={identity: 'EventDetector_events'})
        self.storeBtn = pg.FeedbackButton("Store to DB")
        #self.storeBtn.clicked.connect(self.storeClicked)
        self.layout.addWidget(self.dbgui)
        self.layout.addWidget(self.storeBtn)
        for name in ['getTableName', 'getDb']:
            setattr(self, name, getattr(self.dbgui, name))



class pyqtgrwindow(Qt.QMainWindow):
    def __init__(self, parent=None, title = '', size=(500,500)):
        super(pyqtgrwindow, self).__init__(parent)
        self.view = pg.GraphicsView()
        self.layout = pg.GraphicsLayout(border=None) # pg.mkPen(0, 0, 255))
        self.resize(size[0], size[1])
        self.setWindowTitle(title)
        self.view.setCentralItem(self.layout)
        self.view.show()
        