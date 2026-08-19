"""The imaging half of a cell producer: move to a tile, find its surface, acquire
a stack over the constrained depth range, and return scored cell candidates."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Callable

from acq4.logging_config import get_logger
from acq4.util.model_config import segmenter_path
from acq4.util.task import check_stop, synch

logger = get_logger(__name__)

# The two files acq4_automation's detector writes when it is given a save
# prefix: the tile's detection z-stack, and the raw integer cellpose label mask
# the health scores were computed from. Their names are spelled out here because
# they are written on the far side of an RPC -- this module has to find them
# again afterwards in order to index them, and has nothing to ask.
#
# The base name they share is load-bearing rather than decorative. The cell
# quality annotation tool identifies a detection session by exactly this: files
# sharing one base name in one directory, the third of them being the operator's
# health ratings, which that tool writes itself if and when a human rates the
# tile. Imagery saved under any other scheme is imagery the annotation corpus
# can never absorb.
_TILE_STACK_SUFFIX = ".ma"
_TILE_MASK_SUFFIX = "_cellpose_masks.npy"


def make_tile_detector(
    camera,
    scope,
    manager,
    pipette=None,
    step_z: float = 1e-6,
    min_volume_m3: float = 0.0,
    slice_dir=None,
) -> Callable:
    """Build the detector seam `Slice.makeCellProducer()` needs.

    `camera`, `scope` and `pipette` must be resolved on the GUI thread and passed
    in; the returned callable runs on the orchestrator's worker thread, where
    reading a device selector widget is not safe.

    `slice_dir` is the slice's own managed directory, and is where each tile's
    detection z-stack and cellpose label mask are written -- see
    `_tile_save_target`. It is optional in the same way `pipette` is: a slice
    with no directory of its own surveys exactly as well and simply keeps no
    imagery, and a slice whose directory cannot be written to does the same.
    Nothing about saving is allowed to end a survey, because the tissue under
    the objective is not going to wait for the disk.

    `pipette` is the manipulator whose tip has to be out of the way before the
    objective travels to a tile, and is optional: a rig with no pipette selected
    surveys perfectly well and simply has nothing to move. It is the manipulator
    rather than the PatchPipette above it because `goHome` is the manipulator's,
    and it returns the motion planner's future for the caller to wait on.

    Surface is found per tile rather than once per slice, so the searched slab
    follows uneven tissue -- that is the whole reason the depth range is
    expressed as offsets from the surface instead of absolute stage z.
    """

    def detect(center, constraints) -> list:
        check_stop()
        if pipette is not None:
            # Out of the way before the objective goes anywhere: the tip is
            # parked wherever it last worked, which is in or just above the
            # tissue this survey is about to move relative to and then image a
            # stack through.
            #
            # Homed on every tile rather than once per survey. Two tiles imaged
            # back to back have nothing between them that moves the pipette, so
            # for those this is a device round trip that changes nothing -- but
            # a refill only happens once the queue has drained, so the ordinary
            # gap between two tiles is a cell being patched and the tip left at
            # that cell's target. Telling those two cases apart would mean this
            # callable second-guessing what the pipette did while it was not
            # looking (an operator jogging it by hand between tiles counts too),
            # and getting that wrong drives the objective at a pipette that is
            # still down. A round trip is the cheaper thing to spend against a
            # tile that is seconds to minutes of imaging either way.
            pipette.goHome("fast").wait()
            # The guard on the far side of that move, in the same place as every
            # other one in here -- immediately before the next slow step. It is
            # inside this branch because it belongs to the home move: with no
            # pipette there is no slow step here to have pressed Stop during.
            check_stop()
        logger.info("Surveying tile at %r", center)
        scope.setGlobalPosition(center, name="autopatch survey move").wait()

        # Captured before the surface search: camera focus tracks scope focus,
        # so a capture taken after `findSurfaceDepth` would be the tile's
        # surface, not the depth the survey started from.
        restore_depth = camera.getFocusDepth()

        check_stop()
        surface = synch(scope.findSurfaceDepth)(camera)
        start_z, stop_z = constraints.z_bounds(surface)

        check_stop()
        try:
            stack = _acquire(camera, start_z, stop_z, step_z)
        finally:
            # Restored on the failure path too: a survey that dies mid-stack
            # must not leave the objective parked deep in the tissue for
            # whatever runs next.
            camera.setFocusDepth(
                restore_depth, name=f"{camera.name()} restore focus after survey stack"
            )

        check_stop()
        models = _health_models(manager)
        tile_dir, base_name = _tile_save_target(slice_dir)
        save_prefix = (
            None if tile_dir is None else os.path.join(tile_dir.name(), base_name)
        )
        results = _detect(
            stack,
            xy_scale=camera.getPixelSize()[0],
            z_scale=step_z,
            models=models,
            min_volume_m3=min_volume_m3,
            save_prefix=save_prefix,
        )
        logger.info("Tile at %r yielded %d candidates", center, len(results))
        if save_prefix is not None and not _index_tile_files(
            tile_dir, base_name, center
        ):
            # detect_neurons logs and swallows a save it could not make, so the
            # cells can arrive with the prefix's files absent. Dropping the
            # prefix here is what stops each of them recording a pointer to a
            # stack that does not exist.
            save_prefix = None
        return _build_cells(
            camera,
            stack,
            results,
            segmenter=segmenter_path(manager),
            models=models,
            tile_center=center,
            detection_prefix=save_prefix,
        )

    return detect


def _tile_save_target(slice_dir):
    """Where this tile's detection stack and mask are to be written: a
    `(directory, base name)` pair, or `(None, None)` when there is nowhere.

    The directory is a `tiles/` subdirectory of the slice's own, so a tile's
    imagery sits beside the Cell directories that tile produced. That placement
    is the whole difference from AutomationDebug's arrangement, which writes the
    same trio into a `cell_annotations/` tree outside the managed hierarchy
    entirely: unindexed, invisible in the Data Manager, and related to the
    experiment it came from only by the clock.

    The base name is timestamped to the microsecond, and is per tile rather than
    per survey because the detector writes two files under it into a directory
    every tile of the run shares. Two tiles under one name is the second tile
    writing over the first tile's stack.

    Nowhere to write is not a failure. A slice with `dirHandle` at None is a run
    the operator started without ever pressing "New slice"; a directory that
    cannot be created is a storage problem the operator will hear about from
    everything else the run does. Neither is a reason to stop imaging tissue.
    """
    if slice_dir is None:
        return None, None
    try:
        tile_dir = slice_dir.getDir("tiles", create=True)
    except Exception:
        logger.warning(
            "Could not open a tiles directory under %r; this tile's detection "
            "stack and cellpose masks will not be saved.",
            slice_dir,
            exc_info=True,
        )
        return None, None
    return tile_dir, datetime.now().strftime("tile_%Y%m%d_%H%M%S_%f")


def _index_tile_files(tile_dir, base_name, center) -> bool:
    """Index whichever of this tile's files were written, and report whether the
    z-stack was one of them.

    They are written by raw path, from inside the teleprox subprocess that runs
    the detector -- which has no DirHandle to write through and could not be
    given one. Nothing has therefore told the Data Manager the files exist, and
    an unindexed file does not appear in its tree at all. Indexing them after
    the fact is what closes that gap.

    Doing it this way round, rather than re-saving the stack through
    `writeFile` on this side, is not merely the lazier option: the cellpose
    label mask never crosses the RPC boundary (`detect_neurons` returns
    centroids and volumes, not masks), so the subprocess is the only place it
    can be written from at all. Splitting the pair across two mechanisms would
    also split the shared base name the annotation tool reloads by.

    The tile's centre goes onto each file's index entry because the names carry
    nothing but a timestamp, and a coordinate is how an operator asks "what did
    the detector see there".

    Reporting False for a missing z-stack is what tells the caller not to record
    a detection prefix on this tile's cells. A file that exists but could not be
    indexed still counts as landed: it is on disk and the prefix names it
    correctly, and the index is a convenience on top of that.
    """
    stack_landed = False
    for suffix in (_TILE_STACK_SUFFIX, _TILE_MASK_SUFFIX):
        name = f"{base_name}{suffix}"
        if not os.path.exists(os.path.join(tile_dir.name(), name)):
            continue
        if suffix == _TILE_STACK_SUFFIX:
            stack_landed = True
        try:
            tile_dir.indexFile(
                name, info={"tile_center": [float(center[0]), float(center[1])]}
            )
        except Exception:
            logger.warning(
                "Saved the tile file %r but could not index it; it will not "
                "appear in the Data Manager tree.",
                name,
                exc_info=True,
            )
    return stack_landed


def _build_cells(
    camera,
    stack,
    results,
    segmenter=None,
    models=None,
    tile_center=None,
    detection_prefix=None,
) -> list:
    """Cells for each (position, score, volume) detection, tracking seeded from `stack`.

    *segmenter* is the cellpose checkpoint tracking should segment with, so a
    tracked cell is found by the same model that detected it.

    The last three arguments are the cell's provenance, and they are attached to
    each cell rather than kept here because that is the only way they reach the
    Cell directory: the orchestrator makes that directory from the cell alone,
    long after this tile has been forgotten. `models` is the set of checkpoints
    that produced the score, `tile_center` is where the objective was, and
    `detection_prefix` names the stack and mask on disk. None of the three is
    declared on Cell -- the same arrangement `volume` has always had -- so every
    reader of them has to use getattr with a default, since a cell the operator
    seeded by hand has none of them.
    """
    cells = []
    for position, score, volume in results:
        cell = _newCell(position)
        cell.score = score
        cell.volume = volume
        cell.tile_center = None if tile_center is None else tuple(tile_center)
        cell.detection_prefix = detection_prefix
        cell.detection_models = dict(models or {})
        try:
            # Seeded from the stack the cell was found in, so tracking is ready
            # without re-acquiring a stack per cell.
            cell.initializeTrackerFromStack(
                camera, stack, use_cellpose=True, segmenter=segmenter
            )
        except Exception:
            # A cell too close to the stack edge cannot be extracted, but it is
            # still a real detection: queue it rather than silently dropping
            # every cell near a tile boundary.
            logger.warning(
                "Could not initialize tracking for the cell detected at %r",
                position,
                exc_info=True,
            )
        cells.append(cell)
    return cells


def _newCell(position):
    """A Cell at `position`, which `_detect` already returns as a global coorx Point.

    Imported here, not at module scope: acq4_automation lives in an internal
    repository, and a top-level import would stop every test under
    acq4/experiment from collecting where it is absent.
    """
    from acq4_automation.feature_tracking.cell import Cell

    return Cell(position)


def _acquire(camera, start_z: float, stop_z: float, step_z: float) -> list:
    """The tile's z-stack."""
    from acq4.util.imaging.sequencer import acquire_z_stack

    return acquire_z_stack(
        camera,
        start_z,
        stop_z,
        step_z,
        slow_fallback=False,
        name="autopatch survey stack",
    )


