from __future__ import print_function

import os
import numpy as np
import pyqtgraph as pg
import pyqtgraph.console as console
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.codeEditor import codeEditorCommand


class Console(Module):
    moduleDisplayName = "Console"
    moduleCategory = "Utilities"

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.manager = manager
        self.localNamespace = {
            'man': manager,
            'pg': pg,
            'np': np,
            'getQtObjectAtClick': getQtObjectAtClick,
        }
        self.configFile = os.path.join('modules', 'Console.cfg')
        self.stateFile = os.path.join('modules', self.name + '_ui.cfg')
        
        msg = """
        Python console built-in variables:
           man - The ACQ4 Manager object
                 man.currentFile  ## currently selected file
                 man.getCurrentDir()  ## current storage directory
                 man.getCurrentDatabase() ## currently selected database
                 man.getDevice("Name")
                 man.getModule("Name")
           pg - pyqtgraph library
                pg.show(imageData)
                pg.plot(plotData)
           np - numpy library
           getQtObjectAtClick() - Call this function, then click on any Qt widget to return the deepest child object at
                that position.
           
        """
        
        self.win = Qt.QMainWindow()
        mp = os.path.dirname(__file__)
        self.win.setWindowIcon(Qt.QIcon(os.path.join(mp, 'icon.png')))
        self.win.resize(800,500)
        self.cw = ConsoleWidget(
            namespace=self.localNamespace,
            text=msg,
            editor=codeEditorCommand(),
            module=self,
            allowNonGuiExecution=True,
        )
        self.win.setCentralWidget(self.cw)
        self.win.setWindowTitle('ACQ4 Console')

        state = self.manager.readConfigFile(self.stateFile)
        # restore window position
        if 'geometry' in state:
            geom = Qt.QRect(*state['geometry'])
            self.win.setGeometry(geom)

        # restore dock configuration
        if 'window' in state:
            ws = Qt.QByteArray.fromPercentEncoding(state['window'].encode())
            self.win.restoreState(ws)

        self.win.show()

    def quit(self):
        print("console quit", self.stateFile)
        ## save ui configuration
        geom = self.win.geometry()
        state = {'window': bytes(self.win.saveState().toPercentEncoding()).decode(), 'geometry': [geom.x(), geom.y(), geom.width(), geom.height()]}
        self.manager.writeConfigFile(state, self.stateFile)
        Module.quit(self)


# reimplement history save/restore methods
class ConsoleWidget(console.ConsoleWidget):
    def __init__(self, *args, **kargs):
        self.module = kargs.pop('module')
        try:
            console.ConsoleWidget.__init__(self, *args, **kargs)
        except TypeError:
            kargs.pop('allowNonGuiExecution')
            console.ConsoleWidget.__init__(self, *args, **kargs)

    def saveHistory(self, history):
        self.module.manager.writeConfigFile({'history': history}, self.module.configFile)
        
    def loadHistory(self):
        config = self.module.manager.readConfigFile(self.module.configFile, missingOk=True)
        if 'history' in config:
            return config['history']


class ClickCapture(Qt.QObject):
    def __init__(self):
        super().__init__()
        self.captured_object = None

    def eventFilter(self, obj, event):
        if event.type() == Qt.QEvent.MouseButtonPress:
            pos = Qt.QCursor.pos()
            self.captured_object = self._dig_deepest(pos)

            Qt.QApplication.restoreOverrideCursor()
            Qt.QApplication.instance().removeEventFilter(self)
            return True
        return False

    def _dig_deepest(self, global_pos):
        widget = Qt.QApplication.widgetAt(global_pos)
        if not widget:
            return None

        return self._recurse_deepest(widget, global_pos)

    def _recurse_deepest(self, widget, global_pos):
        local_pos = widget.mapFromGlobal(global_pos)

        # Item views: try to get model index/item
        if isinstance(widget, Qt.QAbstractItemView):
            index = widget.indexAt(local_pos)
            if index.isValid():
                # This is probably as deep as we can go
                return {
                    'type': 'item_view_item',
                    'widget': widget,
                    'index': index,
                    'data': widget.model().data(index) if widget.model() else None,
                    'item': widget.model().itemFromIndex(index) if hasattr(widget.model(), 'itemFromIndex') else None
                }

        # Graphics views: try to get graphics items
        if isinstance(widget, Qt.QGraphicsView):
            scene_pos = widget.mapToScene(local_pos)
            items = widget.scene().items(scene_pos) if widget.scene() else []
            if items:
                return {
                    'type': 'graphics_item',
                    'view': widget,
                    'item': items[0],  # topmost item
                    'all_items': items
                }

        # Tab widgets: get the actual tab content
        if isinstance(widget, Qt.QTabWidget):
            tab_bar = widget.tabBar()
            if tab_bar and tab_bar.geometry().contains(local_pos):
                tab_index = tab_bar.tabAt(tab_bar.mapFromParent(local_pos))
                if tab_index >= 0:
                    return {
                        'type': 'tab',
                        'widget': widget,
                        'tab_index': tab_index,
                        'tab_text': widget.tabText(tab_index)
                    }

        # Check for child widgets
        child = widget.childAt(local_pos)
        if child and child != widget:
            # Recurse into the child
            deeper = self._recurse_deepest(child, global_pos)
            return deeper if deeper else child

        # If we can't go deeper, return this widget
        return widget


def getQtObjectAtClick():
    app = Qt.QApplication.instance()
    if not app:
        raise RuntimeError("No Qt.QApplication instance found")

    capturer = ClickCapture()
    Qt.QApplication.setOverrideCursor(Qt.QCursor(Qt.Qt.CrossCursor))
    app.installEventFilter(capturer)

    print("Click to capture deepest object...")

    while capturer.captured_object is None:
        app.processEvents()
        Qt.QTimer.singleShot(10, lambda: None)

    return capturer.captured_object
