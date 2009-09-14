from scipy.optimize import leastsq
from scipy import *
from scipy.ndimage import *

def gaussian2D(v, x):
    ## v is [amplitude, x offset, y offset, width, Z offset]
    ## "width" is the full width of the gaussian at (amplitude / e)
    return (v[0] * exp( - ((x[0]-v[1])**2 + (x[1]-v[2])**2) / (0.25 * v[3]**2))) + v[4]

def fitGaussian2D(image, guess):
    #func = lambda x, y: gaussian2D(guess, [x, y])
    erf = lambda v, img: (fromfunction(lambda x, y: gaussian2D(v, [x, y]), img.shape) - img).flatten()
    return leastsq(erf, guess, image)
    
def blur(img, sigma):
    return gaussian_filter(img, sigma)
