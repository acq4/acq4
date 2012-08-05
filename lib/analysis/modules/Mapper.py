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
            - If we can get a good measure of this, we should also be able to formulate
              a distribution describing spontaneous events. We can then ask how much of the 
              actual distribution exceeds this and automatically partition events into evoked / spont.
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
import scipy.misc
import scipy.interpolate
import pyqtgraph as pg
import pyqtgraph.console
import user
import pyqtgraph.multiprocess as mp

def poissonProcess(rate, tmax=None, n=None):
    """Simulate a poisson process; return a list of event times"""
    events = []
    t = 0
    while True:
        t += np.random.exponential(1./rate)
        if tmax is not None and t > tmax:
            break
        events.append(t)
        if n is not None and len(events) >= n:
            break
    return np.array(events)

#def poissonProb1(events, xvals, rate, correctForSelection=False):
    ### Given a list of event times,
    ### evaluate poisson cdf of events for multiple windows (0 to x for x in xvals)
    ### for each value x in xvals, returns the probability that events from 0 to x
    ### would be produced by a poisson process with the given rate.
    ##n = (events[:, np.newaxis] < xvals[np.newaxis,:]).sum(axis=0)
    ##p = stats.poisson(rate * x)
    
    ### In the case that events == xvals (the windows to evaluate are _selected_ 
    ### based on the event times), we must apply a correction factor to the expectation
    ### value: rate*x  =>  rate * (x + 1/rate). This effectively increases the size of the window
    ### by one period, which reduces the probability to the expected value.
    
    ### return 1.0 - p.cdf(n)
    
    #y = []
    #for i in range(len(xvals)):
        #x = xvals[i]
        #e = 0
        #if correctForSelection:
            #e = 1./rate
        #y.append(stats.poisson(rate * (x+e)).cdf(i+1))
    #return 1.0-np.array(y)

#def poissonScore(events, rate):
    ### 1) For each event, measure the probability that the event and those preceding
    ###    it could be produced by a poisson process
    ### 2) Of the probabilities computed in 1), select the minimum value
    ### 3) X = 1 / min to convert from probability to improbability
    ### 4) apply some magic: Y = sqrt(X) / 2  -- don't know why this works, but
    ###    it scales the value such that 1 in Y random trials will produce a score >= Y
    
    #pp = poissonProb(events, events, rate, correctForSelection=True)
    #if len(pp) == 0:
        #return 1.0
    #else:
        #return ((1.0 / pp.min())**1.0) / (rate ** 0.5)

##def poissonIntegral(events, rate, tMin, tMax):
    ### This version sucks
    ##pp = poissonProb(events, events, rate)
    ##if len(pp) == 0:
        ##return 1.0
    ##else:
        ##return (1.0 / pp.mean())**0.5
        
#poissonIntCache = {}
#def poissonIntegral(events, rate, tMin, tMax, plot=False):
    
    #global poissonIntCache
    #xvals = np.linspace(tMin, tMax, 1000)
    #dt = xvals[1]-xvals[0]
    #tot = 0
    #t = tMin
    #nev = 0
    #allprobs = []
    #events = list(events)
    #events.sort()
    #events.append(tMax)
    #for ev in events:
        #if ev < tMin:
            #continue
        #if ev > tMax:
            #ev = tMax
        #i1 = int((t-tMin) / dt)
        #i2 = int((ev-tMin) / dt)
        #if nev not in poissonIntCache:
            #poissonIntCache[nev] = np.array([1-stats.poisson(rate * x).cdf(nev) for x in xvals])
        #probs = poissonIntCache[nev][i1:i2]
        #tot += (1./probs).sum()
        #allprobs.append(1./probs)
        #t = ev
        #nev += 1
        #if ev == tMax:
            #break
        
    #if plot:
        #y = np.concatenate(allprobs)
        #pg.plot(x=xvals[:len(y)], y=y)
    #return tot * dt
    ##return (1. / poissonProb(events, xvals, rate)).sum() ** 0.5
        

#def poissonIntegralBlame(ev, rate, xMin, xMax):
    ### estimate how much each event contributes to the poisson-integral of a list of events.
    #pp = []
    #for i in range(len(ev)):
        #ev2 = list(ev)
        #ev2.pop(i)
        #pp1 = poissonIntegral(ev, rate, xMin, xMax)
        #pp2 = poissonIntegral(ev2, rate, xMin, xMax)
        #pp.append(pp1 / pp2)
    #ret = np.array(pp)
    #assert not any(np.isnan(pp))
    #return ret

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
    
