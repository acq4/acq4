import sys
import win32com.client
import pywintypes
import numpy as np
import subprocess as sp

"""
Thanks to: Jason Yamada-Hanff  https://github.com/yamad/igor-mode

Main documentation:  Igor Pro Folder\Miscellaneous\Windows Automation\Automation Server.ihf


* Use fprintf to return data:
   igor('fprintf 0, "%d", 1+3')

* Access waves:
   df = i.app.DataFolder("root:MIES:ITCDevices:ITC1600:Device0")
   wave = df.Wave('OscilloscopeData')

   # get data type and array shape
   typ, rows, cols, layers, chunks = wave.GetDimensions()
   dtype = dtypes[typ]
   shape = [rows, cols, layers, chunks]
   ndim = shape.index(0)
   shape = shape[:ndim]

   # get [(slope, intercept), ...] scale factors for each axis
   scaling = [wave.GetScaling(ax) for ax in range(len(shape))]

   np.array(wave.GetNumericWaveData(typ))

* Access global variables:
   df = i.app.DataFolder("root")
   var = df.Variable("myvar")
   var.GetNumericValue()
   var.GetStringValue()
"""

dtypes = { 
    0x02: 'float32',
    0x04: 'float64',
    0x08: 'byte',
    0x10: 'short',
    0x20: 'long',
    0x48: 'ubyte',
    0x50: 'ushort',
    0x60: 'ulong',
    0x01: 'complex',
    0x00: 'str',
}


class IgorBridge(object):
    def __init__(self):
        self.app = None

    def tryReconnect(func):
        def _tryReconnect(self, *args, **kwds):
            if self.app is None:
                self.connect()
            try:
                return func(self, *args, **kwds)
            except pywintypes.com_error as exc:
                if exc.args[0] == -2147023174:
                    # server unavailable; try reconnecting
                    self.connect()
                    return func(self, *args, **kwds)
                else:
                    raise
        return _tryReconnect

    @staticmethod
    def igorProcessExists():
        """Return True if an Igor process is currently running.
        """
        return 'Igor.exe' in sp.check_output(['wmic', 'process', 'get', 'description,executablepath'])        

    def connect(self):
        self.app = None
        # Need to check for running process to avoid starting a new one.
        if self.igorProcessExists():
            self.app = win32com.client.gencache.EnsureDispatch("IgorPro.Application")
        else:
            raise Exception("No Igor process found.")

    @tryReconnect
    def __call__(self, cmd):
        err, errmsg, hist, res = self.app.Execute2(1, 0, cmd, 0, "", "", "")
        if err != 0:
            raise RuntimeError("Igor call returned error code %d: %s" % (err, errmsg))
        return res

    @tryReconnect
    def getWave(self, folder, waveName):
        df = self.app.DataFolder(folder)
        wave = df.Wave(waveName)

        # get data type and array shape
        typ, rows, cols, layers, chunks = wave.GetDimensions()
        dtype = dtypes[typ]
        shape = [rows, cols, layers, chunks]
        ndim = shape.index(0)
        shape = shape[:ndim]

        # get [(slope, intercept), ...] scale factors for each axis
        # could use this to return a metaarray..
        scaling = [wave.GetScaling(ax) for ax in range(len(shape))]

        data = np.array(wave.GetNumericWaveData(typ))

        return data, scaling

    @tryReconnect
    def getVariable(self, folder, varName):
        df = self.app.DataFolder(folder)
        var = df.Variable(varName)
        typ = var.get_DataType()
        if dtypes[typ] == 'str':
            return var.GetStringValue()
        else:
            r,i = var.getNumericValue()
            if dtypes[typ] == 'complex':
                return complex(r, i)
            else:
                return r


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        path = 'root:MIES:ITCDevices:ITC1600:Device0'
        file = 'OscilloscopeData'
    else:
        path, file = sys.argv[1:3]

    import pyqtgraph as pg
    app = pg.mkQApp()
    plt = pg.plot(labels={'bottom': ('Time', 's')})
    igor = IgorBridge()

    def update():
        global data, scaling
        if not plt.isVisible():
            timer.stop()
            return
        data, scaling = igor.getWave(path, file)
        #data, scaling = igor.getWave('root:MIES:ITCDevices:ITC1600:Device0:TestPulse', 'TestPulseITC')
        print(data.shape)
        x = np.arange(data.shape[0]) * (scaling[0][0] * 1e-3)
        plt.clear()
        if data.ndim == 2:
            plt.plot(x, data[:,-1])
        else:
            plt.plot(x, data)


    timer = pg.QtCore.QTimer()
    timer.timeout.connect(update)
    timer.start(1000)

    app.exec_()