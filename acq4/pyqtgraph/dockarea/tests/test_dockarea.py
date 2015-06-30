# -*- coding: utf-8 -*-

import pyqtgraph as pg
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


