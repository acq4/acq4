# -*- coding: utf-8 -*-

import pytest
import pyqtgraph as pg
from collections import OrderedDict
pg.mkQApp()

import pyqtgraph.dockarea as da

def test_dockarea():
    a = da.DockArea()
    d1 = da.Dock("dock 1")
    a.addDock(d1, 'left')

    assert a.topContainer is d1.container()
    assert d1.container().container() is a
    assert d1.area is a
    assert a.topContainer.widget(0) is d1

    d2 = da.Dock("dock 2")
    a.addDock(d2, 'right')

    assert a.topContainer is d1.container()
    assert a.topContainer is d2.container()
    assert d1.container().container() is a
    assert d2.container().container() is a
    assert d2.area is a
    assert a.topContainer.widget(0) is d1
    assert a.topContainer.widget(1) is d2

    d3 = da.Dock("dock 3")
    a.addDock(d3, 'bottom')

    assert a.topContainer is d3.container()
    assert d2.container().container() is d3.container()
    assert d1.container().container() is d3.container()
    assert d1.container().container().container() is a
    assert d2.container().container().container() is a
    assert d3.container().container() is a
    assert d3.area is a
    assert d2.area is a
    assert a.topContainer.widget(0) is d1.container()
    assert a.topContainer.widget(1) is d3

    d4 = da.Dock("dock 4")
    a.addDock(d4, 'below', d3)

    assert d4.container().type() == 'tab'
    assert d4.container() is d3.container()
    assert d3.container().container() is d2.container().container()
    assert d4.area is a

    # layout now looks like:
    #    vcontainer
    #        hcontainer
    #            dock 1
    #            dock 2
    #        tcontainer
    #            dock 3
    #            dock 4

    # test save/restore state
    state = a.saveState()
    a2 = da.DockArea()
    # default behavior is to raise exception if docks are missing
    with pytest.raises(Exception):
        a2.restoreState(state)

    # test restore with ignore missing
    a2.restoreState(state, missing='ignore')
    assert a2.topContainer.count() == 0

    # test restore with auto-create
    a2.restoreState(state, missing='create')
    assert a2.saveState() == state

    # double-check that state actually matches the output of saveState()
    c1 = a2.topContainer
    assert c1.type() == 'vertical'
    c2 = c1.widget(0)
    c3 = c1.widget(1)
    assert c2.type() == 'horizontal'
    assert c2.widget(0).name() == 'dock 1'
    assert c2.widget(1).name() == 'dock 2'
    assert c3.type() == 'tab'
    assert c3.widget(0).name() == 'dock 3'
    assert c3.widget(1).name() == 'dock 4'

    # test restore with docks already present
    a3 = da.DockArea()
    a3docks = []
    for i in range(1, 5):
        dock = da.Dock('dock %d' % i)
        a3docks.append(dock)
        a3.addDock(dock, 'right')
    a3.restoreState(state)
    assert a3.saveState() == state

    # test restore with extra docks present    
    a3 = da.DockArea()
    a3docks = []
    for i in [1, 2, 5, 4, 3]:
        dock = da.Dock('dock %d' % i)
        a3docks.append(dock)
        a3.addDock(dock, 'left')
    a3.restoreState(state)


    # test a more complex restore
    a4 = da.DockArea()
    state1 = {'float': [], 'main': 
        ('horizontal', [
            ('vertical', [
                ('horizontal', [
                    ('tab', [
                        ('dock', u'Microscope', {}), 
                        ('dock', u'Camera', {}), 
                        ('dock', u'Manipulator2', {}), 
                        ('dock', u'Manipulator1', {})
                        ], {'index': 1}), 
                    ('vertical', [
                        ('dock', 'View', {}), 
                        ('horizontal', [
                            ('dock', 'ROI Plot', {}), 
                            ('dock', 'Image Sequencer', {})
                            ], {'sizes': [184, 363]})
                        ], {'sizes': [355, 120]})
                    ], {'sizes': [9, 552]})
                ], {'sizes': [480]}), 
            ('dock', 'Depth', {})
            ], {'sizes': [566, 69]})
        }

    state2 = OrderedDict([(u'float', []), (u'main', 
        ('horizontal', [
            ('vertical', [
                ('horizontal', [
                    ('dock', u'Camera', {}), 
                    ('vertical', [
                        ('dock', 'View', {}), 
                        ('horizontal', [
                            ('dock', 'ROI Plot', {}), 
                            ('dock', 'Image Sequencer', {})
                            ], {'sizes': [492, 485]})
                        ], {'sizes': [936, 0]})
                    ], {'sizes': [172, 982]})
                ], {'sizes': [941]}), 
            ('vertical', [
                ('dock', 'Depth', {}), 
                ('dock', u'Manipulator1', {}), 
                ('dock', u'Microscope', {})
                ], {'sizes': [681, 225, 25]})
            ], {'sizes': [1159, 116]}))])

    a4.restoreState(state1, missing='create')
    a4.restoreState(state2, missing='ignore')


