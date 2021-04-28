from __future__ import print_function
from six.moves import range
__author__ = 'pbmanis'
"""
Copyright 2014  Paul Manis and Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""
import re
from acq4.util import Qt
import pyqtgraph as pg

try:
    import matplotlib as MP
    from matplotlib.ticker import FormatStrFormatter
    import matplotlib.pyplot as PL
    import matplotlib.gridspec as gridspec
    import matplotlib.gridspec as GS
    HAVE_MPL = True
except ImportError:
    HAVE_MPL = False

if HAVE_MPL:
    MP.use('TKAgg')
    # Do not modify the following code
    # sets up matplotlib with sans-serif plotting...
    PL.rcParams['text.usetex'] = True
    PL.rcParams['interactive'] = False
    PL.rcParams['font.family'] = 'sans-serif'
    PL.rcParams['font.sans-serif'] = 'Arial'
    PL.rcParams['mathtext.default'] = 'sf'
    PL.rcParams['figure.facecolor'] = 'white'
    # next setting allows pdf font to be readable in Adobe Illustrator
    PL.rcParams['pdf.fonttype'] = 42
    PL.rcParams['text.dvipnghack'] = True
    # to here (matplotlib stuff - touchy!)

stdFont = 'Arial'


def cleanRepl(matchobj):
    """
        Clean up a directory name so that it can be written to a
        matplotlib title without encountering LaTeX escape sequences
        Replace backslashes with forward slashes
        replace underscores (subscript) with escaped underscores
    """
    if matchobj.group(0) == '\\':
        return '/'
    if matchobj.group(0) == '_':
        return '\_'
    if matchobj.group(0) == '/':
        return '/'
    else:
        return ''

def matplotlibExport(gridlayout=None, title=None):
    """
    Constructs a matplotlib window that shows the current plots laid out in the same
    format as the pyqtgraph window
    You might use this for publication purposes, since matplotlib allows export
    of the window to a variety of formats, and will contain proper fonts (not "outlined").
    Also can be used for automatic generation of PDF files with savefig.

    :param: QtGridLayout object that specifies how the grid was built
            The layout will contain pyqtgraph widgets added with .addLayout
    :return: nothing

    """

    if not HAVE_MPL:
        raise Exception("Method matplotlibExport requires matplotlib; not importable.")
    if gridlayout is None or gridlayout.__class__ != Qt.QGridLayout().__class__:
        raise Exception("Method matplotlibExport requires a QGridLayout")

    fig = PL.figure()
    PL.rcParams['text.usetex'] = False
    # escape filename information so it can be rendered by removing
    # common characters that trip up latex...:
    escs = re.compile('[\\\/_]')
    print(title)
    if title is not None:
        tiname = '%r' % title
        tiname = re.sub(escs, cleanRepl, tiname)[1:-1]
        fig.suptitle(r''+tiname)
    PL.autoscale(enable=True, axis='both', tight=None)
    # build the plot based on the grid layout
    gs = gridspec.GridSpec(gridlayout.rowCount(), gridlayout.columnCount())  # build matplotlib gridspec
    for i in range(gridlayout.count()):
        w = gridlayout.itemAt(i).widget()  # retrieve the plot widget...
        (x, y, c, r) = gridlayout.getItemPosition(i)  # and gridspecs paramters
        mplax = PL.subplot(gs[x:(c+x), y:(r+y)])  # map to mpl subplot geometry
        export_panel(w, mplax)  # now fill the plot
    gs.update(wspace=0.25, hspace=0.5)  # adjust spacing
#    PL.draw()
# hook to save figure - not used here
#       PL.savefig(os.path.join(self.commonPrefix, self.protocolfile))
    PL.show()

def export_panel(pgitem, ax):
    """
    export_panel recreates the contents of one pyqtgraph plot item into a specified
    matplotlib axis item
    :param fileName:
    :return:
    """
    # get labels from the pyqtgraph graphic item
    plitem = pgitem.getPlotItem()
    xlabel = plitem.axes['bottom']['item'].label.toPlainText()
    ylabel = plitem.axes['left']['item'].label.toPlainText()
    title = plitem.titleLabel.text
    fn = pg.functions
    ax.clear()
    cleanAxes(ax)  # make a "nice" plot

    for item in plitem.curves:
        x, y = item.getData()
        opts = item.opts
        pen = fn.mkPen(opts['pen'])
        if pen.style() == Qt.Qt.NoPen:
            linestyle = ''
        else:
            linestyle = '-'
        color = tuple([c/255. for c in fn.colorTuple(pen.color())])
        symbol = opts['symbol']
        if symbol == 't':
            symbol = '^'
        symbolPen = fn.mkPen(opts['symbolPen'])
        symbolBrush = fn.mkBrush(opts['symbolBrush'])
        markeredgecolor = tuple([c/255. for c in fn.colorTuple(symbolPen.color())])
        markerfacecolor = tuple([c/255. for c in fn.colorTuple(symbolBrush.color())])
        markersize = opts['symbolSize']

        if opts['fillLevel'] is not None and opts['fillBrush'] is not None:
            fillBrush = fn.mkBrush(opts['fillBrush'])
            fillcolor = tuple([c/255. for c in fn.colorTuple(fillBrush.color())])
            ax.fill_between(x=x, y1=y, y2=opts['fillLevel'], facecolor=fillcolor)

        pl = ax.plot(x, y, marker=symbol, color=color, linewidth=pen.width(),
                     linestyle=linestyle, markeredgecolor=markeredgecolor, markerfacecolor=markerfacecolor,
                     markersize=markersize)
        xr, yr = plitem.viewRange()
        ax.set_xbound(*xr)
        ax.set_ybound(*yr)
    ax.set_xlabel(xlabel)  # place the labels.
    ax.set_ylabel(ylabel)


# for matplotlib cleanup:
# These were borrowed from Manis' "PlotHelpers.py"
#
def cleanAxes(axl):
    if type(axl) is not list:
        axl = [axl]
    for ax in axl:
        for loc, spine in ax.spines.items():
            if loc in ['left', 'bottom']:
                pass
            elif loc in ['right', 'top']:
                spine.set_color('none')  # do not draw the spine
            else:
                raise ValueError('Unknown spine location: %s' % loc)
             # turn off ticks when there is no spine
            ax.xaxis.set_ticks_position('bottom')
            # stopped working in matplotlib 1.10
            ax.yaxis.set_ticks_position('left')
        update_font(ax)

def update_font(axl, size=6, font=stdFont):
    if type(axl) is not list:
        axl = [axl]
    fontProperties = {'family': 'sans-serif', 'sans-serif': [font],
                      'weight': 'normal', 'font-size': size}
    for ax in axl:
        for tick in ax.xaxis.get_major_ticks():
            tick.label1.set_family('sans-serif')
            tick.label1.set_fontname(stdFont)
            tick.label1.set_size(size)

        for tick in ax.yaxis.get_major_ticks():
            tick.label1.set_family('sans-serif')
            tick.label1.set_fontname(stdFont)
            tick.label1.set_size(size)
        # xlab = ax.axes.get_xticklabels()
        # print xlab
        # print dir(xlab)
        # for x in xlab:
        #     x.set_fontproperties(fontProperties)
        # ylab = ax.axes.get_yticklabels()
        # for y in ylab:
        #     y.set_fontproperties(fontProperties)
        #ax.set_xticklabels(ax.get_xticks(), fontProperties)
        #ax.set_yticklabels(ax.get_yticks(), fontProperties)
        ax.xaxis.set_smart_bounds(True)
        ax.yaxis.set_smart_bounds(True)
        ax.tick_params(axis='both', labelsize=9)

def formatTicks(axl, axis='xy', fmt='%d', font='Arial'):
    """
    Convert tick labels to intergers
    to do just one axis, set axis = 'x' or 'y'
    control the format with the formatting string
    """
    if type(axl) is not list:
        axl = [axl]
    majorFormatter = FormatStrFormatter(fmt)
    for ax in axl:
        if 'x' in axis:
            ax.xaxis.set_major_formatter(majorFormatter)
        if 'y' in axis:
            ax.yaxis.set_major_formatter(majorFormatter)


