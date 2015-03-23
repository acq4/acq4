# -*- coding: utf-8 -*-
"""

ScriptProcessor processes a script file (generally), loading data using the requested
loading routine and printing 
This is part of Acq4

Paul B. Manis, Ph.D.
2011-2013.

Pep8 compliant (via pep8.py) 10/25/2013
Refactoring begun 3/21/2015

"""


import os
import os.path
import numpy as np
import re
from acq4.analysis.AnalysisModule import AnalysisModule
from acq4.util.metaarray import MetaArray
from acq4.pyqtgraph import configfile
from PyQt4 import QtGui, QtCore

class ScriptProcessor(AnalysisModule):
    
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
    
    def setAnalysis(self, analysis=None, fileloader=None, template=None, clamps=None):
        """
        Set the analysis and the file loader routines
        that will be called by our script
        """
        self.analysis = analysis
        self.loadFile = fileloader
        self.data_template = template
        self.clamps = clamps

    def read_script(self, name=''):
        """
        read a script file from disk, and use that information to drive the analysis
        :param name:
        :return:
        """
        
        self.script_name = QtGui.QFileDialog.getOpenFileName(
                   None, 'Open Script File', '', 'Script (*.cfg)')
        if self.script_name == '':  # cancel returns empty string
            return None
        self.script = configfile.readConfigFile(self.script_name)
        if self.script is None:
