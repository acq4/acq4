import pyqtgraph as pg
import pytest

from acq4.util import Qt
from acq4.util.Canvas import Canvas
from acq4.util.Canvas.items.MarkersCanvasItem import MarkersCanvasItem


@pytest.fixture
def markers():
    pg.mkQApp()
    item = MarkersCanvasItem()
    yield item
    item._markerCtrl.close()


@pytest.mark.parametrize('attached', [False, True])
def test_remove_marker_detaches_its_target(markers, attached):
    scene = Qt.QGraphicsScene()
    if attached:
        scene.addItem(markers.graphicsItem())
    markers.addMarker('cell', (1, 2, 3))
    target = markers.params.child('cell').target

    markers.removeMarker('cell')

    assert markers.params.children() == []
    assert target.parentItem() is None
    assert target.scene() is None
    assert target not in scene.items()


def test_parameter_tree_removal_detaches_target(markers):
    scene = Qt.QGraphicsScene()
    scene.addItem(markers.graphicsItem())
    markers.addMarker('cell', (1, 2, 3))
    param = markers.params.child('cell')
    target = param.target

    param.remove()

    assert markers.params.children() == []
    assert target.parentItem() is None
    assert target.scene() is None
    assert target not in scene.items()


def test_restore_replaces_existing_marker_targets(markers, request):
    canvas = Canvas()
    request.addfinalizer(canvas.close)
    canvas.addItem(markers)
    scene = markers.graphicsItem().scene()
    markers.addMarker('old', (1, 2, 3))
    old_target = markers.params.child('old').target
    state = markers.saveState()
    state['markers'] = [('new', (4, 5, 6))]

    markers.restoreState(state)

    assert [param.name() for param in markers.params.children()] == ['new']
    new_marker = markers.params.child('new')
    assert new_marker['Position'] == (4, 5, 6)
    assert new_marker.target.pos() == Qt.QPointF(4, 5)
    assert new_marker.target.scene() is scene
    assert old_target.parentItem() is None
    assert old_target.scene() is None
