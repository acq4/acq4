from acq4.devices.TwoPhotonPhotostimulator.TwoPhotonPhotostimulator import TwoPhotonPhotostimulator
import acq4.pyqtgraph as pg

class PrairieViewPhotostimulator(TwoPhotonPhotostimulator):

    def __init__(self, deviceManager, config, name):
        TwoPhotonPhotostimulator.__init__(self, deviceManager, config, name)

        if config.get('mock', False):
            from acq4.util.MockPrairieView import MockPrairieView
            self.pv = MockPrairieView()
        else:
            ip = config.get('ipaddress', None)
            from acq4.util.PrairieView import PrairieView
            self.pv = PrairieView(ip)


    def mapToPrairie(self, pos, frame):
        """Map *pos* from global coordinates to frame coordinates, then map frame coordinates to between 0 and 1. """
        #frame = man.getModule('PrairieViewStimulator').window().interface.lastFrame ## get the last frame from PrairieImagerDevice
        ## map pos to frame coordinates, p will be in pixels

        p = pg.Point(frame.globalTransform().inverted()[0].map(pos))
        
        ## map from pixels to percent of image
        xPixels = frame.info()['PrairieMetaInfo']['Environment']['PixelsPerLine']
        yPixels = frame.info()['PrairieMetaInfo']['Environment']['LinesPerFrame']

        x = p.x()/float(xPixels)
        y = p.y()/float(yPixels)

        return (x, y)

    def isInBounds(self, pos, frame=None):
        pos = self.mapToPrairie(pos, frame)
        if (not 0 < pos[0] < 1) or (not 0 < pos[1] < 1):
            return False
        else:
            return True

    def spiralSizeToPrairie(self, size, frame):
        xPixels = frame.info()['PrairieMetaInfo']['Environment']['PixelsPerLine']
        pixelLength = frame.info()['PrairieMetaInfo']['Environment']['XAxis_umPerPixel']

        x=float(size*1000000)/float(xPixels)/pixelLength
        return x
    

    def runStimulation(self, params):
        self.pv.markPoints(params['pos'], params['laserPower'], params['duration'], params['spiralSize'], params['spiralRevolutions'], params['nPulses'], params['intervals'])
