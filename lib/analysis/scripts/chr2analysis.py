__author__ = 'pbmanis'

from collections import OrderedDict

initialized = False

if not initialized:
    global summary, initialized
    summary=[]
    initialized = True


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
            print '   ' + x + ' = ',
            print eval('self.' + x)

def protocolInfo(fh, inputs):
    global summary
    nspikes = len(inputs)
    reps = fh.info()[('protocol', 'repetitions')]
    pulseDurIndex = fh.info()[('LED-Blue', 'Command.PulseTrain_length')]
    #if reps == 0 and pulseDurIndex == 0:
    #    print 'File\tRep\tPulseDur\tStartTime\tIPI\tNspikes\tEPSPSlopes'
    fn = fh.shortName()
    pulseDur = fh.parent().info()['sequenceParams'][('LED-Blue','Command.PulseTrain_length')][pulseDurIndex]
    pulseTrainInfo = fh.parent().info()['devices']['LED-Blue']['channels']['Command']['waveGeneratorWidget']['stimuli']['PulseTrain']
    startTime = pulseTrainInfo['start']['value']
    ipi = pulseTrainInfo['interpulse_length']['value']
#    print '%12s\t%d\t%8.3f\t%8.3f\t%8.3f\t%d\t' % (fn, reps, pulseDur*1000., startTime*1000., ipi*1000., nspikes)
    res = OrderedDict([('File: ', fn), ('startTime', startTime*1000), ('IPI', ipi*1000),
                       ('PulseDur', pulseDur*1000), ('NSpikes', nspikes)])
    summary.append(res)
    return res

def getSummary():
    global summary
    return summary

def clearSummary():
    global summary
    summary = []

def printSummary():
    global summary
    if len(summary) == 0:
        return
    title = ''
    kl = []
    for s in summary[0].keys():
        title = title + s + '\t'
        kl.append(s)
    print title
    for i in range(len(summary)):
        for k in kl: # keeps order
            print summary[i][k], '\t',
        print ''
    print '\n'
#    print '%12s\t%d\t%8.3f\t%8.3f\t%8.3f\t%d\t' % (fn, reps, pulseDur*1000., startTime*1000., ipi*1000., nspikes)


