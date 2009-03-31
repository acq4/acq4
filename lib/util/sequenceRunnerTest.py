#!/usr/bin/python -i
# -*- coding: utf-8 -*-
from SequenceRunner import *
from numpy import *

print "========== runSequence test: simplest way to invoke sequence ============"
def fn(x, y):
    print x, "*", y, "=", x*y
    return x*y
print runSequence(fn, {'x': [1,3,5,7], 'y': [2,4,6,8]}, ['y', 'x'])


print "\n========== seq.start(fn) test: Sequence using reusable SR object ============"
seq = SequenceRunner({'x': [1,3,5,7], 'y': [2,4,6,8]}, ['y', 'x'])
print seq.start(fn)



print "\n========== seq.start() test: Sequence using subclassed SR object ============"

class SR(SequenceRunner):
    def execute(self, x, y, z):
        return x * y + z

s = SR({'x': [1,3,5,7], 'y': [2,4,6,8], 'z': 0.5}, ['y', 'x'])
print s.start()

print "\n========== seq.start() 3D parameter space test ============"
s.setParams({'x': [1,3,5,7], 'y': [2,4,6,8], 'z': [0.5, 0.6, 0.7]})
s.setOrder(['x', 'z', 'y'])
a = s.start()
print a

print "\n========== break test: kernel function may skip parts of the parameter space ============"
s = SR({'x': [1,3,5,7,9,11,13], 'y': [2,4,6,8,10,12,14]}, ['x', 'y'])
def fn(x, y):
    prod = x * y
    if x > 7:
        raise Exception('break', 2)
    if prod > 60:
        raise Exception('break', 1)
    return prod
print s.start(fn, returnMask=True)


print "\n========== line end test: functions run at specific edges of the parameter space ============"
s = SR({'x': [1,3,5,7], 'y': [2,4,6,8]}, ['x', 'y'])
def fn(x, y):
    return x*y
def fn2(ind):
    print "end of row", ind
s.setEndFuncs([None, fn2])
s.start(fn)




print "\n========== nested index test: specific parts of each parameter are flagged for iteration ============"
def fn(x, y):
    print "x:", x, "   y:", y
    return 0
runSequence(fn, {'x': [1,3,[5,6,7],8], 'y': {'a': 1, 'b': [1,2,[3,'x',5],6]}}, ['y["b"][2]', 'x[2]'])


print "\n========== ndarray return test: kernel function returns an array, return is 2D array ============"
def fn(tVals, yVals, nPts):
    """Generate a waveform n points long with steps defined by tVals and yVals"""
    arr = zeros((nPts))
    tVals.append(nPts)
    for i in range(len(yVals)):
        arr[tVals[i]:tVals[i+1]] = yVals[i]
    return arr
print runSequence(fn, {'nPts': 10, 'tVals': [0, 3, 8], 'yVals': [0, [-5, -2, 2, 5], 0]}, ['yVals[1]'])