def _detect(stack, xy_scale, z_scale, models, min_volume_m3, save_prefix=None) -> list:
    """Every (position, score, volume) candidate in `stack`, best first.

    `save_prefix` is what makes the detector keep the stack it was given and the
    cellpose mask it derived; without one, both are destroyed as soon as the
    candidates have been extracted from them, which for a survey means every
    tile's imagery is discarded the moment its cells exist.

    `n=None` asks for all of them rather than the handful that will be queued,
    and that is deliberate: `n` slices a list already ordered best-first, so
    truncating here would happen before CellProducer has dropped the cells
    outside the slice's regions or below its health cutoff. A tile at a region's
    edge is where those discards cluster -- the field of view straddles the
    outline on purpose, since that context is what lets the segmenter find cells
    sitting right at it -- so a cap out here would routinely be spent entirely
    on cells nothing will patch, leaving the tile looking barren. The cap that
    matters is on what gets queued, and it lives with the producer that queues.

    See _newCell on the import.
    """
    from acq4_automation.object_detection import detect_neurons

    return detect_neurons(
        stack,
        xy_scale=xy_scale,
        z_scale=z_scale,
        trim_edges=True,
        min_volume_m3=min_volume_m3,
        n=None,
        save_prefix=save_prefix,
        **models,
    )


def _health_models(manager) -> dict:
    """The configured detection/classification model paths from global `misc` config.

    The same keys AutomationDebug reads, so a rig configured for the debug
    bench needs no extra configuration to run a survey.
    """
    misc = manager.config.get("misc", {}) if manager is not None else {}
    return {
        "segmenter": misc.get("segmenterPath", None),
        "autoencoder": misc.get("autoencoderPath", None),
        "classifier": misc.get("classifierPath", None),
        "resnet_classifier": misc.get("resnetClassifierPath", None),
    }
