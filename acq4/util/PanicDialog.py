"""Panic Lock resume dialog (see ``Panic Lock Spec.md`` §9.1).

The dialog is the operator's only way out of a halt: it announces that the rig
is halted, says why, and offers the single action §8 permits -- Resume, which
clears the latch and nothing else.

Two objects live here:

``PanicDialog``
    The window itself. Modeless, and deliberately hard to get rid of: no close
    button, no Alt+F4, no ``close()``, and no ESC. ESC is the panic key, so a
    press while this dialog has focus must mean "panic again", never "close
    this".

``PanicDialogController``
    A tiny QObject that owns the dialog, creates it lazily, and -- crucially --
    guarantees it is created and shown on the GUI thread. ``GlobalHalt.halt()``
    can be called from any device thread, so ``sigHaltRequested`` may be emitted
    anywhere; see the class docstring for why a plain auto connection is the
    right marshalling mechanism here.

The dialog is *not* imported by ``acq4/panic.py``: the panic state object stays
free of widget code, and the UI attaches to it from outside. ``Manager`` builds
the controller (``Manager.globalHalt`` is where the live state lives).
"""

from __future__ import annotations

from acq4.util import Qt

__all__ = ["PanicDialog", "PanicDialogController"]


class PanicDialog(Qt.QDialog):
    """The panic window: headline, reason, Resume button (§9.1).

    Modeless with respect to the event loop -- it is shown, never ``exec()``ed
    -- so the halt path and every other window keep running while it is up.
    """

    def __init__(self, globalHalt, parent=None):
        Qt.QDialog.__init__(self, parent)
        self._globalHalt = globalHalt

        self.setWindowTitle("ACQ4 Panic Lock")
        self.setModal(False)
        # Not closeable except by Resume (§9.1). CustomizeWindowHint drops every
        # title-bar button that is not explicitly asked for, so there is no X --
        # and, on Windows, no system-menu Close for Alt+F4 to reach either.
        # closeEvent() refuses anything that still gets through.
        self.setWindowFlags(
            Qt.Qt.Dialog | Qt.Qt.CustomizeWindowHint | Qt.Qt.WindowTitleHint
        )

        layout = Qt.QVBoxLayout()
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        self.setLayout(layout)

        self.headlineLabel = Qt.QLabel("ALL DEVICES HALTED")
        font = self.headlineLabel.font()
        font.setBold(True)
        font.setPointSize(max(font.pointSize(), 1) + 8)
        self.headlineLabel.setFont(font)
        self.headlineLabel.setAlignment(Qt.Qt.AlignCenter)
        layout.addWidget(self.headlineLabel)

        self.reasonLabel = Qt.QLabel("")
        self.reasonLabel.setWordWrap(True)
        self.reasonLabel.setAlignment(Qt.Qt.AlignCenter)
        self.reasonLabel.setMinimumWidth(360)
        self.reasonLabel.setTextInteractionFlags(Qt.Qt.TextSelectableByMouse)
        layout.addWidget(self.reasonLabel)

        btnLayout = Qt.QHBoxLayout()
        btnLayout.addStretch()
        self.resumeBtn = Qt.QPushButton("Resume")
        btnLayout.addWidget(self.resumeBtn)
        btnLayout.addStretch()
        layout.addLayout(btnLayout)

        self.resumeBtn.clicked.connect(self.resumeClicked)

    # -- showing -----------------------------------------------------------

    def showPanic(self):
        """Show, raise and activate. Called on *every* ``halt()`` (§9.1).

        Including a repeat halt that changed no state: a second ESC press means
        "I mean it" (§3), and the operator has to see the rig respond to it.
        Raising and activating are what make that visible when the dialog was
        already up but buried behind another window.
        """
        self.reasonLabel.setText(self._globalHalt.reason or "")
        self.show()
        self.setWindowState(
            (self.windowState() & ~Qt.Qt.WindowMinimized) | Qt.Qt.WindowActive
        )
        self.raise_()
        self.activateWindow()
        self.resumeBtn.setFocus()

    def dismiss(self):
        """Take the dialog down. The only sanctioned way out.

        ``hide()``, not ``close()``: ``close()`` goes through ``closeEvent()``,
        which this class refuses.
        """
        self.hide()

    # -- resume ------------------------------------------------------------

    def resumeClicked(self):
        """Clear the latch (§8) and take the dialog down.

        Nothing is restored: shutters stay closed, pressure stays at
        atmosphere, no interrupted move resumes. §8 forbids it -- the operator
        must consciously re-enable each energy source.
        """
        self._globalHalt.resume()
        self.dismiss()

    # -- refusing to go away -----------------------------------------------

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Qt.Key_Escape:
            # QDialog maps ESC to reject(); swallow it before that can happen.
            # In a running application the ESC key never reaches here at all:
            # Qt dispatches QEvent.Shortcut ahead of the key press, so the
            # application-scoped ESC QShortcut consumes it and panics again,
            # which re-runs showPanic() through sigHaltRequested. This handler
            # is the backstop for a session with no shortcut installed.
            ev.accept()
            return
        Qt.QDialog.keyPressEvent(self, ev)

    def reject(self):
        """No-op (§9.1). Resume is the only exit; ESC and the X are not."""
        return

    def closeEvent(self, ev):
        """Refuse every close: the title-bar X, Alt+F4, and ``close()`` (§9.1).

        Unconditional. `dismiss()` does not come through here -- it hides the
        window instead -- so there is no case in which closing is the right
        answer.
        """
        ev.ignore()


