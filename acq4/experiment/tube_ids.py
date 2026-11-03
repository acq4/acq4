"""Tube identity for an InteractionSiteArray: format one tube's id from an
operator's template, lay out a rack's fill order, and keep the day's running
tube count."""
from __future__ import annotations

import time

_COUNT_FILE = "tube_count"
_DATE_FORMAT = "%y%m%d"


def format_tube_id(template, **namespace) -> str:
    """Render one tube's id.

    `template` is either a callable taking the namespace as keywords, or a
    string run first through time.strftime (so %y%m%d and friends expand) and
    then evaluated as an f-string against the namespace (so {tube_count + 701}
    does). Both halves have precedent in this tree: storage.create_data_dir
    runs folder-type names through strftime, and NucleusCollectState evaluates
    its pressureSequence config string.

    Raises ValueError naming the problem for a template the operator got wrong,
    so the dialog can show it in place rather than failing a run.
    """
    if callable(template):
        return str(template(**namespace))
    dated = time.strftime(template)
    try:
        return eval(f"f{dated!r}", {}, dict(namespace))
    except Exception as exc:
        raise ValueError(f"could not format tube id from {template!r}: {exc}") from exc


def well_label(index: int, cols: int) -> str:
    """The "A01"-style label for a 0-based site index in a grid `cols` wide."""
    row, col = divmod(index, cols)
    return f"{chr(ord('A') + row)}{col + 1:02d}"


def tube_position(site) -> str:
    """The site's well label within its array, or its device name when it has no
    array parent (a standalone site assigned directly to a role)."""
    array = site.parentDevice()
    if array is None or not hasattr(array, "getFirstAvailableSite"):
        return site.name()
    return well_label(array.sites.index(site), array.cols)


def fill_order(rows: int, cols: int, column_major: bool = False) -> list[int]:
    """Site indices in the order the operator fills them."""
    if not column_major:
        return list(range(rows * cols))
    return [r * cols + c for c in range(cols) for r in range(rows)]


def tube_namespace(index: int, cols: int, tube_count: int) -> dict:
    """The names a template may use for one tube.

    index/row/col/well are the site's physical position and do not move with
    the fill order; tube_count is the day's running number for this tube, and
    is the one name the fill order changes.
    """
    row, col = divmod(index, cols)
    return {
        "index": index,
        "row": row,
        "col": col,
        "well": well_label(index, cols),
        "tube_count": tube_count,
    }


def generate_tube_ids(
    template,
    rows: int,
    cols: int,
    start_n: int,
    column_major: bool = False,
    overrides: "dict[int, str] | None" = None,
) -> dict:
    """{site index: id} for a whole rack, numbered from `start_n` along the
    chosen fill order. An overridden index keeps the operator's text and still
    consumes its place in the numbering, so the tubes around it do not shift
    when one is retyped.
    """
    overrides = overrides or {}
    ids = {}
    for ordinal, index in enumerate(fill_order(rows, cols, column_major)):
        if index in overrides:
            ids[index] = overrides[index]
            continue
        ids[index] = format_tube_id(
            template, **tube_namespace(index, cols, start_n + ordinal)
        )
    return ids


def read_tube_count(array) -> int:
    """The number of tubes filled today, or 0 when the stored record is from
    another date.

    Stored through the array's own config file, which is why it survives both a
    restart and a move to the next slice: there is no code for either, only the
    file's placement.
    """
    record = array.readConfigFile(_COUNT_FILE) or {}
    if record.get("date") != time.strftime(_DATE_FORMAT):
        return 0
    return int(record.get("count", 0))


def write_tube_count(array, count: int) -> None:
    """Record today's running tube count for this array."""
    array.writeConfigFile(
        {"date": time.strftime(_DATE_FORMAT), "count": int(count)}, _COUNT_FILE
    )
