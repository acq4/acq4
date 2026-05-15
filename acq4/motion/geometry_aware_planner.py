# GeometryAwareMotionPlanner: DefaultMotionPlanner variant with full obstacle avoidance.
# Uses convex-hull geometry and path search instead of the heuristic angle-based routing.
from __future__ import annotations

from acq4 import getManager
from acq4.util.future import future_wrap
from .default_planner import (
    DefaultMotionPlanner,
    MOVE_TO_DESTINATION,
    OBSTACLE_AVOIDANCE,
    RETRACTION_TO_AVOID_SAMPLE_TEAR,
    WAYPOINT_TO_AVOID_SAMPLE_TEAR,
)


class GeometryAwareMotionPlanner(DefaultMotionPlanner):
    """DefaultMotionPlanner variant that uses full geometric obstacle avoidance for pipette paths.

    Primes a convex-hull obstacle cache on first use per pipette via the Visualize3D module.
    All other planning behaviour (interaction sites, scope parking, etc.) is inherited.

    Configure via MotionPlanner.class in the ACQ4 config file:
        MotionPlanner:
            class: acq4.motion.GeometryAwareMotionPlanner
    """

    def __init__(self, config=None):
        super().__init__(config)
        self._cache_primers: dict[str, object] = {}  # pip.name() -> Future

    def _safe_path(self, pip, globalStart, globalStop, speed, explanation=None):
        pip_name = pip.name()
        if pip_name not in self._cache_primers:
            self._cache_primers[pip_name] = self._prime_caches(pip)
        self._cache_primers[pip_name].wait()

        boundaries = pip.getBoundaries()
        surface = pip.scopeDevice().getSurfaceDepth()
        boundaries += [Plane((0, 0, 1), (0, 0, surface), "sample surface")]
        prepend_path = append_path = []
        explanation = explanation or MOVE_TO_DESTINATION

        initial_waypoint = self._plan_around_surface(pip, globalStart)
        if initial_waypoint is not None:
            prepend_path = [(initial_waypoint, "slow", False, RETRACTION_TO_AVOID_SAMPLE_TEAR)]
            globalStart = initial_waypoint
        final_waypoint = self._plan_around_surface(pip, globalStop)
        if final_waypoint is not None:
            append_path = [(globalStop, "slow", False, explanation)]
            explanation = WAYPOINT_TO_AVOID_SAMPLE_TEAR
            globalStop = final_waypoint

        win = getManager().getOrLoadModule("Visualize3D").window()
        viz = win.findAdapter(lambda a: a.device == pip).pathSearchVisualizer()
        geo_planner, from_pip_to_global = self._get_planning_context(pip)
        try:
            path = geo_planner.find_path(
                pip.getGeometry(),
                from_pip_to_global,
                globalStart,
                globalStop,
                boundaries,
                visualizer=viz,
            )
        except Exception as e:
            viz.focus()
            raise ValueError(f"Move '{explanation}' could not be planned: {e}") from e
        if len(path) == 0:
            path = [(globalStop, speed, False, explanation)]
        else:
            path = [(wp, speed, False, OBSTACLE_AVOIDANCE) for wp in path]
            goal = path.pop()
            path += [(goal[0], speed, False, explanation)]
        path = prepend_path + path + append_path
        if viz:
            viz.endPath([globalStart] + [p[0] for p in path])
        return path

    def _plan_around_surface(self, pip, pos):
        surface = pip.approachDepth()
        if pos[2] >= surface:
            return None
        return pip.positionAtDepth(surface, start=pos)

    def _get_planning_context(self, pip):
        man = getManager()
        geometries = {}
        for dev_name in man.listInterfaces("OptomechDevice"):
            dev = man.getDevice(dev_name)
            if dev == pip:
                continue
            geom = dev.getGeometry()
            if geom is not None:
                pg_xform = dev.globalPhysicalTransform().as_pyqtgraph()
                physical_xform = SRT3DTransform.from_pyqtgraph(
                    pg_xform, from_cs=dev.geometryCacheKey, to_cs="global"
                )
                geometries[geom] = physical_xform
        geo_planner = GeometryMotionPlanner(geometries)
        pg_xform = pip.globalPhysicalTransform().as_pyqtgraph()
        from_pip_to_global = SRT3DTransform.from_pyqtgraph(
            pg_xform, from_cs=pip.geometryCacheKey, to_cs="global"
        )
        return geo_planner, from_pip_to_global

    @future_wrap
    def _prime_caches(self, pip, _future):
        try:
            man = getManager()
            while not man.isReady.wait(0.05):
                _future.checkStop()
            mod = man.getOrLoadModule("Visualize3D")
            while not mod.isReady.wait(0.05):
                _future.checkStop()
            viz = mod.window().findAdapter(lambda a: a.device == pip).pathSearchVisualizer()
            geo_planner, from_pip_to_global = self._get_planning_context(pip)
            geo_planner.make_convolved_obstacles(pip.getGeometry(), from_pip_to_global, viz)
            pip.logger.info("Finished priming path finding cache")
        except RuntimeError:
            pip.logger.exception("Blew up while attempting to prime path finding cache")
