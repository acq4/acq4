import lib.Manager
import numpy as np
import lib.analysis.tools.functions as afn
import scipy


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
    
    
def calculateProb(sites, spacing=5e-6):
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
    
def convolveCells(sites, spacing=5e-6, probThreshold=0.02, probRadius=90e-6):
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
        data = afn.bendelsSpatialCorrelationAlgorithm(data, 90e-6, spontRate, data[0]['PostRegionLen'])
  
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
        
        
def convolveCells_newAtlas(sites, keys=None, factor=1.11849, spacing=5e-6, probThreshold=0.02, sampleSpacing=35e-6):
    if keys == None:
        keys = {
            'x':'xPosCell',
            'y':'yPosCell',
            'mappedX': 'modXPosCell',
            'mappedY': 'percentDepth'}
            
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
        data = afn.bendelsSpatialCorrelationAlgorithm(data, 90e-6, spontRate, data[0]['PostRegionLen'])
  
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
        arr[i][arr[i] > 0.02] = 1
        arr[i][arr[i] <= 0.02] = 0
        
        sampling[i] = scipy.ndimage.gaussian_filter(sampling[i], 2)
        sampling[i] = sampling[i]/0.039
        sampling[i][sampling[i] > 0.02] = 1
        sampling[i][sampling[i] <= 0.02] = 0        
    return arr, sampling