#def productlog(x):
    #n = np.arange(1, 30, dtype=float)
    #return ((x ** n) * ((-n) ** (n-1)) / scipy.misc.factorial(n)).sum()
    
    
    
#def productlog(x, prec=1e-12):
    #"""
    #Stolen from py-fcm:
    #Productlog or LambertW function computes principal solution for w in f(w) = w*exp(w).
    #""" 
    ##  fast estimate with closed-form approximation
    #if (x <= 500):
        #lxl = np.log(x + 1.0)
        #return 0.665 * (1+0.0195*lxl) * lxl + 0.04
    #else:
        #return np.log(x - 4.0) - (1.0 - 1.0/np.log(x)) * np.log(np.log(x))

def poissonProb(n, t, l, clip=False):
    """
    For a poisson process, return the probability of seeing at least *n* events in *t* seconds given
    that the process has a mean rate *l*.
    """
    p = stats.poisson(l*t).cdf(n)   
    if clip:
        p = np.clip(p, 0, 1.0-1e-25)
    return p
    
def maxPoissonProb(ev, l):
    """
    For a list of events, compute poissonImp for each event; return the maximum and the index of the maximum.
    """
    if len(ev) == 0:
        return 0.0
    nVals = np.array([(ev<=t).sum()-1 for t in ev]) 
    pi = poissonProb(nVals, ev, l)  ## note that by using n=0 to len(ev)-1, we correct for the fact that the time window always ends at the last event
    mp = pi.max()
        
    return mp

def poissonScore(ev, l, tMax=None, ampMean=None, ampStdev=None, normalize=True):
    nSets = len(ev)
    ev = [x['time'] for x in ev]  ## select times from event set
    ev = np.concatenate(ev)   ## mix events together
    
    mpp = min(maxPoissonProb(ev, l*nSets), 1.0-1e-12)  ## don't allow returning inf
    score =  1.0 / (1.0 - mpp)
    #n = len(ev)
    if normalize:
        ret = mapPoissonScore(l*tMax*nSets, score)
    else:
        ret = score
    if np.isscalar(ret):
        assert not np.isnan(ret)
    else:
        assert not any(np.isnan(ret))
    
    return ret


        
poissonScoreNorm = None
def mapPoissonScore(n, x):
    global poissonScoreNorm
    if poissonScoreNorm is None:
        poissonScoreNorm = generateNormalizationTable()
        
    nind = np.log(n)/np.log(2)
    n1 = np.clip(int(np.floor(nind)), 0, poissonScoreNorm.shape[1]-2)
    n2 = n1+1
    
    mapped1 = []
    for i in [n1, n2]:
        norm = poissonScoreNorm[:,i]
        ind = np.argwhere(norm[0] > x)
        if len(ind) == 0:
            ind = len(norm[0])-1
        else:
            ind = ind[0,0]
        if ind == 0:
            ind = 1
        x1, x2 = norm[0, ind-1:ind+1]
        y1, y2 = norm[1, ind-1:ind+1]
        if x1 == x2:
            s = 0.0
        else:
            s = (x-x1) / float(x2-x1)
        mapped1.append(y1 + s*(y2-y1))
    
    mapped = mapped1[0] + (mapped1[1]-mapped1[0]) * (nind-n1)/float(n2-n1)
    
    ## doesn't handle points outside of the original data.
    #mapped = scipy.interpolate.griddata(poissonScoreNorm[0], poissonScoreNorm[1], [x], method='cubic')[0]
    #normTable, tVals, xVals = poissonScoreNorm
    #spline = scipy.interpolate.RectBivariateSpline(tVals, xVals, normTable)
    #mapped = spline.ev(n, x)[0]
    #raise Exception()
    assert not (np.isinf(mapped) or np.isnan(mapped))
    return mapped

