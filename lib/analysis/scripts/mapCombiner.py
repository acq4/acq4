import lib.Manager
import numpy as np
import lib.analysis.tools.functions as afn
import scipy
from lib.util.pyqtgraph.multiprocess import Parallelize
from pyqtgraph.debug import Profiler
try:
    import cv2
    HAVE_CV2 = True
except ImportError:
    HAVE_CV2 = False
    


probabilityInputs = np.array([
    [[0,0,0], ## 2011.12.14 s0c1
     [0,1,1],
     [0,1,1],
     [1,0,0]],
    [[0,1,1], ## 2012.01.04 s1c0
     [1,1,1],
     [0,0,0],
     [1,0,0]],
    [[0,0,0], ## 2012.01.06 s0c1
     [0,1,1],
     [0,0,0],
     [0,0,1]],
    [[0,0,1], ## 2012.01.06 s1c0
     [0,1,0],
     [0,1,0],
     [0,0,0]],
    [[0,0,0], ## 2012.01.19 s0c0
     [0,0,0],
     [0,0,0],
     [0,0,0]],
    [[0,0,1], ## 2012.01.19 s0c1
     [1,1,1],
     [1,0,0],
     [0,1,0]],
    [[1,1,0], ## 2012.01,25 s0c0
     [0,1,1],
     [0,0,0],
     [0,1,1]],
    [[0,0,0], ## 2012.02.01 s0c0
     [0,1,0],
     [0,0,0],
     [0,0,0]],
    [[0,0,0], ## 2012.02.08 s0c0
     [1,1,0],
     [0,0,0],
     [1,0,0]],
    [[0,1,0], ## 2012.02.18 s0c0
     [0,1,0],
     [0,0,0],
     [0,1,0]], 
    [[0,0,0], ## 2012.02.18 s1c0
     [1,1,1],
     [0,0,0],
     [0,1,0]],
    [[0,0,1], ## 2012.02.18 s1c1
     [1,1,0],
     [0,0,1],
     [0,1,1]],
    [[0,0,1], ## 2012.02.20 s0c0
     [1,1,1],
     [0,0,0],
     [1,0,1]],
    [[0,1,0], ## 2012.02.22 s2c0
     [0,1,0], 
     [0,0,0],
     [0,0,0]],
    [[0,1,1], ## 2012.02.23 s1c0
     [0,1,0],
     [0,1,1],
     [0,0,1]],
    [[0,0,0], ## 2012.02.23 s1c1
     [0,1,0],
     [0,0,1],
     [1,0,0]],
    [[0,1,0], ## 2012.02.24 s0c0
     [1,1,0],
     [1,0,0],
     [1,1,0]],
    [[0,0,0], ## 2012.02.26 s0c0
     [1,1,1],
     [0,1,1],
     [0,1,0]],
    [[0,0,0], ## 2012.02.26 s1c1
     [0,1,0],
     [0,0,0],
     [1,1,1]],
    [[0,1,0], ## 2012.02.27 s0c0
     [0,1,1],
     [0,0,0],
     [1,1,0]],
    [[0,0,0], ## 2012.02.27 s0c1
     [0,1,0],
     [0,0,1],
     [0,1,0]],
    [[0,0,0], ## 2012.02.27 s1c0
     [1,1,1],
     [0,1,0],
     [1,1,1]]])
     
     

def reserveArray(data, spacing=5e-6):
    cells = set(data['CellDir'])
    n = len(cells)
    
    xmin = data['xPos'].min()
    ymin = data['yPos'].min()
    xdim = int((data['xPos'].max()-xmin)/spacing)+5
    ydim = int((data['yPos'].max()-ymin)/spacing)+5    
    
    return np.zeros((n, xdim, ydim), dtype=float)
    
    
