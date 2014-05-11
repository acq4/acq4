import numpy as np
import acq4.pyqtgraph as pg
from .component import ScanProgramComponent



class LineScanComponent(ScanProgramComponent):
    """
    Scans the laser over a path composed of multiple line segments.
    """
    name = 'step'

    #elif cmd['type'] == 'line':
        #if lastPos is None:
            #raise Exception("'line' command with no defined starting position")
        #pos = cmd['pos']
        
        #xPos = linspace(lastPos[0], pos[0], stopInd-startInd)
        #yPos = linspace(lastPos[1], pos[1], stopInd-startInd)
        #x, y = self.mapToScanner(xPos, yPos)
        #arr[0, startInd:stopInd] = x
        #arr[1, startInd:stopInd] = y
        #lastPos = pos
        
    #elif cmd['type'] == 'lineScan':
        #startPos = cmd['points'][0]                
        #stopPos = cmd['points'][1]               
        #scanLength = (stopInd - startInd)/cmd['nScans'] # in point indices, not time.
        #retraceLength = cmd['retraceDuration']/dt
        #scanLength = scanLength - retraceLength # adjust for retrace
        #scanPause = np.ones(int(retraceLength))
        #scanPointList = []
        #cmd['samplesPerScan'] = scanLength
        #cmd['samplesPerPause'] = scanPause.shape[0]
        #xPos = np.linspace(startPos.x(), stopPos.x(), scanLength)
        #xPos = np.append(xPos, startPos.x()*scanPause)
        #scanPointList.append(int(scanLength/dt))
        #cmd['scanPointList'] = scanPointList
        #yPos = np.linspace(startPos.y(), stopPos.y(), scanLength)
        #yPos = np.append(yPos, startPos.x()*scanPause)
        #x, y = self.mapToScanner(xPos, yPos)
        #x = np.tile(x, cmd['nScans'])
        #y = np.tile(y, cmd['nScans'])
        #arr[0, startInd:startInd + len(x)] = x
        #arr[1, startInd:startInd + len(y)] = y
        #arr[0, startInd + len(x):stopInd] = arr[0, startInd + len(x)-1] # fill in any unused sample on this scan section
        #arr[1, startInd + len(y):stopInd] = arr[1, startInd + len(y)-1]
        #lastPos = (x[-1], y[-1])

    def generateVoltageArray(self, arr, startInd, stopInd):
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
        
        return stopInd
    