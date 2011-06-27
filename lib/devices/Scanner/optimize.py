import numpy as np
from debug import Profiler

def optimizeSequence(locations, costFn):
    ## determine an optimal sequence of locations to stimulate
    ## given that nearby points may not be stimulated close together in time
    
    ## locations is a list of (x,y) tuples
    ## return value is a sorted list of tuples: ((x,y), time)
    ##    where 'time' is the minimum interval before stimulating the current spot.
    
    #prof2 = Profiler('     findSolution()')
    targetNumber = len(locations)
    locations = locations[:]
    np.random.shuffle(locations)
    #prof2.mark('setup')
    
    #### Try sorting points into quadrants to make both computing order and scanning faster -- use this as a best guess to compute order
    locs = np.array(locations, [('x', float),('y', float)])
    medx = np.median(locs['x'])
    medy = np.median(locs['y'])
    
    ## sort spots into quadrants
    quad1 = locs[(locs['x'] <= medx)*(locs['y'] > medy)]
    quad2 = locs[(locs['x'] > medx)*(locs['y'] > medy)]
    quad3 = locs[(locs['x'] <= medx)*(locs['y'] <= medy)]
    quad4 = locs[(locs['x'] > medx)*(locs['y'] <= medy)]
    
    ## rearrange spots so that sets of 4 (1 from each quadrant) can be added to the locations list
    minLen = min([len(quad1), len(quad2), len(quad3), len(quad4)])
    locs = np.zeros((minLen, 4), [('x', float), ('y', float)])
    locs[:,0] = quad1[:minLen]
    locs[:,1] = quad2[:minLen]
    locs[:,2] = quad3[:minLen]
    locs[:,3] = quad4[:minLen]
    
    ## add sets of 4 spots to list
    #locations = []
    #for i in range(minLen):
        #locations += locs[i].tolist()
    locations = locs.flatten().tolist()
        
    ## add any remaining spots that didn't fit evenly into the locs array
    for q in [quad1, quad2, quad3, quad4]:
        if minLen < len(q):
            locations += q[minLen:].tolist()
            
    #print "Target Number: ", targetNumber, "    locations: ", len(locations)
    
    #### Compute order 
    if True:
        solution = [(locations.pop(), 0.0)]
        while len(locations) > 0:
            #prof2.mark('lenLocations: %i' %len(locations))
            minTime = None
            minIndex = None
            n=len(locations)-1
            for i in range(len(locations)):
                #if i > n:
                    #break
                #prof2.mark(i)
                time, dist = computeTime(solution, locations[i], costFn)
                #prof2.mark('found time')
                if minTime is None or time < minTime:
                    minTime = time
                    minIndex = i
                if time == 0.0:  ## can't get any better; stop searching
                    #solution.append((locations.pop(i), time))
                    #n-=1
                    break
            solution.append((locations.pop(minIndex), minTime))
            yield((len(solution), len(locations)+len(solution)))
        #prof2.finish()
        yield solution, None
        #return solution
    
    
        

def computeTime(solution, loc, func):
    """Return the minimum time that must be waited before stimulating the location, given that solution has already run"""
    #if func is None:
        #func = self.costFunction()
    #minDist = state['minDist']
    #minTime = state['minTime']
    minWaitTime = 0.0
    cumWaitTime = 0
    for i in range(len(solution)-1, -1, -1):
        l = solution[i][0]
        dx = loc[0] - l[0]
        dy = loc[1] - l[1]
        dist = (dx **2 + dy **2) ** 0.5
        #if dist > minDist:
            #time = 0.0
        #else:
        time = max(0.0, func(dist) - cumWaitTime)
        #print i, "cumulative time:", cumWaitTime, "distance: %0.1fum" % (dist * 1e6), "time:", time
        minWaitTime = max(minWaitTime, time)
        cumWaitTime += solution[i][1]
        if cumWaitTime > minTime:
            #print "break after", len(solution)-i
            break
    #print "--> minimum:", minWaitTime
    return minWaitTime, dist







if __name__ == '__main__':
    import sys, os
    path = os.path.abspath(os.path.split(__file__)[0])
    sys.path.append(os.path.join(path, '..', '..', 'util'))
    
    import user, time, collections
    from PyQt4 import QtGui, QtCore
    import pyqtgraph as pg
    app = QtGui.QApplication([])
    
    minTime = 10.
    minDist = 0.5e-3
    b = np.log(0.1) / minDist**2
    costCache = {}
    def costFn(dist):
        global costCache, b, minTime
        try:
            cost = costCache[dist]
        except KeyError:
            cost = minTime * np.exp(b * dist**2)
            costCache[dist] = cost
        return cost
    
    locSets = collections.OrderedDict()

    def check(a, b):
        bLocs = [x[0] for x in b]
        bTimes = [x[1] for x in b]
        if len(a) != len(b):
            print "  WARNING: optimize changed size of list"
            return
        for i in range(len(a)):
            if a[i] not in bLocs:
                print "  WARNING: optimize changed contents of list"
                print a[i], "not in solution"
                return
            elif bLocs[i] not in a:
                print "  WARNING: optimize changed contents of list"
                print bLocs[i], "not in original"
                return
        #print "List check OK"
        print "  total cost:\t%0.1f" % sum(bTimes)
        print "  max interval:\t%0.1f" % max(bTimes)


    view = pg.GraphicsWindow()
    view.show()
    for d in [0.2e-3, 0.5e-3]:
        for n in [5, 10, 20]:
            locs = []
            for i in np.linspace(-d, d, n):
                for j in np.linspace(-d, d, n):
                    locs.append((i,j))
            key = "grid\td=%0.1gmm\tn=%d" % (d*2000, n)
            locSets[key] = locs
            
            print key
            start = time.time()
            for step, last in optimizeSequence(locs, costFn):
                if last is None:
                    l2 = step
                else:
                    pass
                    #print step, '/', last
            print "  compute time:\t%0.1f" % (time.time()-start)
            
            check(locs, l2)
            
            vb = pg.ViewBox()
            view.addItem(vb)
            data = [{'pos': l2[i][0], 'brush': (i * 255/ len(l2),)*3} for i in range(len(l2))]
            
            sp = pg.ScatterPlotItem(data, pen='w', pxMode=False, size=1e-4)
            vb.addItem(sp)
            vb.autoRange()
        view.nextRow()
        
    #views = []
    #for k, locs in locSets.iteritems():
        #print k
        #start = time.time()
        #for step, last in optimizeSequence(locs, costFn):
            #if last is None:
                #l2 = step
            #else:
                #pass
                ##print step, '/', last
        #print "  compute time:\t%0.1f" % (time.time()-start)
        
        #check(locs, l2)
        
        #v = pg.GraphicsWindow(title=k)
        #v.vb = pg.ViewBox()
        #v.setCentralItem(v.vb)
        #v.show()
        #data = [{'pos': l2[i][0], 'brush': (i * 255/ len(l2),)*3} for i in range(len(l2))]
        
        #sp = pg.ScatterPlotItem(data, pen='w', pxMode=False, size=1e-4)
        #v.vb.addItem(sp)
        #v.vb.autoRange()
        #views.append(v)
        ##v.setRange(QtCore.QRectF(-0.002, -0.002, 0.004, 0.004))
    
    
    