def generateNormalizationTable(nEvents=10000):
    print "Generating poissonScore normalization table..."
    rate = 1.0
    tVals = 2**np.arange(9)
    global normScores
    normScores = []
    for i, t in enumerate(tVals):
        n = int(nEvents / (rate*t)**0.5)
        normScores.append(np.empty(int(n)))
        for j in xrange(int(n)):
            if j%1000==0:
                print t, j
            ev = [{'time': poissonProcess(rate, t)}]
            
            normScores[i][j] = poissonScore(ev, 1.0, normalize=False)
        
    xVals = 0.92 ** np.arange(500)
    xVals[-1] = 1e-25
    norm = np.empty((2, len(tVals),len(xVals)))
    for i in range(norm.shape[1]):
        for j, x in enumerate(xVals):
            norm[:, i, j] = scipy.stats.scoreatpercentile(normScores[i], (1-x)*100), 1.0/max(x, 1e-25)
        
    return norm

    
def testMapping(rate=1.0, tmax=1.0, n=10000):
    scores = np.empty(n)
    mapped = np.empty(n)
    ev = []
    for i in xrange(len(scores)):
        ev.append([{'time': poissonProcess(rate, tmax)}])
        scores[i] = poissonScore(ev[-1], rate, tMax=tmax)
        #mapped[i] = mapPoissonScore(rate*tmax, scores[i])
    
    for j in [1,2,3,4]:
        print "  %d: %f" % (10**j, (scores>10**j).sum() / float(len(scores)))
    return ev, scores
    
def poissonScoreBlame(ev, rate):
    nVals = np.array([(ev<=t).sum()-1 for t in ev]) 
    pp1 = 1.0 /   (1.0 - poissonProb(nVals, ev, rate, clip=True))
    pp2 = 1.0 /   (1.0 - poissonProb(nVals-1, ev, rate, clip=True))
    diff = pp1 / pp2
    blame = np.array([diff[np.argwhere(ev >= ev[i])].max() for i in range(len(ev))])
    return blame
    
    
    
def poissonRepScore(ev, l, tMax, ampMean, ampStdev, useAmps=False):
    """
    Given a set of event lists, return probability that a poisson process would generate all sets of events.
    ev = [
       [t1, t2, t3, ...],    ## trial 1
       [t1, t2, t3, ...],    ## trial 2
       ...
    ]
    """
    events = ev
    ev = [x['time'] for x in ev]  ## select times from event set
    
    ev2 = []
    for i in range(len(ev)):
        arr = np.zeros(len(ev[i]), dtype=[('trial', int), ('time', float)])
        arr['time'] = ev[i]
        arr['trial'] = i
        ev2.append(arr)
    ev2 = np.sort(np.concatenate(ev2), order=['time', 'trial'])
    if len(ev2) == 0:
        return 1.0
    
    ev = map(np.sort, ev)
    pp = np.empty((len(ev), len(ev2)))
    for i, trial in enumerate(ev):
        nVals = []
        for j in range(len(ev2)):
            n = (trial<ev2[j]['time']).sum()
            if any(trial == ev2[j]['time']) and ev2[j]['trial'] > i:  ## need to correct for the case where two events in separate trials happen to have exactly the same time.
                n += 1
            nVals.append(n)
        
        pp[i] = 1.0 / (1.0 - poissonProb(np.array(nVals), ev2['time'], l))
        if useAmps:
            pp[i] *= [gaussProb(events[i]['amp'][events[i]['time']<=t], ampMean, ampStdev) for t in ev2['time']]
            
            
    return pp.prod(axis=0).max() ##** (1.0 / len(ev))  ## normalize by number of trials [disabled--we WANT to see the significance that comes from multiple trials.]
    
    
    
    
    
    
def poissonRepAmpScore(*args):
    return poissonRepScore(*args, useAmps=True)
    

def gaussProb(amps, mean, stdev):
    """
    Given a gaussian distribution with mean, stdev, return the improbability
    of seeing all of the given amplitudes consecutively, normalized for the number of events.
    """
    if len(amps) == 0:
        return 1.0
    p = 1.0 - stats.norm(mean, stdev).cdf(amps)
    return 1.0 / (p.prod() ** (1./len(amps)))
    
    
app = pg.mkQApp()
con = pyqtgraph.console.ConsoleWidget()
con.show()
con.catchAllExceptions()


## Test ability of poissonScore to predict proability of seeing false positives

