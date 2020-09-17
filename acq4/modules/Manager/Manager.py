# -*- coding: utf-8 -*-
from __future__ import print_function

import os

from acq4 import modules
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.debug import printExc

Ui_MainWindow = Qt.importTemplate(".ManagerTemplate")


class Manager(Module):
    moduleDisplayName = "Manager"
    moduleCategory = None

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.win = Qt.QMainWindow()
        mp = os.path.dirname(__file__)
        self.win.setWindowIcon(Qt.QIcon(os.path.join(mp, "icon.png")))
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self.win)
        self.stateFile = os.path.join("modules", self.name + "_ui.cfg")

        self.modGroupOrder = ["Acquisition", "Analysis", "Utilities"]

        self._deviceDocksByName = {}
        self.addDeviceDocks()
        self.updateModList()
        self.updateConfList()

        self.ui.loadConfigBtn.clicked.connect(self.loadConfig)
        self.ui.loadModuleBtn.clicked.connect(self.loadSelectedModule)
        self.ui.reloadModuleBtn.clicked.connect(self.reloadAll)
        self.ui.organizeUIBtn.clicked.connect(self.organizeUI)
        self.ui.configList.itemDoubleClicked.connect(self.loadConfig)
        self.ui.moduleList.itemDoubleClicked.connect(self.loadSelectedModule)
        self.ui.quitBtn.clicked.connect(self.requestQuit)

        state = self.manager.readConfigFile(self.stateFile)
        # restore window position
        if "geometry" in state:
            geom = Qt.QRect(*state["geometry"])
            self.win.setGeometry(geom)

        # restore dock configuration
        if "window" in state:
            ws = Qt.QByteArray.fromPercentEncoding(state["window"].encode())
            self.win.restoreState(ws)

        self.win.show()

    def addDeviceDocks(self):
        firstDock = None
        for d in self.manager.listDevices():
            try:
                dock = self.createDockForDevice(d)
                if dock is None:
                    continue
                self._deviceDocksByName[d] = dock
                self.win.addDockWidget(Qt.Qt.RightDockWidgetArea, dock)

                # By default, we stack all docks
                if firstDock is None:
                    firstDock = dock
                else:
                    self.win.tabifyDockWidget(firstDock, dock)
            except:
                self.showMessage("Error creating dock for device '%s', see console for details." % d, 10000)
                printExc("Error while creating dock for device '%s':" % d)

    def createDockForDevice(self, deviceName):
        dw = self.manager.getDevice(deviceName).deviceInterface(self)
        if dw is None:
            return None
        dock = Qt.QDockWidget(deviceName)
        dock.setFeatures(dock.DockWidgetMovable | dock.DockWidgetFloatable)
        dock.setObjectName(deviceName)
        dock.setWidget(dw)
        return dock

    def organizeUI(self):
        for dock in self._deviceDocksByName.values():
            self.win.removeDockWidget(dock)
            dock.close()

        # shrink the main window to start
        geom = self.win.geometry()
        minWinSize = self.ui.verticalLayout.sizeHint()
        heightSoFar = minWinSize.height()
        self.win.setGeometry(geom.x(), geom.y(), minWinSize.width(), heightSoFar)

        groupedDevices = {}
        for devName in self._deviceDocksByName.keys():
            groupedDevices.setdefault(devName[:5], {}).setdefault("device names", []).append(devName)
        groups = [group for group in groupedDevices.values() if len(group["device names"]) > 1]
        misc = [group["device names"][0] for group in groupedDevices.values() if len(group["device names"]) == 1]
        groups.append({"device names": misc})

        self._deviceDocksByName = {}
        for group in groups:
            for dev in group["device names"]:
                dock = self.createDockForDevice(dev)
                self._deviceDocksByName[dev] = dock

                minSize = dock.sizeHint()
                group["required width"] = max(minSize.width(), group.get("required width", 0))
                group["required height"] = max(minSize.height(), group.get("required height", 0))

        orient = Qt.Qt.Vertical
        heightUsedThisColumn = 0
        for group in sorted(groups, key=lambda g: (g["required height"], g["required width"])):
            if heightUsedThisColumn + group["required height"] > heightSoFar:
                orient = Qt.Qt.Horizontal
                heightUsedThisColumn = 0
            firstDock = None
            for dev in group["device names"]:
                dock = self._deviceDocksByName[dev]
                self.win.addDockWidget(Qt.Qt.RightDockWidgetArea, dock, orient)
                if firstDock is None:
                    firstDock = dock
                else:
                    self.win.tabifyDockWidget(firstDock, dock)
            if orient == Qt.Qt.Horizontal:
                orient = Qt.Qt.Vertical
            else:
                heightUsedThisColumn += group["required height"]

    def showMessage(self, *args):
        self.ui.statusBar.showMessage(*args)

    def updateModList(self):
        # Fill the list of modules.

        # clear tree and create top-level items in default order
        self.ui.moduleList.clear()
        self._modGrpItems = {}
        for n in self.modGroupOrder:
            self._mkModGrpItem(n)

        # load defined configurations first
        confMods = []
        for name, conf in self.manager.listDefinedModules().items():
            cls = modules.getModuleClass(conf["module"])
            confMods.append(cls)
            root = self._mkModGrpItem(cls.moduleCategory)
            item = Qt.QTreeWidgetItem([name])
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
            item.confModName = name
            root.addChild(item)

        # if a module has no defined configurations, then just give it a default entry without configuration.
        for name, cls in modules.getModuleClasses().items():
            if cls is Manager or cls in confMods:
                continue
            root = self._mkModGrpItem(cls.moduleCategory)
            dispName = cls.moduleDisplayName or cls.__name__
            item = Qt.QTreeWidgetItem([dispName])
            item.modName = name
            root.addChild(item)

    def _mkModGrpItem(self, name):
        if name is None:
            name = "Other"
        if name in self._modGrpItems:
            return self._modGrpItems[name]
        parts = name.split(".")
        if len(parts) > 1:
            root = self._mkModGrpItem(".".join(parts[:-1]))
        else:
            root = self.ui.moduleList.invisibleRootItem()
        item = Qt.QTreeWidgetItem([parts[-1]])
        root.addChild(item)
        item.setExpanded(True)
        self._modGrpItems[name] = item
        return item

    def updateConfList(self):
        self.ui.configList.clear()
        for m in self.manager.listConfigurations():
            self.ui.configList.addItem(m)

    def show(self):
        self.win.show()

    def requestQuit(self):
        self.manager.quit()

    def loadSelectedModule(self):
        item = self.ui.moduleList.currentItem()
        if hasattr(item, "confModName"):
            self.loadConfiguredModule(item.confModName)
        elif hasattr(item, "modName"):
            self.loadModule(item.modName)

    def loadConfiguredModule(self, mod):
        try:
            Qt.QApplication.setOverrideCursor(Qt.QCursor(Qt.Qt.WaitCursor))
            self.manager.loadDefinedModule(mod)
            self.showMessage("Loaded module configuration '%s'." % mod, 10000)
        finally:
            Qt.QApplication.restoreOverrideCursor()

    def loadModule(self, mod):
        try:
            Qt.QApplication.setOverrideCursor(Qt.QCursor(Qt.Qt.WaitCursor))
            self.manager.loadModule(mod)
            self.showMessage("Loaded module '%s'." % mod, 10000)
        finally:
            Qt.QApplication.restoreOverrideCursor()

    def reloadAll(self):
        self.manager.reloadAll()
        # mod = str(self.ui.moduleList.currentItem().text())
        # self.manager.loadDefinedModule(mod, forceReload=True)
        # self.showMessage("Loaded module '%s'." % mod, 10000)

    def loadConfig(self):
        # print "LOAD CONFIG"
        cfg = str(self.ui.configList.currentItem().text())
        self.manager.loadDefinedConfig(cfg)
        self.updateModList()
        self.showMessage("Loaded configuration '%s'." % cfg, 10000)

    def quit(self):
        # save ui configuration
        geom = self.win.geometry()
        state = {
            "window": bytes(self.win.saveState().toPercentEncoding()).decode(),
            "geometry": [geom.x(), geom.y(), geom.width(), geom.height()],
        }
        self.manager.writeConfigFile(state, self.stateFile)
        Module.quit(self)
