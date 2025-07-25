import numpy
import scipy.ndimage
import scipy.signal

import acq4.util.Mutex as Mutex
from acq4.devices.Device import Device, DeviceTask
from acq4.devices.NiDAQ.taskGUI import NiDAQTask
from acq4.util.debug import printExc


class NiDAQ(Device):
    """
    National Instruments DAQ device for multi-channel analog/digital I/O operations.
    
    Provides buffered and unbuffered analog/digital input/output with hardware timing,
    triggering, and synchronized multi-channel data acquisition.
    
    Configuration options:
    
    * **mock** (bool, optional): If True, use mock DAQ instead of real hardware. Default: False
    
    * **device** (str, optional): Specific DAQ device name to use (e.g., 'Dev1'). If not specified,
      uses any available device
    
    * **defaultAIMode** (str, optional): Default input mode for analog input channels
        - 'rse': Referenced single-ended (default)
        - 'nrse': Non-referenced single-ended  
        - 'diff': Differential
    
    * **defaultAIRange** (list, optional): Default voltage range for analog inputs as [min, max].
      Default: [-10, 10]
    
    * **defaultAORange** (list, optional): Default voltage range for analog outputs as [min, max].
      Default: [-10, 10]
    
    Example configuration::
    
        DAQ:
            driver: 'NiDAQ'
            device: 'Dev1'
            defaultAIMode: 'NRSE'
            defaultAIRange: [-10, 10]
            defaultAORange: [-10, 10]
    
        # Other devices reference DAQ channels using standard syntax:
        SomeDevice:
            driver: 'DAQGeneric'
            channels:
                inputChan:
                    device: 'DAQ'
                    channel: '/Dev1/ai0'
                    type: 'ai'
                outputChan:
                    device: 'DAQ'
                    channel: '/Dev1/ao0'
                    type: 'ao'
    """

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.config = config
        self.exclusiveDevice = config.get('device', None)
        self._defaultAIRange = config.get('defaultAIRange', [-10, 10])
        self._defaultAORange = config.get('defaultAORange', [-10, 10])

        ## make local copy of device handle
        if config is not None and config.get('mock', False):
            from acq4.drivers.nidaq.mock import NIDAQ
        else:
            from acq4.drivers.nidaq.nidaq import NIDAQ
        self.n = NIDAQ
        print(f"Created NiDAQ handle, devices are {self.n.listDevices()!r}")
        self.delayedSet = Mutex.threadsafe({})

    def createTask(self, cmd, parentTask):
        return Task(self, cmd, parentTask)

    def setChannelValue(self, chan, value, block=False, delaySetIfBusy=False, ignoreLock=False):
        """Set a channel on this DAQ. 
        Arguments:
            block: bool. If True, wait until the device is available. 
                   If False, return immediately if the device is not available.
            delaySetIfBusy: If True and the hardware is currently reserved, then
                            schedule the set to occur immediately when the hardware becomes available again.
            ignoreLock: attempt to set the channel value even if the device is reserved.
        Returns True if the channel was set, False otherwise.
        """
        if ignoreLock:
            res = True
        else:
            res = self.reserve(block=block)

        self.verifyChannelBelongs(chan)

        if not block and not res:
            if delaySetIfBusy:
                self.delayedSet[chan] = value
            return False

        try:
            if 'ao' in chan:
                self.n.writeAnalogSample(chan, value, vRange=self._defaultAORange)
            else:
                if value is True or value == 1:
                    value = 0xFFFFFFFF
                else:
                    value = 0
                self.n.writeDigitalSample(chan, value)
        except:
            print(f"Error while setting channel {chan} to {value}:")
            raise
        finally:
            if not ignoreLock:
                self.release()
        return True

    def verifyChannelBelongs(self, chan):
        if self.exclusiveDevice is not None and not chan.startswith(f"/{self.exclusiveDevice}/"):
            raise ValueError(f"Channel {chan} does not belong to device {self.exclusiveDevice}")

    def release(self):
        ## take care of any channel-value-set requests that arrived while the device was locked
        try:
            self.delayedSet.lock()
            for chan, val in self.delayedSet.items():
                try:
                    self.setChannelValue(chan, val, ignoreLock=True)
                except Exception:
                    printExc("Error resetting channel value:")
            self.delayedSet.clear()
        finally:
            self.delayedSet.unlock()
        return Device.release(self)

    def getChannelValue(self, chan, mode=None, block=True):
        if mode is None:
            mode = self.config.get('defaultAIMode', None)

        self.verifyChannelBelongs(chan)
        res = self.reserve(block=block)
        if not res:  ## False means non-blocking lock attempt failed.
            return False
        try:
            if 'ai' in chan:
                val = self.n.readAnalogSample(chan, mode=mode, vRange=self._defaultAIRange)
            else:
                val = self.n.readDigitalSample(chan)
                if val <= 0:
                    val = 0
                else:
                    val = 1
        except:
            print(f"Error while getting channel value {chan}:")
            raise
        finally:
            self.release()
        return val

    def taskInterface(self, taskRunner):
        return NiDAQTask(self, taskRunner)

    # def listTriggerPorts(self):
    # p = self.n.listDILines()
    # return [x for x in p if 'PFI' in x]

    @staticmethod
    def downsample(data, ds, method, **kargs):
        if method == 'subsample':
            data = data[::ds].copy()

        elif method == 'mean':
            # MC: broken code, commented out.
            raise ValueError("Mean resampling not implemented.")
            # decimate by averaging points together (does not remove HF noise, just folds it down.)
            # if res['info']['type'] in ['di', 'do']:
            #     data = NiDAQ.meanResample(data, ds, binary=True)
            # else:
            #     data = NiDAQ.meanResample(data, ds)

        elif method == 'fourier':
            # Decimate using fourier resampling -- causes ringing artifacts, very slow to compute (possibly uses butterworth filter?)
            newLen = int(data.shape[0] / ds)
            data = scipy.signal.resample(data, newLen, window=8)  # Use a kaiser window with beta=8

        elif method == 'bessel_mean':
            # Lowpass, then average. Bessel filter has less efficient lowpass characteristics and filters some of the passband as well.
            data = NiDAQ.lowpass(data, 2.0 / ds, filter='bessel', order=4, bidir=True)
            data = NiDAQ.meanResample(data, ds)

        elif method == 'butterworth_mean':
            # Lowpass, then average. Butterworth filter causes ringing artifacts.
            data = NiDAQ.lowpass(data, 1.0 / ds, bidir=True, filter='butterworth')
            data = NiDAQ.meanResample(data, ds)

        elif method == 'lowpass_mean':
            # Lowpass, then average. (for testing)
            data = NiDAQ.lowpass(data, **kargs)
            data = NiDAQ.meanResample(data, ds)

        return data

    @staticmethod
    def meanResample(data, ds, binary=False):
        """Resample data by taking mean of ds samples at a time"""
        newLen = int(data.shape[0] / ds) * ds
        data = data[:newLen]
        data.shape = (int(data.shape[0] / ds), ds)
        if binary:
            return data.mean(axis=1).round().astype(numpy.byte)
        else:
            return data.mean(axis=1)

    @staticmethod
    def lowpass(data, cutoff, order=4, bidir=True, filter='bessel', stopCutoff=None, gpass=2., gstop=20.,
                samplerate=None):
        """Bi-directional bessel/butterworth lowpass filter"""
        if samplerate is not None:
            cutoff /= 0.5 * samplerate
            if stopCutoff is not None:
                stopCutoff /= 0.5 * samplerate

        if filter == 'bessel':
            ## How do we compute Wn?
            ### function determining magnitude transfer of 4th-order bessel filter
            # from scipy.optimize import fsolve

            # def m(w):
            # return 105. / (w**8 + 10*w**6 + 135*w**4 + 1575*w**2 + 11025.)**0.5
            # v = fsolve(lambda x: m(x)-limit, 1.0)
            # Wn = cutoff / (sampr*v)
            b, a = scipy.signal.bessel(order, cutoff, btype='low')
        elif filter == 'butterworth':
            if stopCutoff is None:
                stopCutoff = cutoff * 2.0
            ord, Wn = scipy.signal.buttord(cutoff, stopCutoff, gpass, gstop)
            b, a = scipy.signal.butter(ord, Wn, btype='low')
        else:
            raise ValueError(f'Unknown filter type "{filter}"')

        padded = numpy.hstack(
            [data[:100], data, data[-100:]])  ## can we intelligently decide how many samples to pad with?

        if bidir:
            data = scipy.signal.lfilter(b, a, scipy.signal.lfilter(b, a, padded)[::-1])[::-1][
                   100:-100]  ## filter twice; once forward, once reversed. (This eliminates phase changes)
        else:
            data = scipy.signal.lfilter(b, a, padded)[100:-100]
        return data

    @staticmethod
    def denoise(data, radius=2, threshold=4):
        """Very simple noise removal function. Compares a point to surrounding points,
        replaces with nearby values if the difference is too large."""

        r2 = radius * 2
        d2 = data[radius:] - data[:-radius]  # a derivative
        stdev = d2.std()
        mask1 = d2 > stdev * threshold  # where derivative is large and positive
        mask2 = d2 < -stdev * threshold  # where derivative is large and negative
        maskpos = mask1[:-radius] * mask2[radius:]  # both need to be true
        maskneg = mask1[radius:] * mask2[:-radius]
        mask = maskpos + maskneg
        # where both are true replace the value with the value from 2 points before
        d5 = numpy.where(mask, data[:-r2], data[radius:-radius])
        d6 = numpy.empty(data.shape, dtype=data.dtype)  # add points back to the ends
        d6[radius:-radius] = d5
        d6[:radius] = data[:radius]
        d6[-radius:] = data[-radius:]
        return d6