#with mp.Parallelize(tasks=[2, 2, 2, 2, 5, 5, 5, 5, 10, 10, 10, 10, 20, 20, 20, 20]) as tasker:
    ##np.random.seed(os.getpid() ^ int(time.time()*100))  ## make sure each fork gets its own random seed
    #for rate in tasker:
        ##rate = 5.
        #tMax = 1.0
        #totals = [0,0,0,0,0,0]
        #pptotals = [0,0,0,0,0,0]
        #trials = 10000
        #for i in xrange(trials):
            #events = poissonProcess(rate, tMax)
            ###prob = 1.0 / poissonProb(events, [tMax], rate)[0]
            ###prob = 1.0 / (1.0 - stats.poisson(rate*tMax).cdf(len(events)))  ## only gives accurate predictions for large rate
            ##prob = 1.0 / (1.0 - stats.poisson(rate*(events[-1]+(1./rate) if len(events) > 0 else tMax)).cdf(len(events)))  ## only gives accurate predictions for large rate
            ##score = poissonIntegral(events, rate, 0.005, 0.3)
            #score = poissonScore(events, rate)
            #for i in range(1,6):
                #if score > 10**i:
                    #totals[i] += 1
                ##if prob > 10**i:
                    ##pptotals[i] += 1
        #print "spont rate:", rate
        #print "False negative scores:"
        #for i in range(1,6):
            #print "   > %d: %d (%0.2f%%)" % (10**i, totals[i], 100*totals[i]/float(trials))
        ##print "False negative probs:"
        ##for i in range(1,6):
            ##print "   > %d: %d (%0.2f%%)" % (10**i, pptotals[i], 100*pptotals[i]/float(trials))

#raise Exception()

## Create a set of test cases:

reps = 3
trials = 20
spontRate = 3.
miniAmp = 1.0
tMax = 0.5

def randAmp(n=1, quanta=1):
    return np.random.gamma(4., size=n) * miniAmp * quanta / 4.

## create a standard set of spontaneous events
spont = [] ## trial, rep
allAmps = []
for i in range(trials):
    spont.append([])
    for j in range(reps):
        times = poissonProcess(spontRate, tMax)
        amps = randAmp(len(times))  ## using scale=4 gives a nice not-quite-gaussian distribution
        source = ['spont'] * len(times)
        spont[i].append((times, amps, source))
        allAmps.append(amps)
        
miniStdev = np.concatenate(allAmps).std()


def spontCopy(i, j, extra):
    times, amps, source = spont[i][j]
    ev = np.zeros(len(times)+extra, dtype=[('time', float), ('amp', float), ('source', object)])
    ev['time'][:len(times)] = times
    ev['amp'][:len(times)] = amps
    ev['source'][:len(times)] = source
    return ev
    
## copy spont. events and add on evoked events
testNames = []
tests = [[[] for i in range(trials)] for k in range(7)]  # test, trial, rep
for i in range(trials):
    for j in range(reps):
        ## Test 0: no evoked events
        testNames.append('No evoked')
        tests[0][i].append(spontCopy(i, j, 0))

        ## Test 1: 1 extra event, single quantum, short latency
        testNames.append('1ev, fast')
        ev = spontCopy(i, j, 1)
        ev[-1] = (np.random.gamma(1.0) * 0.01, 1, 'evoked')
        tests[1][i].append(ev)

        ## Test 2: 2 extra events, single quantum, short latency
        testNames.append('2ev, fast')
        ev = spontCopy(i, j, 2)
        for k, t in enumerate(np.random.gamma(1.0, size=2)*0.01):
            ev[-(k+1)] = (t, 1, 'evoked')
        tests[2][i].append(ev)

        ## Test 3: 3 extra events, single quantum, long latency
        testNames.append('3ev, slow')
        ev = spontCopy(i, j, 3)
        for k,t in enumerate(np.random.gamma(1.0, size=3)*0.07):
            ev[-(k+1)] = (t, 1, 'evoked')
        tests[3][i].append(ev)

        ## Test 4: 1 extra event, 2 quanta, short latency
        testNames.append('1ev, 2x, fast')
        ev = spontCopy(i, j, 1)
        ev[-1] = (np.random.gamma(1.0)*0.01, 2, 'evoked')
        tests[4][i].append(ev)

        ## Test 5: 1 extra event, 3 quanta, long latency
        testNames.append('1ev, 3x, slow')
        ev = spontCopy(i, j, 1)
        ev[-1] = (np.random.gamma(1.0)*0.05, 3, 'evoked')
        tests[5][i].append(ev)

        ## Test 6: 1 extra events specific time (tests handling of simultaneous events)
        #testNames.append('3ev simultaneous')
        #ev = spontCopy(i, j, 1)
        #ev[-1] = (0.01, 1, 'evoked')
        #tests[6][i].append(ev)
        
        ## 2 events, 1 failure
        testNames.append('0ev; 1ev; 2ev')
        ev = spontCopy(i, j, j)
        if j > 0:
            for k, t in enumerate(np.random.gamma(1.0, size=j)*0.01):
                ev[-(k+1)] = (t, 1, 'evoked')
        tests[6][i].append(ev)
        

