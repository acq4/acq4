# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from lib.analysis.AnalysisModule import AnalysisModule
from advancedTypes import OrderedDict
import pyqtgraph as pg
from metaarray import MetaArray
import numpy
import scipy
import ctrlTemplate
from lib.analysis.tools import Utility
from lib.analysis.tools import Fitting


class pbm_ImageAnalysis(AnalysisModule):
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        # per-instance parameters:
        self.currentDataDirectory = None # currently selected data directory (if valid)
        self.refImage = None # Reference image data used for ratio calculations
                                # This image may come from a separate file or a calculation on the present file
        self.physData = None # physiology data associated with the current image
        self.dataStruct = 'flat' # 'flat' or 'interleaved' are valid at present.
        self.ignoreFirst = False # ImagePhys_ignoreFirst
        self.tStart = 0.0 # baseline time start = applies to the image: ImagePhys_BaseStart
        self.tEnd = 50.0 # baseline time end (msec) : ImagePhys_BaseEnd
        self.imageLPF = 0.0 # low pass filter of the image data, Hz: ImagePhys_ImgLPF
        self.physLPF = 0.0 # low pass filter of the physiology data, Hz (0 = no filtering): ImagePhys_PhysLPF
        self.physLPFChanged = False # flag in case the physiology LPF changes (avoid recalculation)
        self.physSign = 0.0 # ImagePhys_PhysSign (detection sign for events)
        self.physThresh = -50.0 # ImagePhys_PhysThresh (threshold in pA to detect events)
        self.ratioImages = False # only set true once a ratio (reference) image is loaded 
        self.baseImage=[]
        self.viewFlag = False # false if viewing movie, true if viewing fixed image
        self.referenceImage = []
        self.AllRois = []
        self.nROI = 0 # count of ROI's in the window
        self.rois = []
        self.currentRoi = None
        self.imageData = [] # Image Data array, information about the data is in the dataState dictionary
        self.lastROITouched=[]
        self.ctrlWidget = QtGui.QWidget()
        self.ctrl = ctrlTemplate.Ui_Form()
        self.ctrl.setupUi(self.ctrlWidget)
        self.initDataState()
        self.RGB = Utility.makeRGB()
        
        ## Setup basic GUI
        self._elements_ = OrderedDict([
            ('File Loader', {'type': 'fileInput', 'size': (150, 300), 'host': self, 'showFileTree': True}),
            ('Image',       {'type': 'imageView', 'pos': ('right', 'File Loader'), 'size': (500, 500)}),
            ('Parameters',  {'type': 'ctrl', 'object': self.ctrlWidget, 'host': self, 'size': (150,300)}), 
            ('ROI Plot',   {'type': 'plot',  'pos': ('right', 'Parameters'),'size': (1000, 300)}),
            ('Phys Plot',   {'type': 'plot',  'pos': ('bottom', 'ROI Plot'),'size': (1000, 300)}),
            ('Trial Plot',  {'type': 'plot', 'size': (1000, 300)}),
#            ('Line Scan',   {'type': 'imageView', 'size': (1000, 300)}),
            #('Data Table',  {'type': 'table', 'pos': ('below', 'Time Plot')}),
        ])
        self.initializeElements()
        self.ctrl.ImagePhys_Update.clicked.connect(self.updateAnalysis)
        self.ctrl.ImagePhys_PhysLPF.valueChanged.connect(self.physLPF_valueChanged)
        self.ROI_Plot = self.getElement('ROI Plot', create=True)
        self.trialPlot = self.getElement('Trial Plot', create=True)
        self.physPlot = self.getElement('Phys Plot', create = True)
        self.lr = pg.LinearRegionItem(self.ROI_Plot, 'vertical', [0, 1])
        self.ROI_Plot.addItem(self.lr)
        self.physPlot.setXLink(self.ROI_Plot) # not sure - this seems to be at the wrong level in the window manager
        self.imageView = self.getElement('Image', create=True)
        self.imageItem = self.imageView.imageItem      
        ## Plots are updated when the selected region changes
        self.lr.sigRegionChanged.connect(self.updateAnalysis)
        self.imageView.sigProcessingChanged.connect(self.processData)
        self.ctrl.ImagePhys_addRoi.clicked.connect(self.addOneROI)
        self.ctrl.ImagePhys_clearRoi.clicked.connect(self.clearAllROI)
        self.ctrl.ImagePhys_getRatio.clicked.connect(self.loadRatioImage)
        self.ctrl.ImagePhys_ImgNormalize.clicked.connect(self.doNormalize)
        self.ctrl.ImagePhys_UnBleach.clicked.connect(self.unbleachImage)
        self.ctrl.ImagePhys_View.clicked.connect(self.changeView)
        self.ctrl.ImagePhys_RetrieveROI.clicked.connect(self.restoreROI)
        self.ctrl.ImagePhys_SaveROI.clicked.connect(self.saveROI)

    def initDataState(self):
        self.dataState = {'Loaded': False, 'bleachCorrection': False, 'Normalized': False,
                        'NType' : None, 'Structure': 'Flat', 'NTrials': 0}
        self.ctrl.ImagePhys_BleachInfo.setText('None')
        self.ctrl.ImagePhys_NormInfo.setText('None')

    def changeView(self):
        print 'changeView'
        if self.dataState['Loaded'] is False:
            return # no data - so skip this.
        print 'data loaded, now flag'
        if self.viewFlag is False: # looking at movie, switch to fixed image
            self.imageView.setImage(self.baseImage)
            self.ctrl.ImagePhys_View.setText('View Movie')
            self.viewFlag = True
        else: # loking at fixed image, switch to movie
            self.imageView.setImage(self.imageData)
            self.ctrl.ImagePhys_View.setText('View Ref Img')
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
        
        if len(dh) != 1:
            QtGui.QMessageBox.warning(self,
                                      "pbm_ImageAnalysis: loadFileRequested Error",
                                      "Can only load one data set/run at a time.")
            return
            # raise Exception("Can only load one data set/run at a time.")
        dh = dh[0]
        if dh.isFile():
            QtGui.QMessageBox.warning(self,
                                      "pbm_ImageAnalysis: loadFileRequested Error",
                                      "Select a Directory containing the data, not the data file itself")
            return