def calculateProb(sites, spacing=5e-6, keys=None):
    cells = set(sites['CellDir'])
    arr = reserveArray(sites, spacing)
    
    for i, c in enumerate(cells):
        sites = data[data['CellDir']==c]
        spontRate = sites['numOfPreEvents'].sum()/sites['PreRegionLen'].sum()
        sites = afn.bendelsSpatialCorrelationAlgorithm(sites, 90e-6, spontRate, sites[0]['PostRegionLen'])
        for s in sites:
            x, y = (int((s['xPos']-xmin)/spacing), int((s['yPos']-ymin)/spacing))
            arr[i, x, y] = s['prob']
            
    return arr
        

def interpolateSlice(sites, spacing=5e-6, method='nearest', probThreshold=0.05):
    xmin = sites['xPos'].min()
    ymin = sites['yPos'].min()
    xdim = int((sites['xPos'].max()-xmin)/spacing)+5
    ydim = int((sites['yPos'].max()-ymin)/spacing)+5
    cells = set(sites['CellDir'])
    n = len(cells)
    
    arr = np.zeros((n, xdim, ydim), dtype=float)
    results = []
    
    for i, c in enumerate(cells):
        data = sites[sites['CellDir'] == c]
        pts = np.array([data['xPos'], data['yPos']], dtype=float)
        pts[0] = pts[0]-xmin
        pts[1] = pts[1]-ymin
        pts = pts.transpose()/spacing
        
        xi = np.indices((xdim, ydim))
        xi = xi.transpose(1,2,0)
        
        spontRate = data['numOfPreEvents'].sum()/data['PreRegionLen'].sum()
        data = afn.bendelsSpatialCorrelationAlgorithm(data, 90e-6, spontRate, data[0]['PostRegionLen'])
        
        #print data['prob'].max()
        data['prob'][data['prob'] < probThreshold] = 2.
       # print data['prob'].max()
        data['prob'][(data['prob'] >= probThreshold)*(data['prob']!= 2.)] = 0.
        data['prob'][data['prob'] == 2.] = 1.
        #print data['prob'].max()
        #print "========= ", data['prob'].mean()
    
        
        res = scipy.interpolate.griddata(pts, data['prob'], xi, method=method)
        arr[i] = res
        results.append(res)
        #arr[i][np.isnan(arr[i])] = .1
    
    return arr
    
def interpolateCells(sites, spacing=5e-6, method='nearest', probThreshold=0.05):
    avgCellX = np.array(list(set(sites['CellXPos']))).mean()
    avgCellY = np.array(list(set(sites['CellYPos']))).mean()
    xmin = (sites['xPos']-sites['CellXPos']).min() ## point furthest left of the cell
    ymin = (sites['yPos']-sites['CellYPos']).min() ## point furthest above the cell
    xmax = (sites['xPos']-sites['CellXPos']).max()
    ymax = (sites['yPos']-sites['CellXPos']).max()
    xdim = int((xmax-xmin)/spacing)+10
    ydim = int((ymax-ymin)/spacing)+10
    avgCellIndex = np.array([int((avgCellX-xmin)/spacing)+5, int((avgCellY-ymin)/spacing)+5])
    cells = set(sites['CellDir'])
    n = len(cells)
    
    arr = np.zeros((n, xdim, ydim), dtype=float)
    results = []
    print 'xdim:', xdim, 'ydim:', ydim
    for i, c in enumerate(cells):
        data = sites[sites['CellDir'] == c]
        trans1 = (data['CellXPos'][0] - avgCellX, data['CellYPos'][0]-avgCellY)
        trans2 = (avgCellX+xmin, avgCellY+ymin)
        pts = np.array([data['xPos']-trans1[0]-trans2[0], data['yPos']-trans1[1]-trans2[1]], dtype=float)
        #pts[0] = pts[0]+(avgCellX-xmin)
        #pts[1] = pts[1]+(avgCellY-ymin)
        xlimits = (int((data['xPos'].min()-trans1[0]-trans2[0])/spacing), int((data['xPos'].max()-trans1[0]-trans2[0])/spacing))
        ylimits = (int((data['yPos'].min()-trans1[1]-trans2[1])/spacing), int((data['yPos'].max()-trans1[1]-trans2[1])/spacing)) 
        print 'xlimits:', xlimits, '   ylimits:', ylimits
        pts = pts.transpose()/spacing 
        
        xi = np.indices((xdim, ydim))
        xi = xi.transpose(1,2,0)
        
        spontRate = data['numOfPreEvents'].sum()/data['PreRegionLen'].sum()
        data = afn.bendelsSpatialCorrelationAlgorithm(data, 90e-6, spontRate, data[0]['PostRegionLen'])
        
        #print data['prob'].max()
        data['prob'][data['prob'] < probThreshold] = 2.
       # print data['prob'].max()
        data['prob'][(data['prob'] >= probThreshold)*(data['prob']!= 2.)] = 0.
        data['prob'][data['prob'] == 2.] = 1.
        #print data['prob'].max()
        #print "========= ", data['prob'].mean()
    
        
        res = scipy.interpolate.griddata(pts, data['prob'], xi, method=method)
        res[:xlimits[0], :] = 0
        res[xlimits[1]+1:, :] = 0
        res[:, :ylimits[0]] = 0
        res[:, ylimits[1]+1:] = 0
        
        arr[i] = res
        results.append(res)
        #arr[i][np.isnan(arr[i])] = .1
    
    return arr, (xmin, ymin)
    