#raise Exception()

## Analyze and plot all:

def checkScores(scores):
    best = None
    bestn = None
    bestval = None
    for i in [0,1]:
        for j in range(scores.shape[1]): 
            x = scores[i,j]
            fn = (scores[0] < x).sum()
            fp = (scores[1] >= x).sum()
            diff = abs(fp-fn)
            if bestval is None or diff < bestval:
                bestval = diff
                best = x
                bestn = (fp+fn)/2.
    return best, bestn
    
    
algorithms = [
    ('Poisson Score', poissonScore),
    ('Poisson Multi', poissonRepScore),
    ('Poisson Multi + Amp', poissonRepAmpScore),
]

win = pg.GraphicsWindow(border=0.3)
with pg.ProgressDialog('processing..', maximum=len(tests)) as dlg:
    for i in range(len(tests)):
        first = (i == 0)
        last = (i == len(tests)-1)
        
        if first:
            evLabel = win.addLabel('Event amplitude', angle=-90, rowspan=len(tests))
        evPlt = win.addPlot()
        
        plots = []
        for title, fn in algorithms:
            if first:
                label = win.addLabel(title, angle=-90, rowspan=len(tests))
            plt = win.addPlot()
            plots.append(plt)
            if first:
                plt.register(title)
            else:
                plt.setXLink(title)
            plt.setLogMode(False, True)
            plt.hideAxis('bottom')
            if last:
                plt.showAxis('bottom')
                plt.setLabel('bottom', 'Trial')
                
            
        #if first:
            #repScoreLabel = win.addLabel('Poisson Rep Score', angle=-90, rowspan=len(tests))
        #repScorePlt = win.addPlot()
        
        #if first:
            #scoreBlameLabel = win.addLabel('Poisson Score Blame', angle=-90, rowspan=len(tests))
        #scoreBlamePlt = win.addPlot()
        
        #if first:
            #intBlameLabel = win.addLabel('Poisson Integral Blame', angle=-90, rowspan=len(tests))
        #intblameplt = win.addPlot()
        
        if first:
            evPlt.register('EventPlot1')
            #scorePlt.register('ScorePlot1')
            #repScorePlt.register('RepScorePlot1')
            #scoreBlamePlt.register('ScoreBlamePlot1')
            #intblameplt.register('IntegralBlamePlot1')
        else:
            evPlt.setXLink('EventPlot1')
            #scorePlt.setXLink('ScorePlot1')
            #repScorePlt.setXLink('RepScorePlot1')
            #scoreBlamePlt.setXLink('ScoreBlamePlot1')
            #intblameplt.setXLink('IntegralBlamePlot1')
            
        #scorePlt.setLogMode(False, True)
        #repScorePlt.setLogMode(False, True)
        #diag = pg.InfiniteLine(angle=45)
        #scorePlt.addItem(diag)
        #scorePlt.hideAxis('left')
        #scorePlt.hideAxis('bottom')
        #repScorePlt.hideAxis('bottom')
        #scoreBlamePlt.setLogMode(False, True)
        
        evPlt.hideAxis('bottom')
        #scoreBlamePlt.hideAxis('bottom')
        evPlt.setLabel('left', testNames[i])
        #scorePlt.hideAxis('bottom')
        if last:
            evPlt.showAxis('bottom')
            evPlt.setLabel('bottom', 'Event time', 's')
            #scoreBlamePlt.showAxis('bottom')
            #scoreBlamePlt.setLabel('bottom', 'Event time', 's')
            #scorePlt.showAxis('bottom')
            #repScorePlt.showAxis('bottom')
            #scorePlt.setLabel('bottom', 'Trial')
            #repScorePlt.setLabel('bottom', 'Trial')
        
        trials = tests[i]
        scores = np.empty((len(algorithms), 2, len(trials)))
        repScores = np.empty((2, len(trials)))
        for j in range(len(trials)):
            
            ## combine all trials together for poissonScore tests
            ev = tests[i][j]
            spont = tests[0][j]
            evTimes = [x['time'] for x in ev]
            spontTimes = [x['time'] for x in spont]
            
            allEv = np.concatenate(ev)
            allSpont = np.concatenate(spont)
            #ev = np.concatenate(tests[i][j])
            #spont = np.concatenate(tests[0][j])
            #nReps = len(tests[i][j])
            
            colors = [(0,255,0,50) if source=='spont' else (255,255,255,50) for source in allEv['source']]
            evPlt.plot(x=allEv['time'], y=allEv['amp'], pen=None, symbolBrush=colors, symbol='d', symbolSize=8, symbolPen=None)
            
            for k, opts in enumerate(algorithms):
                title, fn = opts
                score1 = fn(ev, spontRate, tMax, miniAmp, miniStdev)
                score2 = fn(spont, spontRate, tMax, miniAmp, miniStdev)
                scores[k, :, j] = score1, score2
                plots[k].plot(x=[j], y=[score1], pen=None, symbolPen=None, symbol='o', symbolBrush=(255,255,255,50))
                plots[k].plot(x=[j], y=[score2], pen=None, symbolPen=None, symbol='o', symbolBrush=(0,255,0,50))

            #blame = poissonScoreBlame(allEv['time'], spontRate*len(ev))
            #scoreBlamePlt.plot(x=allEv['time'], y=blame, pen=None, symbolBrush=colors, symbol='d', symbolSize=8, symbolPen=None)
            
            ## poissonRepScore tests
            #score1 = poissonRepScore(evTimes, spontRate)
            #score2 = poissonRepScore(spontTimes, spontRate)
            #repScores[:, j] = score1, score2
            #repScorePlt.plot(x=[j], y=[score1], pen=None, symbolPen=None, symbol='o', symbolBrush=(255,255,255,50))
            #repScorePlt.plot(x=[j], y=[score2], pen=None, symbolPen=None, symbol='o', symbolBrush=(0,255,0,50))
            
            
            #blame = poissonIntegralBlame(ev['time'], spontRate, xMin, xMax)
            #intblameplt.plot(x=ev['time'], y=blame, pen=None, symbolBrush=colors, symbol='d', symbolSize=8, symbolPen=None)
        
        ## Report on ability of each algorithm to separate spontaneous from evoked
        for k, opts in enumerate(algorithms):
            thresh, errors = checkScores(scores[k])
            plots[k].setTitle("%0.2g, %d" % (thresh, errors))
        
        ## Plot score histograms
        #bins = np.linspace(-1, 6, 50)
        #h1 = np.histogram(np.log10(scores[0, :]), bins=bins)
        #h2 = np.histogram(np.log10(scores[1, :]), bins=bins)
        #scorePlt.plot(x=0.5*(h1[1][1:]+h1[1][:-1]), y=h1[0], pen='w')
        #scorePlt.plot(x=0.5*(h2[1][1:]+h2[1][:-1]), y=h2[0], pen='g')
            
        #bins = np.linspace(-1, 14, 50)
        #h1 = np.histogram(np.log10(repScores[0, :]), bins=bins)
        #h2 = np.histogram(np.log10(repScores[1, :]), bins=bins)
        #repScorePlt.plot(x=0.5*(h1[1][1:]+h1[1][:-1]), y=h1[0], pen='w')
        #repScorePlt.plot(x=0.5*(h2[1][1:]+h2[1][:-1]), y=h2[0], pen='g')
            
        dlg += 1
        if dlg.wasCanceled():
            break
            
        win.nextRow()
    
    
    







    
    
    
    
    
    
    
    
    
    
    
    

    
