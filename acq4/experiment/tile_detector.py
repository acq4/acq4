"""The imaging half of a cell producer: move to a tile, find its surface, acquire
a stack over the constrained depth range, and return scored cell candidates."""

from __future__ import annotations

from typing import Callable

from acq4.logging_config import get_logger
from acq4.util.model_config import segmenter_path
from acq4.util.task import check_stop, synch

logger = get_logger(__name__)


def make_tile_detector(
    camera,
    scope,
    manager,
    step_z: float = 1e-6,
    min_volume_m3: float = 0.0,
    max_candidates: int = 5,
) -> Callable:
    """Build the detector seam `Slice.makeCellProducer()` needs.

    `camera` and `scope` must be resolved on the GUI thread and passed in; the
    returned callable runs on the orchestrator's worker thread, where reading a
    device selector widget is not safe.

    Surface is found per tile rather than once per slice, so the searched slab
    follows uneven tissue -- that is the whole reason the depth range is
    expressed as offsets from the surface instead of absolute stage z.
    """

    def detect(center, constraints) -> list:
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
        results = _detect(
            stack,
            xy_scale=camera.getPixelSize()[0],
            z_scale=step_z,
            models=_health_models(manager),
            min_volume_m3=min_volume_m3,
            max_candidates=max_candidates,
        )
        logger.info("Tile at %r yielded %d candidates", center, len(results))
        return _build_cells(camera, stack, results, segmenter_path(manager))

    return detect


def _build_cells(camera, stack, results, segmenter=None) -> list:
    """Cells for each (position, score) detection, tracking seeded from `stack`.

    *segmenter* is the cellpose checkpoint tracking should segment with, so a
    tracked cell is found by the same model that detected it.
    """
    cells = []
    for position, score in results:
        cell = _newCell(position)
        cell.score = score
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


def _detect(stack, xy_scale, z_scale, models, min_volume_m3, max_candidates) -> list:
    """Scored (position, score) candidates in `stack`. See _newCell on the import."""
    from acq4_automation.object_detection import detect_neurons

    return detect_neurons(
        stack,
        xy_scale=xy_scale,
        z_scale=z_scale,
        trim_edges=True,
        min_volume_m3=min_volume_m3,
        n=max_candidates,
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