def convolveCells(sites, spacing=5e-6, probThreshold=0.02, probRadius=90e-6, timeWindow=0.1, eventKey='numOfPostEvents'):
    #avgCellX = np.array(list(set(sites['xPosCell']))).mean()
    #avgCellY = np.array(list(set(sites['yPosCell']))).mean()
    #xmin = (sites['xPos']-sites['xPosCell']).min() ## point furthest left of the cell
    xmin = sites['xPosCell'].min()
    #ymin = (sites['yPos']-sites['yPosCell']).min() ## point furthest above the cell
    ymin = sites['yPosCell'].min()
    #xmax = (sites['xPos']-sites['xPosCell']).max()
    xmax = sites['xPosCell'].max()
    #ymax = (sites['yPos']-sites['yPosCell']).max()
    ymax = sites['yPosCell'].max()
    xdim = int((xmax-xmin)/spacing)+10
    ydim = int((ymax-ymin)/spacing)+10
    #avgCellIndex = np.array([int((avgCellX-xmin)/spacing)+5, int((avgCellY-ymin)/spacing)+5])
    cells = set(sites['CellDir'])
    n = len(cells)
    
    arr = np.zeros((n, xdim, ydim), dtype=float)
    results = []
    
    for i, c in enumerate(cells):
        data = sites[sites['CellDir']==c]
        spontRate = data['numOfPreEvents'].sum()/data['PreRegionLen'].sum()
        data = afn.bendelsSpatialCorrelationAlgorithm(data, probRadius, spontRate, timeWindow=timeWindow, eventKey=eventKey)
  
        probs = np.zeros(len(data))
        probs[data['prob'] < probThreshold] = 1.
        for j, s in enumerate(data):
            trans1 = (data['CellXPos'][0] - avgCellX, data['CellYPos'][0]-avgCellY)
            trans2 = (avgCellX+xmin, avgCellY+ymin)            
            x, y = (int((s['xPos']-trans1[0]-trans2[0])/spacing), int((s['yPos']-trans1[1]-trans2[1])/spacing))
            arr[i, x, y] = probs[j]
              
        results.append(arr[i].copy())
        arr[i] = scipy.ndimage.gaussian_filter(arr[i], 2)
        arr[i] = arr[i]/0.039
        arr[i][arr[i] > 0.02] = 1
        #arr[i][(arr[i] > 0.02)*(arr[i] <=0.04)] = 1
        arr[i][arr[i] <= 0.02] = 0
        
    return arr, results
    
        
