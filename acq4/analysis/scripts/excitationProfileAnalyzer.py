from __future__ import print_function
from acq4.util import Qt
import acq4.Manager
import acq4.pyqtgraph as pg
import numpy as np
import acq4.util.functions as fn

#man = acq4.Manager.getManager() 
#dm = man.getModule('Data Manager')
#db = dm.currentDatabase()
#mod = man.dataModel


#sites = db.select('sites', toArray=True)

lasers = [1e-6, 2e-6, 3e-6, 4e-6, 5e-6, 6e-6, 7e-6] ## list of StimEnergys to calculate firing probability for
distances = [0, 25e-6, 50e-6, 75e-6, 100e-6, 125e-6, 150e-6, 175e-6, 200e-6, 1e-3]
x = [x + (distances[i+1]-x)/2. for i, x in enumerate(distances[:-1])]

def calculateSpikingProb(sites, lasers, distances, stimEnergyBumper=0.2e-6):
    probs = np.zeros((len(lasers), len(distances)-1))
    for i, l in enumerate(lasers):
        data = sites[(sites['StimEnergy'] >= l-stimEnergyBumper)*(sites['StimEnergy'] <=l+stimEnergyBumper)]
        for j, x in enumerate(distances[:-1]):
            d2 = data[(data['distance'] > distances[j])*(data['distance'] <= distances[j+1])]
            if len(d2) != 0:
                probs[i,j] = len(d2[d2['SpikeCount'] >= 1]) / float(len(d2))
    return probs

def calculateCumulativeDistribution(sites, lasers, distances, stimEnergyBumper=0.2e-6):
    
    dist = np.zeros((len(distances)-1, len(lasers)))
    for i, d in enumerate(distances[:-1]):
        cells = set(sites['CellDir'])
        total = len(cells)
        count = 0
        d1 = sites[(sites['distance'] > d)*(sites['distance'] <= distances[i+1])]
        for j, l in enumerate(lasers):
            d2 = d1[(d1['StimEnergy'] >= l-stimEnergyBumper)*(d1['StimEnergy'] <=l+stimEnergyBumper)]     
            for k, c in enumerate(cells.copy()):
                d3 = d2[d2['CellDir'] == c]
                if len(d3[d3['SpikeCount'] > 0]) > 0:
                    count += 1
                    cells.remove(c)
            total = len(set(d2['CellDir']))
            if total > 2:
                dist[i,j] = count/float(total)
    return dist
            
        
                    


