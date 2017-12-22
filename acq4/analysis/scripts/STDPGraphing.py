from __future__ import print_function
import pyqtgraph as pg
import numpy as np

view = pg.GraphicsView()
l = pg.GraphicsLayout(border=(100,100,100))
view.setCentralItem(l)

def graphPlasticityPerCell(trials, baseDir, columns=3):
    cells = list(set(trials['CellDir']))
    plots = []
    for i in range(len(cells)):
        if i % columns == 0:
            l.nextRow()

        p = l.addPlot(title=cells[i].name(relativeTo=baseDir))
        data = trials[trials['CellDir'] == cells[i]]
        p.plot(data['time'], data['normalizedPspSlope'], pen=None, symbol='o')
        plots.append(p)
    return plots

def graphAveragePlasticityByGroup(trials, group=1):
    """Trials is a numpy record array that might come from a database view. """

    data = trials[trials['drug_group']==group]
    cells = set(data['CellDir'])

    timebins = np.arange(0, 3300, 60)

    results = np.zeros((len(timebins), len(cells), 2))

    for i, c in enumerate(cells):
        d = data[data['CellDir']==c]
        results[:len(d), i, 0] = d['normalizedPspSlope']
        results[:len(d), i, 1] = d['UseData']

    avgSlope = np.ma.masked_array(results[:,:,0], mask=~results[:,:,1].astype(bool)).mean(axis=0)
    stdev = np.ma.masked_array(results[:,:,0], mask=~results[:,:,1].astype(bool)).std(axis=0)

    plot = pg.plot(timebins+30, avgSlope)
    c1 = pg.PlotCurveItem(timebins+30, avgSlope+stdev, 'r')
    c2 = pg.PlotCurveItem(timebins+30, avgSlope-stdev, 'r')
    plot.addItem(pg.FillBetweenItem(c1,c2, brush=(255,0,0,100)))

    return plot

def writeCSV(data, group, filename, baseDir):
    f = open(filename, 'w')
    #f.write('Group: %s \n'%str(group))

    #data = data[data['drug_group'] == group]
    cells = list(set(data['CellDir']))

    for c in cells:
        f.write('%s, ,,' %c.name(relativeTo=baseDir))
    f.write('\n')

    for c in cells:
        f.write('time, normalizedPSPSlope,,')
    f.write('\n')

    n = 0
    for c in cells:
        if len(data[data['CellDir']==c]) > n:
            n = len(data[data['CellDir']==c])

    for i in range(n):
        for c in cells:
            d = data[data['CellDir']==c]
            try:
                f.write('%s,%s,,'%(d[i]['time'], d[i]['normalizedPspSlope']))
            except IndexError:
                print("skipping index %i for Cell %s"%(i, c.name()))
                f.write(',,,')
        f.write('\n')

    f.close()













    