# -*- coding: utf-8 -*-

#### Test suite for MetaArray

from MetaArray import *
from numpy import *

## Create an array with every option possible

arr = zeros((2, 5, 3, 5), dtype=int)
for i in range(arr.shape[0]):
    for j in range(arr.shape[1]):
        for k in range(arr.shape[2]):
            for l in range(arr.shape[3]):
                arr[i,j,k,l] = (i+1)*1000 + (j+1)*100 + (k+1)*10 + (l+1)
    
info = [
    axis('Axis1'), 
    axis('Axis2', values=[1,2,3,4,5]), 
    axis('Axis3', cols=[
        ('Ax3Col1'),
        ('Ax3Col2', 'mV', 'Axis3 Column2'),
        (('Ax3','Col3'), 'A', 'Axis3 Column3')]),
    {'name': 'Axis4', 'values': array([1.1, 1.2, 1.3, 1.4, 1.5]), 'units': 's'},
    {'extra': 'info'}
]

ma = MetaArray(arr, info=info)

print "====  Original Array ======="
print ma
print "\n\n"

#### Tests follow:


#### Index/slice tests: check that all values and meta info are correct after slice
print "\n -- normal integer indexing\n"

print "\n  ma[1]"
print ma[1]

print "\n  ma[1, 2:4]"
print ma[1, 2:4]

print "\n  ma[1, 1:5:2]"
print ma[1, 1:5:2]

print "\n -- named axis indexing\n"

print "\n  ma['Axis2':3]"
print ma['Axis2':3]

print "\n  ma['Axis2':3:5]"
print ma['Axis2':3:5]

print "\n  ma[1, 'Axis2':3]"
print ma[1, 'Axis2':3]

print "\n  ma[:, 'Axis2':3]"
print ma[:, 'Axis2':3]

print "\n  ma['Axis2':3, 'Axis4':0:2]"
print ma['Axis2':3, 'Axis4':0:2]


print "\n -- column name indexing\n"

print "\n  ma['Axis3':'Ax3Col1']"
print ma['Axis3':'Ax3Col1']

print "\n  ma['Axis3':('Ax3','Col3')]"
print ma['Axis3':('Ax3','Col3')]

print "\n  ma[:, :, 'Ax3Col2']"
print ma[:, :, 'Ax3Col2']

print "\n  ma[:, :, ('Ax3','Col3')]"
print ma[:, :, ('Ax3','Col3')]


print "\n -- axis value range indexing\n"

print "\n  ma['Axis2':1.5:4.5]"
print ma['Axis2':1.5:4.5]

print "\n  ma['Axis4':1.15:1.45]"
print ma['Axis4':1.15:1.45]

print "\n  ma['Axis4':1.15:1.25]"
print ma['Axis4':1.15:1.25]



print "\n -- list indexing\n"

print "\n  ma[:, [0,2,4]]"
print ma[:, [0,2,4]]

print "\n  ma['Axis4':[0,2,4]]"
print ma['Axis4':[0,2,4]]

print "\n  ma['Axis3':[0, ('Ax3','Col3')]]"
print ma['Axis3':[0, ('Ax3','Col3')]]



print "\n -- boolean indexing\n"

print "\n  ma[:, array([True, True, False, True, False])]"
print ma[:, array([True, True, False, True, False])]

print "\n  ma['Axis4':array([True, False, False, False])]"
print ma['Axis4':array([True, False, False, False])]





#### Array operations 
#  - Concatenate
#  - Append
#  - Extend
#  - Rowsort




#### File I/O tests

print "\n================  File I/O Tests  ===================\n"
tf = '/tmp/MetaArrayTest'

# write whole array

print "\n  -- write/read test"
ma.write(tf)
ma2 = MetaArray(file=tf)

print ma2
print "\nArrays are equivalent:", all(ma == ma2)
#print "Meta info is equivalent:", ma.infoCopy() == ma2.infoCopy()
os.remove(tf)

# CSV write

# append mode


print "\n  -- append test (%s)" % tf
ma['Axis2':0:2].write(tf, appendAxis='Axis2')
for i in range(2,ma.shape[1]):
    ma['Axis2':[i]].write(tf, appendAxis='Axis2')

ma2 = MetaArray(file=tf)

print ma2
print "\nArrays are equivalent:", all(ma == ma2)
#print "Meta info is equivalent:", ma.infoCopy() == ma2.infoCopy()

os.remove(tf)