def convolveCells_Xuying(sites, spacing=5e-6, probThreshold=0.02, probRadius=90e-6):
    #avgCellX = np.array(list(set(sites['xPosCell']))).mean()
    #avgCellY = np.array(list(set(sites['yPosCell']))).mean()
    #xmin = (sites['xPos']-sites['xPosCell']).min() ## point furthest left of the cell
    xmin = sites['xPosCell'].min()
    #ymin = (sites['yPos']-sites['yPosCell']).min() ## point furthest above the cell
    ymin = sites['yPosCell'].min()
    #xmax = (sites['xPos']-sites['xPosCell']).max()
    xmax = sites['xPosCell'].max()
    #ymax = (sites['yPos']-sites['yPosCell']).max()
    ymax = sites['yPosCell'].max()
    xdim = int((xmax-xmin)/spacing)+10
    ydim = int((ymax-ymin)/spacing)+10
    #avgCellIndex = np.array([int((avgCellX-xmin)/spacing)+5, int((avgCellY-ymin)/spacing)+5])
    cells = set(sites['CellDir'])
    n = len(cells)
    
    arr = np.zeros((n, xdim, ydim), dtype=float)
    results = []
    
    #kernel = np.zeros((xdim, ydim))
    #midx = xdim/2
    #midy = ydim/2
    #radius = int((sampleSpacing)/spacing)
    #radius2 = radius**2
    #for x in range(midx-radius, midx+radius):
        #for y in range(midy - radius, midy+radius):
            #r2 = (x-radius)**2 + (y-radius)**2
            #if r2 <= radius2:
                #kernel[x,y] = 1 
    results = []
    for i, c in enumerate(cells):
        data = sites[sites['CellDir']==c]
        spontRate = data['numOfPreEvents'].sum()/data['PreRegionLen'].sum()
        data = afn.bendelsSpatialCorrelationAlgorithm(data, probRadius, spontRate, data[0]['PostRegionLen'])
        #data['prob'][data['prob'] < probThreshold] = 2.         
        #data['prob'][(data['prob'] >= probThreshold)*(data[i]['prob']!= 2.)] = 0.
        #data['prob'][data['prob'] == 2.] = 1. 
        probs = np.zeros(len(data))
        probs[data['prob'] < probThreshold] = 1.
        for j, s in enumerate(data):
            #trans1 = (data['xPosCell'][0] - avgCellX, data['yPosCell'][0]-avgCellY)
            #trans2 = (avgCellX+xmin, avgCellY+ymin)
            trans = (xmin, ymin)
            #x, y = (int((s['xPos']-trans1[0]-trans2[0])/spacing), int((s['yPos']-trans1[1]-trans2[1])/spacing))
            x, y = (int((s['xPosCell']-trans[0])/spacing), int((s['yPosCell'] - trans[1])/spacing))
            #print i, x, y, j
            arr[i, x, y] = probs[j] 
              
        results.append(arr[i].copy())
        arr[i] = scipy.ndimage.gaussian_filter(arr[i], 2)
        arr[i] = arr[i]/0.039
        #arr[i][arr[i] > 0.04] = 2
        #arr[i][(arr[i] > 0.02)*(arr[i] <=0.04)] = 1
        arr[i][arr[i] > 0.02] = 1
        arr[i][arr[i] <= 0.02] = 0
        
        #arr[i] = scipy.ndimage.convolve(arr[i], kernel)
        
    return arr, results
    
    #for p in params:
        #if 'mode' in params[p].keys():
            #arrs[p] = scipy.interpolate.griddata(pts, data[p], xi, method=params[p]['mode']) ## griddata function hangs when method='linear' in scipy versions earlier than 0.10.0
            #arrs[p][np.isnan(arrs[p])] = 0
    #return arrs
        
        
