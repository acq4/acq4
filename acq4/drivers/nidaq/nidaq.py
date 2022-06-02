# -*- coding: utf-8 -*-
from __future__ import print_function, division

import ctypes
from inspect import signature

import PyDAQmx
import numpy as np
import six

dataTypeConversions = {
    '<f8': 'F64',
    '<i2': 'I16',
    '<i4': 'I32',
    '<u2': 'U16',
    '<u4': 'U32',
    '|u1': 'U8',
}


def init():
    global NIDAQ
    NIDAQ = _NIDAQ()


class _NIDAQ:
    NIDAQ_CREATED = False

    def __init__(self):
        if _NIDAQ.NIDAQ_CREATED:
            raise Exception("Will not create another nidaq instance--use the pre-existing NIDAQ object.")
        self.devices = {}

        # cached tasks used for scalar AO/AI operations
        # (this shaves a few ms from the cost of reading/writing scalars)
        self._scalarTasks = {}

        # :TODO: initialize the driver
        _NIDAQ.NIDAQ_CREATED = True

    def __repr__(self):
        return "<niDAQmx driver wrapper>"

    def listDevices(self):
        return self.GetSysDevNames().split(", ")

    def __getattr__(self, attr):
        if hasattr(PyDAQmx, attr):
            if callable(getattr(PyDAQmx, attr)):
                return lambda *args: self.call(attr, *args)
            else:
                return getattr(PyDAQmx, attr)
        else:
            raise NameError("{} not found among DAQmx constants or functions".format(attr))

    def call(self, func, *args):
        fn = getattr(PyDAQmx, func)

        sig = signature(fn)

        if "bufferSize" in sig.parameters:
            buffSize = fn(data=None, bufferSize=0, *args)
            ret = ctypes.create_string_buffer(b"\0" * buffSize)
            if "reserved" in sig.parameters and len(args) < len(sig.parameters):
                args += (None,)
            fn(*args, data=ret, bufferSize=buffSize)
            return ret.value.decode("utf-8")
        elif len(args) < len(sig.parameters):
            # Assume 1 missing arg, which is the pointer to the useful return value
            # Assumptions are generally bad things...
            cfuncInfo = PyDAQmx.function_dict["DAQmx" + func]
            dataType = cfuncInfo["arg_type"][-1]
            ret = dataType._type_()
            if "data" in sig.parameters or "isTaskDone" in sig.parameters:
                args += (dataType(ret),)
            if "value" in sig.parameters and not func.startswith("Write"):
                args += (dataType(ret),)
            if "reserved" in sig.parameters and len(args) < len(sig.parameters):
                args += (None,)
            fn(*args)
            return ret.value
        else:
            return fn(*args)


        # if func[:3] == "Get":  # byref arguments will be handled automatically.
        #     # functions that return char* can be called with a null pointer to get the size of the buffer needed.
        #     if (argSig[-2][1] == ["char", "*"] or argSig[-2][1] == ["char", [-1]]) and argSig[-1][0] == "bufferSize":
        #         returnValue = argSig[-2][0]
        #         extra = {returnValue: None, "bufferSize": 0}
        #         buffSize = fn(*args, **extra)()
        #         ret = ctypes.create_string_buffer(b"\0" * buffSize)
        #         args += (ret, buffSize)
        #
        # # Python 3 requires bytes instead of str arguments here
        # args = list(args)
        # for i, arg in enumerate(args):
        #     if isinstance(arg, str):
        #         args[i] = arg.encode()
        #
        # # if there is a 'reserved' argument, it MUST be 0 (don't let clibrary try to fill it for us)
        # if argSig[-1][0] == "reserved":
        #     ret = fn(*args, reserved=None)
        # else:
        #     ret = fn(*args)
        #
        # errCode = ret()
        #
        # if errCode < 0:
        #     msg = "NiDAQ Error while running function '%s%s':\n%s" % (func, str(args), self.error())
        #     raise NIDAQError(errCode, msg)
        # elif errCode > 0:
        #     print("NiDAQ Warning while running function '%s%s'" % (func, str(args)))
        #     print(self.error(errCode))
        #
        # if returnValue is not None:  # If a specific return value was indicated, return it now
        #     return ret[returnValue]
        #
        # # otherwise, try to guess which values should be returned
        # vals = ret.auto()
        # if len(vals) == 1:
        #     return vals[0]
        # elif len(vals) > 1:
        #     return vals

    def _call(self, func, *args, **kargs):
        try:
            return getattr(self.nidaq, func)(*args, **kargs)
        except:
            print(func, args)
            raise

    def CreateTask(self, taskName):
        taskPtr = PyDAQmx.TaskHandle()
        self.call("CreateTask", taskName, taskPtr)
        return taskPtr.value

    def error(self, errCode=None):
        """Return a string with error information. If errCode is None, then the currently 'active' error will be used."""
        if errCode is None:
            err = self.GetExtendedErrorInfo().decode("ascii")
        else:
            err = self.GetErrorString(errCode).decode("ascii")
        err.replace("\\n", "\n")
        return err

    def __del__(self):
        self.__class__.NIDAQ_CREATED = False

    def createTask(self, name=""):
        return Task(self, name)

    def createSuperTask(self):
        from . import SuperTask

        return SuperTask.SuperTask(self)

    def interpretMode(self, mode):
        modes = {
            "rse": PyDAQmx.Val_RSE,
            "nrse": PyDAQmx.Val_NRSE,
            "diff": PyDAQmx.Val_Diff,
            "chanperline": PyDAQmx.Val_ChanPerLine,
            "chanforalllines": PyDAQmx.Val_ChanForAllLines,
        }
        if isinstance(mode, six.string_types):
            mode = mode.lower()
            mode = modes.get(mode, None)
        return mode

    def writeAnalogSample(self, chan, value, vRange=(-10.0, 10.0), timeout=10.0):
        """Set the value of an AO port"""
        key = ("ao", chan)
        t = self._scalarTasks.get(key, None)
        if t is None:
            t = self.createTask()
            t.CreateAOVoltageChan(chan, "", vRange[0], vRange[1], PyDAQmx.Val_Volts, None)
            self._scalarTasks[key] = t
        t.WriteAnalogScalarF64(True, timeout, value)

    def readAnalogSample(self, chan, mode=None, vRange=(-10.0, 10.0), timeout=10.0):
        """Get the value of an AI port"""
        if mode is None:
            mode = PyDAQmx.Val_Cfg_Default
        else:
            mode = self.interpretMode(mode)

        key = ("ai", mode, chan)
        t = self._scalarTasks.get(key, None)
        if t is None:
            t = self.createTask()
            t.CreateAIVoltageChan(chan, "", mode, vRange[0], vRange[1], PyDAQmx.Val_Volts, None)
            self._scalarTasks[key] = t
        return t.ReadAnalogScalarF64(timeout)

    def writeDigitalSample(self, chan, value, timeout=10.0):
        """Set the value of an AO or DO port"""
        key = ("do", chan)
        t = self._scalarTasks.get(key, None)
        if t is None:
            t = self.createTask()
            t.CreateDOChan(chan, "", PyDAQmx.Val_ChanForAllLines)
            self._scalarTasks[key] = t
        t.WriteDigitalScalarU32(True, timeout, value)

    def readDigitalSample(self, chan, timeout=10.0):
        """Get the value of a DI port"""
        key = ("di", chan)
        t = self._scalarTasks.get(key, None)
        if t is None:
            t = self.createTask()
            t.CreateDIChan(chan, "", PyDAQmx.Val_ChanForAllLines)
            self._scalarTasks[key] = t
        return t.ReadDigitalScalarU32(timeout)

    def listAIChannels(self, dev=None):
        return self.GetDevAIPhysicalChans(dev).split(", ")

    def listAOChannels(self, dev):
        return self.GetDevAOPhysicalChans(dev).split(", ")

    def listDILines(self, dev):
        return self.GetDevDILines(dev).split(", ")

    def listDIPorts(self, dev):
        return self.GetDevDIPorts(dev).split(", ")

    def listDOLines(self, dev):
        return self.GetDevDOLines(dev).split(", ")

    def listDOPorts(self, dev):
        return self.GetDevDOPorts(dev).split(", ")