#            raise Exception("Select a Directory containing the data, not the data file itself")
        self.ROI_Plot.clearPlots()
        self.initDataState()
        self.getDataStruct()
        self.currentDataDirectory = dh

        if self.dataStruct is 'flat':
            print 'getting Flat data structure!'
            self.rawData = []
            self.readPhysiology(dh)
            img = dh['Camera/frames.ma'].read() # read the image stack
            if self.ignoreFirst:
                fi = 1
            else:
                fi = 0
            self.imageData = img.view(numpy.ndarray) # load into rawData, clipping the first image if needed
            self.imageData = self.imageData[fi:]
            self.baseImage = self.imageData[0] # just to show after processing...
            self.imageTimes = img.infoCopy()[0].values()[1]
            self.imageTimes = self.imageTimes[fi:]
            self.imageView.setImage(self.imageData)
            self.dataState['Loaded'] = True
            self.dataState['Structure'] = 'Flat'

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
            
            return True

    def readPhysiology(self, dh):
        """ call to read the physiology from the primary data channel
        dh is thehandle to the directory where the data is stored (not the file itself)
        """
        self.physPlot.clearPlots()
        self.physData = []
        if dh is None:
            return
        data = self.dataModel.getClampFile(dh).read() # retrieve the physiology traces
        self.physData = self.dataModel.getClampPrimary(data)
        info1 = data.infoCopy()
        samplefreq = info1[2]['DAQ']['primary']['rate']
        if self.physLPF > 250.0 and self.physLPF < 0.5*samplefreq: # respect Nyquist, just minimally
            print self.physData.shape
            self.physData =  Utility.SignalFilter_LPFBessel(self.physData, self.physLPF, samplefreq, NPole = 8)
            print self.physData.shape
        self.physLPFChanged = False # we have updated now, so flag is reset
        maxplotpts=8192
        shdat = self.physData.shape
        decimate_factor = 2
        if shdat[0] > 2*maxplotpts:
            decimate_factor = int(numpy.floor(shdat[0]/maxplotpts))
            if decimate_factor < 2:
                decimate_factor = 2
        else:
            pass
            # store primary channel data and read command amplitude
        print 'decimate factor: %d' % (decimate_factor)
        print 'Number of points in original data set: ', shdat
        tdat = data.infoCopy()[1]['values']
        tdat = tdat[::decimate_factor]
        self.physPlot.plot(x=tdat, y=self.physData[::decimate_factor], pen=pg.mkPen('w')) # , decimate=decimate_factor)
        
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
        lpf = self.ctrl.ImagePhys_PhysLPF.value()
        if lpf == 0.0:
            self.physLPF = 0.0
        else:
            self.physLPF = lpf
        print "data struct = %s" % self.dataStruct
        print "ignore First: ", self.ignoreFirst
        print "lpf: %8.1f" % self.physLPF

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
        self.updateThisROI(self.lastROITouched)    


#--------------- From PyImageAnalysis3.py: -----------------------------
#---------------- ROI routines on Images  ------------------------------

    def clearAllROI(self):
        """ remove all rois and all references to the rois """
        for roi in self.AllRois:
            roi.hide()
            del roi
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
        print '# Rois: %d' % len(self.AllRois)
        if ourWidget in self.AllRois:
            id = ourWidget.ID # get the id of the roi
            self.AllRois.remove(ourWidget)  # remove it from our list
            ourWidget.hide()
            del ourWidget
            #sip.delete(ourWidget) # and delete the object
        else:
            QtGui.QMessageBox.warning(self,
                                      Qt.QString("Delete ROI - Error"),
                                      "Last ROI was not in ROI list?")
        self.nROI = len(rois)
        for roi in self.AllRois:
            roi.ID = rois.index(roi) # renumber the roi list.
        print '# Rois after delete: %d' % len(rois)
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
        roi = pg.widgets.RectROI(pos, hw, scaleSnap=True, translateSnap=True)