#def poissonImp(n, t, l):
    #"""
    #For a poisson process, return the improbability of seeing at least *n* events in *t* seconds given
    #that the process has a mean rate *l* AND the last event occurs at time *t*.
    #"""
    #return 1.0 / (1.0 - stats.poisson(l*t).cdf(n-1))   ## using n-1 corrects for the fact that we _know_ one of the events is at the end.
    ##l = l * t + 1
    ##i = np.arange(0, n+1)
    ##cdf = np.exp(-l) * (l**i / scipy.misc.factorial(i)).sum()
    ##return 1.0 / (1.0 - cdf)

#def maxPoissonImp(ev, l):
    #"""
    #For a list of events, compute poissonImp for each event; return the maximum and the index of the maximum.
    #"""
    #pi = poissonImp(np.arange(1, len(ev)+1), ev, l)
    #ind = np.argmax(pi)
    #return pi[ind], ind
    
#def timeOfPoissonImp(p, n, l, guess=0.1):
    #"""
    #Solve p == poissonImp(n, t, l) for t
    #"""
    #def erf(t):
        #return p - poissonImp(n, t, l)
    #return scipy.optimize.leastsq(erf, guess)[0][0]
    
#def polyRedist(v, x):
    #return v[0] + v[1] * x + v[2] * x**2 + v[3] * x**3 + v[4] * x**4

