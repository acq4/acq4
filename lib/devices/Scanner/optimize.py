import numpy as np
from debug import Profiler

#def optimizeSequence(locations, costFn):
    ### determine an optimal sequence of locations to stimulate
    ### given that nearby points may not be stimulated close together in time
    
    ### locations is a list of (x,y) tuples
    ### return value is a sorted list of tuples: ((x,y), time)
    ###    where 'time' is the minimum interval before stimulating the current spot.
    
    ##prof2 = Profiler('     findSolution()')
    #targetNumber = len(locations)
    #locations = locations[:]
    #np.random.shuffle(locations)
    ##prof2.mark('setup')
    
    ##### Try sorting points into quadrants to make both computing order and scanning faster -- use this as a best guess to compute order
    #locs = np.array(locations, [('x', float),('y', float)])
    #medx = np.median(locs['x'])
    #medy = np.median(locs['y'])
    
    ### sort spots into quadrants
    #quad1 = locs[(locs['x'] <= medx)*(locs['y'] > medy)]
    #quad2 = locs[(locs['x'] > medx)*(locs['y'] > medy)]
    #quad3 = locs[(locs['x'] <= medx)*(locs['y'] <= medy)]
    #quad4 = locs[(locs['x'] > medx)*(locs['y'] <= medy)]
    
    ### rearrange spots so that sets of 4 (1 from each quadrant) can be added to the locations list
    #minLen = min([len(quad1), len(quad2), len(quad3), len(quad4)])
    #locs = np.zeros((minLen, 4), [('x', float), ('y', float)])
    #locs[:,0] = quad1[:minLen]
    #locs[:,1] = quad2[:minLen]
    #locs[:,2] = quad3[:minLen]
    #locs[:,3] = quad4[:minLen]
    
    ### add sets of 4 spots to list
    ##locations = []
    ##for i in range(minLen):
        ##locations += locs[i].tolist()
    #locations = locs.flatten().tolist()
        
    ### add any remaining spots that didn't fit evenly into the locs array
    #for q in [quad1, quad2, quad3, quad4]:
        #if minLen < len(q):
            #locations += q[minLen:].tolist()
            
    ##print "Target Number: ", targetNumber, "    locations: ", len(locations)
    
    ##### Compute order 
    #if True:
        #solution = [(locations.pop(), 0.0)]
        #while len(locations) > 0:
            ##prof2.mark('lenLocations: %i' %len(locations))
            #minTime = None
            #minIndex = None
            #n=len(locations)-1
            #for i in range(len(locations)):
                ##if i > n:
                    ##break
                ##prof2.mark(i)
                #time, dist = computeTime(solution, locations[i], costFn)
                ##prof2.mark('found time')
                #if minTime is None or time < minTime:
                    #minTime = time
                    #minIndex = i
                #if time == 0.0:  ## can't get any better; stop searching
                    ##solution.append((locations.pop(i), time))
                    ##n-=1
                    #break
            #solution.append((locations.pop(minIndex), minTime))
            #yield((len(solution), len(locations)+len(solution)))
        ##prof2.finish()
        #yield solution, None
        ##return solution
    
    
        

#def computeTime(solution, loc, func):
    #"""Return the minimum time that must be waited before stimulating the location, given that solution has already run"""
    ##if func is None:
        ##func = self.costFunction()
    ##minDist = state['minDist']
    ##minTime = state['minTime']
    #minWaitTime = 0.0
    #cumWaitTime = 0
    #for i in range(len(solution)-1, -1, -1):
        #l = solution[i][0]
        #dx = loc[0] - l[0]
        #dy = loc[1] - l[1]
        #dist = (dx **2 + dy **2) ** 0.5
        ##if dist > minDist:
            ##time = 0.0
        ##else:
        #time = max(0.0, func(dist) - cumWaitTime)
        ##print i, "cumulative time:", cumWaitTime, "distance: %0.1fum" % (dist * 1e6), "time:", time
        #minWaitTime = max(minWaitTime, time)
        #cumWaitTime += solution[i][1]
        #if cumWaitTime > minTime:
            ##print "break after", len(solution)-i
            #break
    ##print "--> minimum:", minWaitTime
    #return minWaitTime, dist



