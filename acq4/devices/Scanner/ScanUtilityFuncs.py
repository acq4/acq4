"""
ScanUtilityFuncs.py

Scanner Utility Class.


1. Decombing routine for scanned images. 
2. Compute scan voltages for a recangular region
adding an overscan region.
3. Create an image with overscan removed.
"""
import numpy as NP
import pyqtgraph as PG



class ScannerUtilities():
    def __init__(self):
        self.scannerDev = None
        self.laserDev = None
        self.rectRoi = [PG.Point(0., 0.), PG.Point(0., 1e-4), PG.Point(1e-4, 0.)]
        self.pixelSize = 1e-6
        self.sampleRate = 1e-5
        self.downSample = 5
        self.overScan = 0.
        self.bidirectional = True
        
        # define set/get routines to control the parameters
    def setScannerDev(self, dev):
        self.scannerDev = dev
    
    def getScannerDev(self):
        return(self.scannerDev)
    
    def setLaserDev(self, dev):
        self.laserDev = dev
    
    def getLaserDev(self):
        return(self.laserDev)
    
    def setRectRoi(self, rect):
        if len(rect) == 3: # must specify all coordinates
            self.rectRoi = rect
        else:
            raise Exception("Scanner Utility: setRectRoi requires array of 3 values")
    
    def getRectRoi(self):
        return(self.rectRoi)
    
    def setPixelSize(self, size):
        self.pixelSize = size
        
    def getPixelSize(self):
        return(self.pixelSize)
    
    def setSampleRate(self, sampleRate):
        if sampleRate < 0:
            raise Exception("Scanner Utility: setSampleRate requires positive rate")
        self.sampleRate = sampleRate
    
    def getSampleRate(self):
        return(self.sampleRate)
    
    def setDownSample(self, downsample):
        if downsample < 1 or downsample > 100:
            raise Exception("Scanner Utility: setDownSample requires positive downsample number")
        self.downSample = downsample
        
    def getDownSample(self):
        return(self.downSample)

    def setOverScan(self, overscan):
        if overscan < 0 or overscan > 100:
            raise Exception("ScannerUtility: setOverScan requires number >0 and < 100")
        self.overScan = overscan
        
    def getOverScan(self):
        return self.overScan
    
    def setBidirectional(self, bidirection):
        self.biDirectional = bidirection
        
    def getBidirectional(self):
        return(self.biDirectional)

    def packScannerParams(self):
        """
        put the current scanner parameters into a dictionary with their names
        and return the value
        """
        scannerParams = {'scannerDev': self.scannerDev, 'laserDev': self.laserDev,
                         'rectRoi': self.rectRoi, 'pixelSize': self.pixelSize, 
                         'sampleRate': self.sampleRate, 'downSample': self.downSample,
                         'overScan': self.overScan, 'bidirectional': self.bidirectional}
        return scannerParams
    
    def checkScannerParams(self):
        sp = self.packScannerParams()
        for p in sp.keys():
            if sp[p] is None:
                raise Exception("ScannerUtility: parameter %s is not set" % p)
        
    def packArgs(self, **kwargs):
        sp = self.packScannerParams() # get the current parameters
        for k, v in kwargs.iteritems():
            if k in sp.keys():
                sp[k] = v
        # now update the instance-specific values from the dictionary
        self.scannerDev = sp['scannerDev']
        self.laserDev = sp['laserDev']
        self.rectRoi = sp['rectRoi']
        self.pixelSize = sp['pixelSize']
        self.sampleRate = sp['sampleRate']
        self.downSample = sp['downSample']
        self.overScan = sp['overScan']
        self.bidirectional = sp['bidirectional']     
        return sp # just in case we want it as well...
    
        
    def designRectScan(self, **kwargs):
        """
        compute the scan voltages for the scanner, corrected by the laser calibration,
        to scan the rectangle specified in standard coordinates, with the rate,
        downsample, overscan and bidirectional flags as set. 
        Pulled from Imager.py, 11/21/2013.
        """
        self.packArgs(**kwargs) # update any specified arguments
        self.checkScannerParams() # verify all are loaded in in range.
        printPars = False
        if 'printPars' in kwargs.keys():
            printPars = kwargs['printPars']
        
        pts = self.rectRoi
      #  print 'Points in sfu/design: ', pts
        xPos = pts[0][0]
        yPos = pts[0][1]
      #  print 'xypos: ', xPos, yPos
        #width = self.rect[2]
        #height = self.rect[3]
        width  = (pts[1] -pts[0]).length() # width is x in M
        height = (pts[2]- pts[0]).length() # heigh in M
        self.nPointsX = int(width/self.pixelSize)
        self.nPointsY = int(height/self.pixelSize)
        xScan = NP.linspace(0., width, self.nPointsX)
        xScan += xPos
        
        overScanWidth = width*self.overScan/100.
        self.overScanPixels = int(self.nPointsX / 2. * (self.overScan/100.))
        self.pixelsPerRow = self.nPointsX + 2 * self.overScanPixels  ## make sure width is increased by an even number.
        samplesPerRow = self.pixelsPerRow * self.downSample
        self.samples = samplesPerRow * self.nPointsY
        if printPars:
            print 'rectRoi: ', self.rectRoi
            print 'pixelsPer Row: ', self.pixelsPerRow
            print 'nPointsX: ', self.nPointsX
            print 'nPointsY: ', self.nPointsY
            print 'overScan: ', self.overScan
            print 'downSample: ', self.downSample
            print 'overscanWidth: ', overScanWidth
            print 'samplesperrow: ', samplesPerRow
            print 'xPos, yPos: ', xPos, yPos
        if not self.bidirectional:
            saw1 = NP.linspace(0., width+overScanWidth, num=samplesPerRow)
            saw1 += xPos-overScanWidth/2.0
            xSaw = NP.tile(saw1, (1, self.nPointsY))[0,:]
        else:
            saw1 = NP.linspace(0., width+overScanWidth, num=samplesPerRow)
            saw1 += xPos-overScanWidth/2.0
            rows = [saw1, saw1[::-1]] * int(self.nPointsY/2)
            if len(rows) < self.nPointsY:
                rows.append(saw1)
            xSaw = NP.concatenate(rows, axis=0)
        
        yvals = NP.linspace(0., width, num=self.nPointsY)
        yvals += yPos
        yScan = NP.empty(self.samples)
        for y in range(self.nPointsY):
            yScan[y*samplesPerRow:(y+1)*samplesPerRow] = yvals[y]
        # now translate this scan into scanner voltage coordinates...
        x, y = self.scannerDev.mapToScanner(xSaw, yScan, self.laserDev)
        xSaw = []
        yScan = []
        
        
        ###----------------------------------------------------------------
        ## note: code not working right yet. 
        ## generate scan array using potentially rotated rectangular ROI
        ## with extended overscan regions.
        
        #n = self.nPointsY # get number of rows
        #m = samplesPerRow # get number of points per row        
        
        #r = NP.mgrid[0:m, 0:n].reshape(1,2,m,n) 
        #if self.bidirectional: # reverse directions of alternate rows
            #order = range(n-1, -1, -1)
            #for yrow in range(1,m,2):
                #r[0,1,yrow,:] = [r[0,1,yrow,i] for i in order]     
        ## convert image coordinates to physical coordinates to pass to scanner.
        #dx = (pts[1] - pts[0])/m # step size per "pixel" in x
        #dy = (pts[2] - pts[0])/n # step size per "pixel" in y
        #v = NP.array([[dx[0], dy[0]], [dx[1], dy[1]]]).reshape(2,2,1,1) 
        #q = (v*r).sum(axis=1)
        #q += NP.array(pts[0]).reshape(2,1,1)
        #q = q.transpose(0,2,1).reshape(2,m*n)
        #x, y = self.scannerDev.mapToScanner(q[0], q[1], self.laserDev)                
        #----------------------------------------------------
        return (x, y)
    
    def getPixelsPerRow(self):
        return self.pixelsPerRow
    
    def getnPointsY(self):
        return self.nPointsY

    def getOverScanPixels(self):
        return self.overScanPixels

    def getSamples(self):
        return self.samples
    
    def getScanInfo(self):
        """
        convenience function - get several scan parameters after the scan
        as a dictionary
        """
        return {'pixelsPerRow': self.pixelsPerRow, 'overScanPixels': self.overScanPixels,
                'nPointsY': self.nPointsY, 'nPointsX': self.nPointsX,
                'samples': self.samples}
    
    def getScanXYSize(self):
        # return the size of the data array that the scan will fill
        # as a tuple
        return (self.pixelsPerRow, self.nPointsY)

    def adjustBidirectional(self, imgData, decombAutoFlag, decombShift):
        """
        If the data is from a bidirectional scan, do the decombing with the 
        fixed shift value.
        Optionally, compute the auto decomb value needed to optimize the image.
        """
        if self.bidirectional:
            for y in range(1, self.nPointsY, 2): # reverse direction for alternate rows
                imgData[:,y] = imgData[::-1,y]
            if decombAutoFlag:
                imgData, shift = self.decomb(imgData, minShift=0*self.sampleRate, maxShift=200e-6*self.sampleRate)  ## correct for mirror lag up to 200us
                decombShift = shift / self.sampleRate
            else:
                imgData, shift = self.decomb(imgData, auto=False, shift=decombShift*self.sampleRate)
        return imgData, decombShift
        

    def makeOverscanBlanking(self, imgData):
        """
        return an array of 1's and 0's where
        the data is 0 in the overscan space, and 1 in the 
        image space
        """
        blankData = NP.zeros(imgData.shape)
        osp = self.getOverScanPixels()
        if osp > 0:
            blankData[osp:-osp] = 1
        else:
            blankData[:] = 1
        return blankData
    
    def removeOverscan(self, imgData):
        """
        Trim the overscan from the image array
        """
        osp = self.getOverScanPixels()
        if osp > 0:
            imgData = imgData[osp:-osp]
        return imgData
    
    def decomb(self, img, minShift=0, maxShift=100, auto=True, shift=0.):
        ## split image into fields
        nr = 2 * (img.shape[1] // 2)
        f1 = img[:,0:nr:2]
        f2 = img[:,1:nr+1:2]
        
        ## find optimal shift
        if auto:
            bestShift = None
            bestError = None
            #errs = []
            for shift in range(int(minShift), int(maxShift)):
                f2s = f2[:-shift] if shift > 0 else f2
                err1 = NP.abs((f1[shift:, 1:]-f2s[:, 1:])**2).sum()
                err2 = NP.abs((f1[shift:, 1:]-f2s[:, :-1])**2).sum()
                totErr = (err1+err2) / float(f1.shape[0]-shift)
                #errs.append(totErr)
                if totErr < bestError or bestError is None:
                    bestError = totErr
                    bestShift = shift
            #PG.plot(errs)
        else:
            bestShift = shift
        
        ## reconstrict from shifted fields
        leftShift = bestShift // 2
        rightShift = leftShift + (bestShift % 2)
        if rightShift == 0:
            return img, 0
        decombed = NP.zeros(img.shape, img.dtype)
        if leftShift > 0:
            decombed[:-leftShift, ::2] = img[leftShift:, ::2]
        else:
            decombed[:, ::2] = img[:, ::2]
        decombed[rightShift:, 1::2] = img[:-rightShift, 1::2]
        return decombed, bestShift