init()

chTypes = {
    PyDAQmx.Val_AI: "AI",
    PyDAQmx.Val_AO: "AO",
    PyDAQmx.Val_DI: "DI",
    PyDAQmx.Val_DO: "DO",
    PyDAQmx.Val_CI: "CI",
    PyDAQmx.Val_CO: "CO",
}


class Task:
    # TaskHandle = None

    def __init__(self, nidaq, taskName=""):
        self.nidaq = nidaq
        self.handle = self.nidaq.CreateTask(taskName)

    def __del__(self):
        self.nidaq.ClearTask(self.handle)

    def __getattr__(self, attr):
        func = getattr(self.nidaq, attr)
        return lambda *args: func(self.handle, *args)

    def __repr__(self):
        return "<Task: %s>" % str(self.GetTaskChannels())

    def start(self):
        self.StartTask()

    def stop(self):
        self.StopTask()

    def isDone(self):
        return self.IsTaskDone()

    def read(self, samples=None, timeout=10.0, dtype=None):
        # reqSamps = samples
        # if samples is None:
        #    samples = self.GetSampQuantSampPerChan()
        #    reqSamps = -1
        if samples is None:
            samples = self.GetSampQuantSampPerChan()
        reqSamps = samples

        numChans = self.GetTaskNumChans()

        shape = (numChans, samples)
        # print "Shape: ", shape

        # Determine the default dtype based on the task type
        tt = self.taskType()
        if dtype is None:
            if tt in [PyDAQmx.Val_AI, PyDAQmx.Val_AO]:
                dtype = np.float64
            elif tt in [PyDAQmx.Val_DI, PyDAQmx.Val_DO]:
                dtype = np.uint32  # uint8 / 16 might be sufficient, but don't seem to work anyway.
            else:
                raise Exception("No default dtype for %s tasks." % chTypes[tt])

        buf = np.empty(shape, dtype=dtype)
        # samplesRead = ctypes.c_long()

        # Determine the correct function name to call based on the dtype requested
        fName = "Read"
        if tt == PyDAQmx.Val_AI:
            if dtype == np.float64:
                fName += "Analog"
            elif dtype in [np.int16, np.uint16, np.int32, np.uint32]:
                fName += "Binary"
            else:
                raise Exception(
                    "dtype %s not allowed for AI channels (must be float64, int16, uint16, int32, or uint32)"
                    % str(dtype)
                )
        elif tt == PyDAQmx.Val_DI:
            if dtype in [np.uint8, np.uint16, np.uint32]:
                fName += "Digital"
            else:
                raise Exception("dtype %s not allowed for DI channels (must be uint8, uint16, or uint32)" % str(dtype))
        elif tt == PyDAQmx.Val_CI:
            fName += "Counter"
        else:
            raise Exception("read() not allowed for this task type (%s)" % chTypes[tt])

        fName += dataTypeConversions[np.dtype(dtype).descr[0][1]]

        self.SetReadRelativeTo(PyDAQmx.Val_FirstSample)
        self.SetReadOffset(0)

        nPts = getattr(self, fName)(reqSamps, timeout, PyDAQmx.Val_GroupByChannel, buf, buf.size, None)
        return buf, nPts

    def write(self, data, timeout=10.0):
        numChans = self.GetTaskNumChans()
        # samplesWritten = c_long()

        # Determine the correct write function to call based on dtype and task type
        fName = "Write"
        tt = self.taskType()
        if tt == PyDAQmx.Val_AO:
            if data.dtype == np.float64:
                fName += "Analog"
            elif data.dtype in [np.int16, np.uint16]:
                fName += "Binary"
            else:
                raise Exception(
                    "dtype %s not allowed for AO channels (must be float64, int16, or uint16)" % str(data.dtype)
                )
        elif tt == PyDAQmx.Val_DO:
            if data.dtype in [np.uint8, np.uint16, np.uint32]:
                fName += "Digital"
            else:
                raise Exception(
                    "dtype %s not allowed for DO channels (must be uint8, uint16, or uint32)" % str(data.dtype)
                )
        else:
            raise Exception("write() not implemented for this task type (%s)" % chTypes[tt])

        fName += dataTypeConversions[data.dtype.descr[0][1]]

        nPts = getattr(self, fName)(data.size // numChans, False, timeout, PyDAQmx.Val_GroupByChannel, data, None)
        return nPts

    def absChannelName(self, n):
        parts = n.lstrip("/").split("/")
        devs = self.GetTaskDevices().split(", ")
        if parts[0] not in devs:
            if len(devs) != 1:
                raise Exception("Cannot determine device to prepend on channel '%s'" % n)
            parts = [devs[0]] + parts
        return "/" + "/".join(parts)

    def taskType(self):
        # print "taskType:"
        ch = self.GetTaskChannels().split(", ")
        # print ch
        ch = self.absChannelName(ch[0])
        # print "First task channel:", ch
        return self.GetChanType(ch)

    def isInputTask(self):
        return self.taskType() in [PyDAQmx.Val_AI, PyDAQmx.Val_DI]

    def isOutputTask(self):
        return self.taskType() in [PyDAQmx.Val_AO, PyDAQmx.Val_DO]