def convolveCells_newAtlas(sites, keys=None, factor=1.11849, spacing=5e-6, probThreshold=0.02, sampleSpacing=35e-6, eventKey=None, timeWindow=None):
    if keys == None:
        keys = {
            'x':'xPosCell',
            'y':'yPosCell',
            'mappedX': 'modXPosCell',
            'mappedY': 'percentDepth'}
    if eventKey == None:
        eventKey = 'numOfPostEvents'
    if timeWindow == None:
        timeWindow = sites[0]['PostRgnLen']
            
    #avgCellX = np.array(list(set(sites['CellXPos']))).mean()
    #avgCellY = np.array(list(set(sites['CellYPos']))).mean()
    #xmin = (sites['xPos']-sites['CellXPos']).min() ## point furthest left of the cell
    xmin = sites[keys['mappedX']].min()
    #ymin = (sites['yPos']-sites['CellYPos']).min() ## point furthest above the cell
    ymin = (sites[keys['mappedY']].min() if sites[keys['mappedY']].min() < 0 else 0.) *factor
    #xmax = (sites['xPos']-sites['CellXPos']).max()
    xmax = sites[keys['mappedX']].max()
    #ymax = (sites['yPos']-sites['CellXPos']).max()
    ymax = sites[keys['mappedY']].max()*factor
                 
    xdim = int((xmax-xmin)/spacing)+10
    ydim = int((ymax-ymin)/spacing)+10
    #avgCellIndex = np.array([int((avgCellX-xmin)/spacing)+5, int((avgCellY-ymin)/spacing)+5])
    
    cells = set(sites['CellDir'])
    n = len(cells)
    
    arr = np.zeros((n, xdim, ydim), dtype=float)
    sampling = np.zeros((n, xdim, ydim), dtype=float)
    #results = []
    
    for i, c in enumerate(cells):
        data = sites[sites['CellDir']==c]
        spontRate = data['numOfPreEvents'].sum()/data['PreRegionLen'].sum()
        data = afn.bendelsSpatialCorrelationAlgorithm(data, 90e-6, spontRate, timeWindow, eventsKey=eventKey)
  
        probs = np.zeros(len(data))
        probs[data['prob'] < probThreshold] = 1.
        for j, s in enumerate(data):
            #trans1 = (s[keys['mappedX']] - xmin, s[keys['mappedY']]-ymin)
            #trans2 = (avgCellX+xmin, avgCellY+ymin)            
            x, y = (int((s[keys['mappedX']]-xmin)/spacing), int((s[keys['mappedY']]*factor-ymin)/spacing))
            arr[i, x, y] = probs[j]
            sampling[i, x, y] = 1
              
        #results.append(arr[i].copy())
        arr[i] = scipy.ndimage.gaussian_filter(arr[i], 2)
        arr[i] = arr[i]/0.039
        arr[i][arr[i] > 0.03] = 1
        arr[i][arr[i] <= 0.03] = 0
        
        sampling[i] = scipy.ndimage.gaussian_filter(sampling[i], 2)
        sampling[i] = sampling[i]/0.039
        sampling[i][sampling[i] > 0.02] = 1
        sampling[i][sampling[i] <= 0.02] = 0        

    return arr, sampling

def randomizeData(data, fields):
    """Return a record array with the data in specified fields randomly sorted.
         **Arguments**
         =============   ==============================================
         data            A record array
         fields          A list of field names (or string of one field name) whose values should be randomly shuffled
         =============   ==============================================
    """
    #prof = Profiler('randomizeData', disabled=False)
    newArr = data.copy()
    
    if type(fields) == type(''):
        fields = [fields]
        
    for f in fields:
        d = data[f]
        np.random.shuffle(d)
        newArr[f]=d
        
    #prof.finish()
    return newArr
    
    
