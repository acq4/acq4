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

def writeCSV(data, filename, baseDir):
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

def writeFIcsv(data, filename, basedir):
    f = open(filename, 'w')

    names = ['Cell', 'Protocol', 'ExperimentPhase', 'agonist', 'antagonist', 'RMP', 'Rin', 'tau', 'AdaptRatio', 'tau_h', 'Gh', 'FiringRate', 'AP1_HalfWidth', 'AP1_Latency', 'AP2_HalfWidth', 'AP2_Latency', 'AHP_Depth','FI_Fzero', 'FI_Ibreak', 'FI_F1amp', 'FI_F2amp', 'FI_Irate']

    for n in names:
        f.write(n+',')
    f.write('\n')

    for i, d in enumerate(data):
        f.write(d['CellDir'].name(relativeTo=basedir)+',')
        f.write(d['ProtocolSequenceDir'].shortName() + ',')
        f.write(d['notes']+',')
        if d['agonist_code'] is not None:
            f.write(d['agonist_code'] +',')
        else:
            f.write(' ,')
        if d['antagonist_code'] is not None:
            f.write(d['antagonist_code'] +',')
        else:
            f.write(' ,')
        f.write(str(d['RMP'])+',')
        f.write(str(d['R_in'])+',')
        f.write(str(d['tau_m'])+',')
        f.write(str(d['AdaptRatio'])+',')
        f.write(str(d['h_tau'])+',')
        f.write(str(d['h_g'])+',')
        for n in ['FiringRate', 'AP1_HalfWidth', 'AP1_Latency', 'AP2_HalfWidth', 'AP2_Latency', 'AHP_Depth','FI_FZero', 'FI_Ibreak', 'FI_F1amp', 'FI_F2amp', 'FI_Irate']:
            f.write('%s,' %str(d[n]))
        f.write('\n')


    f.close()









    