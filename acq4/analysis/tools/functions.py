from __future__ import print_function
import numpy as np
import math
from acq4.pyqtgraph.debug import Profiler
import acq4.util.functions as utilFn



def convertPtsToSparseImage(data, params, spacing=5e-6):
    """Function for converting a list of stimulation spots and their associated values into a fine-scale smoothed image.
           data - a numpy record array which includes fields for 'xPos', 'yPos' and the parameters specified in params.
           params - a list of values to set
           spacing - the size of each pixel in the returned grid (default is 5um)
           
        Return a 2D record array with fields for each param in params - if 2 or more data points fall in the same grid location
        their values are averaged.
        """
    if len(params) == 0:
        return
    ## sanity checks
    if params==None:
        raise Exception("Don't know which parameters to process. Options are: %s" %str(data.dtype.names))
    if 'xPos' not in data.dtype.names or 'yPos' not in data.dtype.names:
        raise Exception("Data needs to have fields for 'xPos' and 'yPos'. Current fields are: %s" %str(data.dtype.names))
      
    ### Project data from current spacing onto finer grid, averaging data from duplicate spots
    xmin = data['xPos'].min()
    ymin = data['yPos'].min()
    xdim = int((data['xPos'].max()-xmin)/spacing)+5
    ydim = int((data['yPos'].max()-ymin)/spacing)+5
    dtype = []
    for p in params:
        dtype.append((p, float))
    dtype.append(('stimNumber', int))
    #print xmin, data['xPos'].max(), spacing
    #print len(data[data['xPos'] > 0.002]) + len(data[data['xPos'] < -0.002])
    #print np.argwhere(data['xPos'] > 0.002)
    #print xdim, ydim
    arr = np.zeros((xdim, ydim), dtype=dtype)
    for s in data:
        x, y = (int((s['xPos']-xmin)/spacing), int((s['yPos']-ymin)/spacing))
        for p in params:
            arr[x,y][p] += s[p]
        arr[x,y]['stimNumber'] += 1
    arr['stimNumber'][arr['stimNumber']==0] = 1
    for f in arr.dtype.names:
        arr[f] = arr[f]/arr['stimNumber']
    #arr = arr/arr['stimNumber']
    arr = np.ascontiguousarray(arr)
    
    return arr


def bendelsSpatialCorrelationAlgorithm(data, radius, spontRate, timeWindow, printProcess=False, eventsKey='numOfPostEvents'):
    ## check that data has 'xPos', 'yPos' and 'numOfPostEvents'
    #SpatialCorrelator.checkArrayInput(data) 
    #prof = Profiler("bendelsSpatialCorrelationAlgorithm", disabled=True)
    fields = data.dtype.names
    if 'xPos' not in fields or 'yPos' not in fields or eventsKey not in fields:
        raise HelpfulException("Array input needs to have the following fields: 'xPos', 'yPos', the field specified in *eventsKey*. Current fields are: %s" %str(fields))   
    #prof.mark("checked fields")
    
    ## add 'prob' field to data array
    if 'prob' not in data.dtype.names:
        arr = utilFn.concatenateColumns([data, np.zeros(len(data), dtype=[('prob', float)])])
        #arr[:] = data     
        data = arr
    else:
        data['prob']=0
    #prof.mark("set 'prob' field")
        
    table = np.zeros((200, 200)) ## add a lookup table so that we don't have to calculate the same probabilities over and over...saves a bit of time
    
    ## spatial correlation algorithm from :
    ## Bendels, MHK; Beed, P; Schmitz, D; Johenning, FW; and Leibold C. Detection of input sites in 
    ## scanning photostimulation data based on spatial correlations. 2010. Journal of Neuroscience Methods.
    
    ## calculate probability of seeing a spontaneous event in time window
    p = 1-np.exp(-spontRate*timeWindow)
    if printProcess:
        print("======  Spontaneous Probability: %f =======" % p)
    #prof.mark('calculated spontaneous probability')
        
    ## for each spot, calculate the probability of having the events in nearby spots occur randomly
    for x in data:
        spots = data[(np.sqrt((data['xPos']-x['xPos'])**2+(data['yPos']-x['yPos'])**2)) < radius]
        nSpots = len(spots)
        nEventSpots = len(spots[spots[eventsKey] > 0])
        
        prob = 0
        if table[nEventSpots, nSpots] != 0: ## try looking up value in table (it was stored there if we calculated it before), otherwise calculate it now
            prob = table[nEventSpots, nSpots]
            #prof.mark('look-up')
        else: 
            for j in range(nEventSpots, nSpots+1):
                a = ((p**j)*((1-p)**(nSpots-j))*math.factorial(nSpots))/(math.factorial(j)*math.factorial(nSpots-j))
                if printProcess:
                    print("        Prob for %i events: %f     Total: %f" %(j, a, prob+a))
                prob += a
            table[nEventSpots, nSpots] = prob
            #prof.mark('calculate')
        if printProcess: ## for debugging
            print("    %i out of %i spots had events. Probability: %f" %(nEventSpots, nSpots, prob))
        x['prob'] = prob
        
        
    #prof.mark("calculated probabilities")
    #prof.finish()
    
    return data

