# -*- coding: utf-8 -*-
from graphicsItems import *

class PlotItem(QtGui.QGraphicsWidget):
    """Plot graphics item that can be added to any graphics scene. Implements axis titles, scales, interactive viewbox."""
    def __init__(self, parent=None):
        QtGui.QGraphicsWidget.__init__(self, parent)
        self.layout = QtGui.QGraphicsGridLayout()
        self.setLayout(self.layout)
        self.layout.setHorizontalSpacing(0)
        self.layout.setVerticalSpacing(0)
        self.vb = ViewBox()
        self.layout.addItem(self.vb, 3, 2)
        
        ## Create and place scale items
        self.scales = {
            'top':    {'item': ScaleItem(orientation='top',    linkView=self.vb), 'pos': (2, 2)}, 
            'bottom': {'item': ScaleItem(orientation='bottom', linkView=self.vb), 'pos': (4, 2)}, 
            'left':   {'item': ScaleItem(orientation='left',   linkView=self.vb), 'pos': (3, 1)}, 
            'right':  {'item': ScaleItem(orientation='right',  linkView=self.vb), 'pos': (3, 3)}
        }
        for k in self.scales:
            self.layout.addItem(self.scales[k]['item'], *self.scales[k]['pos'])
            
        ## Create and place label items
        self.labels = {
            'title':  {'item': LabelItem('title', size='11pt'),  'pos': (0, 2)},
            'top':    {'item': LabelItem('top'),    'pos': (1, 2)},
            'bottom': {'item': LabelItem('bottom'), 'pos': (5, 2)},
            'left':   {'item': LabelItem('left'),   'pos': (3, 0)},
            'right':  {'item': LabelItem('right'),  'pos': (3, 4)}
        }
        self.labels['left']['item'].setAngle(90)
        self.labels['right']['item'].setAngle(90)
        for k in self.labels:
            self.layout.addItem(self.labels[k]['item'], *self.labels[k]['pos'])

        for i in range(6):
            self.layout.setRowPreferredHeight(i, 0)
            self.layout.setRowMinimumHeight(i, 0)
            self.layout.setRowSpacing(i, 0)
            self.layout.setRowStretchFactor(i, 1)
            
        for i in range(5):
            self.layout.setColumnPreferredWidth(i, 0)
            self.layout.setColumnMinimumWidth(i, 0)
            self.layout.setColumnSpacing(i, 0)
            self.layout.setColumnStretchFactor(i, 1)
        self.layout.setRowStretchFactor(3, 100)
        self.layout.setColumnStretchFactor(2, 100)
        
        self.showLabel('right', False)
        self.showLabel('top', False)
        self.showLabel('title', False)
        self.showLabel('left', False)
        self.showLabel('bottom', False)
        self.showScale('right', False)
        self.showScale('top', False)

        #self.xScale = ScaleItem(orientation='bottom', linkView=self.vb)
        #self.layout.addItem(self.xScale, 1, 2)
        #self.yScale = ScaleItem(orientation='left', linkView=self.vb)
        #self.layout.addItem(self.yScale, 0, 1)

        #self.xLabel = LabelItem(u"<span style='color: #ff0000; font-weight: bold'>X</span> <i>Axis</i> <span style='font-size: 6pt'>(μV)</span>", html=True, color=QtGui.QColor(200, 200, 200))
        #self.layout.setRowFixedHeight(2, 20)
        #self.layout.setRowFixedHeight(1, 30)
        #self.layout.addItem(self.xLabel, 2, 2)
        #self.yLabel = LabelItem("Y Axis", color=QtGui.QColor(200, 200, 200))
        #self.yLabel.setAngle(90)
        #self.layout.setColumnFixedWidth(0, 20)
        #self.layout.setColumnFixedWidth(1, 60)
        #self.layout.addItem(self.yLabel, 0, 0)
        
        ## Wrap a few methods from viewBox
        for m in ['setXRange', 'setYRange', 'autoRange']:
            setattr(self, m, getattr(self.vb, m))
        

    def addItem(self, *args):
        self.vb.addItem(*args)
        
    def _checkLabelKey(self, key):
        if key not in self.labels:
            raise Exception("Label '%s' not found. Labels are: %s" % (key, str(self.labels.keys())))
        
    def getLabel(self, key):
        self._checkLabelKey(key)
        return self.labels[key]['item']
        
    def _checkScaleKey(self, key):
        if key not in self.scales:
            raise Exception("Scale '%s' not found. Scales are: %s" % (key, str(self.scales.keys())))
        
    def getScale(self, key):
        self._checkScaleKey(key)
        return self.scales[key]['item']
        
    def showLabel(self, key, show=True):
        l = self.getLabel(key)
        p = self.labels[key]['pos']
        if show:
            l.show()
            if key in ['left', 'right']:
                self.layout.setColumnFixedWidth(p[1], l.size().width())
                l.setMaximumWidth(20)
            else:
                self.layout.setRowFixedHeight(p[0], l.size().height())
                l.setMaximumHeight(20)
        else:
            l.hide()
            if key in ['left', 'right']:
                self.layout.setColumnFixedWidth(p[1], 0)
                l.setMaximumWidth(0)
            else:
                self.layout.setRowFixedHeight(p[0], 0)
                l.setMaximumHeight(0)
        
    def showScale(self, key, show=True):
        s = self.getScale(key)
        p = self.labels[key]['pos']
        if show:
            s.show()
            if key in ['left', 'right']:
                self.layout.setColumnFixedWidth(p[1], l.size().width())
                s.setMaximumWidth(30)
            else:
                self.layout.setRowFixedHeight(p[0], l.size().height())
                s.setMaximumHeight(30)
        else:
            s.hide()
            if key in ['left', 'right']:
                self.layout.setColumnFixedWidth(p[1], 0)
                s.setMaximumWidth(0)
            else:
                self.layout.setRowFixedHeight(p[0], 0)
                s.setMaximumHeight(0)
        
    def plot(self, data=None, x=None, clear=False, params=None, pen=None, replot=True):
        if clear:
            self.clear()
        if params is None:
            params = {}
        if isinstance(data, MetaArray):
            curves = self._plotMetaArray(data)
        elif isinstance(data, ndarray):
            curves = self._plotArray(data, x=x)
        elif isinstance(data, list):
            if x is not None:
                x = array(x)
            curves = self._plotArray(array(data), x=x)
        elif data is None:
            curves = [PlotCurve()]
        else:
            raise Exception('Not sure how to plot object of type %s' % type(data))
            
        for c in curves:
            self.attachCurve(c, params)
            if pen is not None:
                c.setPen(pen)
            
            
        if replot:
            self.replot()
        
        #self.indexParams(params, ids)
        
        if data is not None and data.ndim == 2:
            return curves
        else:
            return curves[0]

    def attachCurve(self, c, params=None):
        c.setParams(params)
        self.curves.append(c)
        Qwt.QwtPlotCurve.attach(c, self)
        
        ## configure curve for this plot
        (alpha, auto) = self.alphaState()
        c.setAlpha(alpha, auto)
        c.setSpectrumMode(self.ctrl.powerSpectrumGroup.isChecked())
        c.setPointMode(self.pointMode())
        
        ## Hide older plots if needed
        self.updateDecimation()
        
        ## Add to average if needed
        self.updateParamList()
        if self.ctrl.averageGroup.isChecked():
            self.addAvgCurve(c)
        
        
    def detachCurve(self, c):
        try:
            Qwt.QwtPlotCurve.detach(c)
        except:
            pass
        
        if c in self.curves:
            self.curves.remove(c)
        self.updateDecimation()
        self.updateParamList()


    def _plotArray(self, arr, x=None):
        arr = atleast_2d(arr)
        if arr.ndim != 2:
            raise Exception("Array must be 1 or 2D to plot (shape is %s)" % arr.shape)
            
        if x is None:
            x = arange(arr.shape[1])
            
        x = atleast_2d(x)
        if x.ndim != 2:
            raise Exception("X array must be 1 or 2D to plot (shape is %s)" % x.shape)
            
        
        ret = []
        for i in range(arr.shape[0]):
            c = PlotCurve()
            c.setData(x[i%x.shape[0]], arr[i])
            #c.attach(self)
            ret.append(c)
            #self.curves.append(c)
                
        return ret
            
        
        
    def _plotMetaArray(self, arr):
        inf = arr.infoCopy()
        
        #print "_plotMetaArray()"
        #print inf
        #print arr.shape
        axes = [0, 1]
            
        if arr.ndim == 2:
            for i in [0,1]:
                if 'cols' in inf[i]:
                    #print "axis %d has cols" % i
                    axes = [1-i, i]
        elif arr.ndim != 1:
            raise Exception('can only automatically plot 1 or 2 dimensional arrays.')
                    
        #print "AXES:", axes
        titles = ['', '']
        for i in [1,0]:
            ax = axes[i]
            t = ''
            if i >= len(inf):
                continue
            
            ## If there are columns, pick title/units from first column
            if 'cols' in inf[ax]:
                s = inf[ax]['cols'][0]
            else:
                s = inf[ax]
                
            if 'name' in s:
                t = s['name']
            if 'units' in s:
                t += ' (%s)' % s['units']
            titles[i] = t
        ### Set axis titles
        #titles = ['', '']
        #for i in [0,1]:
            #if 'title' in inf[axes[i]]:
                #titles[i] = inf[axes[i]]['title']
            #else:
                #titles[i] = inf[axes[i]]['name']
            #if 'units' in inf[axes[i]]:
                #titles[i] = titles[i] + ' (%s)' % inf[axes[i]]['units']
                
        self.setAxisTitle(self.xBottom, titles[0])
        self.setAxisTitle(self.yLeft, titles[1])

        ## create curves
        #curves = []
        try:
            xv = arr.xvals(axes[0])
        except:
            print "Making up xvals"
            #print arr
            #raise
            xv = range(arr.shape[axes[0]])
        
        ret = []
        if arr.ndim == 2:
            for i in range(arr.shape[axes[1]]):
                c = PlotCurve()
                
                axName = inf[axes[1]]['name']
                #print "ARRAY:"
                yArr = arr[axName:i].view(ndarray)
                #print xv.shape, xv.min(), xv.max()
                #print yArr.shape, yArr.min(), yArr.max()
                #c.setData(array([1,2,3,4,5]), array([1,4,2,3,5]))
                c.setData(xv, yArr)
                
                ret.append(c)
        else:
            c = PlotCurve()
            #c.setData(array([1,2,3,4,5]), array([1,4,2,3,5]))
            print xv.shape, arr.view(ndarray).shape
            c.setData(xv, arr.view(ndarray))
            ret.append(c)
            
        return ret
        #return []

    def saveSvgClicked(self):
        self.fileDialog = QtGui.QFileDialog(self)
        if PlotWidget.lastFileDir is not None:
            self.fileDialog.setDirectory(PlotWidget.lastFileDir)
        self.fileDialog.setFileMode(QtGui.QFileDialog.AnyFile)
        self.fileDialog.setAcceptMode(QtGui.QFileDialog.AcceptSave)
        self.fileDialog.show()
        QtCore.QObject.connect(self.fileDialog, QtCore.SIGNAL('fileSelected(const QString)'), self.svgFileSelected)
            
    def svgFileSelected(self, fileName):
        #PlotWidget.lastFileDir = os.path.split(fileName)[0]
        self.writeSvg(str(fileName))
        self.fileDialog = None

    def saveImgClicked(self):
        self.fileDialog = QtGui.QFileDialog(self)
        if PlotWidget.lastFileDir is not None:
            self.fileDialog.setDirectory(PlotWidget.lastFileDir)
        self.fileDialog.setFileMode(QtGui.QFileDialog.AnyFile)
        self.fileDialog.setAcceptMode(QtGui.QFileDialog.AcceptSave)
        self.fileDialog.show()
        QtCore.QObject.connect(self.fileDialog, QtCore.SIGNAL('fileSelected(const QString)'), self.imgFileSelected)
            
    def imgFileSelected(self, fileName):
        #PlotWidget.lastFileDir = os.path.split(fileName)[0]
        self.writeImage(str(fileName))
        self.fileDialog = None
      

    def writeSvg(self, fileName=None):
        if fileName is None:
            fileName = str(QtGui.QFileDialog.getSaveFileName())
        #s = self.size()
        #self.setSize(self.size() * 4)
        self.svg = QtSvg.QSvgGenerator()
        self.svg.setFileName(fileName)
        self.svg.setSize(self.size())
        #self.svg.setResolution(600)
        painter = QtGui.QPainter(self.svg)
        self.print_(painter, self.rect())
        #self.setSize(s)
        
    def writeImage(self, fileName=None):
        if fileName is None:
            fileName = str(QtGui.QFileDialog.getSaveFileName())
        self.png = QtGui.QImage(self.size(), QtGui.QImage.Format_ARGB32)
        painter = QtGui.QPainter(self.png)
        #rh = self.renderHints()
        #self.setRenderHints(QtGui.QPainter.Antialiasing)
        self.print_(painter, self.rect())
        #self.setRenderHints(rh)
        self.png.save(fileName)
        
        
    def clear(self):
        Qwt.QwtPlot.clear(self)
        self.curves = []
        #self.paramList = {}
        self.avgCurves = {}

    def saveState(self):
        state = self.stateGroup.state()
        state['paramList'] = self.paramList.copy()
        #print "\nSAVE %s:\n" % str(self.name), state
        #print "Saving state. averageGroup.isChecked(): %s  state: %s" % (str(self.ctrl.averageGroup.isChecked()), str(state['averageGroup']))
        return state
        
    def restoreState(self, state):
        if 'paramList' in state:
            self.paramList = state['paramList'].copy()
            self.stateGroup.setState(state)
        self.updateParamList()
        #print "\nRESTORE %s:\n" % str(self.name), state
        #print "Restoring state. averageGroup.isChecked(): %s  state: %s" % (str(self.ctrl.averageGroup.isChecked()), str(state['averageGroup']))
        #avg = self.ctrl.averageGroup.isChecked()
        #if avg != state['averageGroup']:
            #print "  WARNING: avgGroup is %s, should be %s" % (str(avg), str(state['averageGroup']))
