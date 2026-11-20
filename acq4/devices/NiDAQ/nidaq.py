import math

import numpy

import acq4.util.Mutex as Mutex
from acq4.devices.Device import Device, DeviceTask
from acq4.devices.NiDAQ.accumulator import DaqChannelAccumulator, checkCommand
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
    def meanResample(data, ds, binary=False):
        """Resample data by taking mean of ds samples at a time"""
        newLen = int(data.shape[0] / ds) * ds
        data = data[:newLen]
        data.shape = (int(data.shape[0] / ds), ds)
        if binary:
            return data.mean(axis=1).round().astype(numpy.byte)
        else:
            return data.mean(axis=1)


class Task(DeviceTask):
    def __init__(self, dev, cmd, parentTask):
        checkCommand(cmd)
        DeviceTask.__init__(self, dev, cmd, parentTask)
        self.cmd = cmd

        ## Create supertask from nidaq driver
        self.st = self.dev.n.createSuperTask()

        self._accumulators = {}  # absolute channel name -> DaqChannelAccumulator
        self._chunkListeners = ()  # replaced, never mutated: read on the reader thread
        self._disabledAccumulators = set()  # channel names, this run
        self._reportedFailures = set()  # channel names in _disabledAccumulators reported by getData(), this run
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
        self._reportedFailures = set()
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
        """Return {'data': ndarray, 'info': {'rate': ..., 'numPts': ..., ...}} for *channel*.

        Completes the channel's accumulator: values it already settled are returned unchanged. If its
        partial results failed during the run, info gets 'partialsFailed': True and the parent task's
        partialResultErrors a message.
        """
        res = self.st.getResult(channel)
        acc = self.channelAccumulator(channel)
        res = acc.finalize(res)
        if acc.channel in self._disabledAccumulators:
            res['info']['partialsFailed'] = True
            if acc.channel not in self._reportedFailures:
                self._reportedFailures.add(acc.channel)
                self.parentTask().partialResultErrors.append(
                    f"Partial results for DAQ channel {acc.channel} failed during the run; "
                    "its final values were completed from the raw buffer"
                )
        return res

    def devName(self):
        return self.dev.name()
