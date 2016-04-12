from acq4.pyqtgraph.parametertree import Parameter, ParameterItem, parameterTypes
import acq4.pyqtgraph as pg


class RegionParameter(parameterTypes.GroupParameter):

    def __init__(self, plot, **opts):
        opts['type'] = 'bool'
        opts['value'] = True
        if not 'name' in opts.keys():
            opts['name'] = 'Region'
        parameterTypes.GroupParameter.__init__(self, **opts)

        self.addChild({'name':'Start', 'type':'float', 'value':opts.get('startValue', 0), 'suffix':'s', 'siPrefix':True, 'step':0.1, 'dec':True})
        self.addChild({'name':'End', 'type':'float', 'value': opts.get('endValue', 0.05), 'suffix':'s', 'siPrefix':True, 'step':0.1, 'dec':True})
        self.addChild({'name':'Color', 'type':'color', 'value':opts.get('color', 'r')})
        self.addChild({'name':'Display', 'type':'bool', 'value':True})

        self.rgn = pg.LinearRegionItem(brush=self.param('Color').value())
        self.rgn.setRegion([self.param('Start').value(), self.param('End').value()])
        self.plot = plot
        self.plot.addItem(self.rgn)




