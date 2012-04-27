from PyQt4 import QtCore, QtGui
import lib.Manager
import pyqtgraph as pg
import numpy as np
import functions as fn

man = lib.Manager.getManager() 
dm = man.getModule('Data Manager')
db = dm.currentDatabase()
mod = man.dataModel


sites = db.select('sites', toArray=True)

lasers = [1e-6, 2e-6, 3e-6, 4e-6, 5e-6, 6e-6, 7e-6] ## list of StimEnergys to calculate firing probability for
distances = [0, 25e-6, 50e-6, 75e-6, 100e-6, 125e-6, 150e-6, 175e-6, 200e-6, 1e-3]

def calculateSpikingProb(sites, lasers, distances, stimEnergyBumper=0.2e-6):
    probs = np.zeros((len(lasers), len(distances)-1))
    for i, l in enumerate(lasers):
        data = sites[(sites['StimEnergy'] >= l-stimEnergyBumper)*(sites['StimEnergy'] <=l+stimEnergyBumper)]
        for j, x in enumerate(distances[:-1]):
            d2 = data[(data['distance'] > distances[j])*(data['distance'] <= distances[j+1])]
            if len(d2) != 0:
                probs[i,j] = len(d2[d2['SpikeCount'] >= 1]) / float(len(d2))
    return probs

x = [x + (distances[i+1]-x)/2. for i, x in enumerate(distances[:-1])]
