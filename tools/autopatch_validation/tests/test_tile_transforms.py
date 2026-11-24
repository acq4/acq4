"""Tests for the tile-transform check, on synthetic tiles cut from one textured
scene so the right answer is known."""

import os
import sys

import numpy as np
import pytest
from coorx import SRT3DTransform
from MetaArray import MetaArray
from scipy.ndimage import gaussian_filter, map_coordinates

import acq4.util.DataManager as dm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tile_transforms as tt  # noqa: E402

PIXEL = 1e-6
TILE = 64


def _scene():
    rng = np.random.default_rng(0)
    return gaussian_filter(rng.random((200, 200)), 2)


def _saveTile(tiles, name, scene, col, row, claimedCol=None, dtype=float):
    """Cut a TILE-square stack at (col, row) and claim it sits at claimedCol."""
    image = scene[row:row + TILE, col:col + TILE]
    if np.issubdtype(dtype, np.integer):
        image = image / scene.max() * 60000
    data = np.stack([image, image]).astype(dtype)  # (z, y, x)
    claimed = col if claimedCol is None else claimedCol
    transform = SRT3DTransform(scale=(PIXEL, PIXEL, 1e-6), offset=(claimed * PIXEL, row * PIXEL, 0.0),
                               from_cs="frame", to_cs="global")
    MetaArray(data, info=[{"name": "z"}, {"name": "y"}, {"name": "x"},
                          {"transform": transform.save_state()}]).write(os.path.join(tiles.name(), name))
    tiles.indexFile(name, info={"transform": transform})


def _makeSlice(path, claimedCol=None, dtype=float):
    root = dm.getDirHandle(str(path), create=True)
    tiles = root.mkdir("tiles")
    scene = _scene()
    _saveTile(tiles, "tile_a.ma", scene, 20, 20, dtype=dtype)
    _saveTile(tiles, "tile_b.ma", scene, 44, 20, claimedCol=claimedCol, dtype=dtype)
    return root.name()


def _saveRotatedTile(tiles, name, scene, transform, claimed):
    """Sample the scene through `transform`, then record `claimed` as the tile's transform."""
    pixels = np.array([(x, y, 0) for y in range(TILE) for x in range(TILE)], dtype=float)
    world = transform.map(pixels) / PIXEL
    image = map_coordinates(scene, [world[:, 1], world[:, 0]], order=1).reshape(TILE, TILE)
    MetaArray(np.stack([image, image]), info=[{"name": "z"}, {"name": "y"}, {"name": "x"},
                                              {"transform": claimed.save_state()}]
              ).write(os.path.join(tiles.name(), name))
    tiles.indexFile(name, info={"transform": claimed})


def _makeRotatedSlice(path, wrongPixels=0):
    root = dm.getDirHandle(str(path), create=True)
    tiles = root.mkdir("tiles")
    scene = gaussian_filter(np.random.default_rng(1).random((400, 400)), 2)
    kwds = dict(scale=(PIXEL, PIXEL, 1e-6), angle=10, axis=(0, 0, 1), from_cs="frame", to_cs="global")
    a = SRT3DTransform(offset=(150e-6, 100e-6, 0.0), **kwds)
    for name, shift, claimedShift in (("tile_a.ma", 0, 0), ("tile_b.ma", 24, 24 + wrongPixels)):
        truth = SRT3DTransform(offset=a.map([[shift, 0, 0]])[0], **kwds)
        claimed = SRT3DTransform(offset=a.map([[claimedShift, 0, 0]])[0], **kwds)
        _saveRotatedTile(tiles, name, scene, truth, claimed)
    return root.name()


@pytest.fixture
def sliceDir(tmp_path):
    return _makeSlice(tmp_path)


def test_tiles_load_with_both_transforms(sliceDir):
    tiles = tt.loadTiles(sliceDir)
    assert [t.name for t in tiles] == ["tile_a.ma", "tile_b.ma"]
    assert all(t.shape == (2, TILE, TILE) for t in tiles)
    assert all(tt.transformDisagreement(t) == pytest.approx(0.0, abs=1e-12) for t in tiles)


def test_correct_transforms_overlap_with_no_shift(sliceDir):
    layers, _extent = tt.mosaicLayers(tt.loadTiles(sliceDir), PIXEL)
    [(i, j, shift)] = tt.overlapShifts(layers)
    assert (i, j) == (0, 1)
    assert shift == pytest.approx((0.0, 0.0), abs=0.5)


def test_loaded_tiles_keep_only_the_projection(sliceDir):
    [tile, _] = tt.loadTiles(sliceDir)
    assert tile.mip.shape == (TILE, TILE)
    assert tile.shape == (2, TILE, TILE)


