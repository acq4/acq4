# -*- coding: utf-8 -*-
from __future__ import print_function
import six
import time
from numpy import *
import acq4.util.ptime as ptime  ## platform-independent precision timing
from collections import OrderedDict
from .base import NIDAQError


class SuperTask:
    """Class for creating and encapsulating multiple synchronous tasks. Holds and assembles arrays for writing to each task as well as per-channel meta data."""
    
    def __init__(self, daq):
        self.daq = daq
        self.tasks = {}
        self.taskInfo = {}
        self.channelInfo = {}
        self.dataWrtten = False
        self.devs = daq.listDevices()
        self.triggerChannel = None
        self.result = None
        
    def absChanName(self, chan):
        parts = chan.lstrip('/').split('/')
        if not parts[0] in self.devs:
            if len(self.devs) == 1:
                parts = self.devs + parts
            else:
                raise Exception("Can not determine device to use for channel %s" % chan)
        return '/' + '/'.join(parts)
        
    def getTaskKey(self, chan, typ=None):
        """Return the task that would be responsible for handling a particular channel"""
        chan = self.absChanName(chan)
        if chan in self.channelInfo and 'task' in self.channelInfo[chan]:
            return self.channelInfo[chan]['task']
        
        if typ is None and chan in self.channelInfo and 'type' in self.channelInfo[chan]:
            typ = self.channelInfo[chan]['type']

        if typ is None:
            raise Exception('Must specify type of task (ai, ao, di, do)')
        parts = chan.lstrip('/').split('/')
        devn = parts[0]
        return (devn, typ)
        
    def getTask(self, chan, typ=None):
        """Return the task which should be used for this channel and i/o type. Creates the task if needed."""
        key = self.getTaskKey(chan, typ)
        if key not in self.tasks:
            self.tasks[key] = self.daq.createTask()
            self.taskInfo[key] = {'cache': None, 'chans': [], 'dataWritten': False}
        return self.tasks[key]
        
    def addChannel(self, chan, typ, mode=None, vRange=[-10., 10.], **kargs):
        chan = self.absChanName(chan)
        (dev, typ) = self.getTaskKey(chan, typ)
        t = self.getTask(chan, typ)
        
        ## Determine mode to use for this channel
        if mode is None:
            if typ == 'ai':
                mode = self.daq.Val_RSE
            elif typ in ['di', 'do']:
                mode = self.daq.Val_ChanPerLine
        elif isinstance(mode, six.string_types):
            # decide which modes are allowed for this channel
            if typ == 'ai':
                allowed = ['RSE', 'NRSE', 'Diff', 'PseudoDiff']
            elif typ in ['di', 'do']:
                allowed = ['ChanPerLine', 'ChanForAllLines']
            else:
                raise TypeError("mode argument not accepted for channel type '%s'" % typ)

            # Is the requested mode in the allowed list?
            lower = list(map(str.lower, allowed))
            try:
                ind = lower.index(mode.lower())
            except ValueError:
                raise ValueError("Mode '%s' not allowed for channel type '%s'" % (mode, typ))

            # Does the driver support the requested mode?
            try:
                mode = getattr(self.daq, 'Val_' + allowed[ind])
            except AttributeError:
                raise ValueError("Mode '%s' not supported by the DAQmx driver" % mode)

        if typ == 'ai':
            #print 'CreateAIVoltageChan(%s, "", %s, vRange[0], vRange[1], Val_Volts, None)' % (chan, str(mode))
            t.CreateAIVoltageChan(chan, "", mode, vRange[0], vRange[1], self.daq.Val_Volts, None, **kargs)
        elif typ == 'ao':
            #print 'CreateAOVoltageChan(%s, "", vRange[0], vRange[1], Val_Volts, None)' % (chan)
            t.CreateAOVoltageChan(chan, "", vRange[0], vRange[1], self.daq.Val_Volts, None, **kargs)
        elif typ == 'di':
            #print 'CreateDIChan(%s, "", %s)' % (chan, str(mode))
            t.CreateDIChan(chan, "", mode, **kargs)
        elif typ == 'do':
            #print 'CreateDOChan(%s, "", %s)' % (chan, str(mode))
            t.CreateDOChan(chan, "", mode, **kargs)
        else:
            raise Exception("Don't know how to create channel type %s" % typ)
        self.taskInfo[(dev, typ)]['chans'].append(chan)
        self.channelInfo[chan] = {
            'task': (dev, typ),
            'index': t.GetTaskNumChans()-1,
        }

    # def setChannelInfo(self, chan, info):
        # chan = self.absChanName(chan)
        # self.channelInfo[chan] = info

    def setWaveform(self, chan, data):
        chan = self.absChanName(chan)
        if chan not in self.channelInfo:
            raise Exception('Must create channel (%s) before setting waveform.' % chan)
        ## For now, all ao waveforms must be between -10 and 10
        
        typ = self.channelInfo[chan]['task'][1]
        if typ in 'ao' and (any(data > 10.0) or any(data < -10.0)):
            self.channelInfo[chan]['data'] = clip(data, -10.0, 10.0)
            self.channelInfo[chan]['clipped'] = True
        else:
            self.channelInfo[chan]['data'] = data
            self.channelInfo[chan]['clipped'] = False
            
        key = self.getTaskKey(chan)
        self.taskInfo[key]['dataWritten'] = False

        # if info is not None:
            # self.channelInfo[chan]['info'] = info
        
    def getTaskData(self, key):
        #key = self.getTaskKey(key)
        if self.taskInfo[key]['cache'] is None:
            ## Assemble waveforms in correct order
            waves = []
            for c in self.taskInfo[key]['chans']:
                if 'data' not in self.channelInfo[c]:
                    raise Exception("No data specified for DAQ channel %s" % c)
                waves.append(atleast_2d(self.channelInfo[c]['data']))
            try:
                self.taskInfo[key]['cache'] = concatenate(waves)
            except:
                print("Input shapes for %s:" % ','.join(list(self.channelInfo.keys())))
                for w in waves:
                    print(w.shape)
                raise
        return self.taskInfo[key]['cache']
        
    def writeTaskData(self):
        for k in self.tasks:
            if self.tasks[k].isOutputTask() and not self.taskInfo[k]['dataWritten']:
                d = self.getTaskData(k)
                # print "  Writing %s %s to task %s" % (d.shape, d.dtype, str(k))
                try:
                    self.tasks[k].write(d)
                except:
                    print("Error while writing data to task '%s':" % str(k))
                    raise
                self.taskInfo[k]['dataWritten'] = True
        
    def hasTasks(self):
        return len(self.tasks) > 0
        
    def configureClocks(self, rate, nPts):
        """Configure sample clock and triggering for all tasks"""
        clkSource = None
        if len(self.tasks) == 0:
            raise Exception("No tasks to configure.")
        keys = list(self.tasks.keys())
        self.numPts = nPts
        self.rate = rate
        
        ## Make sure we're only using 1 DAQ device (not sure how to tie 2 together yet)
        ndevs = len(set([k[0] for k in keys]))
        #if ndevs > 1:
            #raise Exception("Multiple DAQ devices not yet supported.")
        dev = keys[0][0]
        
        if (dev, 'ao') in keys:  ## Try ao first since E-series devices don't seem to work the other way around..
            clkSource = 'ao' # '/Dev1/ao/SampleClock'
        elif (dev, 'ai') in keys:
            clkSource = 'ai'  # '/Dev1/ai/SampleClock'
        else:
            ## Only digital tasks, configure a fake AI task so we can use the ai sample clock.
            ## Even better: Configure a counter to make a clock..
            aich = '/%s/ai0' % dev
            self.addChannel(aich, 'ai')
            clkSource = 'ai'  # '/Dev1/ai/SampleClock'
        
        self.clockSource = (dev, clkSource)
        
        ## Configure sample clock, rate for all tasks
        clk = '/%s/%s/SampleClock' % (dev, clkSource)
        
        
        #keys = self.tasks.keys()
        #keys.remove(self.clockSource)
        #keys.insert(0, self.clockSource)
        #for k in keys:

        for k in self.tasks:
            ## TODO: this must be skipped for the task which uses clkSource by default.
            try:
                maxrate = self.tasks[k].GetSampClkMaxRate()
            except NIDAQError as exc:
                if exc.errCode == -200452:
                    # Task does not support GetSampClkMaxRate
                    pass
            else:
                if rate > maxrate:
                    raise ValueError("Requested sample rate %d exceeds maximum (%d) for this device." % (int(rate), int(maxrate)))

            if k[1] != clkSource:
                #print "%s CfgSampClkTiming(%s, %f, Val_Rising, Val_FiniteSamps, %d)" % (str(k), clk, rate, nPts)

                self.tasks[k].CfgSampClkTiming(clk, rate, self.daq.Val_Rising, self.daq.Val_FiniteSamps, nPts)
            else:
                #print "%s CfgSampClkTiming('', %f, Val_Rising, Val_FiniteSamps, %d)" % (str(k), rate, nPts)
                self.tasks[k].CfgSampClkTiming("", rate, self.daq.Val_Rising, self.daq.Val_FiniteSamps, nPts)

        
    def setTrigger(self, trig):
        #self.tasks[self.clockSource].CfgDigEdgeStartTrig(trig, Val_Rising)

        for t in self.tasks:
            if t[1] in ['di', 'do']:   ## M-series DAQ does not have trigger for digital acquisition
                #print "  skipping trigger for digital task"
                continue
            #print t
            if self.tasks[t].absChannelName(trig) == '/%s/%s/StartTrigger' % t:
                #print "  Skipping trigger set; already correct."
               continue
            #print "  trigger %s %s" % (str(t), trig)
            self.tasks[t].CfgDigEdgeStartTrig(trig, self.daq.Val_Rising)
        self.triggerChannel = trig

    def start(self):
        self.writeTaskData()  ## Only writes if needed.
        
        self.result = None
        ## TODO: Reserve all hardware needed before starting tasks
        
        keys = list(self.tasks.keys())
        ## move clock task key to the end
        if self.clockSource in keys:
            #print "  Starting %s last" % str(tt) 
            keys.remove(self.clockSource)
            keys.append(self.clockSource)
        for k in keys[:-1]:
            #print "starting task", k
            self.tasks[k].start()
        #self.startTime = time.clock()
        self.startTime = ptime.time()
        #print "start time:", self.startTime
        self.tasks[keys[-1]].start()
        #print "starting clock task:", keys[-1]
        
