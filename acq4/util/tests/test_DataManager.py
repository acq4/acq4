from __future__ import print_function
import tempfile, shutil, atexit, os
import acq4.util.DataManager as dm
from acq4.util.DirTreeWidget import DirTreeWidget
import acq4.pyqtgraph as pg

app = pg.mkQApp()

root = tempfile.mkdtemp()
def remove_tempdir():
    shutil.rmtree(root)
atexit.register(remove_tempdir)


def test_datamanager():

    rh = dm.getDirHandle(root)

    # check handles are cached
    rh2 = dm.getDirHandle(root)
    assert rh is rh2

    # test meta info is stored and reloaded correctly
    rh.setInfo({'test_int': 1, 'test_str': 'xxx'})
    assert rh.info()['test_int'] == 1
    assert rh.info()['test_str'] == 'xxx'

    # Create a subdir with meta info
    d1 = rh.mkdir('subdir', info={'a': 'b'})
    assert d1.info()['a'] == 'b'
    assert d1.shortName() == 'subdir'
    assert d1.name() == os.path.join(rh.name(), 'subdir')

    # Create a DirTreeWidget; check that the contents are correct.
    dw = DirTreeWidget(baseDirHandle=rh)
    assert dw.topLevelItemCount() == 1
    item = dw.topLevelItem(0)
    assert item.text(0) == d1.shortName()
    assert item.handle is d1
    assert item.childCount() == 0

    # Create a subdir and update the tree widget
    d2 = d1.mkdir('subdir2')
    dw.rebuildChildren(item)
    assert item.childCount() == 1

    # test _getTree
    d3 = rh.mkdir('subdir3')
    assert d3.name() not in dm.dm._getTree(d1.name())
    assert d2.name() in dm.dm._getTree(d1.name())

    #
    # root
    #   + subdir
    #   |   + subdir2
    #   + subdir3
    #
    assert d1.name(relativeTo=rh) == 'subdir'
    assert d2.name(relativeTo=rh) == os.path.join('subdir', 'subdir2')
    assert d2.name(relativeTo=d1) == 'subdir2'
    assert d2.name(relativeTo=d2) == ''
    assert d1.name(relativeTo=d2) == '..'
    assert rh.name(relativeTo=d2) == os.path.join('..', '..')
    assert d3.name(relativeTo=d2) == os.path.join('..', '..', 'subdir3')
    assert d2.name(relativeTo=d3) == os.path.join('..', 'subdir', 'subdir2')

    # rename subdir from tree widget
    item.setText(0, 'subdir_renamed')
    assert d1.shortName() == 'subdir_renamed'

    # delete subdir
    d1.delete()
    dw.rebuildTree()
    assert dw.topLevelItemCount() == 1



