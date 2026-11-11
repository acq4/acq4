import math

import numpy
import scipy.ndimage
import scipy.signal

import acq4.util.Mutex as Mutex
from acq4.devices.Device import Device, DeviceTask
from acq4.devices.NiDAQ.accumulator import DaqChannelAccumulator
from acq4.devices.NiDAQ.taskGUI import NiDAQTask
from acq4.util.partial_results import SettleSpec


class NiDAQ(Device):
    """
    National Instruments DAQ device for multi-channel analog/digital I/O operations.
    
    Provides buffered and unbuffered analog/digital input/output with hardware timing,
    triggering, and synchronized multi-channel data acquisition.
    
    Configuration options:
    
    * **mock** (bool, optional): If True, use mock DAQ instead of real hardware. Default: False
    
    * **device** (str, optional): Specific DAQ device name to use (e.g., 'Dev1'). If not specified,
      uses any available device. This allows multiple NiDAQ devices to be used simultaneously by 
      different users (as long as the underlying hardware supports this).
    
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
        self.exclusiveDevice = config.get('device', None)
        self._defaultAIRange = config.get('defaultAIRange', [-10, 10])
        self._defaultAORange = config.get('defaultAORange', [-10, 10])

        ## make local copy of device handle
        if config is not None and config.get('mock', False):
            from acq4.drivers.nidaq.mock import NIDAQ
        else:
            from acq4.drivers.nidaq.nidaq import NIDAQ
        self.n = NIDAQ
        self.logger.info(f"Created NiDAQ handle, devices are {self.n.listDevices()!r}")
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
            res = self.reserve(block=block, reserver=f"{self.name()}.setChannelValue")

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
            self.logger.error(
                f"Error while setting channel {chan} to {value!r} "
                f"(range {self._defaultAORange}, block={block}, ignoreLock={ignoreLock})"
            )
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
                    self.logger.exception("Error resetting channel value:")
            self.delayedSet.clear()
        finally:
            self.delayedSet.unlock()
        return Device.release(self)

    def getChannelValue(self, chan, mode=None, block=True):
        if mode is None:
            mode = self.config.get('defaultAIMode', None)

        self.verifyChannelBelongs(chan)
        res = self.reserve(block=block, reserver=f"{self.name()}.getChannelValue")
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
        b, a = NiDAQ.lowpassDesign(cutoff, order=order, filter=filter, stopCutoff=stopCutoff, gpass=gpass,
                                   gstop=gstop, samplerate=samplerate)

        padded = numpy.hstack(
            [data[:100], data, data[-100:]])  ## can we intelligently decide how many samples to pad with?

        if bidir:
            data = scipy.signal.lfilter(b, a, scipy.signal.lfilter(b, a, padded)[::-1])[::-1][
                   100:-100]  ## filter twice; once forward, once reversed. (This eliminates phase changes)
        else:
            data = scipy.signal.lfilter(b, a, padded)[100:-100]
        return data

    @staticmethod
    def lowpassDesign(cutoff, order=4, filter='bessel', stopCutoff=None, gpass=2., gstop=20., samplerate=None,
                      output='ba'):
        """Return the filter lowpass() applies: (b, a), or (z, p, k) with output='zpk'."""
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
            return scipy.signal.bessel(order, cutoff, btype='low', output=output)
        elif filter == 'butterworth':
            if stopCutoff is None:
                stopCutoff = cutoff * 2.0
            ord, Wn = scipy.signal.buttord(cutoff, stopCutoff, gpass, gstop)
            return scipy.signal.butter(ord, Wn, btype='low', output=output)
        else:
            raise ValueError(f'Unknown filter type "{filter}"')

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

        self._accumulators = {}  # absolute channel name -> DaqChannelAccumulator
        self._chunkListeners = ()  # replaced, never mutated: read on the reader thread
        self._disabledAccumulators = set()  # channel names, this run
        self._disabledListeners = set()  # ids of listeners in _chunkListeners, this run
        self._emitFailed = False
        self._clocksConfigured = False
        self._settleSpecs = {}

    def getChanSampleRate(self, ch):
        """Return the sample rate that will be used for ch"""

        return self.cmd['rate']  ## currently, all channels use the same rate

    def configure(self):
        # defaultAIMode = self.dev.config.get('defaultAIMode', None)

        self._settleSpecs = {}
        self._disabledAccumulators = set()
        self._disabledListeners = set()
        self._emitFailed = False

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
        self._clocksConfigured = True

        ## Determine how the task will be triggered
        if 'triggerChan' in self.cmd:
            self.st.setTrigger(self.cmd['triggerChan'])
        elif 'triggerDevice' in self.cmd:
            tDevName = self.cmd['triggerDevice']
            tDev = self.dev.dm.getDevice(tDevName)
            triggerChan = tDev.getTriggerChannels(self.dev.name())['input']
            assert triggerChan is not None, f"Task requests for {tDevName} to trigger {self.dev.name()}, but no trigger channel is configured between these devices."
            self.st.setTrigger(triggerChan)

        for acc in list(self._accumulators.values()):
            self._prepareAccumulator(acc)
        self._configureChunks()

    def _prepareAccumulator(self, acc):
        """Ready *acc* for this run: reset an input channel, settle an output channel from its waveform."""
        if acc.chanType in ('ao', 'do'):
            try:
                acc.setOutputWaveform(self.st.outputChannelData(acc.channel))
            except Exception:
                self.dev.logger.warning(f"No partial results for output channel {acc.channel}", exc_info=True)
        else:
            acc.reset(self.st.rawChannelData(acc.channel).dtype)

    def _configureChunks(self):
        """Install the chunk handler if the parent task requests partial results."""
        interval = self.parentTask().updateInterval()
        if interval is None:
            return
        rate = self.cmd['rate']
        nPts = self.cmd['numPts']
        ds = self.cmd.get('downsample', 1)
        ds = int(ds) if ds > 1 else 1
        chunkSize = math.ceil(round(interval * rate / ds, 6)) * ds  # round: float error must not add a bin
        if chunkSize >= nPts:
            reason = f"update interval ({interval:g} s) is not shorter than the acquisition ({nPts / rate:g} s)"
            self._settleSpecs = {'': SettleSpec(math.inf, reason)}
            self.dev.logger.info(f"No partial results: {reason}")
            return
        self.st.setChunkHandler(chunkSize, self._onChunk)

    def _onChunk(self, nAcquired):
        """SuperTask chunk handler (reader thread): update input accumulators, call chunk listeners, then emit.

        A failing accumulator or listener is logged and skipped for the rest of the run; nothing raises.
        """
        for acc in list(self._accumulators.values()):
            if acc.chanType not in ('ai', 'di') or acc.channel in self._disabledAccumulators:
                continue
            try:
                acc.update(self.st.rawChannelData(acc.channel), nAcquired)
            except Exception:
                self._disabledAccumulators.add(acc.channel)
                self.dev.logger.exception(f"Partial results for {acc.channel} failed; disabled for this run")
        for fn in self._chunkListeners:
            if id(fn) in self._disabledListeners:
                continue
            try:
                fn()
            except Exception:
                self._disabledListeners.add(id(fn))
                self.dev.logger.exception(f"DAQ chunk listener {fn!r} failed; disabled for this run")
        try:
            self.parentTask().emitPartialResults()
        except Exception:
            if not self._emitFailed:
                self._emitFailed = True
                self.dev.logger.exception("Error emitting partial task results")

    def channelAccumulator(self, channel):
        """Return the DaqChannelAccumulator for *channel*, creating it if needed.

        *channel* must already have been added with addChannel(); may be called from createChannels().
        """
        chan = self.st.absChanName(channel)
        acc = self._accumulators.get(chan)
        if acc is None:
            info = self.st.channelInfo.get(chan)
            if info is None or 'task' not in info:
                raise ValueError(f"Channel {channel} has not been added to this DAQ task")
            acc = DaqChannelAccumulator(chan, info['task'][1], self.cmd, logger=self.dev.logger)
            if self._clocksConfigured:
                self._prepareAccumulator(acc)
            self._accumulators[chan] = acc
        return acc

    def addChunkListener(self, fn):
        """Call fn() on the DAQ reader thread after each chunk, once every accumulator has been updated.

        A listener that raises is logged and not called again this run.
        """
        self._chunkListeners = self._chunkListeners + (fn,)

    def settleSpecs(self):
        """Return {'': SettleSpec} if partial results were requested but cannot run, else {}."""
        return dict(self._settleSpecs)

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
        return self.channelAccumulator(channel).finalize(res)

    def devName(self):
        return self.dev.name()
