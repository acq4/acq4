"""Manager.removeWindowShortcut removes only the shortcut belonging to the
window it is given."""
import weakref

from acq4.Manager import Manager


class _Win:
    pass


class _Holder:
    removeWindowShortcut = Manager.removeWindowShortcut

    def __init__(self, *wins):
        self.shortcuts = [(object(), "k", weakref.ref(w)) for w in wins]


def test_removes_the_matching_shortcut():
    a, b = _Win(), _Win()
    m = _Holder(a, b)

    m.removeWindowShortcut(a)

    assert [s[2]() for s in m.shortcuts] == [b]


def test_unknown_window_removes_nothing():
    a, b = _Win(), _Win()
    m = _Holder(a, b)

    m.removeWindowShortcut(None)
    m.removeWindowShortcut(_Win())

    assert [s[2]() for s in m.shortcuts] == [a, b]
