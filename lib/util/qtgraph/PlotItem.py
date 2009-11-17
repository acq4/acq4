# -*- coding: utf-8 -*-
from graphicsItems import *
from plotConfigTemplate import *
from lib.util.WidgetGroup import *

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
        self.alpha = 1.0
        self.autoAlpha = True
        self.spectrumMode = False
         
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
        self.showScale('left', True)
        self.showScale('bottom', True)

        ## Wrap a few methods from viewBox
        for m in ['setXRange', 'setYRange', 'autoRange']:
            setattr(self, m, getattr(self.vb, m))
            
            
        self.curves = []
        
        ### Set up context menu
        
        w = QtGui.QWidget()
        self.ctrl = c = Ui_Form()
        c.setupUi(w)
        dv = QtGui.QDoubleValidator(self)
        self.ctrlMenu = QtGui.QMenu()
        ac = QtGui.QWidgetAction(self)
        ac.setDefaultWidget(w)
        self.ctrlMenu.addAction(ac)
        
        self.stateGroup = WidgetGroup(self.ctrlMenu)
        
        self.fileDialog = None
        
        self.xLinkPlot = None
        self.yLinkPlot = None
        self.linksBlocked = False


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
                self.layout.setColumnFixedWidth(p[1], s.size().width())
                s.setMaximumWidth(40)
            else:
                self.layout.setRowFixedHeight(p[0], s.size().height())
                s.setMaximumHeight(20)
        else:
            s.hide()
            if key in ['left', 'right']:
                self.layout.setColumnFixedWidth(p[1], 0)
                s.setMaximumWidth(0)
            else:
                self.layout.setRowFixedHeight(p[0], 0)
                s.setMaximumHeight(0)
        
    def plot(self, data=None, x=None, clear=False, params=None, pen=None):
        if clear:
            self.clear()
        if params is None:
            params = {}
        if isinstance(data, MetaArray):
            curve = self._plotMetaArray(data, x=x)
        elif isinstance(data, ndarray):
            curve = self._plotArray(data, x=x)
        elif isinstance(data, list):
            if x is not None:
                x = array(x)
            curve = self._plotArray(array(data), x=x)
        elif data is None:
            curve = [PlotCurveItem()]
        else:
            raise Exception('Not sure how to plot object of type %s' % type(data))
            
        print data, curve
        self.addCurve(curve, params)
        if pen is not None:
            curve.setPen(pen)
        
        return curve

    def addCurve(self, c, params=None):
        c.setMeta(params)
        self.curves.append(c)
        #Qwt.QwtPlotCurve.attach(c, self)
        self.addItem(c)
        
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
        
        
    def removeCurve(self, c):
        if c in self.curves:
            self.curves.remove(c)
        self.updateDecimation()
        self.updateParamList()

    def updateParamList(self):
        self.ctrl.avgParamList.clear()
        ## Check to see that each parameter for each curve is present in the list
        #print "\nUpdate param list", self
        #print "paramList:", self.paramList
        for c in self.curves:
            #print "  curve:", c
            for p in c.meta().keys():
                #print "    param:", p
                if type(p) is tuple:
                    p = '.'.join(p)
                    
                ## If the parameter is not in the list, add it.
                matches = self.ctrl.avgParamList.findItems(p, QtCore.Qt.MatchExactly)
                #print "      matches:", matches
                if len(matches) == 0:
                    i = QtGui.QListWidgetItem(p)
                    if p in self.paramList and self.paramList[p] is True:
                        #print "      set checked"
                        i.setCheckState(QtCore.Qt.Checked)
                    else:
                        #print "      set unchecked"
                        i.setCheckState(QtCore.Qt.Unchecked)
                    self.ctrl.avgParamList.addItem(i)
                else:
                    i = matches[0]
                    
                self.paramList[p] = (i.checkState() == QtCore.Qt.Checked)
        #print "paramList:", self.paramList

    def _plotArray(self, arr, x=None):
        if arr.ndim != 1:
            raise Exception("Array must be 1D to plot (shape is %s)" % arr.shape)
        if x is None:
            x = arange(arr.shape[0])
        if x.ndim != 1:
            raise Exception("X array must be 1D to plot (shape is %s)" % x.shape)
        c = PlotCurveItem(arr, x=x)
        return c
            
        
        
    def _plotMetaArray(self, arr):
        inf = arr.infoCopy()
        if arr.ndim != 1:
            raise Exception('can only automatically plot 1 dimensional arrays.')
        ## create curve
        try:
            xv = arr.xvals(0)
        except:
            xv = range(arr.shape[0])
        c = PlotCurveItem()
        c.setData(x=xv, y=arr.view(ndarray))
            
        return c

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


    def widgetGroupInterface(self):
        return (None, PlotWidget.saveState, PlotWidget.restoreState)
      
    def updateSpectrumMode(self, b=None):
        if b is None:
            b = self.ctrl.powerSpectrumGroup.isChecked()
        curves = filter(lambda i: isinstance(i, Qwt.QwtPlotCurve), self.itemList())
        for c in curves:
            c.setSpectrumMode(b)
        self.enableAutoScale()
        self.replot()
            
    def enableAutoScale(self):
        self.ctrl.xAutoRadio.setChecked(True)
        self.ctrl.yAutoRadio.setChecked(True)
        self.autoBtn.hide()
      
    def updateDecimation(self):
        if self.ctrl.maxTracesCheck.isChecked():
            numCurves = self.ctrl.maxTracesSpin.value()
        else:
            numCurves = -1
            
        #curves = filter(lambda i: isinstance(i, Qwt.QwtPlotCurve), self.itemList())
        curves = self.curves[:]
        split = len(curves) - numCurves
        for i in range(len(curves)):
            if numCurves == -1 or i >= split:
                curves[i].show()
            else:
                if self.ctrl.forgetTracesCheck.isChecked():
                    curves[i].free()
                    self.detachCurve(curves[i])
                else:
                    curves[i].hide()
        
      
    def updateAlpha(self, *args):
        (alpha, auto) = self.alphaState()
        for c in self.curves:
            c.setAlpha(alpha, auto)
                
        self.replot(autoRange=False)
     
    def alphaState(self):
        enabled = self.ctrl.alphaGroup.isChecked()
        auto = self.ctrl.autoAlphaCheck.isChecked()
        alpha = float(self.ctrl.alphaSlider.value()) / self.ctrl.alphaSlider.maximum()
        if auto:
            alpha = 1.0  ## should be 1/number of overlapping plots
        if not enabled:
            auto = False
            alpha = 1.0
        return (alpha, auto)

    def pointMode(self):
        if self.ctrl.pointsGroup.isChecked():
            if self.ctrl.autoPointsCheck.isChecked():
                mode = None
            else:
                mode = True
        else:
            mode = False
        return mode