class Task(DeviceTask):
    def __init__(self, dev, cmd, parentTask):
        DeviceTask.__init__(self, dev, cmd, parentTask)
        self.cmd = cmd

        ## Create supertask from nidaq driver
        self.st = self.dev.n.createSuperTask()

    def getChanSampleRate(self, ch):
        """Return the sample rate that will be used for ch"""

        return self.cmd['rate']  ## currently, all channels use the same rate

    def configure(self):
        # defaultAIMode = self.dev.config.get('defaultAIMode', None)

        ## Request to all devices that they create the channels they use on this task
        tasks = self.parentTask().tasks
        for dName in tasks:
            if hasattr(tasks[dName], 'createChannels'):
                tasks[dName].createChannels(self)

        ## If no devices requested buffered operations, then do not configure clock.
        ## This might eventually cause some triggering issues..
        if not self.st.hasTasks():
            return

        ## Determine the sample clock source, configure tasks
        self.st.configureClocks(rate=self.cmd['rate'], nPts=self.cmd['numPts'])

        ## Determine how the task will be triggered
        if 'triggerChan' in self.cmd:
            self.st.setTrigger(self.cmd['triggerChan'])
        elif 'triggerDevice' in self.cmd:
            tDevName = self.cmd['triggerDevice']
            tDev = self.dev.dm.getDevice(tDevName)
            triggerChan = tDev.getTriggerChannels(self.dev.name())['input']
            assert triggerChan is not None, f"Task requests for {tDevName} to trigger {self.dev.name()}, but no trigger channel is configured between these devices."
            self.st.setTrigger(triggerChan)

    def getStartOrder(self):
        before = []
        after = []
        if 'triggerDevice' in self.cmd:
            after.append(self.cmd['triggerDevice'])
        return before, after

    def addChannel(self, channel, type, mode=None, **kwargs):
        ## set default channel mode before adding
        if type == 'ai':
            if mode is None:
                mode = self.dev.config.get('defaultAIMode', None)
            if 'vRange' not in kwargs:
                kwargs['vRange'] = self.dev._defaultAIRange
        elif type == 'ao':
            if 'vRange' not in kwargs:
                kwargs['vRange'] = self.dev._defaultAORange

        return self.st.addChannel(channel, type, mode, **kwargs)

    def setWaveform(self, *args, **kwargs):
        return self.st.setWaveform(*args, **kwargs)

    def start(self):
        if self.st.hasTasks():
            self.st.start()

    def isDone(self):
        if self.st.hasTasks():
            return self.st.isDone()
        else:
            return True

    def stop(self, wait=False, abort=False):
        if self.st.hasTasks():
            self.st.stop(wait=wait, abort=abort)

    def getResult(self):
        ## Results should be collected by individual devices using getData
        return None

    def storeResult(self, dirHandle):
        pass

    def getData(self, channel):
        """Return the data collected for a specific channel. Return looks like:
        {
          'data': ndarray,
          'info': {'rate': xx, 'numPts': xx, ...}
        }
        """
        res = self.st.getResult(channel)
        data = res['data']

        if 'downsample' in self.cmd:
            ds = self.cmd['downsample']
        else:
            ds = 1

        if 'filterMethod' in self.cmd:
            method = self.cmd['filterMethod']

            if method == 'None':
                pass
            # elif method == 'gaussian':
            # width = self.cmd['gaussianWidth']

            # data = scipy.ndimage.gaussian_filter(data, width)

            # res['info']['filterMethod'] = method
            # res['info']['filterWidth'] = width
            elif method == 'Bessel':
                cutoff = self.cmd['besselCutoff']
                order = self.cmd['besselOrder']
                bidir = self.cmd.get('besselBidirectional', True)
                data = NiDAQ.lowpass(data, filter='bessel', bidir=bidir, cutoff=cutoff, order=order,
                                     samplerate=res['info']['rate'])

                res['info']['filterMethod'] = method
                res['info']['filterCutoff'] = cutoff
                res['info']['filterOrder'] = order
                res['info']['filterBidirectional'] = bidir
            elif method == 'Butterworth':
                passF = self.cmd['butterworthPassband']
                stopF = self.cmd['butterworthStopband']
                passDB = self.cmd['butterworthPassDB']
                stopDB = self.cmd['butterworthStopDB']
                bidir = self.cmd.get('butterworthBidirectional', True)

                data = NiDAQ.lowpass(data, filter='butterworth', bidir=bidir, cutoff=passF, stopCutoff=stopF,
                                     gpass=passDB, gstop=stopDB, samplerate=res['info']['rate'])

                res['info']['filterMethod'] = method
                res['info']['filterPassband'] = passF
                res['info']['filterStopband'] = stopF
                res['info']['filterPassbandDB'] = passDB
                res['info']['filterStopbandDB'] = stopDB
                res['info']['filterBidirectional'] = bidir

            else:
                printExc(f"Unknown filter method '{method}'")

        if ds > 1:
            if res['info']['type'] in ['di', 'do']:
                res['data'] = (res['data'] > 0).astype(numpy.byte)
                data = data[::ds]
                res['info']['downsampling'] = ds
                res['info']['downsampleMethod'] = 'subsample'
                res['info']['rate'] = res['info']['rate'] / ds
            elif res['info']['type'] in ['ai', 'ao']:
                data = NiDAQ.meanResample(data, ds)
                res['info']['downsampling'] = ds
                res['info']['downsampleMethod'] = 'mean'
                res['info']['rate'] = res['info']['rate'] / ds

        if 'denoiseMethod' in self.cmd:
            method = self.cmd['denoiseMethod']
            if method == 'None':
                pass
            elif method == 'Pointwise':
                width = self.cmd['denoiseWidth']
                thresh = self.cmd['denoiseThreshold']

                res['info']['denoiseMethod'] = method
                res['info']['denoiseWidth'] = width
                res['info']['denoiseThreshold'] = thresh
                data = NiDAQ.denoise(data, width, thresh)
            else:
                printExc(f"Unknown denoise method '{method}'")

        res['data'] = data
        res['info']['numPts'] = data.shape[0]

        return res

    def devName(self):
        return self.dev.name()