def spatialCorrelationAlgorithm_ZScore(data, radius, printProcess=False, eventsKey='ZScore', spontKey='SpontZScore', threshold=1.645):
    ## check that data has 'xPos', 'yPos' and 'numOfPostEvents'
    #SpatialCorrelator.checkArrayInput(data) 
    #prof = Profiler("bendelsSpatialCorrelationAlgorithm", disabled=True)
    fields = data.dtype.names
    if 'xPos' not in fields or 'yPos' not in fields or eventsKey not in fields or spontKey not in fields:
        raise HelpfulException("Array input needs to have the following fields: 'xPos', 'yPos', the fields specified in *eventsKey* and *spontKey*. Current fields are: %s" %str(fields))   
    #prof.mark("checked fields")
    
    ## add 'prob' field to data array
    if 'prob' not in data.dtype.names:
        arr = utilFn.concatenateColumns([data, np.zeros(len(data), dtype=[('prob', float)])])
        #arr[:] = data     
        data = arr
    else:
        data['prob']=0
    #prof.mark("set 'prob' field")
        
    table = np.zeros((200, 200)) ## add a lookup table so that we don't have to calculate the same probabilities over and over...saves a bit of time
    
    ## spatial correlation algorithm from :
    ## Bendels, MHK; Beed, P; Schmitz, D; Johenning, FW; and Leibold C. Detection of input sites in 
    ## scanning photostimulation data based on spatial correlations. 2010. Journal of Neuroscience Methods.
    
    ## calculate probability of seeing a spontaneous event in time window -- for ZScore method, calculate probability that ZScore is spontaneously high
    p = len(data[data[spontKey] < -threshold])/float(len(data))
    #p = 1-np.exp(-spontRate*timeWindow)
    #if printProcess:
    #    print "======  Spontaneous Probability: %f =======" % p
    #prof.mark('calculated spontaneous probability')
    
        
    ## for each spot, calculate the probability of having the events in nearby spots occur randomly
    for x in data:
        spots = data[(np.sqrt((data['xPos']-x['xPos'])**2+(data['yPos']-x['yPos'])**2)) < radius]
        nSpots = len(spots)
        nEventSpots = len(spots[spots[eventsKey] < -threshold])
        
        prob = 0
        if table[nEventSpots, nSpots] != 0: ## try looking up value in table (it was stored there if we calculated it before), otherwise calculate it now
            prob = table[nEventSpots, nSpots]
            #prof.mark('look-up')
        else: 
            for j in range(nEventSpots, nSpots+1):
                a = ((p**j)*((1-p)**(nSpots-j))*math.factorial(nSpots))/(math.factorial(j)*math.factorial(nSpots-j))
                if printProcess:
                    print("        Prob for %i events: %f     Total: %f" %(j, a, prob+a))
                prob += a
            table[nEventSpots, nSpots] = prob
            #prof.mark('calculate')
        if printProcess: ## for debugging
            print("    %i out of %i spots had events. Probability: %f" %(nEventSpots, nSpots, prob))
        x['prob'] = prob
        
        
    #prof.mark("calculated probabilities")
    #prof.finish()
    
    return data