#def polyRedistFit(ev1, ev2):
    #"""
    #Find polynomial coefficients mapping ev1 onto ev2
    #"""
    #h2 = np.histogram(ev2, bins=200)
    #def err(v):
        #h1 = np.histogram(polyRedist(v, ev1), bins=200)
        ##print v, ((h2[0]-h1[0])**2).sum()
        #return h2[0] - h1[0]
    #return scipy.optimize.leastsq(err, x0=(0, 1, 0, 0, 0))
    
#def ellipseRedist(v, x):
    #x0, x1 = v
    #xp = x0 + x * (x1 - x0)
    #y0 = -(1-x0**2)**0.5
    #y1 = -(1-x1**2)**0.5
    #yp = -(1-xp**2)**0.5
    #y = (yp - y0) / (y1 - y0)
    #return y

#def ellipseRedistFit(ev1, ev2, **kwds):
    #"""
    #Find circular coefficients mapping ev1 onto ev2
    #"""
    #h2 = np.histogram(ev2, bins=200)
    #def err(v):
        #print v
        #v = (v[0], min(v[1], 0.9999999))
        #h1 = np.histogram(ellipseRedist(v, ev1), bins=200)
        #return ((h2[0][-50:] - h1[0][-50:])**2).sum()
    #return scipy.optimize.fmin(err, x0=(0.995, 0.9995), **kwds)

#def poissonImpInv(x, l):
    #return -(2 + productlog(-x / np.exp(3))) / l

#rate = 15.
#trials = 1000000

## create a series of poisson event trains with n=1
##ev1 = np.vstack([poissonProcess(rate=rate, n=1) for i in xrange(trials)])
##mpi1 = np.array([maxPoissonImp(e, rate) for e in ev1])


## create a series of poisson event trains with n=2
#app = pg.mkQApp()
#plt = pg.plot(title='Distribution of probability values')
#plt2 = pg.plot(title='Cumulative distribution of probability values')
#pp = []
#mpp = []
#nval = np.array([2,3,5,8,12,17,23,30])
#for n in nval:
    #ev2 = np.vstack([poissonProcess(rate=rate, n=n) for i in xrange(trials)])
    ##pi2 = np.array([poissonImp(n, e[-1], rate) for e in ev2])
    ##mpi2 = np.array([maxPoissonImp(e, rate) for e in ev2])
    ##mpi20 = mpi2[mpi2[:,1]==0][:,0]
    ##mpi21 = mpi2[mpi2[:,1]==1][:,0]
    #app.processEvents()
    #pp2 = np.array([poissonProb(n, e[-1], rate) for e in ev2])
    #app.processEvents()
    #mpp2 = np.array([maxPoissonProb(e, rate) for e in ev2])

    ##break
    
    ##print "\nPoisson improbability (n=%d):" % n
    ##for i in range(1,4):
        ##print "  %d: %0.2f%%" % (10**i, (pi2>10**i).sum() * 100. / trials)
    ##print "Max poisson improbability (n=%d):" % n
    ##for i in range(1,4):
        ##print "  %d: %0.2f%%" % (10**i, (mpi2[:,0]>10**i).sum() * 100. / trials)
    #print "\nPoisson probability (n=%d):" % n
    #for i in range(1,4):
        #thresh = 1.-10**-i
        #print "  %0.2f: %0.2f%%" % (thresh, (pp2>thresh).sum() * 100. / trials)
    #print "Max poisson probability (n=%d):" % n
    #for i in range(1,4):
        #thresh = 1.-10**-i
        #print "  %0.2f: %0.2f%%" % (thresh, (mpp2[:,0]>thresh).sum() * 100. / trials)


    #h = np.histogram(pp2, bins=100)
    #plt.plot(h[1][1:], h[0], pen='g')
    #h = np.histogram(mpp2[:,0], bins=100)
    #plt.plot(h[1][1:], h[0], pen='y')
    #app.processEvents()
    
    #pp.append(pp2)
    #mpp.append(mpp2)


