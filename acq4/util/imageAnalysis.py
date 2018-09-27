# -*- coding: utf-8 -*-
from __future__ import print_function
"""
ImageAnalysis.py -  Generic image analysis functions
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""

from scipy.optimize import leastsq
from scipy import *
from scipy.ndimage import *

def gaussian2D(v, x):
    ## v is [amplitude, x offset, y offset, sigma, Z offset]
    return (v[0] * exp( - ((x[0]-v[1])**2 + (x[1]-v[2])**2) / (2 * v[3]**2))) + v[4]

def fitGaussian2D(image, guess):
    """
    Fit a 2D gaussian to an image. 
    guess is [amplitude, x offset, y offset, sigma, Z offset]
    """
    #func = lambda x, y: gaussian2D(guess, [x, y])
    erf = lambda v, img: (fromfunction(lambda x, y: gaussian2D(v, [x, y]), img.shape) - img).flatten()
    return leastsq(erf, guess, image)
    
def blur(img, sigma):
    return gaussian_filter(img, sigma)
