import pyqtgraph as pg

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


    