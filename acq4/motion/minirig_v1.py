# MinirigV1MotionPlanner: extends DefaultMotionPlanner with microscope parking for cleaning wells.
from __future__ import annotations

import threading

import numpy as np

from acq4 import getManager
from .default_planner import DefaultMotionPlanner
from .plan import AtomicMove, SequentialGroup
from .plan import MovePlanStep
from .planner import PlanningError
from .spec import MoveSpec

#: How close counts as "at" park height or at a well approach pose (m). Config key:
#: ``parkTransitTolerance``.
PARK_TRANSIT_TOLERANCE = 1e-3

#: What the operator may choose when the stage sits off the recorded way back.  These become
#: buttons in that order, safest first: the unchecked one should not be the easiest to hit.
REPOSITION_AND_CONTINUE = "I repositioned it; continue"
REPOSITION_AND_DISCARD = "I repositioned it; forget the way back"
MOVE_ANYWAY = "Move anyway, unchecked"


def _operator_can_be_asked() -> bool:
    """False when nothing is running a UI, so there is nobody to hand a refusal to."""
    from acq4.util import Qt

    return Qt.QApplication.instance() is not None


class MinirigV1MotionPlanner(DefaultMotionPlanner):
    """Motion planner for the v1 minirig rig.

    Extends DefaultMotionPlanner with "microscope parking": when approaching an InteractionSite
    that has a scopeParkPos in its config, the scope is moved out of the way before the pipette
    approaches.  The sequence is:

        1. Scope up (z-only, to park height) — scope clears objective before any lateral
           move.  Skipped when the stage already sits at a well approach pose, where
           climbing first is unsafe and step 3 runs as a single diagonal instead.
        2. Pipette retract to approach depth — pip exits tissue before scope moves laterally
        3. Scope to park position (lateral, or diagonal when step 1 was skipped)
        4. Site stage to approach position (if the site is on a movable stage)
        5. Pipette to site approach position

    The reverse sequence runs when the pipette subsequently exits via any pipette move or
    interaction exit.  It also runs when the site's stage (or any child of that stage) is
    moved: any pipette docked in a mobile site on that stage is first safely extracted, then
    the scope is unwound, before the requested stage move proceeds.

    Configure via MotionPlanner.class in the ACQ4 config file:
        MotionPlanner:
            class: "acq4.motion.MinirigV1MotionPlanner"
    """

    def __init__(self, config=None):
        super().__init__(config)
        # key: pip.name() -> (scope_device, [original_pos, up_pos, park_pos], pip, site)
        # forward_path is in forward order; pip and site identify what must be unwound/extracted
        # when the site's stage (or a child of it) later moves.
        self._scope_context: dict[str, tuple] = {}
        # Per-instance thread-local storage for the context snapshot taken at the start of
        # plan().  Each execute() call runs on its own thread, so this is safe against
        # concurrent calls on the same planner instance.
        self._plan_context_tls = threading.local()
        self._transit_tolerance = float(
            (config or {}).get("parkTransitTolerance", PARK_TRANSIT_TOLERANCE)
        )

    # ------------------------------------------------------------------
    # Snapshot scope context before planning so it can be restored on lock failure
    # ------------------------------------------------------------------

    def plan(self, specs, name=""):
        # Snapshot before any pops so _on_lock_failure can restore if we never get the lock.
        self._plan_context_tls.snapshot = dict(self._scope_context)
        try:
            return super().plan(specs, name=name)
        except Exception:
            # planner.plan() is called outside execute()'s try, so a refusal here reaches
            # no rollback hook. A plan that raised moved nothing, so anything it recorded
            # about a parked scope describes a park that never happened.
            snapshot = self._plan_context_tls.snapshot
            for pip_name in [k for k in self._scope_context if k not in snapshot]:
                del self._scope_context[pip_name]
            for pip_name, ctx_val in snapshot.items():
                self._scope_context.setdefault(pip_name, ctx_val)
            raise

    def _on_lock_failure(self, plan) -> None:
        # _scope_unwind_group pops _scope_context during plan(), before device locks are
        # acquired.  If reserveDevices() times out the unwind never runs, but the context
        # is already gone — so the scope stays parked with no record.  The next approach
        # then captures the parked position as original_pos, and future unwinds return the
        # scope to the park position instead of home.  Restoring here breaks that cycle.
        snapshot = getattr(self._plan_context_tls, 'snapshot', {})
        for pip_name, ctx_val in snapshot.items():
            self._scope_context.setdefault(pip_name, ctx_val)

    # ------------------------------------------------------------------
    # Certifying stage motion without collision detection
    # ------------------------------------------------------------------
    # This planner cannot prove an arbitrary stage path is clear, so it only drives to park
    # along the two routes the rig owner vouched for: one starting at or above park height,
    # and one starting at a saved well approach pose.  Anything else is refused.  A refusal
    # never strands anyone: the dial and joystick controls drive the stage through
    # DirectMotionController, which bypasses the planner entirely.

    def _near(self, pos, candidates) -> bool:
        pos = np.asarray(pos, dtype=float)
        return any(
            np.linalg.norm(pos - np.asarray(c, dtype=float)) <= self._transit_tolerance
            for c in candidates
        )

    def _carrying_stage(self, moving):
        """The well-bearing stage *moving* rides on, or None.

        Resolving this first is what lets the scope and the wells be compared at all: they
        are siblings under the stage, not ancestors of one another.
        """
        for site in self._interaction_sites():
            stage = getattr(site, "_parentStage", None)
            if stage is not None and self._device_in_stage_subtree(moving, stage):
                return stage
        return None

    def _at_a_well_approach_pose(self, moving) -> bool:
        """True when a site riding with *moving* sits at one of its saved approach positions.

        Everything on the stage shifts by one global vector, so "the stage is at a well's
        approach pose" and "that well is at its approach position" are the same statement.
        The second needs no frame conversion, so it is the one tested.
        """
        for site in self._interaction_sites():
            stage = getattr(site, "_parentStage", None)
            if stage is None or not self._device_in_stage_subtree(moving, stage):
                continue
            here = np.asarray(site.globalPosition(), dtype=float)
            for saved in site.positions.values():
                approach = saved.get("site global")
                if approach is not None and self._near(approach, [here]):
                    return True
        return False

    def _well_poses_for(self, moving) -> list:
        """Poses of *moving* that put a site it carries at one of that site's approaches."""
        now = np.asarray(moving.globalPosition(), dtype=float)
        poses = []
        for site in self._interaction_sites():
            stage = getattr(site, "_parentStage", None)
            if stage is None or not self._device_in_stage_subtree(moving, stage):
                continue
            here = np.asarray(site.globalPosition(), dtype=float)
            for saved in site.positions.values():
                approach = saved.get("site global")
                if approach is not None:
                    poses.append(now + (np.asarray(approach, dtype=float) - here))
        return poses

    def _unwind_poses_for(self, moving, scope) -> list:
        """Poses of *moving* that put *scope* on a node of a recorded way back."""
        now = np.asarray(moving.globalPosition(), dtype=float)
        scope_now = np.asarray(scope.globalPosition(), dtype=float)
        return [
            now + (np.asarray(node, dtype=float) - scope_now)
            for ctx_scope, forward_path, _pip, _site in self._scope_context.values()
            if ctx_scope is scope
            for node in forward_path
        ]

    def _park_position_targeted(self, moving, target, scope):
        """The configured park position *target* would put *scope* at, or None."""
        now = np.asarray(moving.globalPosition(), dtype=float)
        scope_now = np.asarray(scope.globalPosition(), dtype=float)
        for site in self._interaction_sites():
            park = site.config.get("scopeParkPos")
            if park is None:
                continue
            park = np.asarray(park, dtype=float)
            if self._near(target, [now + (park - scope_now)]):
                return park
        return None

    def _park_poses_for(self, moving, scope) -> list:
        """Poses of *moving* that put *scope* at some site's configured park position."""
        now = np.asarray(moving.globalPosition(), dtype=float)
        scope_now = np.asarray(scope.globalPosition(), dtype=float)
        poses = []
        for site in self._interaction_sites():
            park = site.config.get("scopeParkPos")
            if park is not None:
                poses.append(now + (np.asarray(park, dtype=float) - scope_now))
        return poses

    def _scope_for_stage(self, moving):
        """A scope riding on *moving*, or None.

        Park positions are scope positions, so without a scope there is no way to tell
        whether a given stage target is a park position.
        """
        carrier = self._carrying_stage(moving) or moving
        for ctx in self._scope_context.values():
            if self._device_in_stage_subtree(ctx[0], carrier):
                return ctx[0]
        try:
            man = getManager()
        except Exception:
            return None
        for pip_name in man.listInterfaces("pipette"):
            try:
                scope = man.getDevice(pip_name).scopeDevice()
            except Exception:
                continue
            if scope is not None and self._device_in_stage_subtree(scope, carrier):
                return scope
        return None

    def _certify_move_to_park(self, scope, park_pos, moving) -> None:
        """Raise PlanningError unless a direct run to *park_pos* is safe from here."""
        scope_now = np.asarray(scope.globalPosition(), dtype=float)
        park_pos = np.asarray(park_pos, dtype=float)
        if scope_now[2] >= park_pos[2] - self._transit_tolerance:
            return
        if moving is not None and self._at_a_well_approach_pose(moving):
            return
        raise PlanningError(
            f"Refusing to drive {scope.name()} from "
            f"{np.round(scope_now * 1e3, 3)} mm straight to its park position "
            f"{np.round(park_pos * 1e3, 3)} mm: that path is not one this planner can "
            f"vouch for. Raise the objective to at least {park_pos[2] * 1e3:.3f} mm, or "
            f"bring the stage to a saved well approach position, and try again. The dials "
            f"move the stage without the planner."
        )

    def _certify_stage_target(self, moving, target) -> None:
        """The three hub rules: leaving a well, leaving park, and arriving at park."""
        scope = self._scope_for_stage(moving)
        if self._at_a_well_approach_pose(moving):
            self._certify_leaving_a_well(moving, target, scope)
        elif scope is None:
            return  # park is a scope position, so without one no rule here has anything to say
        elif self._near(moving.globalPosition(), self._park_poses_for(moving, scope)):
            self._certify_leaving_park(moving, target, scope)
        else:
            self._certify_reaching_park(moving, target, scope)

    def _certify_leaving_a_well(self, moving, target, scope) -> None:
        """While a well sits at its approach pose, park is the only place the stage may go."""
        if scope is not None and self._near(target, self._park_poses_for(moving, scope)):
            return
        raise PlanningError(
            f"{moving.name()} is at a well approach position, where the only move this "
            f"planner will make is to a park position; "
            f"{np.round(np.asarray(target, dtype=float) * 1e3, 3)} mm is not one. Park "
            f"first, or jog with the dials, which bypass the planner."
        )

    def _certify_leaving_park(self, moving, target, scope) -> None:
        """Parked, the stage goes to a well approach position or back the way it came."""
        if self._near(
            target, self._well_poses_for(moving) + self._unwind_poses_for(moving, scope)
        ):
            return
        raise PlanningError(
            f"{moving.name()} is parked, where this planner will only move it to a well "
            f"approach position or back along the path it recorded on the way out; "
            f"{np.round(np.asarray(target, dtype=float) * 1e3, 3)} mm is neither. Jog "
            f"with the dials, which bypass the planner."
        )

    def _certify_reaching_park(self, moving, target, scope) -> None:
        """A move ending at park has to start somewhere this planner can vouch for.

        Without this, park was reachable from any pose at all, as long as no well happened
        to be sitting at its approach position to trigger the rule above.
        """
        park = self._park_position_targeted(moving, target, scope)
        if park is not None:
            self._certify_move_to_park(scope, park, moving)

    def _ask_off_path(self, error: PlanningError) -> str:
        """Put an off-path refusal to the operator and return what they chose.

        The planner cannot tell a stage someone jogged from one a failed move left behind,
        and the two want opposite things done about the recorded path, so the choice is the
        operator's.  With no UI to ask through, the refusal stands.
        """
        if not _operator_can_be_asked():
            raise error
        from acq4.util.PromptUser import prompt

        return prompt(
            "Stage is off the recorded path",
            str(error),
            [REPOSITION_AND_CONTINUE, REPOSITION_AND_DISCARD, MOVE_ANYWAY],
        )

    def _unwind_decision(self, scope, park_pos, moving) -> str:
        """Certify the run to park, asking again for as long as it will not certify.

        Re-reading the device on each pass is what makes "I repositioned it" mean anything:
        a click on its own is not evidence that the stage moved.
        """
        while True:
            try:
                self._certify_move_to_park(scope, park_pos, moving)
                return REPOSITION_AND_CONTINUE
            except PlanningError as e:
                choice = self._ask_off_path(e)
                if choice != REPOSITION_AND_CONTINUE:
                    return choice

    def _checked_stage_move(self, spec: "MoveSpec", name: str) -> "MovePlanStep":
        """Plan a stage move, failing here rather than part-way through the sequence.

        Pipette waypoints are limit-checked while planning; without this the stage's were
        not, so an unreachable target parked the scope and swung the stage before raising.
        """
        step = self._plan_generic(spec, name)
        self._check_limits(step, name)
        return step

    def _check_limits(self, step: "MovePlanStep", name: str) -> None:
        """Raise PlanningError if *step* sends its device outside the device's limits.

        Only a limit violation is converted. Anything else coming out of the check is a
        fault in the check itself and says nothing about whether the position is reachable,
        so it propagates -- the same reasoning Stage.checkRangeOfMotion documents.
        """
        from acq4.devices.Stage import OutOfLimitsError  # avoids a devices<->motion cycle

        if not isinstance(step, AtomicMove):
            return
        check = getattr(step.device, "checkGlobalLimits", None)
        if check is None:
            return
        try:
            check(step.position, step.kwargs.get("linear", False))
        except OutOfLimitsError as e:
            raise PlanningError(
                f"{step.device.name()} cannot reach "
                f"{np.round(np.asarray(step.position) * 1e3, 3)} mm for '{name}' "
                f"-- outside its limits: {e}"
            ) from e

    # ------------------------------------------------------------------
    # Override: full approach sequence with scope park
    # ------------------------------------------------------------------

    def _plan_interaction_approach(
        self, spec: "MoveSpec", name: str = ""
    ) -> "MovePlanStep":
        site = spec.relative_to
        pip = spec.device
        pip_name = pip.name()

        if "scopeParkPos" not in site.config:
            return super()._plan_interaction_approach(spec, name)

        scope = pip.scopeDevice()
        park_pos = np.asarray(site.config["scopeParkPos"], dtype=float)
        scope_now = np.array(scope.globalPosition())
        speed = spec.speed or "fast"
        pip_start = np.array(pip.globalPosition())

        # Where the scope is, not what the bookkeeping says. The context is written during
        # plan(), before any motor turns, so a failure anywhere in execution leaves one
        # behind; reading it as "already parked" skipped the park and moved the stage with
        # the objective wherever the failure left it.
        already_parked = bool(
            np.linalg.norm(scope_now - park_pos) <= self._transit_tolerance
        )
        # A re-park must not record the half-parked position as home: that is the only
        # record of where the scope has to return to.
        previous = self._scope_context.get(pip_name)
        if already_parked and previous is None:
            # Taking the parked position as home would make every later unwind a no-op and
            # strand the scope at park, with the planner certain it was already home.
            raise PlanningError(
                f"{scope.name()} is already at the park position for {site.name()} but "
                f"this planner has no record of where it was parked from, so it would "
                f"have no way back. Jog it off park with the dials and try again."
            )
        original_pos = np.array(previous[1][0]) if previous is not None else scope_now
        up_pos = np.array([original_pos[0], original_pos[1], park_pos[2]])

        steps = []
        # Climbing to park height first is the safe opener from the recording chamber,
        # where the objective has to clear the bath before anything translates.  Out of a
        # well approach pose it is the one ordering this rig cannot survive, and there the
        # stage drives to park in one interpolated diagonal instead -- the same route
        # _certify_move_to_park vouches for when the scope unwinds from a well.
        climb_first = not already_parked and not self._at_a_well_approach_pose(scope)
        if climb_first:
            steps.append(
                AtomicMove(
                    scope,
                    np.array([scope_now[0], scope_now[1], park_pos[2]]),
                    speed,
                    "scope up before park",
                )
            )

        # The pipette clears the wells before anything riding the stage moves, whether that
        # is the scope going lateral to park or the stage carrying the rack to its approach
        # pose. Skipping this when the scope happened to be parked already would shear a
        # pipette still sitting in a tube against the tube it is in.
        pip_safe = pip.positionAtDepth(pip.approachDepth(), start=pip_start)
        if pip_safe[2] > pip_start[2]:
            steps.append(AtomicMove(pip, pip_safe, speed, "pip retract before scope park"))
        steps.append(
            AtomicMove(pip, pip.homePosition(), speed, "pipette home before scope park")
        )
        pip_start = np.array(pip.homePosition())

        if not already_parked:
            # Lateral when the climb above already made the height; the diagonal otherwise.
            steps.append(AtomicMove(scope, park_pos, speed, "scope to park position"))

        self._scope_context[pip_name] = (
            scope,
            [original_pos, up_pos, park_pos],
            pip,
            site,
        )

        # site stage to approach position (if on a movable stage)
        approach_global = np.array(site.approachGlobal(pip))
        site_spec = site.approachMoveSpec(pip, speed=speed)
        if site_spec is not None:
            # The stage starts this move from park, either because the steps above put it
            # there or because it was already there, so the route needs no further proof.
            steps.append(self._checked_stage_move(site_spec, f"position {site.name()}"))

        # pipette to approach position (safe path from current retracted position)
        kw = spec.kwargs
        pip_to_approach = self._safe_path(pip, pip_start, approach_global, speed)
        steps.extend(
            AtomicMove(pip, pos, spd, expl, {"linear": lin, **kw})
            for pos, spd, lin, expl in pip_to_approach
        )

        # pipette into site (only when going inside and approach is saved)
        going_inside = not np.allclose(spec.position, 0)
        if going_inside and site.hasApproachPosition(pip):
            # mapToGlobal reads the site's transform now, before the stage has moved it, so
            # the target has to be carried the same distance the stage is about to travel.
            site_delta = approach_global - np.asarray(site.globalPosition(), dtype=float)
            target_global = np.array(site.mapToGlobal(spec.position)) + site_delta
            steps.append(
                AtomicMove(
                    pip,
                    target_global,
                    speed,
                    "pipette into site",
                    {"linear": True, **kw},
                )
            )

        return SequentialGroup(steps, name or f"approach {site.name()}")

    # ------------------------------------------------------------------
    # Shared helpers: scope unwind steps
    # ------------------------------------------------------------------

    def _scope_unwind_group(self, pip_name: str) -> "MovePlanStep | None":
        """Pop the parked-scope context for *pip_name* and return the scope-return steps.

        Returns a SequentialGroup that walks the scope back along its forward park path, or
        None when no scope is parked for that pipette, or when the scope is off that path
        and the operator chose to forget it rather than drive it.
        """
        if pip_name not in self._scope_context:
            return None
        scope, forward_path, _pip, site = self._scope_context[pip_name]
        original_pos, up_pos, park_pos = forward_path
        # The return path is a full reversal, so park is re-commanded first.  When the scope
        # is still at park that first step is a no-op and the rest retraces the route it
        # came by.  When it is not, the step is a run to park from an unknown position, and
        # only the certification below says whether that run can be made at all.
        if not self._near(scope.globalPosition(), [park_pos]):
            decision = self._unwind_decision(
                scope, park_pos, getattr(site, "_parentStage", None)
            )
            if decision == REPOSITION_AND_DISCARD:
                # The operator took the scope back themselves, so the record describes a
                # park that is over; driving it would send the scope out to park again.
                self._scope_context.pop(pip_name)
                return None
        # Popped only once the move is allowed, so a refusal leaves the record intact.
        self._scope_context.pop(pip_name)
        scope_steps = [
            AtomicMove(scope, park_pos, "fast", "scope back to park position"),
            AtomicMove(scope, up_pos, "fast", "scope lateral over original position"),
            AtomicMove(scope, original_pos, "fast", "scope down to original position"),
        ]
        return SequentialGroup(scope_steps, "scope unwind")

    def _append_scope_unwind(
        self, base: "MovePlanStep", pip_name: str
    ) -> "MovePlanStep":
        """Append scope-return steps after *base* (used when the pipette itself moves away)."""
        unwind = self._scope_unwind_group(pip_name)
        if unwind is None:
            return base
        return SequentialGroup(base.steps + [unwind], base.explanation)

    # ------------------------------------------------------------------
    # Override: append scope unwind when exiting via approach waypoint
    # ------------------------------------------------------------------

    def _plan_interaction_exit(
        self, spec: "MoveSpec", name: str = "", containing_site=None
    ) -> "MovePlanStep":
        base = super()._plan_interaction_exit(spec, name, containing_site)
        return self._append_scope_unwind(base, spec.device.name())

    # ------------------------------------------------------------------
    # Override: append scope unwind on direct pipette moves (fallback)
    # ------------------------------------------------------------------

    def _plan_pipette_move(self, spec: "MoveSpec", name: str = "") -> "MovePlanStep":
        base = super()._plan_pipette_move(spec, name)
        return self._append_scope_unwind(base, spec.device.name())

    # ------------------------------------------------------------------
    # Override: a stage (or any child of it) move must also unwind the scope,
    # first safely extracting any pipette docked in a mobile site on that stage.
    # ------------------------------------------------------------------

    def _plan_one(self, spec: "MoveSpec", name: str = "") -> "MovePlanStep":
        base = super()._plan_one(spec, name)
        is_generic = not self._is_interaction_site(
            spec.relative_to
        ) and not self._is_pipette(spec.device)
        if is_generic:
            return self._handle_stage_move(base, spec)
        return base

    def _handle_stage_move(
        self, base: "MovePlanStep", spec: "MoveSpec"
    ) -> "MovePlanStep":
        """Prepend pipette extraction and scope unwind when *spec* moves a stage holding a
        mobile site in which a pipette is currently parked.

        For every parked-scope context whose site lives on (or under) the moving device's
        stage, the pipette is first extracted from the site (if it is inside), then the scope
        is unwound, and finally the requested stage move runs.
        """
        moving = spec.device
        # Both checks run before the loop below, which pops scope contexts as it builds the
        # unwind: refusing afterwards would discard the only record of where the scope has
        # to return to, and would leave the pipette extracted for a move that never ran.
        self._check_limits(base, base.explanation or "stage move")
        # Certified even when an unwind is about to be prepended. An unwind *opens* at park
        # but *closes* at the scope's pre-approach position, so it is the closing step that
        # decides where this move starts from -- exempting the move because the unwind
        # begins at park would leave the longest translation of the three unchecked.
        if isinstance(base, AtomicMove):
            self._certify_stage_target(moving, base.position)

        prefix: list = []
        # Snapshot the context: _scope_unwind_group() mutates the dict while we iterate.
        for pip_name, ctx in list(self._scope_context.items()):
            _scope, _forward_path, pip, site = ctx
            stage = getattr(site, "_parentStage", None)
            if stage is None or not self._device_in_stage_subtree(moving, stage):
                continue
            # Only extract when the pipette is actually inside the (about-to-move) site.
            if self._find_containing_site(pip) is site:
                prefix.append(self._plan_pipette_extraction(pip, site, spec.speed))
            unwind = self._scope_unwind_group(pip_name)
            if unwind is not None:
                prefix.append(unwind)
        if not prefix:
            return base
        return SequentialGroup(prefix + [base], base.explanation)

    @staticmethod
    def _device_in_stage_subtree(device, stage) -> bool:
        """Return True if *device* is *stage* or any descendant of it (via the parentDevice chain)."""
        node = device
        while node is not None:
            if node is stage:
                return True
            node = node.parentDevice() if hasattr(node, "parentDevice") else None
        return False

    def _plan_pipette_extraction(self, pip, site, speed) -> "MovePlanStep":
        """Plan a safe extraction of *pip* from *site*: exit via the approach waypoint, then home.

        Uses the base interaction-exit logic so no scope unwind is appended here; the caller
        handles unwinding explicitly.
        """
        extraction_spec = MoveSpec(
            pip, np.array(pip.homePosition()), speed=speed or "fast"
        )
        return super()._plan_interaction_exit(
            extraction_spec,
            f"extract {pip.name()} from {site.name()} before stage move",
            site,
        )