#mpp1 = mpp[0][mpp[0][:,1]==0]
#mpp2 = mpp[0][mpp[0][:,1]==1]
#h1 = np.histogram(mpp1[:,3], bins=100)
#h2 = np.histogram(mpp1[:,2], bins=100)
#h3 = np.histogram(mpp2[:,2], bins=100)
#h4 = np.histogram(mpp2[:,3], bins=100)
#pg.plot(h1[1][1:], (h2[0]+h4[0])-(h1[0]+h3[0]))


#p = []
#for i in range(len(mpp)):
    #p.append(plt2.plot(pen=(i,10)))
#a = array([ 0.95 ,  0.93 ,  0.91 ,  0.89 ,  0.88 ,  0.865,  0.855,  0.855])
#b = array([ 1.49,  1.86,  2.35,  2.78,  3.2 ,  3.48,  3.7 ,  4.07])

#scipy.optimize.fmin(lambda v: ((b - (1.+ v[0] * (nval-1) ** v[1]))**2).sum(), x0=[1., 2.])
#scipy.optimize.fmin(lambda v: ((b - (1.+ v[0] * (nval-1) ** v[1]))**2).sum(), x0=[1., 2.])

### plot a reference line for a uniform distribution of probability vaules
#uniformEvents = np.concatenate([mpp[0][:,2], mpp[1][:,2], mpp[2][:,2], mpp[3][:,2]])
#h = np.histogram(uniformEvents, bins=500)
#h[0][1:] += h[0][:-1]
#plt2.plot(h[1][1:], h[0] / float(len(uniformEvents)))

#def redist(i):
    #global a, b, mpp
    #return (1.0 - (1.0 - mpp[i][:,0])**a[i])**b[i]

#def replot(i):
    #ev = redist(i)
    #h = np.histogram(ev, bins=500)
    #h[0][1:] += h[0][:-1]
    #p[i].setData(h[1][1:], h[0] / float(len(ev)))

    
### Approach:
### look at scoreatpercentile across different values of n
#pervals = 100*(1.-np.logspace(-4, -.2, 40))
#per = np.zeros((8,len(pervals)))
#for i in range(8):
  #for j in range(len(pervals)):
    #per[i,j] = scipy.stats.scoreatpercentile(mpp[i][:,0], pervals[j])

### Note that (1-np.array(per[i])) * nval**1.36  
### makes a very nearly linear set of points
#plt4 = pg.plot()
#for i in range(len(pervals)):
    #plt4.plot(nval, (1.-per[:,i])*nval**1.36, symbol='o')

#regress = []
#for i in range(len(pervals)):
    #reg = scipy.stats.linregress(nval, (1-np.array(per[:,i])) * nval**1.36)
    #regress.append(reg)
    #x = np.array([-10, 40])
    #plt4.plot(x, reg[0] * x + reg[1], pen='r')

#plt5 = pg.plot()
#plt5.plot(100-pervals, [reg[0] for reg in regress], symbol='o')  ## note: plotting this on log-log turns it linear.
### log(y) = m log(x) + b
### note also that this means the relationship is y = A x^B
#fit = scipy.optimize.fmin(lambda v: (( np.log(np.array([reg[0] for reg in regress])) - (np.log(v[0]) + np.log(100-pervals) * v[1]) )**2).sum(), [1, 2])
#plt5.plot(100-pervals, fit[0] * (100-pervals) ** fit[1], pen='r')

#raise Exception()
























## show that poissonProcess works as expected
#plt = pg.plot()
#for rate in [3, 10, 20]:
    #d1 = np.random.poisson(rate, size=100000)
    #h1 = np.histogram(d1, bins=range(d1.max()+1))

    #d2 = np.array([len(poissonProcess(rate, 1)) for i in xrange(100000)])
    #h2 = np.histogram(d2, bins=range(d2.max()+1))

    #plt.plot(h2[1][1:], h2[0], pen='g', symbolSize=3)
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