def randomProbTest(sites, n=10, cellDir=None, probThreshold=0.02, timeWindow=0.1, eventKey='numOfPostEvents'):
    #prof = Profiler('randomProbTest', disabled=False)
    
    tasks = range(n)
    results = []
    
    data = sites[sites['CellDir']==cellDir]
    spontRate = data['numOfPreEvents'].sum()/data['PreRegionLen'].sum()
    #prof.mark('selected data, calculated spontRate')
    
    d = afn.bendelsSpatialCorrelationAlgorithm(data, 90e-6, spontRate, timeWindow, eventsKey=eventKey)
    actualNum = len(d[d['prob'] < probThreshold])
    #prof.mark('calculated actual number of spots')
    
    with Parallelize(tasks, results=results)as tasker:
        for task in tasker:
            randomData = randomizeData(data, eventKey)
            randomData = afn.bendelsSpatialCorrelationAlgorithm(randomData, 90e-6, spontRate, timeWindow, eventsKey=eventKey)
            tasker.results.append(len(randomData[randomData['prob'] < probThreshold])) 
    #prof.mark('calculated number of spots for %i random trials'%n)
    
    #prof.finish()

    return actualNum, results

def getContourStats(arr, spacing=5e-6): ### needs debugging
    """"""
    global HAVE_CV2
    if not HAVE_CV2:
        raise Exception("Cannot get contours because OpenCV2 could not be imported")
    #arr, sampling = convolveCells_newAtlas(sites, spacing=spacing)
    xPositions = []
    yPositions = []
    areas = []
    cells = []
    
    if len(arr.shape) == 3:
        n=arr.shape[0]
    elif len(arr.shape) == 2:
        n=1
    else:
        raise Exception("Array argument needs to have either 2 (width, height) or 3 (n, width, height) dimensions")
        
    for i in range(n):
        if n == 1:
            data = arr.copy().astype('uint8')
        else:
            data = arr[i].copy().astype('uint8')
            
        contours, hierarchy = cv2.findContours(data.copy(), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if len(contours) is 0 or hierarchy is None:
            continue
        hierarchy = hierarchy[0]
        
        #for j, cnt in enumerate(contours):
            #cnt_len = cv2.arcLength(cnt, True)
            #cnt = cv2.approxPolyDP(cnt, 0.02*cnt_len, True)
            ##m.append(cv2.minAreaRect(cnt))
            #area = cv2.contourArea(cnt)    
            #cnt = cnt.reshape(-1,2) # just gets rid of an extra array dimension
            #cnt = np.append(cnt, cnt[0]) 
            ##cnt = np.array([cnt, cnt[0]])
   
            #poly = np.array([cnt.reshape(-1,2)]) #needed for moments to take the argument (??)
            #m = cv2.moments(poly)
            #cm= (m['m10']/m['m00'], m['m01']/m['m00']) ## compute center of mass of this point  
            
            #xPositions.append(cm[0])
            #yPositions.append(cm[1])
            #areas.append(area)
            
        for j, c in enumerate(contours):
            if hierarchy[j][3] != -1: ## means this is a hole in a larger contour and we don't want to count it
                continue
            xmin = c[:,:,1].min()-3
            xmax = c[:,:,1].max()+3
            ymin = c[:,:,0].min()-3
            ymax = c[:,:,0].max()+3
            print i, j
            print '   x:', xmin, xmax
            print '   y:', ymin, ymax
            m = cv2.moments(data[xmin:xmax, ymin:ymax])
            y = (m['m10']/m['m00'])+0.5 ## the contour/moments functions seem to leave off the right and bottom edge of contours, so we add it back
            x = (m['m01']/m['m00'])+0.5
            xPositions.append((x+xmin)*spacing)
            yPositions.append((y+ymin)*spacing)
            areas.append(m['m00']*(spacing**2))
            cells.append(i)
            
    ret = np.zeros(len(areas), dtype=[('xCenterPos', float), ('yCenterPos', float), ('area', float), ('cell', int)])
    ret['xCenterPos'] = np.array(xPositions)
    ret['yCenterPos'] = np.array(yPositions)
    ret['area'] = np.array(areas)
    ret['cell'] = np.array(cells)
    return ret
    
    
    
