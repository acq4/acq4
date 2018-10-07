# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
from collections import OrderedDict

class ParamList(Qt.QTreeWidget):
    def __init__(self, *args):
        Qt.QTreeWidget.__init__(self, *args)
        self.header().setResizeMode(Qt.QHeaderView.ResizeToContents)
        self.setAnimated(False)


    checkStateMap = {
        True: Qt.Qt.Checked,
        False: Qt.Qt.Unchecked
    }
    
    def updateList(self, dev, params):
        """Update the list of sequence parameters for dev."""
        # Catalog the parameters that already exist for this device:
        items = {}
        for i in self.findItems(dev, Qt.Qt.MatchExactly | Qt.Qt.MatchRecursive, 0):
            items[str(i.text(1))] = i
        ## Add new sequence parameters, update old ones
        for p in params:
            if p not in items:
                #print dev, p, params[p]
                item = Qt.QTreeWidgetItem([dev, p, str(len(params[p]))])
                item.setFlags(
                    Qt.Qt.ItemIsSelectable | 
                    Qt.Qt.ItemIsDragEnabled |
                    Qt.Qt.ItemIsDropEnabled |
                    Qt.Qt.ItemIsUserCheckable |
                    Qt.Qt.ItemIsEnabled)
                item.setCheckState(0, Qt.Qt.Checked)
                items[p] = item
                if dev == 'protocol' and p == 'repetitions':
                    self.insertTopLevelItem(0, item)
                else:
                    self.addTopLevelItem(item)
                self.expandAll()
                #item.setExpanded(True)  ## Must happen AFTER adding to tree.  Also this causes warnings to appear (and possibly other problems?)
            #items[p].setData(2, Qt.Qt.DisplayRole, Qt.QVariant(str(len(params[p]))))
            items[p].setText(2, str(len(params[p])))
            items[p].paramData = [dev, p, str(len(params[p]))]
            items[p].params = list(params[p])
            
        ## remove non-existent sequence parameters (but not their children)
        for key in items:
            if key not in params:
                item = items[key]
                childs = item.takeChildren()
                p = item.parent()
                if p is None:
                    ind = self.indexOfTopLevelItem(item)
                    self.takeTopLevelItem(ind)
                    for c in childs:
                        self.addTopLevelItem(c)
                else:
                    p.removeChild(item)
                    for c in childs:
                        p.addChild(c)
    
    def saveState(self):
        state = []
        for i in self.topLevelItems():
            d = self.itemData(i)
            childs = []
            for j in range(i.childCount()):
                dd = self.itemData(i.child(j))
                childs.append(dd)
            state.append(d + (childs,))
        return state
    
    def loadState(self, state):
        """Order all parameters to match order in list. Does not create or destroy any parameters."""
        items = self.topLevelItems()
        
        ordered = []
        
        ## Go through parameter list, remove items from treewidget and store in temporary list
        for p in state:
            (dev, param, enabled, childs) = p
            item = self.findItem(dev, param)
            if item is None:
                continue
            item.setCheckState(0, ParamList.checkStateMap[enabled])
            o2 = []
            ordered.append((self.takeItem(item), o2))
            for c in childs:
                (dev2, param2, enabled2) = c
                item = self.findItem(dev2, param2)
                if item is None:
                    continue
                item.setCheckState(0, ParamList.checkStateMap[enabled])
                o2.append(self.takeItem(item))
        
        ## Re-add items from param list in correct order
        for i in ordered:
            self.addTopLevelItem(i[0])
            for i2 in i[1]:
                i[0].addChild(i2)
    
    def dropEvent(self, ev):
        Qt.QTreeWidget.dropEvent(self, ev)
        
        ## Enable drop for top-level items, disable for all others.
        for i in self.topLevelItems():
            i.setFlags(i.flags() | Qt.Qt.ItemIsDropEnabled)
            for j in range(i.childCount()):
                i.child(j).setFlags(i.flags() & (~Qt.Qt.ItemIsDropEnabled))
            i.setExpanded(True)
                
    def itemData(self, item):
        dev = str(item.text(0))
        param = str(item.text(1))
        enab = (item.checkState(0)==Qt.Qt.Checked)
        return(dev, param, enab)
        
    def topLevelItems(self):
        items = []
        for i in range(self.topLevelItemCount()):
            items.append(self.topLevelItem(i))
        return items
        
    def findItem(self, dev, param):
        items = self.findItems(dev, Qt.Qt.MatchExactly | Qt.Qt.MatchRecursive, 0)
        for i in items:
            #p = str(i.data(1, Qt.Qt.DisplayRole).toString())
            p = i.paramData[1]
            if p == param:
                return i
        return None
        
    def takeItem(self, item):
        p = item.parent()
        if p is None:
            return self.takeTopLevelItem(self.indexOfTopLevelItem(item))
        else:
            return p.takeChild(p.indexOfChild(item))

    def listParams(self):
        """Return a list of tuples, one for each parameter in the list: (device, parameter, number, [childs])
        If the parameter has children, then (device, parameter) is listed for each enabled parameter."""
        
        params = []
        for i in self.topLevelItems():
            (dev, param, enabled) = self.itemData(i)
            if enabled:
                #num = i.text(2).toInt()[0]
                num = i.paramData[2]
                if num < 1:
                    continue
                childs = []
                for j in range(i.childCount()):
                    (dev2, param2, en2) = self.itemData(i.child(j))
                    if en2:
                        childs.append((dev2, param2))
                params.append((dev, param, i.params, childs))
        return params
        
    def removeDevice(self, dev):
        """Remove all parameters for a specific device"""
        items = self.findItems(dev, Qt.Qt.MatchExactly | Qt.Qt.MatchRecursive, 0)
        for i in items:
            self.takeItem(i)
        
        