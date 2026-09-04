"""Zone Service — data model and membership API for named spatial zones.

Each device may have a set of named zones (convex hulls). The DeviceZones
singleton (Manager.deviceZones) persists zone config and answers membership
queries without any knowledge of motion planning.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import coorx
import numpy as np
from scipy.spatial import ConvexHull, QhullError

if TYPE_CHECKING:
    from acq4.devices.Device import Device

POSITION_TOLERANCE = 1e-4  # 0.1 mm — handles float drift at hull boundaries


class ZoneConfigError(Exception):
    pass


class DuplicateZoneNameError(ValueError):
    """A zone name collides with another zone on the same device.

    Zone names key the saved config, so two zones sharing a name on one device
    would collapse into one the next time that device's zones are written.
    """


def _point_in_hull(hull: ConvexHull, point: np.ndarray, tol: float) -> bool:
    return bool(np.all(hull.equations @ np.append(point, 1) <= tol))


class Zone:
    """A named convex-hull region associated with a specific device.

    hull_points are stored as a plain ndarray internally; the hull_points
    property returns them wrapped in a coorx.PointArray.
    """

    def __init__(
        self,
        name: str,
        hull_points: np.ndarray,
        relative_to: "Device | None" = None,
    ):
        self.name = name
        self._hull_points: np.ndarray = np.asarray(hull_points, dtype=float)
        if self._hull_points.ndim == 1 and len(self._hull_points) == 0:
            self._hull_points = np.empty((0, 3), dtype=float)
        self.relative_to: "Device | None" = relative_to
        self._hull: ConvexHull | None = None
        if len(self._hull_points) >= 4:
            self._rebuild_hull()

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    @property
    def hull_points(self) -> "coorx.PointArray | np.ndarray":
        # coorx.PointArray raises ValueError on empty coordinate arrays; return the
        # raw ndarray in that case so callers using np.asarray() still work correctly.
        if len(self._hull_points) == 0:
            return self._hull_points
        return coorx.PointArray(self._hull_points)

    @property
    def hull(self) -> ConvexHull | None:
        return self._hull

    def mesh(self) -> tuple[np.ndarray, np.ndarray] | None:
        """Return (vertices N×3, faces M×3) for GL mesh rendering, or None.

        Both arrays are copies so callers may modify them freely. Suitable for
        passing directly to pyqtgraph.opengl.MeshData(vertexes=v, faces=f).
        """
        if self._hull is None:
            return None
        return self._hull.points.copy(), self._hull.simplices.copy()

    def global_hull_points(self) -> np.ndarray:
        """Return hull points mapped to global coordinates."""
        pts = self._hull_points.copy()
        if len(pts) == 0 or self.relative_to is None:
            return pts
        return np.array([self.relative_to.mapToGlobal(pt) for pt in pts])

    def global_mesh(self) -> tuple[np.ndarray, np.ndarray] | None:
        """Like mesh(), but vertices are in global coordinates."""
        if self._hull is None:
            return None
        verts = self._hull.points.copy()
        if self.relative_to is not None:
            verts = np.array([self.relative_to.mapToGlobal(pt) for pt in verts])
        return verts, self._hull.simplices.copy()

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_point(self, point: np.ndarray) -> None:
        pt = np.asarray(point, dtype=float).reshape(1, 3)
        if len(self._hull_points) == 0:
            self._hull_points = pt
        else:
            self._hull_points = np.vstack([self._hull_points, pt])
        if len(self._hull_points) >= 4:
            self._rebuild_hull()

    def remove_points(self, indices: list[int]) -> None:
        mask = np.ones(len(self._hull_points), dtype=bool)
        for i in indices:
            mask[i] = False
        self._hull_points = self._hull_points[mask]
        if len(self._hull_points) >= 4:
            self._rebuild_hull()
        else:
            self._hull = None

    def set_point(self, index: int, point: np.ndarray) -> None:
        self._hull_points[index] = np.asarray(point, dtype=float)
        if len(self._hull_points) >= 4:
            self._rebuild_hull()

    def clear_points(self) -> None:
        self._hull_points = np.empty((0, 3), dtype=float)
        self._hull = None

    def set_relative_to(self, device: "Device | None") -> None:
        self.relative_to = device

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _rebuild_hull(self) -> None:
        try:
            self._hull = ConvexHull(self._hull_points)
        except QhullError:
            self._hull = None

    def validate(self, device_name: str) -> None:
        """Raise ZoneConfigError if the hull points are structurally malformed.

        An incomplete zone -- too few points, or a set that is still coplanar --
        is a normal editing state: points accumulate one at a time while
        recording, and the first several rarely span three axes. Such a zone
        builds no hull and so never matches a membership query, but it is not a
        config error.
        """
        pts = self._hull_points
        if pts.ndim != 2 or pts.shape[1] != 3:
            raise ZoneConfigError(
                f"Zone '{self.name}' for {device_name} has hull points of shape "
                f"{pts.shape}; an N×3 array of 3D points is required."
            )

    def to_config(self) -> dict:
        cfg: dict = {
            "hull_points": [list(pt) for pt in self._hull_points],
        }
        if self.relative_to is not None:
            cfg["relativeTo"] = self.relative_to.name()
        return cfg


class DeviceZones:
    """Singleton service for per-device spatial zones.

    Accessible as ``Manager.deviceZones``. Loads zone config on first access
    per device, saves on every mutation (except during continuous recording,
    which must call save_device_zones() explicitly when complete).
    """

    def __init__(self, manager=None, position_tolerance: float = POSITION_TOLERANCE):
        self._manager = manager
        self.position_tolerance = position_tolerance
        self._zones: dict[str, list[Zone]] = {}
        self._loaded: set[str] = set()

    # ------------------------------------------------------------------
    # Membership queries
    # ------------------------------------------------------------------

    def find_zones(
        self, device: "Device", position_global: np.ndarray | None = None
    ) -> list[Zone]:
        """Return all zones containing position_global (defaults to device's current position)."""
        if position_global is None:
            position_global = device.globalPosition()
        self._ensure_loaded(device)
        matches = []
        for zone in self._zones.get(device.name(), []):
            if zone.relative_to is None:
                test_point = position_global
            else:
                test_point = zone.relative_to.mapFromGlobal(position_global)
            if zone.hull is not None and _point_in_hull(
                zone.hull, test_point, self.position_tolerance
            ):
                matches.append(zone)
        return matches

    def list_zones(self, device: "Device") -> list[Zone]:
        """Return all zones configured for device, in config order."""
        self._ensure_loaded(device)
        return list(self._zones.get(device.name(), []))

    # ------------------------------------------------------------------
    # Zone management
    # ------------------------------------------------------------------

    def add_zone(
        self,
        device: "Device",
        name: str,
        relative_to: "Device | None" = None,
        save: bool = True,
    ) -> Zone:
        self._ensure_loaded(device)
        name = self._unique_name(device, name)
        zone = Zone(name, np.empty((0, 3), dtype=float), relative_to=relative_to)
        self._zones.setdefault(device.name(), []).append(zone)
        if save:
            self.save_device_zones(device)
        return zone

    def remove_zone(self, device: "Device", zone_name: str, save: bool = True) -> None:
        self._ensure_loaded(device)
        zones = self._zones.get(device.name(), [])
        self._zones[device.name()] = [z for z in zones if z.name != zone_name]
        if save:
            self.save_device_zones(device)

    def reorder_zones(
        self, device: "Device", new_order: list[str], save: bool = True
    ) -> None:
        self._ensure_loaded(device)
        by_name = {z.name: z for z in self._zones.get(device.name(), [])}
        self._zones[device.name()] = [by_name[n] for n in new_order if n in by_name]
        if save:
            self.save_device_zones(device)

    def rename_zone(
        self, device: "Device", old_name: str, new_name: str, save: bool = True
    ) -> None:
        self._ensure_loaded(device)
        zones = self._zones.get(device.name(), [])
        for z in zones:
            if z.name == old_name:
                zone = z
                break
        else:
            raise KeyError(f"{device.name()} has no zone named '{old_name}'")
        if new_name != old_name and any(z.name == new_name for z in zones):
            raise DuplicateZoneNameError(
                f"{device.name()} already has a zone named '{new_name}'."
            )
        zone.name = new_name
        if save:
            self.save_device_zones(device)

    # ------------------------------------------------------------------
    # Config I/O
    # ------------------------------------------------------------------

    def load_device_zones(self, device: "Device") -> None:
        cfg = device.readConfigFile("motion_zones.cfg")
        raw_zones = cfg.get("zones", {})
        zones = []
        for zone_name, zone_cfg in raw_zones.items():
            pts_cfg = zone_cfg.get("hull_points", [])
            if pts_cfg is not None and len(pts_cfg) > 0:
                try:
                    pts = np.array(pts_cfg, dtype=float)
                except (TypeError, ValueError) as exc:
                    raise ZoneConfigError(
                        f"Zone '{zone_name}' for {device.name()}: "
                        f"hull_points could not be read as numbers ({exc})."
                    ) from exc
            else:
                pts = np.empty((0, 3), dtype=float)

            rel_name = zone_cfg.get("relativeTo", None)
            relative_to = None
            if rel_name is not None:
                if self._manager is None:
                    raise ZoneConfigError(
                        f"Zone '{zone_name}' for {device.name()}: "
                        f"relativeTo device '{rel_name}' not found."
                    )
                try:
                    relative_to = self._manager.getDevice(rel_name)
                except Exception:
                    raise ZoneConfigError(
                        f"Zone '{zone_name}' for {device.name()}: "
                        f"relativeTo device '{rel_name}' not found."
                    )

            zone = Zone(zone_name, pts, relative_to=relative_to)
            zone.validate(device.name())
            zones.append(zone)

        self._zones[device.name()] = zones
        self._loaded.add(device.name())

    def save_device_zones(self, device: "Device") -> None:
        zones = self._zones.get(device.name(), [])
        cfg = {"zones": {z.name: z.to_config() for z in zones}}
        device.writeConfigFile(cfg, "motion_zones.cfg")

    def invalidate_device(self, device: "Device") -> None:
        """Force a reload of device zones on next access."""
        self._loaded.discard(device.name())
        self._zones.pop(device.name(), None)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _unique_name(self, device: "Device", name: str) -> str:
        """Return *name*, suffixed with a counter if the device already uses it.

        Zone names key the saved config, so a duplicate would silently discard a
        zone on the next save.
        """
        taken = {z.name for z in self._zones.get(device.name(), [])}
        if name not in taken:
            return name
        n = 2
        while f"{name} {n}" in taken:
            n += 1
        return f"{name} {n}"

    def _ensure_loaded(self, device: "Device") -> None:
        if device.name() not in self._loaded:
            try:
                self.load_device_zones(device)
            except FileNotFoundError:
                # No config written for this device yet — the only failure that
                # legitimately means "no zones". Anything else must propagate:
                # caching an empty list would let the next save overwrite
                # zones we simply failed to read.
                self._zones[device.name()] = []
                self._loaded.add(device.name())
