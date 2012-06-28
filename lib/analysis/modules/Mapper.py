"""
Description:
    
Input: event / site data previously analyzed by photostim
Output: 
    - per-event probability of being direct / evoked / spont
    - per-site probability of having evoked / direct input
    - per-cell measurements of direct and presynaptic area

Whereas photostim largely operates on a single stimulation (or a single stimulation site)
at a time, mapper operates on complete mapping datasets--multiple scans within a cell

Ideally, this module should replace the 'stats' and 'map' functionality in photostim
as well as integrate megan's map analysis, but I would really like it 
to be an independent module (and if it's not too difficult, it should _also_ be possible
to integrate it with photostim)


Features:

    - tracks spontaneous event rate over the timecourse of a cell as well as the prevalence
    of specific event features -- amplitude, shape, etc. This data is used to 
    determine:
        - For each event, the probability that it is evoked / spontaneous / direct
        - For each site, the probability that it contains evoked and/or direct events
    This should have no notion of 'episodes' -- events at the beginning of one trace
    may have been evoked by the previous stim.
    - can report total number of evoked presynaptic sites per atlas region, total area of direct activation
    
    - display colored maps in 3d atlas
    
    - event-explorer functionality:    (perhaps this should stay separate)
        - display scatter plots of events based on various filtering criteria
        - mark regions of events within scatter plot as being invalid
        - filter generator: filter down events one criteria at a time, use lines / rois to control limits
            eg: plot by amplitude, tau; select a population of events that are known to be too large / fast
                replot by relative error and length/tau ratio; select another subset
                once a group is selected / deselected, tag the set (new column in events table)
                


Changes to event detector:
    - Ability to manually adjust PSP fits, particularly for direct responses (this goes into event detector?)
    - Ability to decrease sensitivity after detecting a direct event
    - Move region selection out of event detector entirely; should be part of mapper
    (the mapper can add columns to the event table if we want..)
    

    
Notes on probability computation:

    We need to be able to detect several different situations:
    
    (1) Obvious, immediate rate change
    
    |___||____|_|_______|____|___|___|_|||||||_|_||__|_||___|____|__|_|___|____|___
                                      ^
    (2) Obvious, delayed rate change
    
    |___||____|_|_______|____|___|___|_|____|__|_|___|___|_||_|_||_|_|__|_|_||_____
                                      ^
    (3) Non-obvious rate change, but responses have good precision   
    
    |______|______|_________|_______|____|______|________|________|_________|______
    _____|___________|_______|___|_______|__________|____|______|______|___________
    ___|________|_________|___|______|___|__|_________|____|_______|___________|___
                                      ^
    (4) Very low spont rate (cannot measure intervals between events)
        with good response precision
        
    ______________________________________|________________________________________
    ________|___________________________________|__________________________________
    _________________________________________|________________________|____________
                                      ^
    (5) Non-obvious rate change, but response amplitudes are very different
    
    __,______.___,_______.___,_______,_____|___,_____._________,_,______.______,___
                                      ^

    

"""












## Code for playing with poisson distributions

import numpy as np
import scipy.stats as stats
import pyqtgraph as pg
import pyqtgraph.console
import user

def poissonProcess(rate, tmax):
    """Simulate a poisson process; return a list of event times"""
    events = []
    t = 0
    while True:
        t += np.random.exponential(1./rate)
        if t > tmax:
            break
        events.append(t)
    return np.array(events)

def poissonProb(events, xvals, rate):
    ## Given a list of event times,
    ## evaluate poisson cdf of events for multiple windows (0 to x for x in xvals)
    ## for each value x in xvals, returns the probability that events from 0 to x
    ## would be produced by a poisson process with the given rate.
    y = []
    for x in xvals:
        y.append(stats.poisson(rate * x).cdf(np.sum(events<=x)))
    return 1.0-np.array(y)

def poissonScore(events, rate):
    ## 1) For each event, measure the probability that the event and those preceding
    ##    it could be produced by a poisson process
    ## 2) Of the probabilities computed in 1), select the minimum value
    ## 3) X = 1 / min to convert from probability to improbability
    ## 4) apply some magic: Y = sqrt(X) / 2  -- don't know why this works, but
    ##    it scales the value such that 1 in Y random trials will produce a score >= Y
    
    pp = poissonProb(events, events, rate)
    if len(pp) == 0:
        return 1.0
    else:
        return 0.5 * ((1.0 / pp.min())**0.5)
    
def poissonBlame(ev, rate):
    ## estimate how much each event contributes to the poisson-score of a list of events.
    pp = []
    for i in range(len(ev)):
        ev2 = list(ev)
        ev2.pop(i)
        #pp.append(poissonScore(ev, rate) / poissonScore(ev2, rate))
        pp1 = 1. / (1.-poissonProb(ev, ev, rate))
        pp2 = 1. / (1.-poissonProb(ev2, ev2, rate))
        pp2l = list(pp2)
        print pp2[max(0,i-1):i]
        pp2l.insert(i, pp2[i-1:i].mean())
        pp.append((pp1 / np.array(pp2l)).max())
    ret = np.array(pp)
    assert not any(np.isnan(pp))
    return ret

