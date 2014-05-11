# -*- coding: utf-8 -*-
import numpy as np
import acq4.pyqtgraph as pg
from acq4.util.HelpfulException import HelpfulException
import ScanUtilityFuncs as SUFA


class ScanProgramGenerator:
    def __init__(self, dev, command):
        self.dev = dev
        self.cmd = command 
        self.SUF = SUFA.ScannerUtilities()
        self.SUF.setScannerDev(self.dev)

    def mapToScanner(self, x, y):
        return self.dev.mapToScanner(x, y, self.cmd['laser'])
    
    def generate(self):
        """LASER LOGO
        Turn a list of movement commands into arrays of x and y values.
        prg looks like:
        { 
            numPts: 10000,
            duration: 1.0,
            commands: [
               {'type': 'step', 'time': 0.0, 'pos': None),           ## start with step to "off" position 
               ('type': 'step', 'time': 0.2, 'pos': (1.3e-6, 4e-6)), ## step to the given location after 200ms
               ('type': 'line', 'time': (0.2, 0.205), 'pos': (1.3e-6, 4e-6))  ## 5ms sweep to the new position 
               ('type': 'step', 'time': 0.205, 'pos': None),           ## finish step to "off" position at 205ms
           ]
        }
        
        Commands we might add in the future:
          - circle
          - spiral
        """
        command = self.cmd
        dt = command['duration'] / command['numPts']
        arr = np.zeros((2, command['numPts']))        
        cmds = command['program']
        lastPos = None     
        lastValue = np.array(self.dev.getVoltage())
        lastStopInd = 0
        for i in range(len(cmds)):
            cmd = cmds[i]
            if cmd['active'] is False:
                continue
            startInd = int(cmd['startTime'] / dt)
            stopInd = int(cmd['endTime'] / dt)
            #print 'scanproggenerator;;;'
            #print startInd, stopInd
            #print cmd['startTime'], cmd['endTime']
            #print 'dt: ', dt
            #print 'dur, pts: ', command['duration'], command['numPts']
            #print 'total time: ', dt*command['numPts']
            #print arr.shape
            if stopInd >= arr.shape[1]:
                raise HelpfulException('Scan Program duration is longer than protocol duration') 
            arr[:,lastStopInd:startInd] = lastValue[:,np.newaxis]
            if cmd['type'] == 'step':
                pos = cmd['pos']
                if pos == None:
                    pos = self.dev.getOffVoltage()
                else:
                    pos = self.mapToScanner(pos[0], pos[1])
                lastPos = pos
                
                arr[0, startInd] = pos[0]
                arr[1, startInd] = pos[1]
                
            elif cmd['type'] == 'line':
                if lastPos is None:
                    raise Exception("'line' command with no defined starting position")
                pos = cmd['pos']
                
                xPos = linspace(lastPos[0], pos[0], stopInd-startInd)
                yPos = linspace(lastPos[1], pos[1], stopInd-startInd)
                x, y = self.mapToScanner(xPos, yPos)
                arr[0, startInd:stopInd] = x
                arr[1, startInd:stopInd] = y
                lastPos = pos
                
            elif cmd['type'] == 'lineScan':
                startPos = cmd['points'][0]                
                stopPos = cmd['points'][1]               
                scanLength = (stopInd - startInd)/cmd['nScans'] # in point indices, not time.
                retraceLength = cmd['retraceDuration']/dt
                scanLength = scanLength - retraceLength # adjust for retrace
                scanPause = np.ones(int(retraceLength))
                scanPointList = []
                cmd['samplesPerScan'] = scanLength
                cmd['samplesPerPause'] = scanPause.shape[0]
                xPos = np.linspace(startPos.x(), stopPos.x(), scanLength)
                xPos = np.append(xPos, startPos.x()*scanPause)
                scanPointList.append(int(scanLength/dt))
                cmd['scanPointList'] = scanPointList
                yPos = np.linspace(startPos.y(), stopPos.y(), scanLength)
                yPos = np.append(yPos, startPos.x()*scanPause)
                x, y = self.mapToScanner(xPos, yPos)
                x = np.tile(x, cmd['nScans'])
                y = np.tile(y, cmd['nScans'])
                arr[0, startInd:startInd + len(x)] = x
                arr[1, startInd:startInd + len(y)] = y
                arr[0, startInd + len(x):stopInd] = arr[0, startInd + len(x)-1] # fill in any unused sample on this scan section
                arr[1, startInd + len(y):stopInd] = arr[1, startInd + len(y)-1]
                lastPos = (x[-1], y[-1])

            elif cmd['type'] == 'multipleLineScan':
                """
                Use a polyline to make a scan that covers multiple regions in an
                interleaved fashion. Alternate line segments of the polyline
                are either the "scan" or the "interscan", allowing rapid movement
                between successive points. 
                Interscan intervals are green on the line, scan intervals are white
                """
                pts = map(pg.Point, cmd['points'])
                startPos = pts[0]                
                stopPos = pts[-1]
                
                #scanPoints = cmd['sweepDuration']/dt # in point indices, not time.
                #interTracePoints = cmd['intertraceDuration']/dt
                #scanPause = np.ones(int(interTracePoints))
                #cmd['samplesPerScan'] = scanPoints
                #cmd['samplesPerPause'] = interTracePoints
                sweepSpeed = 1000*cmd['sweepSpeed'] # in m/msec
                interSweepSpeed = 1000*cmd['interSweepSpeed']
                ScanFlag = False
                xp = np.array([])
                yp = np.array([])
                pockels = np.array([])
                nSegmentScans = 0
                nIntersegmentScans = 0
                scanPointList = []
                interScanFlag = False
                for k in xrange(len(pts)): # loop through the list of points
                    k2 = k + 1
                    if k2 > len(pts)-1:
                        k2 = 0
                    dist = (pg.Point(pts[k]-pts[k2])).length()
                    if interScanFlag is False:
                        scanPoints = int((dist/sweepSpeed)/dt)
                        xPos = np.linspace(pts[k].x(), pts[k2].x(), scanPoints)
                        yPos = np.linspace(pts[k].y(), pts[k2].y(), scanPoints)
                        pockels = np.append(pockels, np.ones(scanPoints))
                        nSegmentScans += 1
                        scanPointList.append(scanPoints)
                    else:
                        interSweepPoints = int((dist/interSweepSpeed)/dt)
                        xPos = np.linspace(pts[k].x(), pts[k2].x(), interSweepPoints)
                        yPos = np.linspace(pts[k].y(), pts[k2].y(), interSweepPoints)
                        pockels = np.append(pockels, np.zeros(interSweepPoints))
                        nIntersegmentScans += 1
                        scanPointList.append(interSweepPoints)
                    x, y = self.mapToScanner(xPos, yPos)
                    xp = np.append(xp, x)
                    yp = np.append(yp, y)
                    interScanFlag = not interScanFlag
                    
                cmd['nSegmentScans'] = nSegmentScans
                cmd['nIntersegmentScans'] = nIntersegmentScans
                cmd['scanPointList'] = scanPointList
                x = np.tile(xp, cmd['nScans'])
                y = np.tile(yp, cmd['nScans'])
                arr[0, startInd:startInd + len(x)] = x
                arr[1, startInd:startInd + len(y)] = y
                arr[0, startInd + len(x):stopInd] = arr[0, startInd + len(x)-1] # fill in any unused sample on this scan section
                arr[1, startInd + len(y):stopInd] = arr[1, startInd + len(y)-1]
                lastPos = (x[-1], y[-1])
                
            elif cmd['type'] == 'rectScan':
                pts = cmd['points']
               # print 'cmd: ', cmd
                self.SUF.setLaserDev(self.cmd['laser'])
                width  = (pts[1] -pts[0]).length() # width is x in M
                height = (pts[2]- pts[0]).length() # heigh in M
                rect = [pts[0][0], pts[0][1], width, height]
                overScanPct = cmd['overScan']
                self.SUF.setRectRoi(pts)
                self.SUF.setOverScan(overScanPct)
                self.SUF.setDownSample(1)
                self.SUF.setBidirectional(True)
                pixelSize = cmd['pixelSize']
                # recalulate pixelSize based on:
                # number of scans (reps) and total duration
                nscans = cmd['nScans']
                dur = cmd['duration']#  - cmd['startTime'] # time for nscans
                durPerScan = dur/nscans # time for one scan
                printParameters = False
                self.SUF.setPixelSize(cmd['pixelSize']) # pixelSize/np.sqrt(pixsf)) # adjust the pixel size
                self.SUF.setSampleRate(1./dt) # actually this is not used... 
                (x,y) = self.SUF.designRectScan() # makes one rectangle
                effScanTime = (self.SUF.getPixelsPerRow()/pixelSize)*(height/pixelSize)*dt # time it actually takes for one scan 
                pixsf = durPerScan/effScanTime # correction for pixel size based pm to,e

                cmd['imageSize'] = (self.SUF.getPixelsPerRow(), self.SUF.getnPointsY())

                if printParameters:
                    print 'scans: ', nscans
                    print 'width: ', width
                    print 'points in width: ', width/pixelSize
                    print 'dt: ', dt
                    print 'points in a scan: ', (width/pixelSize)*(height/pixelSize)
                    print 'effective scan time: ', effScanTime
                    print 'pixsf: ', pixsf
                    print 'original: ', pixelSize
                    print 'new pix size: ', pixelSize*pixsf
               
                n = self.SUF.getnPointsY() # get number of rows
                m = self.SUF.getPixelsPerRow() # get nnumber of points per row

                ## Build array with scanner voltages for rect repeated once per scan
                for i in range(cmd['nScans']):
                    thisStart = startInd+i*n*m
                    arr[0, thisStart:thisStart + len(x)] = x
                    arr[1, thisStart:thisStart + len(y)] = y
                arr[0, startInd+n*m*cmd['nScans']:stopInd] = arr[0, startInd+n*m*cmd['nScans'] -1] # fill in any unused sample on this scan section
                arr[1, startInd+n*m*cmd['nScans']:stopInd] = arr[1, startInd+n*m*cmd['nScans'] -1]
                lastPos = (x[-1], y[-1])
            
            
            # A side-effect modification of the 'command' dict so that analysis can access
            # this information later
            cmd['startStopIndices'] = (startInd, stopInd)
            cmd['scanParameters'] = self.SUF.packScannerParams()
            cmd['scanInfo'] = self.SUF.getScanInfo()
            lastValue = arr[:,stopInd-1]
            lastStopInd = stopInd
            
            
        arr[:,lastStopInd:] = lastValue[:,np.newaxis]
        
        return arr