#            print 'Failed to read script'
#            self.ctrl.IVCurve_ScriptName.setText('None')
            return None
        # set the data manager to the script if we can
        print self.script['directory']
        if 'directory' in self.script.keys():
            try:
                self.dataManager.setBaseDir(self.script['directory'])
                print('Set base dir to: {:s}'.format(self.script['directory']))
            except:
                print('ScriptProcessor:read_script: Cannot set base directory to %s\nLikely directory was not found' % self.script['directory'])
        return self.script_name
        
    def run_script(self):
        """
        revalidate and run the current script
        :return:
        """
        if self.validate_script():
            self.run_script()
        else:
            raise Exception("Script failed validation - see terminal output")

    def validate_script(self):
        """
        validate the current script - by checking the existence of the files needed for the analysis

        :return: False if cannot find files; True if all are found
        """
        # if self.script['module'] != 'IVCurve':
        #     print 'Script is not for IVCurve (found %s)' % self.script['module']
        #     return False
        if 'directory' in self.script.keys():
            try:
                
                #print dir(self.dataManager())
                self.dataManager().setBaseDir(self.script['directory'])
                print('Set base dir to: {:s}'.format(self.script['directory']))
            except:
                print('ScriptProcessor:read_script: \n   Cannot set base directory to %s\n   Likely directory was not found' % self.script['directory'])
                return False
                
        all_found = True
        trailingchars = [c for c in map(chr, xrange(97, 123))]  # trailing chars used to identify different parts of a cell's data
        for c in self.script['Cells']:
            if self.script['Cells'][c]['include'] is False:
                continue
            sortedkeys = sorted(self.script['Cells'][c]['choice'].keys())  # sort by order of recording
            for p in sortedkeys:
                pr = self.script['protocol'] + '_' + p  # add the underscore here
                if c[-1] in trailingchars:
                    cell = c[:-1]
                else:
                    cell = c
                fn = os.path.join(cell, pr)
                #print fn
                #print 'dm selected file: ', self.dataManager().selectedFile()
                if 'directory' in self.script.keys():
                    dm_selected_file = self.script['directory']
                else:
                    dm_selected_file = self.dataManager().selectedFile().name()
                DataManager.cleanup()
                gc.collect()
                fullpath = os.path.join(dm_selected_file, fn)
                file_ok = os.path.exists(fullpath)
                if file_ok:
                    print('File found: {:s}'.format(fullpath))
                else:
                    print '  current dataManager self.dm points to file: ', dm_selected_file
                    print '  and file not found was: ', fullpath
                    all_found = False
                #else:
                #    print 'file found ok: %s' % fullpath
        return all_found

    def run_script(self):
        """
        Run a script, doing all of the requested analysis
        :return:
        """
        if self.script['testfiles']:
            return
        # settext = self.scripts_form.PSPReversal_ScriptResults_text.setPlainText
        # apptext = self.scripts_form.PSPReversal_ScriptResults_text.appendPlainText
        self.textout = ('\nScript File: {:<32s}\n'.format(self.script_name))
        # settext(self.textout)
        script_header = True  # reset the table to a print new header for each cell
        trailingchars = [c for c in map(chr, xrange(97, 123))]  # trailing chars used to identify different parts of a cell's data
        self.dataManager().setBaseDir(self.script['directory'])
        ordered = sorted(self.script['Cells'].keys())  # order the analysis by date/slice/cell
        for cell in ordered:
            thiscell = self.script['Cells'][cell]
            #print 'processing cell: %s' % thiscell
            if thiscell['include'] is False:  # skip this cell
                print 'Skipped: %s' % cell
                continue
            sortedkeys = sorted(thiscell['choice'].keys())  # sort by order of recording (# on protocol)
            for p in sortedkeys:
                if thiscell['choice'][p] not in self.script['datafilter']:  # pick out steady-state conditions
                    print 'p: %s not in data: ' % (thiscell['choice'][p]), self.script['datafilter']
                    continue
                # print 'working on %s' % thiscell['choice'][p]
                pr = self.script['protocol'] + '_' + p  # add the underscore here
                if cell[-1] in trailingchars:  # check last letter - if not a number clip it
                    cell_file = cell[:-1]
                else:
                    cell_file = cell
                fn = os.path.join(cell_file, pr)
                #dm_selected_file = self.dataManager().selectedFile().name()
                dm_selected_file = self.script['directory']
                fullpath = os.path.join(dm_selected_file, fn)
                file_ok = os.path.exists(fullpath)
                if not file_ok:  # get the directory handle and take it from there
                    print 'File is not ok: %s' % fullpath
                    continue
                # self.ctrl.PSPReversal_KeepT.setChecked(QtCore.Qt.Unchecked)  # make sure this is unchecked
                dh = self.dataManager().manager.dirHandle(fullpath)
                if not self.loadFile([dh]):  # note: must pass a list
                    print 'Failed to load requested file: ', fullpath
                    continue  # skip bad sets of records...
                #print thiscell.keys()
                #print 'old data mode: ', self.Clamps.data_mode
                if 'datamode' in thiscell.keys():
                    self.clamps.data_mode = thiscell['datamode']
                    # print 'datamode may be overridden: self.Clamps.data_mode = %s' % self.Clamps.data_mode
                # apptext(('Protocol: {:<s} <br>Choice: {:<s}'.format(pr, thiscell['choice'][p])))
                #print dir(self.data_plot)
                # self.main_layout.update()
                self.analysis_summary['Drugs'] = thiscell['choice'][p]
                if 'genotype' in thiscell.keys():
                    self.analysis_summary['Genotype'] = thiscell['genotype']
                else:
                    self.analysis_summary['Genotype'] = ''
                # alt_flag = bool(thiscell['alternation'])
                # self.analysis_parameters['alternation'] = alt_flag
                # self.ctrl.PSPReversal_Alternation.setChecked((QtCore.Qt.Unchecked, QtCore.Qt.Checked)[alt_flag])
                # if 'junctionpotential' in thiscell:
                #     self.analysis_parameters['junction'] = thiscell['junctionpotential']
                #     self.ctrl.PSPReversal_Junction.setValue(float(thiscell['junctionpotential']))
                # else:
                #     self.analysis_parameters['junction'] = float(self.script['global_jp'])
                #     self.ctrl.PSPReversal_Junction.setValue(float(self.script['global_jp']))

                self.auto_updater = False
                self.get_script_analysisPars(self.script, thiscell)
                m = thiscell['choice'][p]  # get the tag for the manipulation
                self.analysis()  # call the caller's analysis routine
                DataManager.cleanup()
                del dh
                gc.collect()
                # self.update_rmp_analysis()
                # for win in ['win0', 'win1', 'win2']:
                #     self.update_win_analysis(win)
                ptxt = self.printAnalysis(printnow=False, script_header=script_header, copytoclipboard=False)
                # apptext(ptxt)
                #print 'ptxt: ', ptxt
                self.textout += ptxt + '\n'
                #print 'textout: ', self.textout
                # print protocol result, optionally a cell header.
                # self.print_formatted_script_output(script_header)
                script_header = False
        print self.textout
        self.auto_updater = True # restore function
        print '\nDone'

    def get_script_analysisPars(self, script_globals, thiscell):
        """
        set the analysis times and modes from the script. Also updates the qt windows
        :return: Nothing.
        """
        self.analysis_parameters = {}
        self.analysis_parameters['baseline'] = False

        self.analysis_parameters['lrwin1'] = {}
        self.analysis_parameters[' '] = {}
        self.analysis_parameters['lrwin0'] = {}
        self.analysis_parameters['lrrmp'] = {}
        self.auto_updater = False  # turn off the updates
        scriptg = {'global_jp': ['junction'], 'global_win1_mode': ['lrwin1', 'mode'],
                   'global_win2_mode': ['lrwin2', 'mode']}
        for k in scriptg.keys():  # set globals first
            if k in script_globals.keys():
                if len(scriptg[k]) == 1:
                    self.analysis_parameters[scriptg[k][0]] = script_globals[k]
                else:
                    self.analysis_parameters[scriptg[k][0]] = {scriptg[k][1]: script_globals[k]}
        if 'junctionpotential' in thiscell:
            self.analysis_parameters['junction'] = thiscell['junctionpotential']
        if 'alternation' in thiscell:
            self.analysis_parameters['alternation'] = thiscell['alternation']
        else:
            self.analysis_parameters['alternation'] = True
        return

    def print_script_output(self):
        """
        print a clean version of the results to the terminal
        :return:
        """
        print self.remove_html_markup(self.textout)

    def copy_script_output(self):
        """
        Copy script output (results) to system clipboard
        :return: Nothing
        """
        self.scripts_form.PSPReversal_ScriptResults_text.copy()

    def printAnalysis(self, printnow=True, script_header=True, copytoclipboard=False, summary=None):
        """
        Print the analysis summary information (Cell, protocol, etc)
        Print a nice formatted version of the analysis output to the terminal.
        The output can be copied to another program (excel, prism) for further analysis
        :param script_header:
        :return:
        """
        if summary is not None:
            self.analysis_summary = summary
            print 'printanalysis: summary: ', self.analysis_summary
        
        # Dictionary structure: key = information about 
        if self.clamps.data_mode in self.dataModel.ic_modes or self.clamps.data_mode == 'vc':
            data_template = self.data_template
        else:
          data_template = (
            OrderedDict([('ElapsedTime', '{:>8.2f}'), ('HoldV', '{:>5.1f}'), ('JP', '{:>5.1f}'),
                         ('Rs', '{:>6.2f}'), ('Cm', '{:>6.1f}'), ('Ru', '{:>6.2f}'),
                         ('Erev', '{:>6.2f}'),
                         ('gsyn_Erev', '{:>9.2f}'), ('gsyn_60', '{:>7.2f}'), ('gsyn_13', '{:>7.2f}'),
                         # ('p0', '{:6.3e}'), ('p1', '{:6.3e}'), ('p2', '{:6.3e}'), ('p3', '{:6.3e}'),
                         ('I_ionic+', '{:>8.3f}'), ('I_ionic-', '{:>8.3f}'), ('ILeak', '{:>7.3f}'),
                         ('win1Start', '{:>9.3f}'), ('win1End', '{:>7.3f}'),
                         ('win2Start', '{:>9.3f}'), ('win2End', '{:>7.3f}'),
                         ('win0Start', '{:>9.3f}'), ('win0End', '{:>7.3f}'),
            ]))
        print data_template
        # summary table header is written anew for each cell
        htxt = ''
        if script_header:
            htxt = '{:34s}\t{:15s}\t{:24s}\t'.format("Cell", "Genotype", "Protocol")
            for k in data_template.keys():
                cnv = '{:<%ds}' % (data_template[k][0])
                # print 'cnv: ', cnv
                htxt += (cnv + '\t').format(k)
            script_header = False
            htxt += '\n'

        ltxt = ''
        if 'Genotype' not in self.analysis_summary.keys():
            self.analysis_summary['Genotype'] = ' '
        ltxt += '{:34s}\t{:15s}\t{:24s}\t'.format(self.analysis_summary['CellID'], self.analysis_summary['Genotype'], self.analysis_summary['Protocol'])
          
        for a in data_template.keys():
            if a in self.analysis_summary.keys():
                txt = self.analysis_summary[a]
                if a in ['Description', 'Notes']:
                    txt = txt.replace('\n', ' ').replace('\r', '')  # remove line breaks from output, replace \n with space
                #print a, data_template[a]
                ltxt += (data_template[a][1]).format(txt) + ' \t'
            else:
                ltxt += ('{:>%ds}' % (data_template[a][0]) + '\t').format('NaN')
        ltxt = ltxt.replace('\n', ' ').replace('\r', '')  # remove line breaks
        ltxt = htxt + ltxt
        if printnow:
            print ltxt
        
        if copytoclipboard:
            clipb = QtGui.QApplication.clipboard()
            clipb.clear(mode=clipb.Clipboard)
            clipb.setText(ltxt, mode=clipb.Clipboard)

        return ltxt

    def remove_html_markup(self, html_string):
        """
        simple html stripper for our own generated text (output of analysis, above).
        This is not generally useful but is better than requiring yet another library
        for the present purpose.
        Taken from a stackoverflow answer.
        :param s: input html marked text
        :return: cleaned text
        """
        tag = False
        quote = False
        out = ""
        html_string = html_string.replace('<br>', '\n') # first just take of line breaks
        for char in html_string:
            if char == '<' and not quote:
                tag = True
            elif char == '>' and not quote:
                tag = False
            elif (char == '"' or char == "'") and tag:
                quote = not quote
            elif not tag:
                out = out + char
        return out
        
    # def print_formatted_script_output(self, script_header=True, copytoclipboard=False):
    #     """
    #     Print a nice formatted version of the analysis output to the terminal.
    #     The output can be copied to another program (excel, prism) for further analysis
    #     :param script_header:
    #     :return:
    #     """
    #     data_template = (OrderedDict([('ElapsedTime', '{:>8.2f}'), ('Drugs', '{:<8s}'), ('HoldV', '{:>5.1f}'), ('JP', '{:>5.1f}'),
    #                                                                     ('Rs', '{:>6.2f}'), ('Cm', '{:>6.1f}'), ('Ru', '{:>6.2f}'),
    #                                                                     ('Erev', '{:>6.2f}'),
    #                                                                     ('gsyn_Erev', '{:>9.2f}'), ('gsyn_60', '{:>7.2f}'), ('gsyn_13', '{:>7.2f}'),
    #                                                                     #('p0', '{:6.3e}'), ('p1', '{:6.3e}'), ('p2', '{:6.3e}'), ('p3', '{:6.3e}'),
    #                                                                     ('I_ionic+', '{:>8.3f}'), ('I_ionic-', '{:>8.3f}'), ('ILeak', '{:>7.3f}'),
    #                                                                     ('win1Start', '{:>9.3f}'), ('win1End', '{:>7.3f}'),
    #                                                                     ('win2Start', '{:>9.3f}'), ('win2End', '{:>7.3f}'),
    #                                                                     ('win0Start', '{:>9.3f}'), ('win0End', '{:>7.3f}'),
    #                                                                     ]))
    #     # summary table header is written anew for each cell
    #     if script_header:
    #         print('{:34s}\t{:24s}\t'.format("Cell", "Protocol")),
    #         for k in data_template.keys():
    #             print('{:<s}\t'.format(k)),
    #         print ''
    #     ltxt = ''
    #     ltxt += ('{:34s}\t{:24s}\t'.format(self.analysis_summary['CellID'], self.analysis_summary['Protocol']))
    #
    #     for a in data_template.keys():
    #         if a in self.analysis_summary.keys():
    #             ltxt += ((data_template[a] + '\t').format(self.analysis_summary[a]))
    #         else:
    #             ltxt += '<   >\t'
    #     print ltxt
    #     if copytoclipboard:
    #         clipb = QtGui.QApplication.clipboard()
    #         clipb.clear(mode=clipb.Clipboard )
    #         clipb.setText(ltxt, mode=clipb.Clipboard)
