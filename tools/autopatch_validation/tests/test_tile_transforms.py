"""Tests for the tile-transform check, on synthetic tiles cut from one textured
scene so the right answer is known."""

import os
import sys

import numpy as np
import pytest
from coorx import SRT3DTransform
from MetaArray import MetaArray
from scipy.ndimage import gaussian_filter

import acq4.util.DataManager as dm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tile_transforms as tt  # noqa: E402

PIXEL = 1e-6
TILE = 64


def _scene():
    rng = np.random.default_rng(0)
    return gaussian_filter(rng.random((200, 200)), 2)


def _saveTile(tiles, name, scene, col, row, claimedCol=None):
    """Cut a TILE-square stack at (col, row) and claim it sits at claimedCol."""
    image = scene[row:row + TILE, col:col + TILE]
    data = np.stack([image, image])  # (z, y, x)
    claimed = col if claimedCol is None else claimedCol
    transform = SRT3DTransform(scale=(PIXEL, PIXEL, 1e-6), offset=(claimed * PIXEL, row * PIXEL, 0.0),
                               from_cs="frame", to_cs="global")
    MetaArray(data, info=[{"name": "z"}, {"name": "y"}, {"name": "x"},
                          {"transform": transform.save_state()}]).write(os.path.join(tiles.name(), name))
    tiles.indexFile(name, info={"transform": transform})


def _makeSlice(path, claimedCol=None):
    root = dm.getDirHandle(str(path), create=True)
    tiles = root.mkdir("tiles")
    scene = _scene()
    _saveTile(tiles, "tile_a.ma", scene, 20, 20)
    _saveTile(tiles, "tile_b.ma", scene, 44, 20, claimedCol=claimedCol)
    return root.name()


@pytest.fixture
def sliceDir(tmp_path):
    return _makeSlice(tmp_path)


def test_tiles_load_with_both_transforms(sliceDir):
    tiles = tt.loadTiles(sliceDir)
    assert [t.name for t in tiles] == ["tile_a.ma", "tile_b.ma"]
    assert all(t.data.shape == (2, TILE, TILE) for t in tiles)
    assert all(tt.transformDisagreement(t) == pytest.approx(0.0, abs=1e-12) for t in tiles)


def test_correct_transforms_overlap_with_no_shift(sliceDir):
    layers, _extent = tt.mosaicLayers(tt.loadTiles(sliceDir), PIXEL)
    [(i, j, shift)] = tt.overlapShifts(layers)
    assert (i, j) == (0, 1)
    assert shift == pytest.approx((0.0, 0.0), abs=0.5)


def test_a_wrong_transform_shows_up_as_a_shift(tmp_path):
    layers, _extent = tt.mosaicLayers(tt.loadTiles(_makeSlice(tmp_path, claimedCol=49)), PIXEL)
    [(_i, _j, shift)] = tt.overlapShifts(layers)
    assert abs(shift[1]) == pytest.approx(5.0, abs=0.5)


def test_the_mosaic_plot_is_written(sliceDir, tmp_path):
    tiles = tt.loadTiles(sliceDir)
    layers, extent = tt.mosaicLayers(tiles, PIXEL)
    out = tmp_path / "mosaic.png"
    tt.plotMosaic(layers, extent, tiles, [{"position": [50e-6, 50e-6, 0.0]}], str(out))
    assert out.stat().st_size > 0


def test_main_passes_on_correct_transforms(sliceDir, tmp_path, capsys):
    out = tmp_path / "ok.png"
    assert tt.main([sliceDir, "--out", str(out)]) == 0
    assert out.stat().st_size > 0
    assert "2 tiles" in capsys.readouterr().out


def test_main_fails_on_a_wrong_transform(tmp_path, capsys):
    sliceDir = _makeSlice(tmp_path / "slice", claimedCol=49)
    assert tt.main([sliceDir, "--out", str(tmp_path / "bad.png")]) == 1
    assert "overlap shift" in capsys.readouterr().out


def test_main_rejects_a_non_directory(tmp_path, capsys):
    assert tt.main([str(tmp_path / "nope")]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_main_rejects_a_slice_without_tiles(tmp_path, capsys):
    assert tt.main([str(tmp_path)]) == 2
    assert "tiles" in capsys.readouterr().err
