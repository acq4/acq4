# -*- coding: utf-8 -*-
from acq4.pyqtgraph.Qt import QtCore, QtGui
from CanvasItem import CanvasItem
import numpy as np
import scipy.ndimage as ndimage
import acq4.pyqtgraph as pg
import acq4.util.DataManager as DataManager
import acq4.util.debug as debug

class ImageCanvasItem(CanvasItem):
    def __init__(self, image=None, **opts):
        """
        CanvasItem displaying an image. 
        The image may be 2 or 3-dimensional.
        Options:
            image: May be a fileHandle, ndarray, or GraphicsItem.
            handle: May optionally be specified in place of image

        """

        ## If no image was specified, check for a file handle..
        if image is None:
            image = opts.get('handle', None)

        item = None
        self.data = None
        self.currentT = None
        
        if isinstance(image, QtGui.QGraphicsItem):
            item = image
        elif isinstance(image, np.ndarray):
            self.data = image
        elif isinstance(image, DataManager.FileHandle):
            opts['handle'] = image
            self.handle = image
            self.data = self.handle.read()

            if 'name' not in opts:
                opts['name'] = self.handle.shortName()

            try:
                if 'transform' in self.handle.info():
                    tr = pg.SRTTransform3D(self.handle.info()['transform'])
                    tr = pg.SRTTransform(tr)  ## convert to 2D
                    opts['pos'] = tr.getTranslation()
                    opts['scale'] = tr.getScale()
                    opts['angle'] = tr.getRotation()
                else:  ## check for older info formats
                    if 'imagePosition' in self.handle.info():
                        opts['scale'] = self.handle.info()['pixelSize']
                        opts['pos'] = self.handle.info()['imagePosition']
                    elif 'Downsample' in self.handle.info():
                        ### Needed to support an older format stored by 2p imager
                        if 'pixelSize' in self.handle.info():
                            opts['scale'] = self.handle.info()['pixelSize']
                        if 'microscope' in self.handle.info():
                            m = self.handle.info()['microscope']
                            print 'm: ',m
                            print 'mpos: ', m['position']
                            opts['pos'] = m['position'][0:2]
                        else:
                            info = self.data._info[-1]
                            opts['pos'] = info.get('imagePosition', None)
                    elif hasattr(self.data, '_info'):
                        info = self.data._info[-1]
                        opts['scale'] = info.get('pixelSize', None)
                        opts['pos'] = info.get('imagePosition', None)
                    else:
                        opts['defaultUserTransform'] = {'scale': (1e-5, 1e-5)}
                        opts['scalable'] = True
            except:
                debug.printExc('Error reading transformation for image file %s:' % image.name())

        if item is None:
            item = pg.ImageItem()
        CanvasItem.__init__(self, item, **opts)

        self.histogram = pg.PlotWidget()
        self.blockHistogram = False
        self.histogram.setMaximumHeight(100)
        self.levelRgn = pg.LinearRegionItem()
        self.histogram.addItem(self.levelRgn)
        self.updateHistogram(autoLevels=True)

        # addWidget arguments: row, column, rowspan, colspan 
        self.layout.addWidget(self.histogram, self.layout.rowCount(), 0, 1, 3)

        self.timeSlider = QtGui.QSlider(QtCore.Qt.Horizontal)
        #self.timeSlider.setMinimum(0)
        #self.timeSlider.setMaximum(self.data.shape[0]-1)
        self.layout.addWidget(self.timeSlider, self.layout.rowCount(), 0, 1, 3)
        self.timeSlider.valueChanged.connect(self.timeChanged)
        self.timeSlider.sliderPressed.connect(self.timeSliderPressed)
        self.timeSlider.sliderReleased.connect(self.timeSliderReleased)
        thisRow = self.layout.rowCount()

        self.edgeBtn = QtGui.QPushButton('Edge')
        self.edgeBtn.clicked.connect(self.edgeClicked)
        self.layout.addWidget(self.edgeBtn, thisRow, 0, 1, 1)

        self.meanBtn = QtGui.QPushButton('Mean')
        self.meanBtn.clicked.connect(self.meanClicked)
        self.layout.addWidget(self.meanBtn, thisRow+1, 0, 1, 1)

        self.tvBtn = QtGui.QPushButton('tv denoise')
        self.tvBtn.clicked.connect(self.tvClicked)
        self.layout.addWidget(self.tvBtn, thisRow+2, 0, 1, 1)

        self.maxBtn = QtGui.QPushButton('Max no Filter')
        self.maxBtn.clicked.connect(self.maxClicked)
        self.layout.addWidget(self.maxBtn, thisRow, 1, 1, 1)

        self.maxBtn2 = QtGui.QPushButton('Max w/Gaussian')
        self.maxBtn2.clicked.connect(self.max2Clicked)
        self.layout.addWidget(self.maxBtn2, thisRow+1, 1, 1, 1)

        self.maxMedianBtn = QtGui.QPushButton('Max w/Median')
        self.maxMedianBtn.clicked.connect(self.maxMedianClicked)
        self.layout.addWidget(self.maxMedianBtn, thisRow+2, 1, 1, 1)

        self.filterOrder = QtGui.QComboBox()
        self.filterLabel = QtGui.QLabel('Order')
        for n in range(1,11):
            self.filterOrder.addItem("%d" % n)
        self.layout.addWidget(self.filterLabel, thisRow+3, 2, 1, 1)
        self.layout.addWidget(self.filterOrder, thisRow+3, 3, 1, 1)
        
        self.zPlanes = QtGui.QComboBox()
        self.zPlanesLabel = QtGui.QLabel('# planes')
        for s in ['All', '1', '2', '3', '4', '5']:
            self.zPlanes.addItem("%s" % s)
        self.layout.addWidget(self.zPlanesLabel, thisRow+3, 0, 1, 1)
        self.layout.addWidget(self.zPlanes, thisRow + 3, 1, 1, 1)

        ## controls that only appear if there is a time axis
        self.timeControls = [self.timeSlider, self.edgeBtn, self.maxBtn, self.meanBtn, self.maxBtn2,
            self.maxMedianBtn, self.filterOrder, self.zPlanes]

        if self.data is not None:
            self.updateImage(self.data)


        self.graphicsItem().sigImageChanged.connect(self.updateHistogram)
        self.levelRgn.sigRegionChanged.connect(self.levelsChanged)
        self.levelRgn.sigRegionChangeFinished.connect(self.levelsChangeFinished)

    @classmethod
    def checkFile(cls, fh):
        if not fh.isFile():
            return 0
        ext = fh.ext().lower()
        if ext == '.ma':
            return 10
        elif ext in ['.ma', '.png', '.jpg', '.tif']:
            return 100
        return 0

    def timeChanged(self, t):
        self.graphicsItem().updateImage(self.data[t])
        self.currentT = t

    def tRange(self):
        """
        for a window around the current image, define a range for
        averaging or whatever
        """
        sh = self.data.shape
        if self.currentT is None:
            tsel = range(0, sh[0])
        else:
            sel = self.zPlanes.currentText()
            if sel == 'All':
                tsel = range(0, sh[0])
            else:
                ir = int(sel)
                llim = self.currentT - ir
                if llim < 0:
                    llim = 0
                rlim = self.currentT + ir
                if rlim > sh[0]:
                    rlim = sh[0]
                tsel = range(llim, rlim)
        return tsel

    def timeSliderPressed(self):
        self.blockHistogram = True

    def edgeClicked(self):
        ## unsharp mask to enhance fine details
        fd = self.data.asarray().astype(float)
        blur = ndimage.gaussian_filter(fd, (0, 1, 1))
        blur2 = ndimage.gaussian_filter(fd, (0, 2, 2))
        dif = blur - blur2
        #dif[dif < 0.] = 0
        self.graphicsItem().updateImage(dif.max(axis=0))
        self.updateHistogram(autoLevels=True)

    def maxClicked(self):
        ## just the max of a stack
        tsel = self.tRange()
        fd = self.data[tsel,:,:].asarray().astype(float)
        self.graphicsItem().updateImage(fd.max(axis=0))
        print 'max stack image udpate done'
        self.updateHistogram(autoLevels=True)
        #print 'histogram updated'
        
    def max2Clicked(self):
        ## just the max of a stack, after a little 3d bluring
        tsel = self.tRange()
        fd = self.data[tsel,:,:].asarray().astype(float)
        filt = self.filterOrder.currentText()
        n = int(filt)
        blur = ndimage.gaussian_filter(fd, (n,n,n))
        print 'image blurred'
        self.graphicsItem().updateImage(blur.max(axis=0))
        print 'image udpate done'
        self.updateHistogram(autoLevels=True)
        #print 'histogram updated'

    def maxMedianClicked(self):
        ## just the max of a stack, after a little 3d bluring
        tsel = self.tRange()
        fd = self.data[tsel,:,:].asarray().astype(float)
        filt = self.filterOrder.currentText()
        n = int(filt) + 1 # value of 1 is no filter so start with 2
        blur = ndimage.median_filter(fd, size=n)
        self.graphicsItem().updateImage(blur.max(axis=0))
        self.updateHistogram(autoLevels=True)

    def meanClicked(self):
        ## just the max of a stack
        tsel = self.tRange()
        fd = self.data[tsel,:,:].asarray().astype(float)
        self.graphicsItem().updateImage(fd.mean(axis=0))
        self.updateHistogram(autoLevels=True)

    def tvClicked(self):
        tsel = self.tRange()
        fd = self.data[tsel,:,:].asarray().astype(float)
        filt = self.filterOrder.currentText()
        n = (int(filt) + 1) # value of 1 is no filter so start with 2
        blur = self.tv_denoise(fd, weight=n, n_iter_max=5)
        self.graphicsItem().updateImage(blur.max(axis=0))
        self.updateHistogram(autoLevels=True)

    def timeSliderReleased(self):
        self.blockHistogram = False
        self.updateHistogram()

    def updateHistogram(self, autoLevels=False):
        if self.blockHistogram:
            return
        x, y = self.graphicsItem().getHistogram()
        if x is None: ## image has no data
            return
        self.histogram.clearPlots()
        self.histogram.plot(x, y)
        if autoLevels:
            self.graphicsItem().updateImage(autoLevels=True)
            w, b = self.graphicsItem().getLevels()
            self.levelRgn.blockSignals(True)
            self.levelRgn.setRegion([w, b])
            self.levelRgn.blockSignals(False)

    def updateImage(self, data, autoLevels=True):
        self.data = data
        if data.ndim == 4:
            showTime = True
        elif data.ndim == 3:
            if data.shape[2] <= 4: ## assume last axis is color
                showTime = False
            else:
                showTime = True
        else:
            showTime = False

        if showTime:
            self.timeSlider.setMinimum(0)
            self.timeSlider.setMaximum(self.data.shape[0]-1)
            self.timeSlider.valueChanged.connect(self.timeChanged)
            self.timeSlider.sliderPressed.connect(self.timeSliderPressed)
            self.timeSlider.sliderReleased.connect(self.timeSliderReleased)
            #self.timeSlider.show()
            #self.maxBtn.show()
            self.graphicsItem().updateImage(data[self.timeSlider.value()])
        else:
            #self.timeSlider.hide()
            #self.maxBtn.hide()
            self.graphicsItem().updateImage(data, autoLevels=autoLevels)

        for widget in self.timeControls:
            widget.setVisible(showTime)

        tr = self.saveTransform()
        self.resetUserTransform()
        self.restoreTransform(tr)

        self.updateHistogram(autoLevels=autoLevels)

    def levelsChanged(self):
        rgn = self.levelRgn.getRegion()
        self.graphicsItem().setLevels(rgn)
        self.hideSelectBox()

    def levelsChangeFinished(self):
        self.showSelectBox()

    def _tv_denoise_3d(self, im, weight=100, eps=2.e-4, n_iter_max=200):
        """
        Perform total-variation denoising on 3-D arrays

        Parameters
        ----------
        im: ndarray
            3-D input data to be denoised

        weight: float, optional
            denoising weight. The greater ``weight``, the more denoising (at 
            the expense of fidelity to ``input``) 

        eps: float, optional
            relative difference of the value of the cost function that determines
            the stop criterion. The algorithm stops when:

                (E_(n-1) - E_n) < eps * E_0

        n_iter_max: int, optional
            maximal number of iterations used for the optimization.

        Returns
        -------
        out: ndarray
            denoised array

        Notes
        -----
        Rudin, Osher and Fatemi algorithm 

        Examples
        ---------
        First build synthetic noisy data
        >>> x, y, z = np.ogrid[0:40, 0:40, 0:40]
        >>> mask = (x -22)**2 + (y - 20)**2 + (z - 17)**2 < 8**2
        >>> mask = mask.astype(np.float)
        >>> mask += 0.2*np.random.randn(*mask.shape)
        >>> res = tv_denoise_3d(mask, weight=100)
        """
        px = np.zeros_like(im)
        py = np.zeros_like(im)
        pz = np.zeros_like(im)
        gx = np.zeros_like(im)
        gy = np.zeros_like(im)
        gz = np.zeros_like(im)
        d = np.zeros_like(im)
        i = 0
        while i < n_iter_max:
            d = - px - py - pz
            d[1:] += px[:-1] 
            d[:, 1:] += py[:, :-1] 
            d[:, :, 1:] += pz[:, :, :-1] 
        
            out = im + d
            E = (d**2).sum()

            gx[:-1] = np.diff(out, axis=0) 
            gy[:, :-1] = np.diff(out, axis=1) 
            gz[:, :, :-1] = np.diff(out, axis=2) 
            norm = np.sqrt(gx**2 + gy**2 + gz**2)
            E += weight * norm.sum()
            norm *= 0.5 / weight
            norm += 1.
            px -= 1./6.*gx
            px /= norm
            py -= 1./6.*gy
            py /= norm
            pz -= 1/6.*gz
            pz /= norm
            E /= float(im.size)
            if i == 0:
                E_init = E
                E_previous = E
            else:
                if np.abs(E_previous - E) < eps * E_init:
                    break
                else:
                    E_previous = E
            i += 1
        return out
 
    def _tv_denoise_2d(self, im, weight=50, eps=2.e-4, n_iter_max=200):
        """
        Perform total-variation denoising

        Parameters
        ----------
        im: ndarray
            input data to be denoised

        weight: float, optional
            denoising weight. The greater ``weight``, the more denoising (at 
            the expense of fidelity to ``input``) 

        eps: float, optional
            relative difference of the value of the cost function that determines
            the stop criterion. The algorithm stops when:

                (E_(n-1) - E_n) < eps * E_0

        n_iter_max: int, optional
            maximal number of iterations used for the optimization.

        Returns
        -------
        out: ndarray
            denoised array

        Notes
        -----
        The principle of total variation denoising is explained in
        http://en.wikipedia.org/wiki/Total_variation_denoising

        This code is an implementation of the algorithm of Rudin, Fatemi and Osher 
        that was proposed by Chambolle in [1]_.

        References
        ----------

        .. [1] A. Chambolle, An algorithm for total variation minimization and 
               applications, Journal of Mathematical Imaging and Vision, 
               Springer, 2004, 20, 89-97.

        Examples
        ---------
        >>> import scipy
        >>> lena = scipy.lena()
        >>> import scipy
        >>> lena = scipy.lena().astype(np.float)
        >>> lena += 0.5 * lena.std()*np.random.randn(*lena.shape)
        >>> denoised_lena = tv_denoise(lena, weight=60.0)
        """
        px = np.zeros_like(im)
        py = np.zeros_like(im)
        gx = np.zeros_like(im)
        gy = np.zeros_like(im)
        d = np.zeros_like(im)
        i = 0
        while i < n_iter_max:
            d = -px -py
            d[1:] += px[:-1] 
            d[:, 1:] += py[:, :-1] 
        
            out = im + d
            E = (d**2).sum()
            gx[:-1] = np.diff(out, axis=0) 
            gy[:, :-1] = np.diff(out, axis=1) 
            norm = np.sqrt(gx**2 + gy**2)
            E += weight * norm.sum()
            norm *= 0.5 / weight
            norm += 1
            px -= 0.25*gx
            px /= norm
            py -= 0.25*gy
            py /= norm
            E /= float(im.size)
            if i == 0:
                E_init = E
                E_previous = E
            else:
                if np.abs(E_previous - E) < eps * E_init:
                    break
                else:
                    E_previous = E
            i += 1
        return out

    def tv_denoise(self, im, weight=50, eps=2.e-4, keep_type=False, n_iter_max=200):
        """
        Perform total-variation denoising on 2-d and 3-d images

        Parameters
        ----------
        im: ndarray (2d or 3d) of ints, uints or floats
            input data to be denoised. `im` can be of any numeric type,
            but it is cast into an ndarray of floats for the computation 
            of the denoised image.

        weight: float, optional
            denoising weight. The greater ``weight``, the more denoising (at 
            the expense of fidelity to ``input``) 

        eps: float, optional
            relative difference of the value of the cost function that 
            determines the stop criterion. The algorithm stops when:

                (E_(n-1) - E_n) < eps * E_0

        keep_type: bool, optional (False)
            whether the output has the same dtype as the input array. 
            keep_type is False by default, and the dtype of the output
            is np.float

        n_iter_max: int, optional
            maximal number of iterations used for the optimization.

        Returns
        -------
        out: ndarray
            denoised array


        Notes
        -----
        The principle of total variation denoising is explained in
        http://en.wikipedia.org/wiki/Total_variation_denoising

        The principle of total variation denoising is to minimize the
        total variation of the image, which can be roughly described as 
        the integral of the norm of the image gradient. Total variation 
        denoising tends to produce "cartoon-like" images, that is, 
        piecewise-constant images.

        This code is an implementation of the algorithm of Rudin, Fatemi and Osher 
        that was proposed by Chambolle in [1]_.

        References
        ----------

        .. [1] A. Chambolle, An algorithm for total variation minimization and 
               applications, Journal of Mathematical Imaging and Vision, 
               Springer, 2004, 20, 89-97.

        Examples
        ---------
        >>> import scipy
        >>> # 2D example using lena
        >>> lena = scipy.lena()
        >>> import scipy
        >>> lena = scipy.lena().astype(np.float)
        >>> lena += 0.5 * lena.std()*np.random.randn(*lena.shape)
        >>> denoised_lena = tv_denoise(lena, weight=60)
        >>> # 3D example on synthetic data
        >>> x, y, z = np.ogrid[0:40, 0:40, 0:40]
        >>> mask = (x -22)**2 + (y - 20)**2 + (z - 17)**2 < 8**2
        >>> mask = mask.astype(np.float)
        >>> mask += 0.2*np.random.randn(*mask.shape)
        >>> res = tv_denoise_3d(mask, weight=100)
        """
        im_type = im.dtype
        if not im_type.kind == 'f':
            im = im.astype(np.float)

        if im.ndim == 2:
            out = self._tv_denoise_2d(im, weight, eps, n_iter_max)
        elif im.ndim == 3:
            out = self._tv_denoise_3d(im, weight, eps, n_iter_max)
        else:
            raise ValueError('only 2-d and 3-d images may be denoised with this function')
        if keep_type:
            return out.astype(im_type)
        else:
            return out



