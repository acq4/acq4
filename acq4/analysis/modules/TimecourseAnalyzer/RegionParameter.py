from __future__ import print_function
from acq4.pyqtgraph.parametertree import Parameter, ParameterItem, parameterTypes
import acq4.pyqtgraph as pg


class RegionParameter(parameterTypes.GroupParameter):

    def __init__(self, plot, **opts):
        opts['type'] = 'bool'
        opts['value'] = True
        if not 'name' in opts.keys():
            opts['name'] = 'Region'
        if 'color' in opts:
            opts['color'] = pg.mkColor(opts['color']).setAlpha(50)
        else:
            opts['color'] = pg.mkColor((255,0,0,50))
            
        parameterTypes.GroupParameter.__init__(self, **opts)


        self.addChild({'name':'Start', 'type':'float', 'value':opts.get('startValue', 0), 'suffix':'s', 'siPrefix':True, 'step':0.1, 'dec':True})
        self.addChild({'name':'End', 'type':'float', 'value': opts.get('endValue', 0.05), 'suffix':'s', 'siPrefix':True, 'step':0.1, 'dec':True})
        self.addChild({'name':'Color', 'type':'color', 'value':opts['color']})
        self.addChild({'name':'Display', 'type':'bool', 'value':True})

        self.rgn = pg.LinearRegionItem(brush=self.child('Color').value())
        self.rgn.setRegion([self.child('Start').value(), self.child('End').value()])
        self.plot = plot
        self.plot.addItem(self.rgn)

        self.child('Start').sigValueChanged.connect(self.regionParamChanged)
        self.child('End').sigValueChanged.connect(self.regionParamChanged)
        self.rgn.sigRegionChangeFinished.connect(self.updateRegionParams)
        self.child('Color').sigValueChanged.connect(self.colorChanged)
        self.child('Display').sigValueChanged.connect(self.displayToggled)


    def regionParamChanged(self):
        try:
            self.rgn.blockSignals(True)
            self.rgn.setRegion([self.child('Start').value(), self.child('End').value()])
        finally:
            self.rgn.blockSignals(False)

    def updateRegionParams(self):
        self.child('Start').setValue(self.rgn.getRegion()[0], blockSignal=self.regionParamChanged)
        self.child('End').setValue(self.rgn.getRegion()[1], blockSignal=self.regionParamChanged)

    def colorChanged(self):
        color = self.child('Color').colorValue()
        self.rgn.setBrush(color)

    def displayToggled(self):
        display = self.child('Display').value()
        if display:
            self.rgn.show()
        else:
            self.rgn.hide()