def test_layers_cover_only_their_own_tile(sliceDir):
    [(a, (aRow, aCol)), (b, (bRow, bCol))] = tt.mosaicLayers(tt.loadTiles(sliceDir), PIXEL)[0]
    assert a.dtype == b.dtype == np.float32
    assert (aRow, aCol) == (0, 0)
    assert bCol == 24
    assert np.isfinite(a).sum() >= (TILE - 2) ** 2


@pytest.mark.parametrize("claimedCol, expected", [(None, 0.0), (49, 5.0)])
def test_integer_stacks_are_sampled_without_losing_their_edges(tmp_path, claimedCol, expected):
    tiles = tt.loadTiles(_makeSlice(tmp_path, claimedCol=claimedCol, dtype=np.uint16))
    layers, _extent = tt.mosaicLayers(tiles, PIXEL)
    assert all(layer.dtype == np.float32 for layer, _offset in layers)
    [(_i, _j, shift)] = tt.overlapShifts(layers)
    assert abs(shift[1]) == pytest.approx(expected, abs=0.5)


@pytest.mark.parametrize("wrongPixels, expected", [(0, 0.0), (5, 5.0)])
def test_rotated_tiles_register_over_their_slanted_overlap(tmp_path, wrongPixels, expected):
    layers, _extent = tt.mosaicLayers(tt.loadTiles(_makeRotatedSlice(tmp_path, wrongPixels)), PIXEL)
    assert all(np.isnan(layer).any() for layer, _offset in layers)
    [(_i, _j, shift)] = tt.overlapShifts(layers)
    assert np.hypot(*shift) == pytest.approx(expected, abs=0.7)


def test_a_grid_too_large_to_mosaic_is_refused(sliceDir, tmp_path, capsys):
    assert tt.main([sliceDir, "--pixel", "1e-9", "--out", str(tmp_path / "x.png")]) == 2
    assert "--pixel" in capsys.readouterr().err


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
    output = capsys.readouterr().out
    assert "2 tiles" in output
    assert "2.0 px (2.0 µm)" in output


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


def test_main_rejects_a_slice_with_no_transformed_tiles(tmp_path, capsys):
    root = dm.getDirHandle(str(tmp_path), create=True)
    root.mkdir("tiles")
    assert tt.main([root.name()]) == 2
    assert "no tiles" in capsys.readouterr().err


def test_main_fails_when_nothing_overlaps(tmp_path, capsys):
    root = dm.getDirHandle(str(tmp_path), create=True)
    tiles = root.mkdir("tiles")
    scene = _scene()
    _saveTile(tiles, "tile_a.ma", scene, 0, 0)
    _saveTile(tiles, "tile_b.ma", scene, 100, 100)
    assert tt.main([root.name(), "--out", str(tmp_path / "x.png")]) == 1
    assert "no overlaps measured" in capsys.readouterr().out


def test_main_fails_when_index_and_file_transforms_disagree(tmp_path, capsys):
    root = dm.getDirHandle(str(tmp_path), create=True)
    tiles = root.mkdir("tiles")
    scene = _scene()
    _saveTile(tiles, "tile_a.ma", scene, 20, 20)
    _saveTile(tiles, "tile_b.ma", scene, 44, 20)
    moved = SRT3DTransform(scale=(PIXEL, PIXEL, 1e-6), offset=(44e-6 + 1e-6, 20e-6, 0.0),
                           from_cs="frame", to_cs="global")
    tiles.indexFile("tile_b.ma", info={"transform": moved})
    assert tt.main([root.name(), "--out", str(tmp_path / "x.png")]) == 1
    assert "µm apart" in capsys.readouterr().out


def test_a_tile_without_a_file_transform_is_reported_but_passes(tmp_path, capsys):
    root = dm.getDirHandle(str(tmp_path), create=True)
    tiles = root.mkdir("tiles")
    scene = _scene()
    _saveTile(tiles, "tile_a.ma", scene, 20, 20)
    _saveTile(tiles, "tile_b.ma", scene, 44, 20)
    path = os.path.join(tiles.name(), "tile_b.ma")
    os.remove(path)
    image = scene[20:20 + TILE, 44:44 + TILE]
    MetaArray(np.stack([image, image]), info=[{"name": "z"}, {"name": "y"}, {"name": "x"}, {}]).write(path)
    assert tt.main([root.name(), "--out", str(tmp_path / "x.png")]) == 0
    assert "(no file transform)" in capsys.readouterr().out