#       roi = qtgraph.widgets.EllipseROI(pos, hw, scaleSnap=True, translateSnap=True)
#       roi = qtgraph.widgets.MultiLineROI([[0,0], [5,5], [10,10]], 3, scaleSnap=True, translateSnap=True)
        roi.ID = self.nROI # give each ROI a unique identification number
        rgb = self.RGB[self.nROI]
        self.nROI = self.nROI + 1
        roi.setPen(QtGui.QPen(QtGui.QColor(rgb[0], rgb[1], rgb[2])))
        roi.color = rgb
        self.AllRois.append(roi)
        self.imageView.addItem(roi)
        roi.sigRegionChanged.connect(self.updateThisROI)
        return (roi)

    def plotImageROIs(self, ourWidget):
        """ plot the ROIs in the image - as an initial instantiation. Every known
            roi gets plotted with the routine 
        """
        if ourWidget in self.AllRois: # must be in the list of our rois - ignore other widgets
            print self.imageData.shape
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
        print 'roiChanged'
        if isinstance(roi, int):
            roi = self.currentRoi
        self.ROI_Plot.clearPlots()
        c = 0
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
            
            c += 1
            
        lineScan = np.hstack(lineScans)
        self.getElement('Line Scan').setImage(lineScan)
        self.currentRoi = roi
        
    def updateThisROI(self, ourWidget, livePlot=True):
        """ called when we need to update the ROI result plot for a particular ROI widget 
        """
        if ourWidget in self.AllRois:
            # print 'im shape: ', self.imageData.shape
            tr = ourWidget.getArrayRegion(self.imageData, self.imageView.imageItem, axes=(1,2))
            tr = tr.mean(axis=2).mean(axis=1) # compute average over the ROI against time
            tr[0] = tr[1]
            if livePlot:
                self.ROI_Plot.plot(data=tr, x=self.imageTimes, clear=True)
            self.lastROITouched = ourWidget # save the most recent one
            return(tr)

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

    def saveROI(self, filename = None):
        """Save the ROI information (locations) to a disk file."""
        sh = numpy.shape(self.FData)
        data = empty([sh[0]+1, sh[1]])
        data[0] = arange(0,sh[1])
        roiData = []
        for i in range(0, sh[0]):
            data[i+1] = self.FData[i]
            roiData.append([self.AllRois[i].pos().x(), self.AllRois[i].pos().y(),
                            self.AllRois[i].boundingRect().height(), self.AllRois[i].boundingRect().width()])
        data = data.T
        if filename is None:
            fileName = Qt.QFileDialog.getSaveFileName(self, "Save ROI data", "*.csv")
        if fileName:
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
    
    def restoreROI(self, filename = None):
        """Retrieve the ROI locations from a file, plot them on the image, and compute the traces."""
        self.clearAllROI() # always start with a clean slate.
        if filename is None:
            fileName = QtGui.QFileDialog.getOpenFileName(self, u'Retrieve ROI data', u'ROIs (*.roi)')
        self.RData = []
        self.nROI = 0
        if fileName:
            fd = open(fileName, 'r')
            for line in fd:
                roixy=fromstring(line, sep=' ')
                roi = self.addOneROI(pos=[roixy[0], roixy[1]], hw=[roixy[2], roixy[3]])
                tr = self.updateThisROI(roi, livePlot=False)
                lcount = len (tr)
                self.RData.append(tr)
            #self.times = arange(0, len(tr))
            self.nROI = len(self.RData)
            self.FData =numpy.array(self.RData)# .reshape(lcount, self.nROI).T
            self.BFData = [] # 'baseline corrected'
            self.plotdata(yMinorTicks = 0, yMajorTicks = 3,
                          yLabel = u'F0<sub>ROI %d</sub>')

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
        if self.dataState['Normalized'] is True: # should not normalize twice!
            return
#        self.clearAllROI()
        sh = self.imageData.shape
        zf = int(sh[0]/20)
        xf = int(sh[1]/10)
        yf = int(sh[2]/10)
        self.im_filt = scipy.ndimage.filters.gaussian_filter(self.imageData, (zf, xf, yf))
#        self.im_filt = scipy.ndimage.filters.gaussian_filter(self.imageData, (3,3,3))
        self.imageData = numpy.array(self.imageData) / self.im_filt
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
        self.imageData = self.imageData / im_filt # do NOT replot!
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
        
        
        