#        for k in keys:
#          if not self.tasks[k].isRunning():
#            print "Warning: task %s didn't start" % str(k)
        
        if self.triggerChannel is not None:
            ## Set up callback to record time when trigger starts
            pass
            
            
    def isDone(self):
        for t in self.tasks:
            if not self.tasks[t].isDone():
                #print "Task", t, "not done yet.."
                return False
        return True
        
    def read(self):
        data = {}
        for t in self.tasks:
            if self.tasks[t].isInputTask():
                #print "Reading from task", t
                data[t] = self.tasks[t].read()
        return data
        
    def stop(self, wait=False, abort=False):
        #print "ST stopping, wait=",wait, " abort:", abort
        ## need to be very careful about stopping and unreserving all hardware, even if there is a failure at some point.
        try:
            if wait:
                while not self.isDone():
                    #print "Sleeping..", time.time()
                    time.sleep(10e-6)
                    
            if not abort and self.isDone():
                # data must be read before stopping the task,
                # but should only be read if we know the task is complete.
                self.getResult()
            
        finally:
            for t in self.tasks:
                try:
                    #print "  ST Stopping task", t
                    self.tasks[t].stop()
                    #print "    ..done"
                finally:
                    # unreserve hardware
                    self.tasks[t].TaskControl(self.daq.Val_Task_Unreserve)
        #print "ST stop complete."

    def getResult(self, channel=None):
        #print "getresult"
        if self.result is None:
            self.result = {}
            readData = self.read()
            for k in self.tasks.keys():
                #print "  ", k
                if self.tasks[k].isOutputTask():
                    #print "    output task"
                    d = self.getTaskData(k)
                    # print "output data set to:"
                    # print d
                else:
                    d = readData[k][0]
                    #print "input data set to:", d
                    #print "    input task, read"
                    #print "    done"
                self.result[k] = {
                    'type': k[1],
                    'data': d,
                    'start': self.startTime,
                    'taskInfo': self.taskInfo[k],
                    'channelInfo': [self.channelInfo[ch] for ch in self.taskInfo[k]['chans']]
                }
        if channel is None:
            return self.result
        else:
            res = self.result[self.channelInfo[channel]['task']]
            ret = {
                'data': res['data'][self.channelInfo[channel]['index']],
                'info': OrderedDict([
                    ('startTime', res['start']), 
                    ('numPts', self.numPts), 
                    ('rate', self.rate), 
                    ('type', self.channelInfo[channel]['task'][1])
                    ])
            }
            if 'clipped' in res:
                ret['info']['clipped'] = res['clipped']

            # print "=== result for channel %s=====" % channel
            # print ret 
            return ret 
# 
    def run(self):
        #print "Start..", time.time()
        self.start()
        #print "wait/stop..", time.time()
        #self.stop(wait=True)
        while not self.isDone():
            time.sleep(10e-6)
        #print "get samples.."
        r = self.getResult()
        return r
