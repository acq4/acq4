# -*- coding: utf-8 -*-
import numpy as np
import acq4.pyqtgraph as pg
from acq4.util.HelpfulException import HelpfulException

class ScanProgramGenerator:
    def __init__(self, dev, command):
        self.dev = dev
        self.cmd = command 
    
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
        arr = np.empty((2, command['numPts']))        
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
            #print dt
            #print arr.shape
            if stopInd >= arr.shape[1]:
                raise HelpfulException('Scan Program duration is longer than protocol duration') 
            arr[:,lastStopInd:startInd] = lastValue[:,np.newaxis]
            if cmd['type'] == 'step':
                pos = cmd['pos']
                if pos == None:
                    pos = self.dev.getOffVoltage()
                else:
                    pos = self.dev.mapToScanner(pos[0], pos[1], self.cmd['laser'])
                lastPos = pos
                
                arr[0, startInd] = pos[0]
                arr[1, startInd] = pos[1]
                
            elif cmd['type'] == 'line':
                if lastPos is None:
                    raise Exception("'line' command with no defined starting position")
                pos = cmd['pos']
                
                xPos = linspace(lastPos[0], pos[0], stopInd-startInd)
                yPos = linspace(lastPos[1], pos[1], stopInd-startInd)
                x, y = self.dev.mapToScanner(xPos, yPos, self.cmd['laser'])
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
                x, y = self.dev.mapToScanner(xPos, yPos, self.cmd['laser'])
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
                    x, y = self.dev.mapToScanner(xPos, yPos, self.cmd['laser'])
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
                width  = (pts[1] -pts[0]).length() # width is x in M
                height = (pts[2]- pts[0]).length() # heigh in M
                n = int(height /cmd['lineSpacing']) # number of rows scanned
                assert n > 0
                m = int((stopInd - startInd)/(n * cmd['nScans'])) # number of points per row
                assert m > 0
                r = np.mgrid[0:m, 0:n].reshape(1,2,m,n) 
                # convert image coordinates to physical coordinates to pass to scanner.
                dx = (pts[1] - pts[0])/m # step size per "pixel" in x
                dy = (pts[2] - pts[0])/n # step size per "pixel" in y
                v = np.array([[dx[0], dy[0]], [dx[1], dy[1]]]).reshape(2,2,1,1) 
                q = (v*r).sum(axis=1)
                q += np.array(pts[0]).reshape(2,1,1)
                q = q.transpose(0,2,1).reshape(2,m*n)
                # convert physical coordinates to scanner voltages
                x, y = self.dev.mapToScanner(q[0], q[1], self.cmd['laser'])
                #cmd['xy'] = (x,y)
                cmd['imageSize'] = (m,n)                    
                # repeat scanner voltages once per scan
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
            lastValue = arr[:,stopInd-1]
            lastStopInd = stopInd
        arr[:,lastStopInd:] = lastValue[:,np.newaxis]
        return arr