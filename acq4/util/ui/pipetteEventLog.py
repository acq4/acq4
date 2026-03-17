# Scrollable event log widget for displaying meaningful pipette state changes.
# Used in PipetteControl (live mode) and MultiPatchLogWidget (replay mode).

from acq4.devices.PatchPipette.patchpipette import LOG_EVENT_TYPES
from acq4.util import Qt


def format_event(event_type: str, event_data: dict) -> str:
    """Return a short human-readable string for a log event."""
    if event_type == 'state_change':
        return f"\u2192 {event_data.get('state', '?')}"
    elif event_type == 'state_event':
        return event_data['info']
    elif event_type == 'new_pipette':
        return "new pipette"
    elif event_type == 'pipette_calibrated':
        return "tip position found"
    elif event_type == 'move_requested':
        if event_data.get("name") is not None:
            return f"move: {event_data['name']}"
        return "move"
    elif event_type == 'new_patch_attempt':
        return "new attempt"
    elif event_type == 'tip_clean_changed':
        return f"pipette tip {'clean' if event_data.get('clean', False) else 'dirty'}"
    return event_type


class PipetteEventLog(Qt.QWidget):
    """Scrollable list showing meaningful pipette log events with alternating row colors.

    In live mode, new events auto-scroll to the bottom. Scrolling up enters history
    mode; scrolling back to the bottom returns to live mode.

    Events are stored with whatever time coordinate the caller uses (absolute epoch
    time for live mode, relative time for replay mode). The display shows time
    relative to the first event seen since the last clear().
    """

    sigTimeSelected = Qt.Signal(float)  # emitted when user clicks an entry; value is stored event time

    def __init__(self, parent=None):
        super().__init__(parent)
        self._events = []  # list of (stored_time, display_text)
        self._start_time = None
        self._live_mode = True

        layout = Qt.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        self._list = Qt.QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setSelectionMode(Qt.QAbstractItemView.SingleSelection)
        self._list.setHorizontalScrollBarPolicy(Qt.Qt.ScrollBarAsNeeded)
        layout.addWidget(self._list)

        self._list.itemClicked.connect(self._itemClicked)
        self._list.verticalScrollBar().valueChanged.connect(self._scrollChanged)

    def addEvent(self, stored_time: float, event_type: str, event_data: dict):
        """Add an event entry to the log. Only LOG_EVENT_TYPES are shown.

        stored_time -- time in whatever coordinate system the caller uses (used
                       for setTime() comparisons and sigTimeSelected emissions)
        event_type  -- one of LOG_EVENT_TYPES (others are silently ignored)
        event_data  -- the full event dict (used for message formatting)
        """
        if event_type not in LOG_EVENT_TYPES:
            return
        if self._start_time is None:
            self._start_time = stored_time

        rel_time = stored_time - self._start_time
        msg = format_event(event_type, event_data)
        text = f"t+{rel_time:.1f}s  {msg}"

        self._events.append((stored_time, text))
        item = Qt.QListWidgetItem(text)
        self._list.addItem(item)

        if self._live_mode:
            self._list.scrollToBottom()

    def clear(self, start_time: float = None):
        """Remove all events and reset the start time reference.

        start_time -- if provided, pin t=0 to this value rather than waiting
                      for the first event to set it.
        """
        self._events.clear()
        self._start_time = start_time
        self._list.clear()

    def setTime(self, time: float):
        """Select and scroll to the most recent event at or before *time*.

        Uses the same coordinate system as the stored_time values passed to addEvent().
        """
        if not self._events:
            return
        idx = None
        for i, (t, _) in enumerate(self._events):
            if t <= time:
                idx = i
        if idx is not None:
            self._list.setCurrentRow(idx)
            self._list.scrollToItem(self._list.item(idx))

    def _itemClicked(self, item: Qt.QListWidgetItem):
        row = self._list.row(item)
        if 0 <= row < len(self._events):
            t, _ = self._events[row]
            self.sigTimeSelected.emit(t)

    def _scrollChanged(self, value: int):
        sb = self._list.verticalScrollBar()
        self._live_mode = (value >= sb.maximum())
