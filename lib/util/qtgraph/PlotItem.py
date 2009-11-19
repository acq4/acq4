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
        QtCore.QObject.connect(self.vb, QtCore.SIGNAL('xRangeChanged'), self.xRangeChanged)
        QtCore.QObject.connect(self.vb, QtCore.SIGNAL('yRangeChanged'), self.yRangeChanged)
        QtCore.QObject.connect(self.vb, QtCore.SIGNAL('rangeChangedManually'), self.enableManualScale)
        
        
        self.layout.addItem(self.vb, 3, 2)
        self.alpha = 1.0
        self.autoAlpha = True
        self.spectrumMode = False
         
        self.autoScale = [True, True]
         
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
        for m in ['setXRange', 'setYRange', 'setRange', 'autoRange']:
            setattr(self, m, getattr(self.vb, m))
            
        self.items = []
        self.curves = []
        self.paramList = {}
        self.avgCurves = {}
        
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

        ## Set up control buttons
        
        self.ctrlBtn = QtGui.QToolButton()
        self.ctrlBtn.setText('?')
        self.autoBtn = QtGui.QToolButton()
        self.autoBtn.setText('A')
        self.autoBtn.hide()
        
        for b in [self.ctrlBtn, self.autoBtn]:
            proxy = QtGui.QGraphicsProxyWidget(self)
            proxy.setWidget(b)
            b.setStyleSheet("background-color: #000000; color: #888; font-size: 6pt")
        QtCore.QObject.connect(self.ctrlBtn, QtCore.SIGNAL('clicked()'), self.ctrlBtnClicked)
        QtCore.QObject.connect(self.autoBtn, QtCore.SIGNAL('clicked()'), self.enableAutoScale)
        
        #self.ctrlBtn.setFixedWidth(60)
        self.setAcceptHoverEvents(True)
        
        ## Connect control widgets
        QtCore.QObject.connect(c.xMinText, QtCore.SIGNAL('editingFinished()'), self.setManualXScale)
        QtCore.QObject.connect(c.xMaxText, QtCore.SIGNAL('editingFinished()'), self.setManualXScale)
        QtCore.QObject.connect(c.yMinText, QtCore.SIGNAL('editingFinished()'), self.setManualYScale)
        QtCore.QObject.connect(c.yMaxText, QtCore.SIGNAL('editingFinished()'), self.setManualYScale)
        
        QtCore.QObject.connect(c.xManualRadio, QtCore.SIGNAL('toggled(bool)'), self.updateXScale)
        QtCore.QObject.connect(c.yManualRadio, QtCore.SIGNAL('toggled(bool)'), self.updateYScale)
        
        QtCore.QObject.connect(c.xAutoRadio, QtCore.SIGNAL('clicked()'), self.updateXScale)
        QtCore.QObject.connect(c.yAutoRadio, QtCore.SIGNAL('clicked()'), self.updateYScale)

        #QtCore.QObject.connect(c.xLogCheck, QtCore.SIGNAL('toggled(bool)'), self.setXLog)
        #QtCore.QObject.connect(c.yLogCheck, QtCore.SIGNAL('toggled(bool)'), self.setYLog)

        #QtCore.QObject.connect(c.alphaGroup, QtCore.SIGNAL('toggled(bool)'), self.updateAlpha)
        #QtCore.QObject.connect(c.alphaSlider, QtCore.SIGNAL('valueChanged(int)'), self.updateAlpha)
        #QtCore.QObject.connect(c.autoAlphaCheck, QtCore.SIGNAL('toggled(bool)'), self.updateAlpha)

        QtCore.QObject.connect(c.powerSpectrumGroup, QtCore.SIGNAL('toggled(bool)'), self.updateSpectrumMode)
        QtCore.QObject.connect(c.saveSvgBtn, QtCore.SIGNAL('clicked()'), self.saveSvgClicked)
        QtCore.QObject.connect(c.saveImgBtn, QtCore.SIGNAL('clicked()'), self.saveImgClicked)
        
        #QtCore.QObject.connect(c.gridGroup, QtCore.SIGNAL('toggled(bool)'), self.updateGrid)
        #QtCore.QObject.connect(c.gridAlphaSlider, QtCore.SIGNAL('valueChanged(int)'), self.updateGrid)
        
        #QtCore.QObject.connect(self.ctrl.xLinkCombo, QtCore.SIGNAL('currentIndexChanged(int)'), self.xLinkComboChanged)
        #QtCore.QObject.connect(self.ctrl.yLinkCombo, QtCore.SIGNAL('currentIndexChanged(int)'), self.yLinkComboChanged)
        
        QtCore.QObject.connect(self.ctrl.avgParamList, QtCore.SIGNAL('itemClicked(QListWidgetItem*)'), self.avgParamListClicked)
        QtCore.QObject.connect(self.ctrl.averageGroup, QtCore.SIGNAL('toggled(bool)'), self.avgToggled)
        
        #QtCore.QObject.connect(self.ctrl.pointsGroup, QtCore.SIGNAL('toggled(bool)'), self.updatePointMode)
        #QtCore.QObject.connect(self.ctrl.autoPointsCheck, QtCore.SIGNAL('toggled(bool)'), self.updatePointMode)
        
        #QtCore.QObject.connect(self.ctrl.maxTracesCheck, QtCore.SIGNAL('toggled(bool)'), self.decimationChanged)
        #QtCore.QObject.connect(self.ctrl.maxTracesSpin, QtCore.SIGNAL('valueChanged(int)'), self.decimationChanged)
        QtCore.QObject.connect(c.xMouseCheck, QtCore.SIGNAL('toggled(bool)'), self.mouseCheckChanged)
        QtCore.QObject.connect(c.yMouseCheck, QtCore.SIGNAL('toggled(bool)'), self.mouseCheckChanged)
        
    def avgToggled(self, b):
        if b:
            self.recomputeAverages()
        for k in self.avgCurves:
            self.avgCurves[k][1].setVisible(b)
        
    def avgParamListClicked(self, item):
        name = str(item.text())
        self.paramList[name] = (item.checkState() == QtCore.Qt.Checked)
        self.recomputeAverages()
        
    def recomputeAverages(self):
        for k in self.avgCurves:
            self.removeItem(self.avgCurves[k][1])
            #Qwt.QwtPlotCurve.detach(self.avgCurves[k][1])
        self.avgCurves = {}
        for c in self.curves:
            self.addAvgCurve(c)
        #self.replot()
        
    def addAvgCurve(self, curve):
        """Add a single curve into the pool of curves averaged together"""
        
        ### First determine the key of the curve to which this new data should be averaged
        remKeys = []
        addKeys = []
        for i in range(self.ctrl.avgParamList.count()):
            item = self.ctrl.avgParamList.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                remKeys.append(str(item.text()))
            else:
                addKeys.append(str(item.text()))
                
        if len(remKeys) < 1:  ## In this case, there would be 1 average plot for each data plot; not useful.
            return
                
        p = curve.meta().copy()
        for k in p:
            if type(k) is tuple:
                p['.'.join(k)] = p[k]
                del p[k]
        for rk in remKeys:
            if rk in p:
                del p[rk]
        for ak in addKeys:
            if ak not in p:
                p[ak] = None
        key = tuple(p.items())
        
        ### Create a new curve if needed
        if key not in self.avgCurves:
            plot = PlotCurveItem()
            plot.setPen(QtGui.QPen(QtGui.QColor(0, 155, 0)))
            plot.setAlpha(1.0, False)
            plot.setZValue(100)
            self.addItem(plot)
            #Qwt.QwtPlotCurve.attach(plot, self)
            self.avgCurves[key] = [0, plot]
        self.avgCurves[key][0] += 1
        (n, plot) = self.avgCurves[key]
        
        ### Average data together
        if plot.yData is not None:
            newData = plot.yData * (n-1) / float(n) + curve.yData * 1.0 / float(n)
            plot.setData(plot.xData, newData)
        else:
            plot.setData(curve.xData, curve.yData)
        
        
    def mouseCheckChanged(self):
        state = [self.ctrl.xMouseCheck.isChecked(), self.ctrl.yMouseCheck.isChecked()]
        self.vb.setMouseEnabled(*state)
        
    def xRangeChanged(self, _, range):
        self.ctrl.xMinText.setText('%0.5g' % range[0])
        self.ctrl.xMaxText.setText('%0.5g' % range[1])

    def yRangeChanged(self, _, range):
        self.ctrl.yMinText.setText('%0.5g' % range[0])
        self.ctrl.yMaxText.setText('%0.5g' % range[1])


    def enableAutoScale(self):
        self.ctrl.xAutoRadio.setChecked(True)
        self.ctrl.yAutoRadio.setChecked(True)
        self.autoBtn.hide()
      
    def updateXScale(self):
        """Set plot to autoscale or not depending on state of radio buttons"""
        if self.ctrl.xManualRadio.isChecked():
            self.setManualXScale()
        else:
            self.setAutoXScale()
        
    def updateYScale(self, b=False):
        """Set plot to autoscale or not depending on state of radio buttons"""
        if self.ctrl.yManualRadio.isChecked():
            self.setManualYScale()
        else:
            self.setAutoYScale()

    def enableManualScale(self, v=[True, True]):
        if v[0]:
            self.autoScale[0] = False
            self.ctrl.xManualRadio.setChecked(True)
            #self.setManualXScale()
        if v[1]:
            self.autoScale[1] = False
            self.ctrl.yManualRadio.setChecked(True)
            #self.setManualYScale()
        self.autoBtn.show()
        
    def setManualXScale(self):
        self.autoScale[0] = False
        x1 = float(self.ctrl.xMinText.text())
        x2 = float(self.ctrl.xMaxText.text())
        self.ctrl.xManualRadio.setChecked(True)
        self.setXRange(x1, x2, padding=0)
        self.autoBtn.show()
        #self.replot()
        
    def setManualYScale(self):
        self.autoScale[1] = False
        y1 = float(self.ctrl.yMinText.text())
        y2 = float(self.ctrl.yMaxText.text())
        self.ctrl.yManualRadio.setChecked(True)
        self.setYRange(y1, y2, padding=0)
        self.autoBtn.show()
        #self.replot()

    def setAutoXScale(self):
        self.autoScale[0] = True
        self.ctrl.xAutoRadio.setChecked(True)
        
    def setAutoYScale(self):
        self.autoScale[1] = True
        self.ctrl.yAutoRadio.setChecked(True)

    def addItem(self, item, *args):
        self.items.append(item)
        self.vb.addItem(item, *args)
        
    def removeItem(self, item):
        if not item in self.items:
            return
        self.items.remove(item)
        self.vb.removeItem(item)
        if item in self.curves:
            self.curves.remove(item)
            self.updateDecimation()
            self.updateParamList()
            QtCore.QObject.connect(item, QtCore.SIGNAL('plotChanged'), self.plotChanged)

    def clear(self):
        for i in self.items[:]:
            self.removeItem(i)
        self.avgCurves = {}
        
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
            curve = PlotCurveItem()
        else:
            raise Exception('Not sure how to plot object of type %s' % type(data))
            
        #print data, curve
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
            
        QtCore.QObject.connect(c, QtCore.SIGNAL('plotChanged'), self.plotChanged)
        self.plotChanged()

    def plotChanged(self, curve=None):
        ## Recompute auto range if needed
        for ax in [0, 1]:
            if self.autoScale[ax]:
                mn = None
                mx = None
                for c in self.curves:
                    cmn, cmx = c.getRange(ax)
                    if mn is None or cmn < mn:
                        mn = cmn
                    if mx is None or cmx > mx:
                        mx = cmx
                self.setRange(ax, mn, mx)

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
        #curves = filter(lambda i: isinstance(i, Qwt.QwtPlotCurve), self.itemList())
        for c in self.curves:
            c.setSpectrumMode(b)
        self.enableAutoScale()
        #self.replot()
            
        
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
        
        

    #def mousePressEvent(self, ev):
        #self.mousePos = array([ev.pos().x(), ev.pos().y()])
        #self.pressPos = self.mousePos.copy()
        #QtGui.QGraphicsWidget.mousePressEvent(self, ev)
        ## NOTE: we will only receive move/release events if we run ev.accept()
        #print 'press'
        
    #def mouseReleaseEvent(self, ev):
        #pos = array([ev.pos().x(), ev.pos().y()])
        #print 'release'
        #if sum(abs(self.pressPos - pos)) < 3:  ## Detect click
            #if ev.button() == QtCore.Qt.RightButton:
                #print 'popup'
                #self.ctrlMenu.popup(self.mapToGlobal(ev.pos()))
        #self.mousePos = pos
        #QtGui.QGraphicsWidget.mouseReleaseEvent(self, ev)

    def resizeEvent(self, ev):
        self.ctrlBtn.move(0, self.size().height() - self.ctrlBtn.size().height())
        self.autoBtn.move(self.ctrlBtn.width(), self.size().height() - self.autoBtn.size().height())
        
    def hoverMoveEvent(self, ev):
        self.mousePos = ev.pos()
        self.mouseScreenPos = ev.screenPos()
        
    def ctrlBtnClicked(self):
        #print self.mousePos
        self.ctrlMenu.popup(self.mouseScreenPos)

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

    def _plotArray(self, arr, x=None):
        if arr.ndim != 1:
            raise Exception("Array must be 1D to plot (shape is %s)" % arr.shape)
        if x is None:
            x = arange(arr.shape[0])
        if x.ndim != 1:
            raise Exception("X array must be 1D to plot (shape is %s)" % x.shape)
        c = PlotCurveItem(arr, x=x)
        return c
            
        
        
    def _plotMetaArray(self, arr, x=None):
        inf = arr.infoCopy()
        if arr.ndim != 1:
            raise Exception('can only automatically plot 1 dimensional arrays.')
        ## create curve
        try:
            xv = arr.xvals(0)
            #print 'xvals:', xv
        except:
            if x is None:
                xv = arange(arr.shape[0])
            else:
                xv = x
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
      

