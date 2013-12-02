__author__ = 'pbmanis'

def protocolInfo(fh):
    print fh
    reps = fh.info()[('protocol', 'repetitions')]
    print 'reps: ', reps
    pulseDurIndex = fh.info()[('LED-Blue', 'Command.PulseTrain_length')]
    fn = fh.shortName()
    pulseDur = fh.parent().info()['sequenceParams'][('LED-Blue','Command.PulseTrain_length')][pulseDurIndex]
    pulseTrainInfo = fh.parent().info()['devices']['LED-Blue']['channels']['Command']['waveGeneratorWidget']['stimuli']['PulseTrain']
    startTime = pulseTrainInfo['start']['value']
    ipi = pulseTrainInfo['interpulse_length']['value']
    print 'file: ', fn,
    print 'startTime: ', startTime, 'ipi: ', ipi, 'pulseDuration: ', pulseDur
    return fn, startTime, ipi, pulseDur


