# -*- coding: utf-8 -*-
from CanvasItem import CanvasItem


class ScanCanvasItem(CanvasItem):
    def __init__(self, item, **opts):
    #def addScan(self, dirHandle, **opts):
        #"""Returns a list of ScanCanvasItems."""
        
        #if 'sequenceParams' in dirHandle.info():
            #dirs = [dirHandle[d] for d in dirHandle.subDirs()]
        #else:
            #dirs = [dirHandle]
            
        #if 'separateParams' not in opts:
            #separateParams = False
        #else:
            #separateParams = opts['separateParams']
            #del(opts['separateParams'])
            
        
        #### check for sequence parameters (besides targets) so that we can separate them out into individual Scans
        #paramKeys = []
        #params = dirHandle.info()['protocol']['params']
        #if len(params) > 1 and separateParams==True:
            #for i in range(len(params)):
                #k = (params[i][0], params[i][1])
                #if k != ('Scanner', 'targets'):
                    #paramKeys.append(k)
            
        #if 'name' not in opts:
            #opts['name'] = dirHandle.shortName()
            

            
        #if len(paramKeys) < 1:    
            #pts = []
            #for d in dirs: #d is a directory handle
                ##d = dh[d]
                #if 'Scanner' in d.info() and 'position' in d.info()['Scanner']:
                    #pos = d.info()['Scanner']['position']
                    #if 'spotSize' in d.info()['Scanner']:
                        #size = d.info()['Scanner']['spotSize']
                    #else:
                        #size = self.defaultSize
                    #pts.append({'pos': pos, 'size': size, 'data': d})
            
            #item = graphicsItems.ScatterPlotItem(pts, pxMode=False)
            #citem = ScanCanvasItem(self, item, handle=dirHandle, **opts)
            #self._addCanvasItem(citem)
            #return [citem]
        #else:
            #pts = {}
            #for d in dirs:
                #k = d.info()[paramKeys[0]]
                #if len(pts) < k+1:
                    #pts[k] = []
                #if 'Scanner' in d.info() and 'position' in d.info()['Scanner']:
                    #pos = d.info()['Scanner']['position']
                    #if 'spotSize' in d.info()['Scanner']:
                        #size = d.info()['Scanner']['spotSize']
                    #else:
                        #size = self.defaultSize
                    #pts[k].append({'pos': pos, 'size': size, 'data': d})
            #spots = []
            #for k in pts.keys():
                #spots.extend(pts[k])
            #item = graphicsItems.ScatterPlotItem(spots=spots, pxMode=False)
            #parentCitem = ScanCanvasItem(self, item, handle=dirHandle, **opts)
            #self._addCanvasItem(parentCitem)
            #scans = []
            #for k in pts.keys():
                #opts['name'] = paramKeys[0][0] + '_%03d' %k
                #item = graphicsItems.ScatterPlotItem(spots=pts[k], pxMode=False)
                #citem = ScanCanvasItem(self, item, handle = dirHandle, parent=parentCitem, **opts)
                #self._addCanvasItem(citem)
                ##scans[opts['name']] = citem
                #scans.append(citem)
            #return scans
        
        #print "Creating ScanCanvasItem...."
        CanvasItem.__init__(self, item, **opts)
        
        self.addScanImageBtn = QtGui.QPushButton()
        self.addScanImageBtn.setText('Add Scan Image')
        self.layout.addWidget(self.addScanImageBtn,4,0,1,2)
        
        self.addScanImageBtn.connect(self.addScanImageBtn, QtCore.SIGNAL('clicked()'), self.loadScanImage)
        
    def loadScanImage(self):
        #print 'loadScanImage called.'
        #dh = self.ui.fileLoader.ui.dirTree.selectedFile()
        #scan = self.canvas.selectedItem()
        dh = self.opts['handle']
        dirs = [dh[d] for d in dh.subDirs()]
        if 'Camera' not in dirs[0].subDirs():
            print "No image data for this scan."
            return
        
        images = []
        nulls = []
        for d in dirs:
            if 'Camera' not in d.subDirs():
                continue
            frames = d['Camera']['frames.ma'].read()
            image = frames[1]-frames[0]
            image[frames[0] > frames[1]] = 0.  ## unsigned type; avoid negative values
            mx = image.max()
            if mx < 50:
                nulls.append(d.shortName())
                continue
            image *= (1000. / mx)
            images.append(image)
            
        print "Null frames for %s:" %dh.shortName(), nulls
        scanImages = np.zeros(images[0].shape)
        for im in images:
            mask = im > scanImages
            scanImages[mask] = im[mask]
        
        info = dirs[0]['Camera']['frames.ma'].read()._info[-1]
    
        pos =  info['imagePosition']
        scale = info['pixelSize']
        item = self.canvas.addImage(scanImages, pos=pos, scale=scale, z=self.opts['z']-1, name='scanImage')
        self.scanImage = item
        
        self.scanImage.restoreTransform(self.saveTransform())
        
        #self.canvas.items[item] = scanImages
        
