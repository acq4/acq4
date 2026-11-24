"""The imaging half of a cell producer: move to a tile, find its surface, acquire
a stack over the constrained depth range, and return its scored detections."""

from __future__ import annotations

import os
import time
from typing import Callable

from coorx import AffineTransform, SRT3DTransform

from acq4.experiment.survey_record import (
    DETECTIONS_SUFFIX,
    Detection,
    TileDetections,
    tileSaveTarget,
)
from acq4.logging_config import get_logger
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
    preset: str | None = None,
) -> Callable:
    """Build the detector seam `Slice.makeCellProducer()` needs.

    The callable returns the tile's `Detection`s (as `TileDetections`, which
    carries the tile's record header); it builds no cells and seeds no trackers.

    `camera`, `scope` and `pipette` must be resolved on the GUI thread and passed
    in; the returned callable runs on the orchestrator's worker thread, where
    reading a device selector widget is not safe.

    `slice_dir` is the slice's own managed directory, and is where each tile's
    detection z-stack and cellpose label mask are written -- see
    `tileSaveTarget`. It is optional in the same way `pipette` is: a slice
    with no directory of its own surveys exactly as well and simply keeps no
    imagery, and a slice whose directory cannot be written to does the same.
    Nothing about saving is allowed to end a survey, because the tissue under
    the objective is not going to wait for the disk.

    `pipette` is the manipulator whose tip has to be out of the way before the
    objective travels to a tile, and is optional: a rig with no pipette selected
    surveys perfectly well and simply has nothing to move. It is the manipulator
    rather than the PatchPipette above it because `goHome` is the manipulator's,
    and it returns the motion planner's future for the caller to wait on.

    `preset` names the microscope imaging preset loaded before each tile, so a
    survey never images under whatever a protocol left loaded (e.g. a
    fluorescence cellfie preset). None or empty loads nothing.

    Surface is found per tile rather than once per slice, so the searched slab
    follows uneven tissue -- that is the whole reason the depth range is
    expressed as offsets from the surface instead of absolute stage z.
    """

    if preset and preset not in scope.presets:
        raise ValueError(
            f"Survey preset {preset!r} is not configured on {scope.name()} "
            f"(available: {', '.join(sorted(scope.presets)) or 'none'})"
        )

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
        if preset:
            scope.loadPreset(preset)
            check_stop()
        logger.info("Surveying tile at %r", center)
        # The planner certifies moves against 3D positions, so the tile's XY is
        # extended with the scope's current z (the surface search sets depth next).
        target = (center[0], center[1], scope.globalPosition()[2])
        scope.setGlobalPosition(target, name="autopatch survey move").wait()

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
        tile_dir, base_name = tileSaveTarget(slice_dir)
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
        tile_id = None
        if save_prefix is not None:
            stack_landed, tile_id = _index_tile_files(
                tile_dir, base_name, center, _stack_transform(stack, step_z)
            )
            if not stack_landed:
                # detect_neurons logs and swallows a save it could not make, so the
                # detections can arrive with the prefix's files absent. Dropping the
                # prefix here is what stops the tile header recording a pointer to a
                # stack that does not exist.
                save_prefix = None
        detections = [
            Detection(
                position=tuple(float(position[i]) for i in range(3)),
                score=score,
                volume=volume,
                area=measured[0] if measured else None,
            )
            for position, score, volume, *measured in results
        ]
        header = {
            "tile_id": tile_id,
            "detection_prefix": save_prefix,
            "tile_center": [float(center[0]), float(center[1])],
            "surface_depth": float(surface),
            "z_bounds": [float(start_z), float(stop_z)],
            "detection_models": {
                name: None if path is None else str(path) for name, path in models.items()
            },
            "detected_at": time.time(),
            "constraints": {
                "min_health": float(constraints.min_health),
                "min_cell_spacing": float(constraints.min_cell_spacing),
                "depth_range": [float(z) for z in constraints.depth_range],
                "rescans_allowed": bool(constraints.rescans_allowed),
                "min_volume_m3": float(min_volume_m3),
                "step_z": float(step_z),
            },
        }
        recordName = None if tile_dir is None else f"{base_name}{DETECTIONS_SUFFIX}"
        return TileDetections(detections, header, tile_dir, recordName)

    return detect


def _stack_transform(stack, z_scale):
    """The transform from this stack's (x, y, z) voxel index to global coordinates.

    Built the way acq4_automation's detect_neurons builds the one it maps
    detections through, so a saved stack and the cells found in it agree.
    tools/autopatch_validation/tile_transforms.py compares this against the
    transform the detector writes into the stack file, which is what catches
    the two drifting apart. Copied first because detect_neurons' own version
    rescales the frame's transform in place.
    """
    transform = stack[0].globalTransform()
    if isinstance(transform, AffineTransform):
        srt = SRT3DTransform()
        srt.set_from_affine(transform)
        transform = srt
    else:
        transform = transform.copy()
    scale = transform.scale
    transform.scale = (scale[0], scale[1], z_scale)
    return transform


def _index_tile_files(tile_dir, base_name, center, transform) -> tuple[bool, str | None]:
    """Index whichever of this tile's files were written, and report whether the
    z-stack was one of them and, if it was indexed, its uuid.

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
    the detector see there". The stack's transform goes on too, so a saved tile
    can be placed in global coordinates without reopening it.

    The returned `stack_landed` being False, for a missing z-stack, is what tells the caller not to record
    a detection prefix on this tile's record. A file that exists but could not be
    indexed still counts as landed: it is on disk and the prefix names it
    correctly, and the index is a convenience on top of that. Such a stack has
    no uuid, so the tile id is None for it.
    """
    stack_landed = False
    tile_id = None
    for suffix in (_TILE_STACK_SUFFIX, _TILE_MASK_SUFFIX):
        name = f"{base_name}{suffix}"
        if not os.path.exists(os.path.join(tile_dir.name(), name)):
            continue
        if suffix == _TILE_STACK_SUFFIX:
            stack_landed = True
        try:
            tile_dir.indexFile(
                name,
                info={
                    "tile_center": [float(center[0]), float(center[1])],
                    "transform": transform,
                },
            )
            if suffix == _TILE_STACK_SUFFIX:
                tile_id = tile_dir[name].info()["__uuid__"]
        except Exception:
            logger.warning(
                "Saved the tile file %r but could not index it; it will not "
                "appear in the Data Manager tree.",
                name,
                exc_info=True,
            )
    return stack_landed, tile_id


def _acquire(camera, start_z: float, stop_z: float, step_z: float) -> list:
    """The tile's z-stack.

    ``fallback_to_stepped=False`` is a throughput choice: a tile whose stepped retry runs
    costs roughly what ten tiles cost without one.
    """
    from acq4.util.imaging.sequencer import acquire_z_stack

    return acquire_z_stack(
        camera,
        start_z,
        stop_z,
        step_z,
        fallback_to_stepped=False,
        name="autopatch survey stack",
    )


def _detect(stack, xy_scale, z_scale, models, min_volume_m3, save_prefix=None) -> list:
    """Every (position, score, volume, cross-section) candidate in `stack`, best first.

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

    Imported here, not at module scope: acq4_automation lives in an internal
    repository, and a top-level import would stop every test under
    acq4/experiment from collecting where it is absent.
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
