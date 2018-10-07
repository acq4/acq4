from __future__ import print_function
import numpy as np
#from debug import Profiler

def opt2(locs, minTime, minDist, deadTime, greed=1.0, seed=None, compMethod='rms'):
    ## compMethod defines how costs are composited. 
    ##   values are 'rms', 'max', 'sum'
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
        dCost = costFn(dist, minTime, minDist)
        if compMethod == 'max':
            cost['cost'] = np.where(dCost > cost['cost'], dCost, cost['cost'])
        elif compMethod == 'rms':
            cost['cost'] = np.sqrt(cost['cost']**2 + dCost**2)
        elif compMethod == 'sum':
            cost['cost'] += dCost
        
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
        #print "yield prg"
        yield 2*r - r**2, 1.0
        
    #print "yield result"
    yield order, None
        
    
def costFn(dist, minTime, minDist):
    #state = self.stateGroup.state()
    #minTime = state['minTime']
    #minDist = state['minDist']
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
    



if __name__ == '__main__':
    import sys, os
    path = os.path.abspath(os.path.split(__file__)[0])
    sys.path.append(os.path.join(path, '..', '..', 'util'))
    
    import user, time, collections
    from acq4.util import Qt
    import acq4.pyqtgraph as pg
    app = Qt.QApplication([])
    
    minTime = 10.
    minDist = 0.5e-3
    b = np.log(0.1) / minDist**2
    costCache = {}
    deadTime = 1.0  ## mandatory waiting time between stimuli due to recording length
    locSets = collections.OrderedDict()

    def check(a, b):
        bLocs = [x[0] for x in b]
        bTimes = [x[1] for x in b]
        if len(a) != len(b):
            print("  WARNING: optimize changed size of list")
            return
        for i in range(len(a)):
            if a[i] not in bLocs:
                print("  WARNING: optimize changed contents of list")
                print(a[i], "not in solution")
                return
            elif bLocs[i] not in a:
                print("  WARNING: optimize changed contents of list")
                print(bLocs[i], "not in original")
                return
        #print "List check OK"


    view = pg.GraphicsWindow(border=(50, 50, 50))
    greed = 1.0
    for d in [0.2e-3, 0.5e-3, 2e-3]:
        for n in [20]:
            for compMethod in ['max', 'rms', 'sum']:
                locs = []
                for i in np.linspace(-d, d, n):
                    for j in np.linspace(-d, d, n):
                        locs.append((i,j))
                key = "grid\td=%0.1gmm\tn=%d\tgreed=%0.2g" % (d*2000, n, greed)
                locSets[key] = locs
                
                start = time.time()
                for step, last in opt2(locs, minTime, minDist, deadTime, greed=greed, compMethod=compMethod):
                    if last is None:
                        l2 = step
                    else:
                        pass
                bTimes = [x[1] for x in l2]
                print(key, "  \tcompute time:\t%0.1f  \ttotal cost:\t%0.1f  \tmax interval:\t%0.1f\t" % (
                    time.time()-start,
                    sum(bTimes),
                    max(bTimes)
                ))
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
                    #t = Qt.QGraphicsTextItem()
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
            print("")
        view.nextRow()
        print("")
    view.show()
        
    