#def poissonBlame(ev, rate):
    ### estimate how much each event contributes to the poisson-score of a list of events.
    #ev = list(ev)
    #ps = poissonScore(ev, rate)
    #pp = []
    #while len(ev) > 0:
        #ev.pop(-1)
        #if len(ev) == 0:
            #ps2 = 1.0
        #else:
            #ps2 = poissonScore(ev, rate)
        #pp.insert(0, ps / ps2)
        #ps = ps2
    #return np.array(pp)
    
    
## show that poissonProcess works as expected
#rate = 3.
#d1 = np.random.poisson(rate, size=100000)
#h1 = np.histogram(d1, bins=range(d1.max()+1))

#d2 = np.array([len(poissonProcess(rate, 1)) for i in xrange(100000)])
#h2 = np.histogram(d2, bins=range(d2.max()+1))

#plt = pg.plot(h2[1][1:], h2[0], pen='g', symbolSize=3)
#plt.plot(h1[1][1:], h1[0], pen='r', symbolSize=3)


## assign post-score to a series of events
#rate = 20.
#ev = poissonProcess(rate, 1.0)
#times = np.linspace(0.0, 1.0, 1000)
#prob = poissonProb(ev, times, rate)
#plt = pg.plot()

#for i in range(5):
    #prob = poissonProb(ev, times, rate)
    #c = plt.plot(x=times, y=1./prob, pen=(i,7))
    #c.setZValue(-i)
    #ev = np.append(ev, 0.06+i*0.01)
    #ev.sort()

    
#def recursiveBlame(ev, inds, rate, depth=0):
    #print "  "*depth, "start:", zip(inds, ev)
    #score = poissonScore(ev, rate)
    ##print "score:"
    #subScores = {}
    #for i in range(len(ev)):
        #ev2 = list(ev)
        #ev2.pop(i)
        #print "  "*depth, "check:", ev2
        #subScores[inds[i]] = score / poissonScore(ev2, rate)
    #print "  " * depth, "scores:", subScores
    
    
    #ev2 = [ev[i] for i in range(len(ev)) if subScores[inds[i]] > 1.0]
    #inds2 = [inds[i] for i in range(len(ev)) if subScores[inds[i]] > 1.0]
    #print "  "*depth, "passed:", zip(inds2, ev2)
    #if len(ev2) < 3:
        #return subScores
        
    #correctedScores = {}
    #for i in range(len(ev2)):
        #print "  "*depth, "remove", inds2[i], ':'
        #ev3 = list(ev2)
        #ev3.pop(i)
        #inds3 = list(inds2)
        #inds3.pop(i)
        #newScores = recursiveBlame(ev3, inds3, rate, depth+2)
        #if newScores is None:
            #continue
        #print "  "*depth, "compute correction:"
        #correction = 1.0
        #for j in range(len(ev3)):
            #c = subScores[inds3[j]] / newScores[inds3[j]]
            #correction *= c
            #print "  "*depth, inds3[j], c
        #correctedScores[inds2[i]] = subScores[inds2[i]] * correction
        #print "  "*depth, "final score:", inds2[i], correctedScores[inds2[i]]
        
        
        
    #return correctedScores
    
    
## Attempt to assign a post-probability to each event
#rate = 3.
#plt = pg.plot(name='Event Score')
#allev1 = []
#allev2 = []
#for i in range(10): ## reps
    #ev = poissonProcess(rate, 1.0)
    #allev1.append(ev)
    #colors = ['g'] * len(ev)
    #for i in range(3):  ## insert 4 events
        #ev = np.append(ev, 0.02 + np.random.gamma(shape=1, scale=0.01))
        #colors.append('w')
    #ev = np.append(ev, 0.07)
    #colors.append('w')
    #ev = np.append(ev, 0.15)
    #colors.append('w')
    
    
    
    #allev2.append(ev)
    #pp = poissonBlame(ev, rate)
    #print len(ev), len(pp), len(colors)
    #plt.plot(x=ev, y=pp, pen=None, symbol='o', symbolBrush=colors).setOpacity(0.5)

#allev1 = np.concatenate(allev1)
#allev2 = np.concatenate(allev2)
#h = np.histogram(allev1, bins=100)
#plt = pg.plot(h[1][1:], h[0], name='PSTH')
#h = np.histogram(allev2, bins=100)
#plt.plot(h[1][1:], h[0])

#print ev
#recursiveBlame(ev, list(range(len(ev))), rate)


app = pg.mkQApp()
con = pyqtgraph.console.ConsoleWidget()
con.show()
con.catchAllExceptions()

## Test ability of poissonScore to predict proability of seeing false positives


