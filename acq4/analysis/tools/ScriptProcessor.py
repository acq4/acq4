# -*- coding: utf-8 -*-
from __future__ import print_function
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
import gc
from acq4.analysis.AnalysisModule import AnalysisModule
from acq4.util.metaarray import MetaArray
from acq4.util import DataManager
from acq4.pyqtgraph import configfile
from acq4.util import Qt
from acq4.pyqtgraph.widgets.ProgressDialog import ProgressDialog

class ScriptProcessor(AnalysisModule):
    
    def __init__(self, host):
        AnalysisModule.__init__(self, host)

    def setAnalysis(self, analysis=None, fileloader=None, template=None, clamps=None, printer=None, dbupdate=None):
        """
        Set the analysis and the file loader routines
        that will be called by our script
        """
        self.analysis = analysis
        self.loadFile = fileloader
        self.data_template = template
        self.clamps = clamps
        self.printAnalysis = printer
        self.dbUpdate = dbupdate

    def read_script(self):
        """
        read a script file from disk, and use that information to drive the analysis
        Parameters
        ----------
        none
         
        Returns
        -------
        script_name : str
            The name of the script that was opened. If the script was not found, could not
            be read, or the dialog was cancelled, the return result will be None
        """
        
        self.script_name = Qt.QFileDialog.getOpenFileName(
                   None, 'Open Script File', '', 'Script (*.cfg)')
        if self.script_name == '':  # cancel returns empty string
            return None
        self.script = configfile.readConfigFile(self.script_name)
        if self.script is None:
#            print 'Failed to read script'
#            self.ctrl.IVCurve_ScriptName.setText('None')
            return None
        # set the data manager to the script if we can
        print(self.script['directory'])
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
        trailingchars = [c for c in map(chr, range(97, 123))]  # trailing chars used to identify different parts of a cell's data
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
                    print('  current dataManager self.dm points to file: ', dm_selected_file)
                    print('  and file not found was: ', fullpath)
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
        trailingchars = [c for c in map(chr, range(97, 123))]  # trailing chars used to identify different parts of a cell's data
        self.dataManager().setBaseDir(self.script['directory'])
        ordered = sorted(self.script['Cells'].keys())  # order the analysis by date/slice/cell
        prog1 = ProgressDialog("Script Processing..", 0, len(ordered))
        ncell  = len(ordered)
        for nc, cell in enumerate(ordered):
            if prog1.wasCanceled():
                break
            presetDict = {}
            thiscell = self.script['Cells'][cell]
            #print 'processing cell: %s' % thiscell
            if thiscell['include'] is False:  # skip this cell
                try:
                    print('Skipped: %s, reason:%s' % (cell, thiscell['reason']))
                except:
                    raise ValueError('cell %s has no tag "reason" but "include" is False' % cell)
                    
                continue
            sortedkeys = sorted(thiscell['choice'].keys())  # sort by order of recording (# on protocol)
            prog1.setValue(nc/ncell)
#            prog2 = ProgressDialog("Cell Processing..%s" , 0, len(sortedkeys)):
            for p in sortedkeys:
                if thiscell['choice'][p] not in self.script['datafilter']:  # pick out steady-state conditions
                    print('p: %s not in data: ' % (thiscell['choice'][p]), self.script['datafilter'])
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
                    print('File is not ok: %s' % fullpath)
                    continue

                m = thiscell['choice'][p]  # get the tag for the manipulation
                presetDict['Choices'] = thiscell['choice'][p]
                if 'genotype' in thiscell.keys():
                    presetDict['Genotype'] = thiscell['genotype']
                else:
                    presetDict['Genotype'] = 'Unknown'
                if 'Celltype' in thiscell.keys():
                    presetDict['Celltype'] = thiscell['Celltype']
                else:
                    presetDict['Celltype'] = 'Unknown'
                if 'spikethresh' in thiscell.keys():
                    presetDict['SpikeThreshold'] = thiscell['spikethresh']
                if 'bridgeCorrection' in thiscell.keys():
                    presetDict['bridgeCorrection'] = thiscell['bridgeCorrection']
                else:
                    presetDict['bridgeCorrection'] = None
                

                dh = self.dataManager().manager.dirHandle(fullpath)
                if not self.loadFile([dh], analyze=False, bridge=presetDict['bridgeCorrection']):  # note: must pass a list of dh; don't let analyisis run at end
                    print('Failed to load requested file: ', fullpath)
                    continue  # skip bad sets of records...
                if 'datamode' in thiscell.keys():
                    self.clamps.data_mode = thiscell['datamode']
                self.auto_updater = False
                self.get_script_analysisPars(self.script, thiscell)
                self.analysis(presets=presetDict)  # call the caller's analysis routine

                if 'addtoDB' in self.script.keys():
                    if self.script['addtoDB'] is True and self.dbUpdate is not None:
                        self.dbUpdate()  # call routine in parent

                ptxt = self.printAnalysis(printnow=False, script_header=script_header, copytoclipboard=False)
                self.textout += ptxt + '\n'
                script_header = False

                DataManager.cleanup()
                del dh
                gc.collect()

        print(self.textout)
        self.auto_updater = True # restore function
#        print '\nDone'

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
                   'global_win2_mode': ['lrwin2', 'mode'], 'Celltype': ['Celltype']}
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
        if 'include' in thiscell.keys():
            self.analysis_parameters['UseData'] = thiscell['include']
        else:
            self.analysis_parameters['UseData'] = True
#        print 'analysis params after get script \n', self.analysis_parameters
        return

    def print_script_output(self):
        """
        print(a clean version of the results to the terminal)
        :return:
        """
        print(self.remove_html_markup(self.textout))

    def copy_script_output(self):
        """
        Copy script output (results) to system clipboard
        :return: Nothing
        """
        self.scripts_form.PSPReversal_ScriptResults_text.copy()

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
        
