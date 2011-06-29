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



def opt2(locs, costFn, greed=0.8):
    ## greed=1 means very greedy; will always pick from the best available spots
    ## greed=0 means altruistic; will always pick from the worst available spots
    ## greed=0.8 performs almost as well as 1.0, but avoids clustering into the center.
    
    
    gFactor = np.clip(1.0-greed, 0, 0.9999)
    
    #l = np.empty((len(locs), 2))
    #for i in xrange(len(locs)):
        #l[i] = locs[i]
    l = np.array(locs)
    
    #l1 = l[np.newaxis,...]
    #l2 = l[:,np.newaxis]
    
    #d = ((l2-l1)**2).sum(axis=2)  ## compute distance^2 between each pair of points (twice)
    
    ## Couple distances with indexes for sorting later
    #di = np.empty(d.shape, dtype=[('dist', float), ('index', int)])
    #di['dist'] = d
    #di['index'] = np.arange(d.shape[0])
    
    ## mask of points not yet taken
    mask = np.ones(len(locs), dtype=bool)
    
    # select a random point
    i = int(np.random.random()*len(locs))
    mask[i] = False
    order = [(locs[i], 0.0)]
    
    ## add the rest of the points in optimal order
    
    ## initialize variables before loop
    totCost = np.zeros(len(locs), dtype=[('cost', float), ('index', int)])
    totCost['index'] = np.arange(len(locs))
    cost = 0
    
    while len(order) < len(locs):
        #p = Profiler('inner loop')
        #print "\n=============\n%d: Point %d has been selected." % (len(order)-1, i)
        #dist = di[i][mask]  ## set of distances and indexes to all remaining points
        lm = l[mask]  ## set of locations remaining
        dist = np.empty(len(lm), dtype=[('dist', float), ('index', int)])
        dist['dist'] = ((lm-l[i])**2).sum(axis=1)  ## distances from current point to each remaining location
        dist['index'] = np.arange(len(l))[mask]    ## .. and their corresponding indexes

        
        ## compute direct cost of visiting each point
        ## (but remember that the TOTAL cost depends on the previous history of points as well)
        dCost = np.empty(len(dist), dtype=[('cost', float), ('index', int)])
        #p.mark('setup')
        #for j in range(len(dCost)):
            #dCost[j]['cost'] = costFn(dist[j]['dist'])
        dCost['cost'] = costFn(dist['dist'])
        #p.mark('compute cost')
        dCost['index'] = dist['index']
        #p.mark('copy')
        
        #print "direct costs:", dCost
        
        # first remove the currently visited point from total cost array
        totCost = totCost[totCost['index'] != i]
        
        #print "previous costs:", totCost
        
        ## next subtract the previous cost, since this has already been paid
        totCost['cost'] = np.clip(totCost['cost']-cost, 0, np.inf)

        #print "previous costs, adjusted:", totCost

        ## finally, add in the set of new costs
        totCost['cost'] = np.where(dCost['cost'] > totCost['cost'], dCost['cost'], totCost['cost'])
        #p.mark('add')

        #print "total costs:", totCost
        
        ## Check that we did it correctly:
        #assert all(totCost['index'] == dCost['index'])
        #for j in range(len(totCost)):
            #if totCost['index'][j] not in dCost['index'] or dCost['index'][j] not in totCost['index']:
                #print "==========================================="
                #print totCost
                #print "---------------"
                #print dCost
                #print "---------------"
                #print j, totCost['index'][j], dCost['index'][j]
                #raise Exception("Somebody screwed up.")
        
        ## sort by cost, find the median cost
        sortedCost = np.sort(totCost, order=['cost'])
        #p.mark('sort')
        mid = int(len(sortedCost) * gFactor)
        medianCost = sortedCost[mid]['cost']
        
        
        ## select one point randomly from all points with that cost value
        nextPts = sortedCost[sortedCost['cost'] == medianCost]
        i2 = int(np.random.random() * len(nextPts))
        i = nextPts[i2]['index']
        cost = nextPts[i2]['cost']
        #p.mark('select')
        
        #print "next point will be %d, cost is %f" % (i, cost)
        
        mask[i] = False
        order.append((locs[i], cost))
        #p.finish()
        yield len(order), len(locs)
    
    yield order, None
        
    
    



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
    deadTime = 1.0  ## mandatory waiting time between stimuli due to recording length
    def costFn(dist):
        global costCache, b, minTime
        try:
            cost = costCache[dist]
        except KeyError:
            cost = minTime * np.exp(b * dist**2)
            costCache[dist] = cost
        return cost

    def costFn2(dist2):
        ### Takes distance^2 as argument!
        global minTime, deadTime, minDist
        A = 2 * minTime / minDist**2
        return np.where(
            dist2 < minDist, 
            np.where(
                dist2 < minDist/2., 
                minTime - A * dist2, 
                A * (dist2**0.5-minDist)**2
            ), 
            0
        )


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


    view = pg.GraphicsWindow(border=(50, 50, 50))
    for d in [0.2e-3, 0.5e-3, 1.0e-3]:#[0.2e-3, 0.5e-3, 2e-3]:
        for n in [20]:
            for greed in [0.0, 0.5, 1.0]:
                locs = []
                for i in np.linspace(-d, d, n):
                    for j in np.linspace(-d, d, n):
                        locs.append((i,j))
                key = "grid\td=%0.1gmm\tn=%d\tgreed=%0.2g" % (d*2000, n, greed)
                locSets[key] = locs
                
                start = time.time()
                for step, last in opt2(locs, costFn2, greed=greed):
                    if last is None:
                        l2 = step
                    else:
                        pass
                bTimes = [x[1] for x in l2]
                print key, "  \tcompute time:\t%0.1f  \ttotal cost:\t%0.1f  \tmax interval:\t%0.1f\t" % (
                    time.time()-start,
                    sum(bTimes),
                    max(bTimes)
                )
                #print "  total cost:\t%0.1f" % sum(bTimes)
                #print "  max interval:\t%0.1f" % max(bTimes)
                
                check(locs, l2)
                
                vb = pg.ViewBox()
                view.addItem(vb)
                data = [{'pos': l2[i][0], 'brush': (i * 255/ len(l2),)*3} for i in range(len(l2))]
                
                sp = pg.ScatterPlotItem(data, pen=0.3, pxMode=False, size=1e-4)
                vb.addItem(sp)
                #for i in range(len(data)):
                    #t = QtGui.QGraphicsTextItem()
                    #t.setHtml('<span style="color: #f00">%d</span>'%i)
                    #t.setFlag(t.ItemIgnoresTransformations, True)
                    #t.setPos(*l2[i][0])
                    #vb.addItem(t)
                
                vb.setRange(sp.boundingRect())
            view.nextRow()
            print ""
        view.nextRow()
        print ""
    view.show()
        
    