class PanicDialogController(Qt.QObject):
    """Puts a `PanicDialog` on screen for every ``halt()``, on the GUI thread.

    Threading (§5c). ``halt()`` may be called from any device thread, so
    ``sigHaltRequested`` can be emitted from anywhere. This object is given GUI
    thread affinity, and the connection is left at ``AutoConnection``, which is
    Qt's own thread marshalling:

    * emitted from the GUI thread (the ESC shortcut, the usual case) -> direct
      call, dialog up immediately, no event-loop round trip;
    * emitted from a device thread -> queued to the GUI thread's event loop.

    Either way ``emit()`` returns at once, so ``halt()`` never blocks on the GUI
    thread. That is why this is not ``run_in_gui_thread``, which *waits* for the
    result and would make ``halt()`` itself depend on a responsive event loop --
    §4.1 says the latch and the fan-out must not.

    The accepted limitation of §4.1 stands and is not worked around here: with
    the GUI thread wedged the queued call never runs and the dialog cannot
    appear. Recovery is a process restart.
    """

    def __init__(self, globalHalt, parent=None):
        Qt.QObject.__init__(self, parent)
        self._globalHalt = globalHalt
        self._dialog = None

        app = Qt.QApplication.instance()
        if parent is None and app is not None and self.thread() != app.thread():
            # Affinity is what decides where the slots run, so pin it rather
            # than relying on who happened to construct the Manager.
            self.moveToThread(app.thread())

        globalHalt.sigHaltRequested.connect(self.haltRequested)
        globalHalt.sigPanicStateChanged.connect(self.panicStateChanged)

    @property
    def dialog(self):
        """The dialog, or None if no halt has happened yet."""
        return self._dialog

    def haltRequested(self):
        """Show/raise/activate the dialog. Runs on the GUI thread."""
        if self._dialog is None:
            # Lazy: a session that never panics never builds a widget, and a
            # headless-until-showGUI() Manager does not need one at import time.
            self._dialog = PanicDialog(self._globalHalt)
        self._dialog.showPanic()

    def panicStateChanged(self, reason):
        """Take the dialog down when the latch clears.

        The Resume button already dismisses the dialog itself; this covers a
        ``resume()`` that came from somewhere else, so the window can never be
        left claiming a halt that is over.
        """
        if reason is None and self._dialog is not None:
            self._dialog.dismiss()
