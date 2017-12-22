#!/usr/bin/env python
# encoding: utf-8
from __future__ import print_function
"""
PlotHelpers.py

Routines to help use matplotlib and make cleaner plots
as well as get plots read for publication. 

Created by Paul Manis on 2010-03-09.
Copyright (c) 2010 Paul B. Manis, Ph.D.. All rights reserved.
"""

import sys
import os
stdFont = 'Arial'

def nice_plot(ax, spines, position = 10, axesoff = False):
    """ Adjust a plot so that it looks nicer than the default matplotlib plot
        Also allow quickaccess to things we like to do for publication plots, including:
           using a calbar instead of an axes: calbar = [x0, y0, xs, ys]
           inserting a reference line (grey, 3pt dashed, 0.5pt, at refline = y position)
    """
    for loc, spine in ax.spines.items():
        if loc in spines:
            spine.set_position(('outward', position)) # outward by 10 points
        else:
            spine.set_color('none') # don't draw spine
    if axesoff is True:
        noaxes(ax)

    # turn off ticks where there is no spine, if there are axes
    if 'left' in spines and not axesoff:
        ax.yaxis.set_ticks_position('left')
    else:
        # no yaxis ticks
        ax.yaxis.set_ticks([])

    if 'bottom' in spines and not axesoff:
        ax.xaxis.set_ticks_position('bottom')
    else:
        # no xaxis ticks
        ax.xaxis.set_ticks([])

def noaxes(ax):
    """ take away all the axis ticks and the lines"""
    ax.xaxis.set_ticks([])
    ax.set_axis_off()
    ax.yaxis.set_ticks([])


def cleanAxes(ax):
    for loc, spine in ax.spines.items():
        if loc in ['left', 'bottom']:
            pass
        elif loc in ['right', 'top']:
            spine.set_color('none') # do not draw the spine
        else:
            raise ValueError('Unknown spine location: %s' % loc)
        # turn off ticks whn there is no spine
        ax.xaxis.set_ticks_position('bottom')
        #pdb.set_trace()
        ax.yaxis.set_ticks_position('left') # stopped working in matplotlib 1.10
    update_font(ax)
    
def update_font(ax):
    for tick in ax.xaxis.get_major_ticks():
          tick.label1.set_fontname(stdFont)
        #      tick.label1.set_family('sans-serif')
          tick.label1.set_size(11)

    for tick in ax.yaxis.get_major_ticks():
          tick.label1.set_fontname(stdFont)
        #      tick.label1.set_family('sans-serif')
          tick.label1.set_size(11)
    ax.xaxis.set_smart_bounds(True)
    ax.yaxis.set_smart_bounds(True) 
    ax.tick_params(axis = 'both', labelsize = 9)

def adjust_spines(ax, spines, direction = 'outward', distance=5, smart=False):
    for loc, spine in ax.spines.items():
        if loc in spines:
            spine.set_position((direction,distance)) # outward by 10 points
            if smart:
                spine.set_smart_bounds(True)
            else:
                spine.set_smart_bounds(False)
        else:
            spine.set_color('none') # don't draw spine
    return
    # turn off ticks where there is no spine
    if 'left' in spines:
        ax.yaxis.set_ticks_position('left')
    else:
        # no yaxis ticks
        ax.yaxis.set_ticks([])

    if 'bottom' in spines:
        ax.xaxis.set_ticks_position('bottom')
    else:
        # no xaxis ticks
        ax.xaxis.set_ticks([])
        
def calbar(ax, calbar = None, axesoff = True, orient = 'left'):
    """ draw a calibration bar and label it up. The calibration bar is defined as:
        [x0, y0, xlen, ylen]
    """
    if axesoff is True:
        noaxes(ax)
    Vfmt = '%.0f'
    if calbar[2] < 1.0:
        Vfmt = '%.1f'
    Hfmt = '%.0f'
    if calbar[3] < 1.0:
        Hfmt = '%.1f'
    if calbar is not None:
        if orient == 'left': # vertical part is on the left
            ax.plot([calbar[0], calbar[0], calbar[0]+calbar[2]], 
                [calbar[1]+calbar[3], calbar[1], calbar[1]],
                color = 'k', linestyle = '-', linewidth = 1.5)
            ax.text(calbar[0]+0.05*calbar[2], calbar[1]+0.5*calbar[3], Hfmt % calbar[3], 
                horizontalalignment = 'left', verticalalignment = 'center',
                fontsize = 11)
        elif orient == 'right': # vertical part goes on the right
            ax.plot([calbar[0] + calbar[2], calbar[0]+calbar[2], calbar[0]], 
                [calbar[1]+calbar[3], calbar[1], calbar[1]],
                color = 'k', linestyle = '-', linewidth = 1.5)
            ax.text(calbar[0]+calbar[2]-0.05*calbar[2], calbar[1]+0.5*calbar[3], Hfmt % calbar[3], 
                horizontalalignment = 'right', verticalalignment = 'center',
                fontsize = 11)
        else:
            print("PlotHelpers.py: I did not understand orientation: %s" % (orient))
            print("plotting as if set to left... ")
            ax.plot([calbar[0], calbar[0], calbar[0]+calbar[2]], 
                [calbar[1]+calbar[3], calbar[1], calbar[1]],
                color = 'k', linestyle = '-', linewidth = 1.5)
            ax.text(calbar[0]+0.05*calbar[2], calbar[1]+0.5*calbar[3], Hfmt % calbar[3], 
                horizontalalignment = 'left', verticalalignment = 'center',
                fontsize = 11)
        ax.text(calbar[0]+calbar[2]*0.5, calbar[1]-0.05*calbar[3], Vfmt % calbar[2], 
            horizontalalignment = 'center', verticalalignment = 'top',
            fontsize = 11)            

def refline(ax, refline = None, color = '0.33', linestyle = '--' ,linewidth = 0.5):
    """ draw a reference line at a particular level of the data on the y axis 
    """
    if refline is not None:
        xlims = ax.get_xlim()
        ax.plot([xlims[0], xlims[1]], [refline, refline], color = color, linestyle=linestyle, linewidth=linewidth)