for rate in [2, 5, 10, 20]:
    print "spont rate:", rate
    #rate = 5.
    tMax = 1.0
    totals = [0,0,0,0,0,0]
    pptotals = [0,0,0,0,0,0]
    trials = 10000
    for i in xrange(trials):
        events = poissonProcess(rate, tMax)
        #prob = 1.0 / (1.-poissonProb(events, [tMax], rate)[0])
        score = poissonScore(events, rate)
        for i in range(1,6):
            if score > 10**i:
                totals[i] += 1
            #if prob > 10**i:
                #pptotals[i] += 1
    print "False negative scores:"
    for i in range(1,6):
        print "   > %d: %d (%0.2f%%)" % (10**i, totals[i], 100*totals[i]/float(trials))
    #print "False negative probs:"
    #for i in range(1,6):
        #print "   > %d: %d (%0.2f%%)" % (10**i, pptotals[i], 100*pptotals[i]/float(trials))


raise SystemExit(0)

## Create a set of test cases:

reps = 30
spontRate = 3.
miniAmp = 1.0
tMax = 0.5

def randAmp(n=1, quanta=1):
    return np.random.gamma(4., size=n) * miniAmp * quanta / 4.

## create a standard set of spontaneous events
spont = []
for i in range(reps):
    times = poissonProcess(spontRate, tMax)
    amps = randAmp(len(times))  ## using scale=4 gives a nice not-quite-gaussian distribution
    source = ['spont'] * len(times)
    spont.append((times, amps, source))


def spontCopy(i, extra):
    times, amps, source = spont[i]
    ev = np.zeros(len(times)+extra, dtype=[('time', float), ('amp', float), ('source', object)])
    ev['time'][:len(times)] = times
    ev['amp'][:len(times)] = amps
    ev['source'][:len(times)] = source
    return ev
    
## copy spont. events and add on evoked events
tests = [[] for i in range(7)]
for i in range(reps):
    ## Test 0: no evoked events
    tests[0].append(spontCopy(i, 0))

    ## Test 1: 1 extra event, single quantum, short latency
    ev = spontCopy(i, 1)
    ev[-1] = (0.01, 1, 'evoked')
    tests[1].append(ev)

    ## Test 2: 2 extra events, single quantum, short latency
    ev = spontCopy(i, 2)
    for j, t in enumerate([0.01, 0.015]):
        ev[-(j+1)] = (t, 1, 'evoked')
    tests[2].append(ev)

    ## Test 3: 4 extra events, single quantum, short latency
    ev = spontCopy(i, 4)
    for j,t in enumerate([0.01, 0.015, 0.024, 0.04]):
        ev[-(j+1)] = (t, 1, 'evoked')
    tests[3].append(ev)

    ## Test 4: 3 extra events, single quantum, long latency
    ev = spontCopy(i, 3)
    for j,t in enumerate([0.07, 0.10, 0.15]):
        ev[-(j+1)] = (t, 1, 'evoked')
    tests[4].append(ev)

    ## Test 5: 1 extra event, 2 quanta, short latency
    ev = spontCopy(i, 1)
    ev[-1] = (0.01, 2, 'evoked')
    tests[5].append(ev)

    ## Test 6: 1 extra event, 3 quanta, long latency
    ev = spontCopy(i, 1)
    ev[-1] = (0.05, 3, 'evoked')
    tests[6].append(ev)


## Analyze and plot all:

win = pg.GraphicsWindow(border=0.3)
with pg.ProgressDialog('processing..', maximum=len(tests)) as dlg:
    for i in range(len(tests)):
        first = (i == 0)
        last = (i == len(tests)-1)
        
        if first:
            evLabel = win.addLabel('Event amplitude', angle=-90, rowspan=len(tests))
        evplt = win.addPlot()
        
        if first:
            scoreLabel = win.addLabel('Poisson Score', angle=-90, rowspan=len(tests))
        scoreplt = win.addPlot()
        
        if first:
            evplt.register('EventPlot1')
            scoreplt.register('ScorePlot1')
        else:
            evplt.setXLink('EventPlot1')
            scoreplt.setXLink('ScorePlot1')
            
        scoreplt.setLogMode(False, True)
        #diag = pg.InfiniteLine(angle=45)
        #scoreplt.addItem(diag)
        #scoreplt.hideAxis('left')
        scoreplt.hideAxis('bottom')
        
        for j in range(reps):
            ev = tests[i][j]
            colors = [(0,255,0,50) if source=='spont' else (255,255,255,50) for source in ev['source']]
            evplt.plot(x=ev['time'], y=ev['amp'], pen=None, symbolBrush=colors, symbol='d', symbolSize=8, symbolPen=None)
            
            #print ev['time']
            score1 = poissonScore(ev['time'], spontRate)
            score2 = poissonScore((ev[ev['source'] == 'spont'])['time'], spontRate)
            scoreplt.plot(x=[j], y=[score1], pen=None, symbol='o', symbolBrush=(255,255,255,100))
            scoreplt.plot(x=[j], y=[score2], pen=None, symbol='o', symbolBrush=(0,255,0,100))
            
            evplt.hideAxis('bottom')
            #scoreplt.hideAxis('bottom')
            if last:
                evplt.showAxis('bottom')
                evplt.setLabel('bottom', 'Event time', 's')
                #scoreplt.showAxis('bottom')
                #scoreplt.setLabel('bottom', 'Spontaneous Score')
            
        dlg += 1
        if dlg.wasCanceled():
            break
            
        win.nextRow()
    
    
    