def opt2(locs, costFn, deadTime, greed=1.0, seed=None):
    ## Generally greed=1 gives the fastest solution, but not necessarily the most ideal.
    gFactor = np.clip(1.0-greed, 0, 0.9999)
    
    locArr = np.array(locs)
    
    # select a random starting point
    if seed is not None:
        np.random.seed(seed)
    i = np.random.randint(len(locs))
    
    ## initialize variables before loop
    order = [(locs[i], 0.0)]
    cost = np.zeros(len(locs), dtype=[('cost', float), ('index', int)])
    cost['index'] = np.arange(len(locs))
    locRem = locArr[:]
    
    ## add the rest of the points in optimal order
    while len(order) < len(locs):
        # remove the currently visited point from location and cost arrays
        mask = cost['index'] != i
        locRem = locRem[mask]      ## array of remaining locations
        cost = cost[mask]          ## previous costs for remaining locations
        
        dist = np.sqrt(((locRem-locArr[i])**2).sum(axis=1))  ## distances from current point to each remaining location

        ## subtract last point's cost, since this has already been paid
        cost['cost'] = np.clip(cost['cost']-order[-1][1], 0, np.inf)

        ## Compute direct costs and take the max value of direct and leftover cost
        dCost = costFn(dist)
        cost['cost'] = np.where(dCost > cost['cost'], dCost, cost['cost'])
        
        ## subtract off dead time
        cost['cost'] = np.clip(cost['cost']-deadTime, 0, np.inf)
        
        ## sort by cost, find the median cost
        sortedCost = np.sort(cost, order=['cost'])
        mid = int(len(sortedCost) * gFactor)
        medianCost = sortedCost[mid]['cost']
        
        ## select one point randomly from all points with that cost value
        nextPts = sortedCost[sortedCost['cost'] == medianCost]
        i2 = np.random.randint(len(nextPts))
        i = nextPts[i2]['index']
        
        #mask[i] = False
        order.append((locs[i], nextPts[i2]['cost']))
        
        ##send progress report
        r = len(order)/float(len(locs))
        yield 2*r - r**2, 1.0
    
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
    #def costFn(dist):
        #global costCache, b, minTime
        #try:
            #cost = costCache[dist]
        #except KeyError:
            #cost = minTime * np.exp(b * dist**2)
            #costCache[dist] = cost
        #return cost

    def costFn2(dist):
        ### Takes distance^2 as argument!
        global minTime, minDist
        A = 2 * minTime / minDist**2
        return np.where(
            dist < minDist, 
            np.where(
                dist < minDist/2., 
                minTime - A * dist**2, 
                A * (dist-minDist)**2
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
    for d in [0.2e-3, 0.5e-3, 1e-3]:
        for greed in [1.0]:
            for n in [20, 20, 20, 20, 20]:
                locs = []
                for i in np.linspace(-d, d, n):
                    for j in np.linspace(-d, d, n):
                        locs.append((i,j))
                key = "grid\td=%0.1gmm\tn=%d\tgreed=%0.2g" % (d*2000, n, greed)
                locSets[key] = locs
                
                start = time.time()
                for step, last in opt2(locs, costFn2, deadTime, greed=greed):
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
                
                ## number spots
                #for i in range(len(data)):
                    #t = QtGui.QGraphicsTextItem()
                    #t.setHtml('<span style="color: #f00">%d</span>'%i)
                    #t.setFlag(t.ItemIgnoresTransformations, True)
                    #t.setPos(*l2[i][0])
                    #vb.addItem(t)
                
                vb.setRange(sp.boundingRect())
                
                ### show video of sequence
                #img = np.zeros((n**2, n, n, 3), dtype=float)
                #l3 = [x[0] for x in l2]
                #l3.sort(lambda a,b: cmp(a[0], b[0]) if a[0]!= b[0] else cmp(a[1], b[1]))
                #l3 = np.array(l3)
                #indx = ((n-1) * (l3[0]+d) / (2*d)).astype(int)
                #indy = ((n-1) * (l3[1]+d) / (2*d)).astype(int)
                #for i in range(n**2):
                    #if i > 0:
                        #img[i] = img[i-1]
                        
                    #dist = np.sqrt(((l3-l2[i][0])**2).sum(axis=1))  ## distances from current point to each remaining location
                    
                    #img[i,:,:,1:] = np.clip(img[i,:,:,1:] - (deadTime + l2[i][1]), 0, minTime)

                    ### Compute direct costs and take the max value of direct and leftover cost
                    #dCost = costFn2(dist)
                    #dCost.shape = (n,n,1)
                    
                    #img[i,:,:,1:] = np.where(dCost > img[i,:,:,1:], dCost, img[i,:,:,1:])
                    
                    
                    #x = int(((n-1) * (l2[i][0][0]+d) / (2*d))+0.5)
                    #y = int(((n-1) * (l2[i][0][1]+d) / (2*d))+0.5)
                    #img[i,x,y,0] = 7
                    ##img[i, x, y] = minTime
                #view2 = pg.show(img, title=key)
                
                
                
            view.nextRow()
            print ""
        view.nextRow()
        print ""
    view.show()
        
    