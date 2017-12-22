from __future__ import print_function
__author__ = 'pbmanis'

from collections import OrderedDict
import re
import numpy as np
import scipy.stats

#initialized = False
#
#if not initialized:
#    global summary, initialized
#    summary=[]
#    initialized = True


class Params(object):
    """
    Class to make organized data a bit like a C struct.
    Instantiate by calling:
    p = Params(mode='tail', chfit=True, exp0fit=False, t0 = 3.59, wx={'one': 1, 'C': [1,2,3,4]) (etc)
    then p.mode returns 'tail', etc.
    p.list() provides a nice print out of the variable.
    """
    def __init__(self, **kwds):
        self.__dict__.update(kwds)

    def list(self):
        o = dir(object())
        for x in dir(self):
            if x in o:
                continue
            if x[0:2] == '__':
                continue
            if x == 'list':
                continue
            print('   ' + x + ' = ', end=" ")
            print(eval('self.' + x))

class ChR2():
    def __init__(self):
       # self.initialized = False # no data loaded
        self.summary = []
        self.stats = {}

    #def sliceInfo(self, fh):
    #    pass
    #
    #def cellInfo(self, fh):
    #    pass


    def protocolInfoLED(self, fh, inputs, derivative):
        """
        protocolInfoLED is called through "Process" for every directory (epoch run) stored below the protocol directory.
        The routine operates on data sets in which the LED has been used (specificially, LED-Blue), as in Xie and Manis,
        2014, Front. in Neural Circuits (VGAT-ChR2 mouse).
        fh is the file handle for the current file we are processing
        inputs is the result of the analysis, which is the result of the threshold detection of spikes
        inputs contains information about the spike latency, width, peak, etc.
        info is the
        The routine returns the "result", which is an ordered dictionary, for each call.
        However, it also updates the global list "summary", thus concatenating the results into a single
        array.
        """
        #global summary
        print('protocolInfoLED***\n')
        self.devicemode = 'LED'
        nspikes = len(inputs)
        reps = fh.parent().info()['protocol']['conf']['repetitions'] # fh.info()[('protocol', 'repetitions')]
        pulseDurIndex = fh.info()[('LED-Blue', 'Command.PulseTrain_length')]

        fn = fh.shortName()
        # find date string in the path, and return path to current data set
        # allows us to identify the data set by date, slice, cell, protocol, etc.
        dm = re.compile(r'(\d{4,4})\.(\d{2,2})\.(\d{2,2})*')
        dsearch = dm.search(fh.name())
        expname = fh.name()[dsearch.start():] # pull full path for experiment here, but leave out everything above the date
        pulseDur = fh.parent().info()['sequenceParams'][('LED-Blue','Command.PulseTrain_length')][pulseDurIndex]
        pulseTrainCommand = fh.parent().info()['devices']['LED-Blue']['channels']['Command']
        pulseTrainInfo = pulseTrainCommand['waveGeneratorWidget']['stimuli']['PulseTrain']
        startTime = pulseTrainInfo['start']['value'] # retrieve start time
        rep = fh.info()[('protocol', 'repetitions')]
        ipi = pulseTrainInfo['interpulse_length']['value'] # retrieve interpulse interval
        npulses = pulseTrainInfo['pulse_number']['value'] # retrieve number of pulses in train
        spikeTimes = [t['time'] for t in inputs]
        # figure max of derivative of the data after each stimulus pulse. 5 msec window.
        t=derivative.xvals("Time")
        slopes = np.zeros(npulses)
        for n in range(npulses):
            t0 = startTime + n * ipi
            t1 = t0 + 3e-3
            x = np.where((t > t0) & (t <= t1))
            slopes[n] = np.max(derivative[x])

        res = OrderedDict([('Experiment: ', expname), ('File: ', fn), ('startTime', startTime),
                           ('NPulses', npulses), ('IPI', ipi), ('PulseDur', pulseDur), ('Reps', reps), ('thisRep', rep),
                           ('NSpikes', nspikes), ('SpikeTimes', spikeTimes), ('Slopes', slopes)])
        self.summary.append(res)
        return res

    def protocolInfoLaser(self, fh, inputs, derivative):
        """
        protocolInfoLaser is called through "flowchart.process" for every directory (epoch run) stored below the protocol directory.
        The routine operates on data sets in which the blue laser has been used (specificially, 473nm), to look
        at pulse duration and OD filter settings.
        fh is the file handle for the current file we are processing
        inputs is the result of the analysis, which is the result of the threshold detection of spikes
        inputs contains information about the spike latency, width, peak, etc.
        info is the
        The routine returns the "result", which is an ordered dictionary, for each call.
        However, it also updates the global list "summary", thus concatenating the results into a single
        array.
        """
        #global summary
        try:
            nspikes = len(inputs)
            self.devicemode = 'Laser'
            #print inputs
    #        print 'FH parent info: ', fh.parent().info()
            print('1')
            reps = fh.parent().info()['protocol']['conf']['repetitions'] # fh.info()[('protocol', 'repetitions')]
            print('2')
            print(list(fh.info().keys()))
            print(fh.info())
            try:
                pulseDurIndex = fh.info()['Laser-Blue', 'Shutter.duration']
            except:
                try:
                    pulseDurIndex = fh.info()['Laser-UV', 'Shutter.duration']
                except:
                    raise ValueError(" No key for Laser-Blue or Laser-UV in data set")
            # fh.info()[('Laser-Blue', 'Command.PulseTrain_length')]
    #        print 'pulsedurindex: ', pulseDurIndex
            fn = fh.shortName()
            # find date string in the path, and return path to current data set
            # allows us to identify the data set by date, slice, cell, protocol, etc.
            dm = re.compile(r'(\d{4,4})\.(\d{2,2})\.(\d{2,2})*')
            dsearch = dm.search(fh.name())
            expname = fh.name()[dsearch.start():] # pull full path for experiment here, but leave out everything above the date
            print('3')
            pulseDur = fh.parent().info()['sequenceParams'][('Laser-Blue','Shutter.duration')] # [pulseDurIndex]
            print('4')
            pulseDur = pulseDur[pulseDurIndex]
            print('5')
            pulseTrainCommandShutter = fh.parent().info()['devices']['Laser-Blue']['channels']['Shutter']
            print('6')
            pulseTrainFcn = pulseTrainCommandShutter['waveGeneratorWidget']['function']
            r = re.compile('(?P<type>pulse)\((?P<delay>\d+),\s(?P<param>\w+),\s(?P<value>\d+)\)')
            s = r.match(pulseTrainFcn)
            print('6.5')
            startTime = float(s.group('delay'))*1e-3   # pulseTrainFcn['start']['value'] # retrieve start time
            print('7')
            rep = 0  # fh.info()[('protocol', 'repetitions')]
            ipi = 1  # pulseTrainInfo['interpulse_length']['value'] # retrieve interpulse interval
            npulses = 1 # pulseTrainInfo['pulse_number']['value'] # retrieve number of pulses in train
            spikeTimes = [t['time'] for t in inputs]
            # figure max of derivative of the data after each stimulus pulse. 5 msec window.
            t = derivative.xvals("Time")
            slopes = np.zeros(npulses)
            print('8')
            for n in range(npulses):
                t0 = startTime + n * ipi
                t1 = t0 + 3e-3
                x = np.where((t > t0) & (t <= t1))
                print('n, x: ', n, x)
                slopes[n] = np.max(derivative[x])

            res = OrderedDict([('Experiment: ', expname), ('File: ', fn), ('startTime', startTime),
                               ('NPulses', npulses), ('IPI', ipi), ('PulseDur', pulseDur), ('Reps', reps),
                               ('thisRep', rep),
                               ('NSpikes', nspikes), ('SpikeTimes', spikeTimes), ('Slopes', slopes)])
            self.summary.append(res)
        except:
            raise Exception('Laser stuff failed')
        return res


    def getSummary(self):
        #global summary
        return self.summary


    def getStats(self):
        return self.getStats()


    def clearSummary(self):
        #global summary
        self.summary = []
        self.tats = {}


    def printSummary(self, printDetails=False):
        #global summary
        if len(self.summary) == 0:
            return
        title = ''
        kl = []
        excludeKeys = ['Experiment: ', 'SpikeTimes', 'Reps']
        if printDetails:
            print('----------------------------------')
            if excludeKeys[0] in self.summary[0].keys():
                print('Experiment: %s  reps: %d' % (self.summary[0][excludeKeys[0]], self.summary[0]['Reps']))
            for s in self.summary[0].keys():
                if s in excludeKeys:
                    continue
                title = title + s + '\t'
                kl.append(s)
            print(title)
            for i in range(len(self.summary)):
                for k in kl: # keeps order
                    if k in excludeKeys:
                        continue
                    print(self.summary[i][k], '\t', end=" ")
                print('')
            print('----------------------------------')
            print('\n')
        # generate a summary that ranks data by pulse duration
        # analysis:
        # mean # spikes per stimulus (count spikes from stimulus onset to the ipi following
        # mean latency of spikes vs stimulus number
        # mean std of spikes vs stimulus number
        # assumption: what varies is the pulse Duration, so we create a dictionary to organize the values
        # and sequence over that.
        pdurs = [x['PulseDur'] for x in self.summary]
        npulses = [x['NPulses'] for x in self.summary]
        reps = self.summary[0]['Reps']  # wont change in protocol
        if reps == 0:
            reps = 1
        uniqDurs, uniqDursIndx = np.unique(pdurs, return_inverse=True)
        ndur = len(uniqDurs)
        npul = npulses[0]  # assumption - the same number of pulses in each run
        nspk = np.zeros((ndur, npul, reps))
        lat = np.zeros((ndur, npul, reps))
        durs = np.zeros((ndur, npul, reps))
        slopes = np.zeros((ndur, npul, reps))
        rep = [[0]*npul] * ndur
        ipi = self.summary[0]['IPI']
        for du in range(len(self.summary)):
            s = self.summary[du]  # get summary for this duration
            duration = s['PulseDur']
            st = np.array(s['SpikeTimes'])
            # now loop through and fill the arrays to make calculations
            repc = s['thisRep']
            for n in range(s['NPulses']):
                t0 = s['startTime'] + n * s['IPI'] # start time for this pulse window
                t1 = t0 + s['IPI']  # end time for this pulse window
                x = np.intersect1d(np.where(st > t0)[0].tolist(), np.where(st <= t1)[0].tolist())
                if len(x) > 0:
                    lat[uniqDursIndx[du], n, repc] = st[x[0]]-t0
                else:
                    lat[uniqDursIndx[du], n, repc] = np.nan
                durs[uniqDursIndx[du], n, repc] = duration  # save the associated pulse duration
                nspk[uniqDursIndx[du], n, repc] = len(x)
                rep[uniqDursIndx[du]][n] = repc
                slopes[uniqDursIndx[du], n, repc] = s['Slopes'][n]

        meanlat = scipy.stats.nanmean(lat, axis=2)
        meannspk = scipy.stats.nanmean(nspk, axis=2)
        stdlat = scipy.stats.nanstd(lat, axis = 2)
        meanslope = scipy.stats.nanmean(slopes, axis=2)
        self.stats = {'npul': npul, 'uniqDurs': uniqDurs, 'meanlat': meanlat,
                      'meannspk': meannspk, 'stdlat': stdlat, 'meanslope': meanslope}
        #
        # print out a summary to copy into another program for plotting, etc.
        # data are put into comma separated columns, with some additional info to identify the
        # data set source.
        print("\n--------------------------\n")
        textbuf = []  # accumulate into the text buffer so we can copy to clipboard...
        textbuf.append("Summary for Experiment: %s Reps = %d" % (self.summary[0][excludeKeys[0]], self.summary[0]['Reps']))
        if npul > 2:  # summary is across pulses. Should only be one duration...
            textbuf.append(' IPI = %f  Duration = %f\n' % (ipi, duration))
            textbuf.append( "Pulse\tDur\tslope\tspikes\tlatency\tstdlatency\n")
            print(uniqDurs)
            for j, d in enumerate(uniqDurs):
                textbuf.append( "Pulse\tDur\tslope\tspikes\tlatency\tstdlatency\n")
                for i in range(npul):
                #print meanslope.shape
                #print meanslope
                    textbuf.append('%3d\t%6.1f\t%6.1f\t%6.2f\t%7.2f\t%7.2f\n' % (i, d*1e3, meanslope[j,i]*1e6,
                                                                              meannspk[j,i], meanlat[j,i]*1000.,
                                                                              stdlat[j,i]*1000.))
                textbuf.append('\n')

        else: # summary is for varying the duration. Just report the first pulse ([0])
            textbuf.append( ' npul = %d IPI = %f\n' % (npul, ipi))
            textbuf .append( "Dur\tslope\tspikes\tlatency\tstdlatency\n")
            for i, d in enumerate(uniqDurs):
               # print i, len(meanslope[0])
                textbuf.append( "%f\t%f\t%f\t%f\t%f\n" % (d, meanslope[i][0], meannspk[i][0], meanlat[i][0], stdlat[i][0]))
        for t in textbuf: # print the contents of the text buffer (which is a list... )
            print(t, end=" ")
        print("\n--------------------------\n")
        #print meanlat[0]
        #print stdlat[0]
        #print meannspk[0]
        #print meanslope[0]
        #print durs[:,:,0]


    def plotSummary(self, plotWidget = None):
        xmax = 0.

        if len(self.stats) == 0:
            return
        symlist = ['o', 'x', 's', 't', 'd', '+', 'o', 'x', 's', 't', 'd', '+']
        symcols = ['blue', 'red']
        for i, plw in enumerate(plotWidget):
            plw.plotItem.clear()
    #        plotWidget.plotItem.scatterPlot().clear()
            if i == 0:
                if self.stats['npul'] > 2:
                    for j, d in enumerate(self.stats['uniqDurs']):
                        plw.plotItem.scatterPlot().setData(x=np.arange(self.stats['npul']),
                                                       y=self.stats['meanslope'][j], symbol=symlist[j])
                    plw.plotItem.setLabel('left', 'Slope (V/s)')
                    plw.plotItem.setLabel('bottom', 'Pulse #')
                else:
                    plw.plotItem.scatterPlot().setData(x =self.stats['uniqDurs'],
                                                       y=[x[0] for x in self.stats['meanslope']], symbol='s')
                    plw.plotItem.setLabel('left', 'Slope (V/s)')
                    plw.plotItem.setLabel('bottom', 'Pulse Dur', 's')
            elif i == 1:
                if self.stats['npul'] > 2:
                    for j, d in enumerate(self.stats['uniqDurs']):
                        plw.plotItem.scatterPlot().setData(x=np.arange(self.stats['npul']),
                                                       y=self.stats['meannspk'][j], symbol=symlist[j])
                    plw.plotItem.setLabel('left', 'Spike Count')
                    plw.plotItem.setLabel('bottom', 'Pulse #')
                else:
                    plw.plotItem.scatterPlot().setData(x = self.stats['uniqDurs'],
                                                       y=[x[0] for x in self.stats['meannspk']], symbol='s')
                    plw.plotItem.setLabel('left', 'Spike Count')
                    plw.plotItem.setLabel('bottom', 'Pulse Dur', 's')
            elif i == 2:
                if self.stats['npul'] > 2:
                    for j, d in enumerate(self.stats['uniqDurs']):
                        plw.plotItem.scatterPlot().setData(x=np.arange(self.stats['npul']),
                                                       y=self.stats['meanlat'][j], symbol=symlist[j])
                    plw.plotItem.setLabel('left', 'Latency', 's')
                    plw.plotItem.setLabel('bottom', 'Pulse #')
                else:
                    plw.plotItem.scatterPlot().setData(x = self.stats['uniqDurs'],
                                                       y=[x[0] for x in self.stats['meanlat']], symbol='s')
                    plw.plotItem.setLabel('left', 'Latency', 's')
                    plw.plotItem.setLabel('bottom', 'Pulse Dur', 's')
            plw.plotItem.autoRange()
            view = plw.plotItem.viewRange()
            if view[0][1] > xmax:
                xmax = view[0][1]
            plw.plotItem.setYRange(0., view[1][1])

        for plw in plotWidget:
            plw.plotItem.setXRange(0., xmax)

