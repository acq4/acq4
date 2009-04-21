"""
Utils.py - general utility routines
- power spectrum
- elliptical filtering
- handling very long input lines for dictionaries

"""
# January, 2009
# Paul B. Manis, Ph.D.
# UNC Chapel Hill
# Department of Otolaryngology/Head and Neck Surgery
# Supported by NIH Grants DC000425-22 and DC004551-07 to PBM.
# Copyright Paul Manis, 2009
#
"""
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import sys, re, os
from pylab import * # includes numpy
import scipy

from random import sample

# compute the power spectrum.
# simple, no windowing etc...

class Utility:
    def __init__(self):
        self.debugFlag = False
    

    def pSpectrum(self, data=None, samplefreq=44100):
        npts = len(data)
    # we should window the data here
        if npts == 0:
            print "? no data in pSpectrum"
            return
    # pad to the nearest higher power of 2
        (a,b) = frexp(npts)
        if a <= 0.5:
            b = b = 1
        npad = 2**b -npts
        if self.debugFlag:
            print "npts: %d   npad: %d   npad+npts: %d" % (npts, npad, npad+npts)    
        padw =  append(data, zeros(npad))
        npts = len(padw)
        spfft = fft(padw)
        nUniquePts = ceil((npts+1)/2.0)
        spfft = spfft[0:nUniquePts]
        spectrum = abs(spfft)
        spectrum = spectrum / float(npts) # scale by the number of points so that
                           # the magnitude does not depend on the length 
                           # of the signal or on its sampling frequency  
        spectrum = spectrum**2  # square it to get the power    
        spmax = amax(spectrum)
        spectrum = spectrum + 1e-12*spmax
        # multiply by two (see technical document for details)
        # odd nfft excludes Nyquist point
        if npts % 2 > 0: # we've got odd number of points fft
            spectrum[1:len(spectrum)] = spectrum[1:len(spectrum)] * 2
        else:
            spectrum[1:len(spectrum) -1] = spectrum[1:len(spectrum) - 1] * 2 # we've got even number of points fft
        freqAzero = arange(0, nUniquePts, 1.0) * (samplefreq / npts)
        return(spectrum, freqAzero)
    
# filter signal with elliptical filter
    def SignalFilter(self, signal, LPF, HPF, samplefreq):
        if self.debugFlag:
            print "sfreq: %f LPF: %f HPF: %f" % (samplefreq, LPF, HPF)
        flpf = float(LPF)
        fhpf = float(HPF)
        sf = float(samplefreq)
        sf2 = sf/2
        wp = [fhpf/sf2, flpf/sf2]
        ws = [0.5*fhpf/sf2, 2*flpf/sf2]
        if self.debugFlag:
            print "signalfilter: samplef: %f  wp: %f, %f  ws: %f, %f lpf: %f  hpf: %f" % (
               sf, wp[0], wp[1], ws[0], ws[1], flpf, fhpf)
        filter_b,filter_a=scipy.signal.iirdesign(wp, ws,
                gpass=1.0,
                gstop=60.0,
                ftype="ellip")
        w=scipy.signal.lfilter(filter_b, filter_a, signal) # filter the incoming signal
        if self.debugFlag:
            print "sig: %f-%f w: %f-%f" % (min(signal), max(signal), min(w), max(w))
        return(w)
        
    # do an eval on a long line (longer than 512 characters)
    # assumes input is a dictionary that is too long
    # parses by breaking the string down and then reconstructing each element
    #
    def long_Eval(self, line):
        sp = line.split(',')
        u = {}
        for di in sp:
            try:
                r = eval('{' + di.strip('{}') + '}')
                u[r.keys()[0]] = r[r.keys()[0]]
            except:
                continue
        return(u)
    
    # long_Eval()
    
    #
# routine to flatten an array/list. 
#
    def flatten(l, ltypes=(list, tuple)):
        i = 0
        while i < len(l):
            while isinstance(l[i], ltypes):
                if not l[i]:
                    l.pop(i)
                    if not len(l):
                        break
                else:
                   l[i:i+1] = list(l[i])
            i += 1
        return l
    
    # flatten()
    

        
################################################################################
#global routines included in this file:
# create thumbnails
from PIL import Image
import glob, os

size = 100, 100
def _mkdir(newdir):
    """works the way a good mkdir should :)
        - already exists, silently complete
        - regular file in the way, raise an exception
        - parent directory(ies) does not exist, make them as well
    """
    if os.path.isdir(newdir):
        pass
    elif os.path.isfile(newdir):
        raise OSError("a file with the same name as the desired " \
                      "dir, '%s', already exists." % newdir)
    else:
        head, tail = os.path.split(newdir)
        if head and not os.path.isdir(head):
            _mkdir(head)
        #print "_mkdir %s" % repr(newdir)
        if tail:
            os.mkdir(newdir)

def makeThumbs():
    datadir = './'
    tdir = 'Thumbs'
    _mkdir(tdir)
    for infile in glob.glob(datadir + "*.jpg"):
        path, file = os.path.split(infile)
        print file
        im = Image.open(infile)
        im.thumbnail(size, Image.ANTIALIAS)
        if os.path.isfile(tdir + '/' + file):
            print "*** " + file + " already exists as thumbnail - skipping\n"
        else:
            im.save(tdir + '/' + file, "JPEG")
            print "made a thumbnail: " + tdir + '/' + file + "\n"



def seqparse(sequence):
    """ parse the list of the format:
     12;23/10 etc... like nxtrec in datac    
     first arg is starting number for output array
     second arg is final number
     / indicates the skip arg type
     basic: /n means skip n : e.g., 1;10/2 = 1,3,5,7,9
     special: /##*r means randomize order (/##rn means use seed n for randomization)
     special: /##*l means spacing of elements is logarithmic
     special: /##*s means spacing is logarithmic, and order is randomized. (/##sn means use seed n for randomization)
     special: /##*a means alternate with a number
     multiple sequences are returned in a list... just like single sequences...
    
     3 ways for list to be structured:
     1. standard datac record parses.
     
     Updated 9/07/2000, 11/13/2000, 4/7/2004 (arbitrary matlab function argument with '=')
     converted to python 3/2/2009
     Paul B. Manis, Ph.D.
     pmanis@med.unc.edu
     """

    seq=[]
    target=[]
    sequence.replace(' ', '') # remove all spaces - nice to read, not needed to calculate
    sequence = str(sequence) #make sure we have a nice string
    (seq2, sep, remain) = sequence.partition('&') # find  and returnnested sequences
    while seq2 is not '':
        try:
            (oneseq, onetarget) = recparse(seq2)
            seq.append(oneseq)
            target.append(onetarget)
        except:
            pass
        (seq2, sep, remain) = remain.partition('&') # find  and returnnested sequences
    return (seq, target)

    
def recparse(cmdstr):
    """ function to parse basic word unit of the list - a;b/c or the like
    syntax is:
    [target:]a;b[/c][*n]
    where:
    target is a parameter target identification (if present)
    the target can be anything - a step, a duration, a level....
    it just needs to be in a form that will be interepreted by the PyStim
    sequencer; it may include a number to indicate which step duration, etc is the
    target.
    a, b and c are numbers
    n, and if present *n implies a "mode"
    such as linear, log, randomized, etc.
    """
    
    recs=[]
    target=[]
    seed=0
    skip = 1.0
    (target, sep, rest) = cmdstr.partition(':') # get the target
    if rest is '':
        rest = target # no : found, so no target designated.
        target=''
    (sfn, sep, rest1) = rest.partition(';')
    (sln, sep, rest2) = rest1.partition('/')
    (sskip, sep, mo) = rest2.partition('*') # look for mode
    fn = float(sfn)
    ln = float(sln)
    skip = float(sskip)
    ln = ln + 0.01*skip
#    print "mo: %s" % (mo)
    if mo is '': # linear spacing; skip is size of step
        recs=eval('arange(%f,%f,%f)' % (fn, ln, skip))

    if mo.find('l') >= 0: # log spacing; skip is length of result
        recs=eval('logspace(log10(%f),log10(%f),%f)' % (fn, ln, skip))
    
    if mo.find('t') >= 0: # just repeat the first value
        recs = eval('%f*[1]' % (fn))
    
    if mo.find('n') >= 0: # use the number of steps, not the step size
        if skip is 1.0:
            sk = (ln - fn)
        else:
            sk = eval('(%f-%f)/(%f-1.0)' % (ln, fn, skip))
        recs=eval('arange(%f,%f,%f)' % (fn, ln, sk))
    
    if mo.find('r') >= 0: # randomize the result
        if recs is []:
            recs=eval('arange(%f,%f,%f)' % (fn, ln, skip))
        recs = sample(recs, len(recs))
        
    if mo.find('a') >= 0: # alternation - also test for a value after that
        (arg, sep, value) = mo.partition('a') # is there anything after the letter?
        if value is '':
            value = 0.0
        else:
            value = float(value)
        val = eval('%f' % (value))
        c = [val]*len(recs)*2 # double the length of the sequence
        c[0:len(c):2] = recs # fill the alternate positions with the sequence
        recs = c # copy back
    return((recs, target))        
    



