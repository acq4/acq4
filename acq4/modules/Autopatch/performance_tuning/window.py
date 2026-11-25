"""The performance tuning review window: trials by run group, with dialogs over the lifecycle steps."""

import json
from pathlib import Path

from acq4.util import Qt, tuning_points
from acq4.util.codeEditor import invokeCodeEditor

from . import brief, catalogue, lifecycle, record, report, scaffold
from .lifecycle import REFUSALS, Refused

DEFAULT_PROTOCOL = "acq4/modules/Autopatch/example_protocols/_example_patch.py"
STANDALONE_TOOLTIP = (
    "Arming needs a running Autopatch window: open this from its "
    "Performance tuning button."
)
TRIAL_COLUMNS = ("Trial", "Title", "Primary factor", "Status", "Cells", "Days", "")
ARM_TOOLTIP = (
    "Pin this run group's protocol and install all of its factors. From the "
    "next Start, each cell, survey and slice that reaches one of their tuning "
    "points is given a condition, and every assignment is logged."
)
DISARM_TOOLTIP = (
    "Remove the run group's factors and unpin its protocol, so Autopatch "
    "runs normally again."
)
RUN_ID_ROLE = Qt.Qt.UserRole + 1


class _AnalysisRun:
    """Holds the one analyze.py process a window may have running.

    The process is not parented to the window: Qt would destroy it with the
    window while still running and then deliver `finished` into the deleted
    object. Kept outside the window so its `destroyed` handler can stop it.
    """

    def __init__(self):
        self.process = None

    def stop(self):
        process, self.process = self.process, None
        if process is None:
            return
        process.finished.disconnect()
        process.errorOccurred.disconnect()
        process.kill()
        process.waitForFinished()


class _WarningRelay(Qt.QObject):
    """Carries warnings raised on any thread to the window's GUI thread as a queued signal."""

    sigWarning = Qt.Signal(str)


class TuningWindow(Qt.QMainWindow):
    def __init__(
        self,
        autopatch=None,
        trials_dir=record.TRIALS_DIR,
        catalogue_path=catalogue.DEFAULT_PATH,
        manager=None,
        mutators_dir=scaffold.MUTATORS_DIR,
    ):
        super().__init__()
        self.autopatch = autopatch
        self.trials_dir = Path(trials_dir)
        self.catalogue_path = Path(catalogue_path)
        self.mutators_dir = Path(mutators_dir)
        if manager is None and autopatch is not None:
            manager = autopatch.manager
        self.manager = manager
        self.tuningWarnings = []
        self.lastRun = None
        self._relay = _WarningRelay(self)
        self._relay.sigWarning.connect(self._addTuningWarning)
        collector = lifecycle.WarningCollector(self._relay.sigWarning.emit)
        self._warnings = collector
        analysisRun = _AnalysisRun()
        self._analysisRun = analysisRun

        # Closes over the collector and the run alone, so destruction stops
        # both without the connection keeping this window alive.
        def stopOnDestroyed(*args):
            collector.stop()
            analysisRun.stop()

        self.destroyed.connect(stopOnDestroyed)
        self._openUrl = Qt.QDesktopServices.openUrl
        self.setWindowTitle("Autopatch performance tuning")
        self._buildUi()
        if autopatch is None:
            for btn in (self.armBtn, self.disarmBtn):
                btn.setEnabled(False)
                btn.setToolTip(STANDALONE_TOOLTIP)
        self.refresh()

    # -- lifecycle -------------------------------------------------------

    def newRunGroup(
        self,
        factors,
        protocol,
        interactions_expected=None,
        interaction_notes="",
        run_id=None,
    ):
        trials = lifecycle.new_run_group(
            self.catalogue_path,
            self.trials_dir,
            factors,
            protocol,
            interactions_expected,
            interaction_notes,
            run_id,
        )
        self.refresh()
        return trials

    def createMutator(self, factor_name, base, point, param=None):
        """Write a stub mutator for a factor that has none; the path of the stub."""
        factor = next(
            (f for f in catalogue.load(self.catalogue_path) if f.name == factor_name),
            None,
        )
        if factor is None:
            raise Refused(f"no factor named {factor_name!r} in the catalogue")
        if factor.mutator is not None:
            raise Refused(f"{factor_name} already has mutator {factor.mutator!r}")
        try:
            return scaffold.mutator_stub(
                factor_name, base, point, self.mutators_dir, param
            )
        except FileExistsError as exc:
            raise Refused(
                f"{exc.args[0]} already exists; finish it and press Register "
                "mutator, or delete it to start over"
            ) from exc

    def awaitingRegistration(self):
        return scaffold.awaiting_registration(self.mutators_dir, self.catalogue_path)

    def registerMutator(self, factor_name):
        cls = scaffold.register_mutator(
            factor_name, self.mutators_dir, self.catalogue_path
        )
        self.refresh()
        return cls

    def armWarnings(self, trial):
        return lifecycle.arm_warnings(self.trials_dir, trial)

    def arm(self, trial):
        if self.autopatch is None:
            raise Refused(STANDALONE_TOOLTIP)
        lifecycle.arm(self.autopatch, self.manager, self.trials_dir, trial)
        self._warnings.start()
        self.refresh()

    def disarm(self):
        if self.autopatch is None:
            raise Refused(STANDALONE_TOOLTIP)
        try:
            lifecycle.disarm(self.autopatch, self._warnings)
        finally:
            self.refresh()

    def release(self):
        """Stop collecting warnings and any analysis run; for an Autopatch window tearing down the run this armed."""
        self._warnings.stop()
        self._analysisRun.stop()

    def _addTuningWarning(self, text):
        self.tuningWarnings.append(text)
        self.warningList.addItem(text)

    def linkableSliceDirs(self, trial):
        return lifecycle.linkable_slice_dirs(self.manager, trial)

    def linkData(self, trial, slice_dirs):
        lifecycle.link_data(self.trials_dir, trial, slice_dirs)
        self.refresh()

    def newAnalysis(self, trial, slug, question, kind="script"):
        config = self.manager.config if self.manager is not None else {}
        analysis_dir = lifecycle.new_analysis(
            config, trial, slug, question, kind, self._openInEditor
        )
        self.refresh()
        return analysis_dir

    @staticmethod
    def _openInEditor(path):
        invokeCodeEditor(path, 1)

    def openAnalysesFolder(self, trial):
        self._openUrl(Qt.QUrl.fromLocalFile(str(Path(trial.dir) / "analyses")))

    def runAnalysis(self, analysis_dir):
        analysis_dir = Path(analysis_dir)
        if not (analysis_dir / lifecycle.SCRIPT_NAME).exists():
            notebook = analysis_dir / lifecycle.NOTEBOOK_NAME
            if not notebook.exists():
                raise lifecycle.missing_analysis(analysis_dir)
            self._openUrl(Qt.QUrl.fromLocalFile(str(notebook)))
            return None
        if self._analysisRun.process is not None:
            raise Refused("an analysis is already running")
        program, args, env = lifecycle.script_command(analysis_dir)
        environment = Qt.QProcessEnvironment()
        for key, value in env.items():
            environment.insert(key, value)
        process = Qt.QProcess()
        process.setProcessChannelMode(Qt.QProcess.MergedChannels)
        process.setWorkingDirectory(str(analysis_dir))
        process.setProcessEnvironment(environment)
        process.finished.connect(
            lambda code, status: self._onRunFinished(
                analysis_dir, process, code, status
            )
        )
        process.errorOccurred.connect(
            lambda error: self._onRunError(analysis_dir, process, error)
        )
        self.lastRun = None
        self._analysisRun.process = process
        self.runView.setPlainText(
            f"Running {analysis_dir.name}/{lifecycle.SCRIPT_NAME}…"
        )
        process.start(program, args)
        return process

    def accept(self, trial, analysis_dir, verdict):
        lifecycle.accept(
            self.catalogue_path, self.trials_dir, trial, analysis_dir, verdict
        )
        self.refresh()

    def reject(self, trial, note):
        lifecycle.reject(trial, note)
        self.refresh()

    def abandon(self, trial, reason):
        lifecycle.abandon(self.catalogue_path, self.trials_dir, trial, reason)
        self.refresh()

    # -- widgets ---------------------------------------------------------

    def _buildUi(self):
        self.trialList = Qt.QTreeWidget()
        self.trialList.setHeaderLabels(list(TRIAL_COLUMNS))
        self.trialList.currentItemChanged.connect(self._onTrialSelected)
        self.details = Qt.QTextBrowser()
        self.analysesList = Qt.QListWidget()
        self.analysesList.currentItemChanged.connect(self._onAnalysisSelected)
        self.analysisView = Qt.QTextBrowser()
        self.warningList = Qt.QListWidget()
        self.runView = Qt.QPlainTextEdit()
        self.runView.setReadOnly(True)

        buttons = Qt.QGridLayout()
        actions = [
            ("newRunGroupBtn", "New run group…", self._onNewRunGroup),
            ("createMutatorBtn", "Create mutator…", self._onCreateMutator),
            ("registerMutatorBtn", "Register mutator…", self._onRegisterMutator),
            ("armBtn", "Arm run group", self._onArm),
            ("disarmBtn", "Disarm", self._guard(self.disarm)),
            ("linkDataBtn", "Link data…", self._onLinkData),
            ("newAnalysisBtn", "New analysis…", self._onNewAnalysis),
            ("openFolderBtn", "Open analyses folder", self._onOpenFolder),
            ("runAnalysisBtn", "Run analysis", self._onRunAnalysis),
            ("acceptBtn", "Accept…", self._onAccept),
            ("rejectBtn", "Reject…", self._onReject),
            ("abandonBtn", "Abandon…", self._onAbandon),
        ]
        for i, (attr, label, slot) in enumerate(actions):
            btn = Qt.QPushButton(label)
            btn.clicked.connect(slot)
            setattr(self, attr, btn)
            buttons.addWidget(btn, i // 5, i % 5)
        self.acceptBtn.setEnabled(False)
        self.armBtn.setToolTip(ARM_TOOLTIP)
        self.disarmBtn.setToolTip(DISARM_TOOLTIP)
        self.armStatus = Qt.QLabel()
        self.armStatus.setWordWrap(True)

        right = Qt.QWidget()
        layout = Qt.QVBoxLayout(right)
        layout.addWidget(self.armStatus)
        layout.addWidget(self.details, 2)
        layout.addLayout(buttons)
        layout.addWidget(Qt.QLabel("Analyses (newest first)"))
        layout.addWidget(self.analysesList, 1)
        layout.addWidget(self.analysisView, 3)
        layout.addWidget(Qt.QLabel("Last analysis run"))
        layout.addWidget(self.runView, 1)
        layout.addWidget(Qt.QLabel("Tuning warnings while armed"))
        layout.addWidget(self.warningList, 1)

        splitter = Qt.QSplitter(Qt.Qt.Horizontal)
        splitter.addWidget(self.trialList)
        splitter.addWidget(right)
        self.setCentralWidget(splitter)
        self.resize(1200, 800)

    def refresh(self):
        selected = self.selectedTrial()
        self.trialList.clear()
        trials = record.all_trials(self.trials_dir)
        groups = {}
        for trial in trials:
            groups.setdefault(trial.run_id, []).append(trial)
        runtime = tuning_points.installed()
        armed_run = None if runtime is None else runtime.run_id
        self.armStatus.setText(
            "Not armed: Autopatch runs normally."
            if armed_run is None
            else f"Armed: run group {armed_run}. Cells are being given conditions."
        )
        for run_id, group in groups.items():
            node = Qt.QTreeWidgetItem(
                [f"{run_id}  ARMED" if run_id == armed_run else run_id]
            )
            node.setData(0, RUN_ID_ROLE, run_id)
            if run_id == armed_run:
                font = node.font(0)
                font.setBold(True)
                node.setFont(0, font)
            self.trialList.addTopLevelItem(node)
            for trial in group:
                item = self._trialItem(trial, group)
                node.addChild(item)
                if selected is not None and trial.dir == selected.dir:
                    self.trialList.setCurrentItem(item)
            node.setExpanded(True)
        self._onTrialSelected()

    def _trialItem(self, trial, group):
        lines = lifecycle.ledger_lines(trial)
        days = lifecycle.days_collecting(trial, lines)
        problems = lifecycle.problems(trial, group)
        item = Qt.QTreeWidgetItem(
            [
                trial.id,
                trial.title,
                trial.primary_factor,
                trial.status,
                str(lifecycle.cells_so_far(lines)),
                "" if days is None else str(days),
                "invalid" if problems else "",
            ]
        )
        if problems:
            item.setToolTip(len(TRIAL_COLUMNS) - 1, "\n".join(problems))
        item.setData(0, Qt.Qt.UserRole, str(trial.dir))
        return item

    def selectedTrial(self):
        item = self.trialList.currentItem()
        path = None if item is None else item.data(0, Qt.Qt.UserRole)
        return None if path is None else record.load(path)

    def selectedAnalysis(self):
        item = self.analysesList.currentItem()
        return None if item is None else Path(item.data(Qt.Qt.UserRole))

    def _onTrialSelected(self, *args):
        trial = self.selectedTrial()
        self.analysesList.clear()
        self.analysisView.clear()
        self.acceptBtn.setEnabled(False)
        if trial is None:
            self.details.clear()
            return
        summary = lifecycle.latest_summary(trial)
        self.details.setPlainText(
            "\n\n".join(
                [
                    f"{trial.id} {trial.title} [{trial.status}]",
                    f"Hypothesis: {trial.hypothesis.strip()}",
                    "Mutators:\n" + json.dumps(trial.mutators, indent=2),
                    record.describe_interactions(trial),
                    "Data: " + (", ".join(trial.data) or "none linked"),
                    "Last analysis summary:\n"
                    + (report.format_text(summary) if summary else "none"),
                ]
            )
        )
        analyses = sorted(
            (p for p in (Path(trial.dir) / "analyses").glob("*") if p.is_dir()),
            reverse=True,
        )
        for path in analyses:
            has = (path / "out" / "summary.json").exists()
            item = Qt.QListWidgetItem(f"{path.name}{'  (summary)' if has else ''}")
            item.setData(Qt.Qt.UserRole, str(path))
            self.analysesList.addItem(item)

    def _onAnalysisSelected(self, *args):
        analysis_dir = self.selectedAnalysis()
        self.analysisView.clear()
        self.acceptBtn.setEnabled(
            analysis_dir is not None and not lifecycle.summary_errors(analysis_dir)
        )
        if analysis_dir is None:
            return
        out = analysis_dir / "out"
        report_path = out / "report.txt"
        text = report_path.read_text() if report_path.exists() else "No report.txt."
        html = "<pre>" + text.replace("&", "&amp;").replace("<", "&lt;") + "</pre>"
        for png in sorted(out.glob("*.png")):
            html += f'<p><img src="{Qt.QUrl.fromLocalFile(str(png)).toString()}"></p>'
        self.analysisView.setHtml(html)

    # -- thin GUI handlers -------------------------------------------------

    def _guard(self, fn):
        def run(*args):
            try:
                fn()
            except REFUSALS as exc:
                self._showRefusal(str(exc))

        return run

    def _showRefusal(self, text):
        Qt.QMessageBox.warning(self, "Refused", text)

    def _needTrial(self):
        trial = self.selectedTrial()
        if trial is None:
            raise Refused("select a trial first")
        return trial

    def _needAnalysis(self):
        analysis_dir = self.selectedAnalysis()
        if analysis_dir is None:
            raise Refused("select an analysis first")
        return analysis_dir

    def _ask(self, title, label):
        text, ok = Qt.QInputDialog.getText(self, title, label)
        return text if ok else None

    def _onNewRunGroup(self):
        self._guard(self._newRunGroupDialog)()

    def _newRunGroupDialog(self):
        dialog = NewRunGroupDialog(self.catalogue_path, self)
        if dialog.exec() == Qt.QDialog.Accepted:
            self.newRunGroup(*dialog.choice())

    def _needFactorWithoutMutator(self):
        if not any(f.mutator is None for f in catalogue.load(self.catalogue_path)):
            raise Refused("every factor in the catalogue already has a mutator")

    def _onCreateMutator(self):
        def create():
            self._needFactorWithoutMutator()
            dialog = CreateMutatorDialog(self.catalogue_path, self)
            if dialog.exec() != Qt.QDialog.Accepted:
                return
            path = self.createMutator(*dialog.choice())
            self._openInEditor(str(path))
            Qt.QMessageBox.information(
                self,
                "Mutator stub written",
                f"Wrote {path}.\n\nFill in its conditions (and its override, "
                "unless it is a profile-param mutator), then press Register "
                "mutator to make the factor available to New run group.",
            )

        self._guard(create)()

    def _onRegisterMutator(self):
        def register():
            waiting = self.awaitingRegistration()
            if not waiting:
                raise Refused("no factor has an unregistered mutator stub")
            name, ok = Qt.QInputDialog.getItem(
                self, "Register mutator", "Factor:", waiting, 0, False
            )
            if not ok:
                return
            self.registerMutator(name)
            Qt.QMessageBox.information(
                self,
                "Mutator registered",
                f"{name} is registered and can join a run group now. Commit "
                f"mutators/{name}.py, mutators/__init__.py and factors.yaml so "
                "trials record a clean checkout.",
            )

        self._guard(register)()

    def _onArm(self):
        def arm():
            trial = self._needTrial()
            found = self.armWarnings(trial)
            if found:
                answer = Qt.QMessageBox.question(
                    self,
                    "Arm with warnings?",
                    "\n".join(found) + "\n\n" + record.describe_interactions(trial),
                )
                if answer != Qt.QMessageBox.Yes:
                    return
            self.arm(trial)

        self._guard(arm)()

    def _onLinkData(self):
        def link():
            trial = self._needTrial()
            offered = self.linkableSliceDirs(trial)
            if not offered:
                raise Refused("the run's ledger names no unlinked slice directories")
            dialog = PickDialog("Link data", offered, self)
            if dialog.exec() == Qt.QDialog.Accepted:
                self.linkData(trial, dialog.picked())

        self._guard(link)()

    def _onNewAnalysis(self):
        def new():
            trial = self._needTrial()
            slug = self._ask("New analysis", "Slug (lowercase, digits, dashes):")
            if slug is None:
                return
            question, ok = Qt.QInputDialog.getMultiLineText(
                self, "New analysis", "Question:"
            )
            if not ok:
                return
            kind, ok = Qt.QInputDialog.getItem(
                self, "New analysis", "Kind:", list(brief.KINDS), 0, False
            )
            if ok:
                self.newAnalysis(trial, slug, question, kind)

        self._guard(new)()

    def _onOpenFolder(self):
        self._guard(lambda: self.openAnalysesFolder(self._needTrial()))()

    def _onRunAnalysis(self):
        def run():
            self.runAnalysis(self._needAnalysis())

        self._guard(run)()

    def _onAccept(self):
        def accept():
            trial, analysis_dir = self._needTrial(), self._needAnalysis()
            verdict = self._ask("Accept", "One-line verdict:")
            if verdict is not None:
                self.accept(trial, analysis_dir, verdict)

        self._guard(accept)()

    def _onReject(self):
        def reject():
            trial = self._needTrial()
            note = self._ask("Reject", "Note:")
            if note is not None:
                self.reject(trial, note)

        self._guard(reject)()

    def _onAbandon(self):
        def abandon():
            trial = self._needTrial()
            reason = self._ask("Abandon", "Reason:")
            if reason is not None:
                self.abandon(trial, reason)

        self._guard(abandon)()

    def _onRunFinished(self, analysis_dir, process, exit_code, exit_status):
        output = bytes(process.readAllStandardOutput()).decode(errors="replace")
        crashed = exit_status == Qt.QProcess.CrashExit
        report_text = lifecycle.read_report(analysis_dir)
        self._finishRun(analysis_dir, process, exit_code, crashed, output, report_text)
        self._onTrialSelected()
        self.runView.setPlainText(
            lifecycle.describe_run(exit_code, crashed, output, report_text)
        )

    def _onRunError(self, analysis_dir, process, error):
        if error != Qt.QProcess.FailedToStart:
            return
        reason = f"could not start {lifecycle.SCRIPT_NAME}: {process.errorString()}"
        self._finishRun(analysis_dir, process, None, False, reason, None)
        self.runView.setPlainText(reason)
        self._showRefusal(reason)

    def _finishRun(
        self, analysis_dir, process, exit_code, crashed, output, report_text
    ):
        self.lastRun = {
            "dir": analysis_dir,
            "exit_code": exit_code,
            "crashed": crashed,
            "output": output,
            "report": report_text,
        }
        self._analysisRun.process = None
        process.deleteLater()

    def closeEvent(self, event):
        self._analysisRun.stop()
        super().closeEvent(event)


class PickDialog(Qt.QDialog):
    """A checklist of strings, all checked to start with."""

    def __init__(self, title, options, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.list = Qt.QListWidget()
        for option in options:
            item = Qt.QListWidgetItem(option)
            item.setCheckState(Qt.Qt.Checked)
            self.list.addItem(item)
        box = Qt.QDialogButtonBox(Qt.QDialogButtonBox.Ok | Qt.QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout = Qt.QVBoxLayout(self)
        layout.addWidget(self.list)
        layout.addWidget(box)

    def picked(self):
        items = (self.list.item(i) for i in range(self.list.count()))
        return [item.text() for item in items if item.checkState() == Qt.Qt.Checked]


class NewRunGroupDialog(Qt.QDialog):
    """Pick factors from the catalogue and a protocol, and say whether the factors could interact."""

    def __init__(self, catalogue_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New run group")
        factors = catalogue.load(catalogue_path)
        proposed = {f.name for f in catalogue.candidates(2, factors)}
        self.factors = {}
        self.list = Qt.QListWidget()
        for f in factors:
            if f.mutator is None:
                item = Qt.QListWidgetItem(f"{f.name} (needs a mutator)")
                item.setFlags(Qt.Qt.NoItemFlags)
            else:
                item = Qt.QListWidgetItem(f"{f.name} [{f.priority}, {f.status}]")
                item.setCheckState(
                    Qt.Qt.Checked if f.name in proposed else Qt.Qt.Unchecked
                )
                self.factors[item.text()] = f
            item.setToolTip(f.summary)
            self.list.addItem(item)
        self.list.itemChanged.connect(self._updateWarnings)
        self.protocol = Qt.QLineEdit(DEFAULT_PROTOCOL)
        self.interactions = self._buildInteractions()
        self.warnings = Qt.QLabel()
        self.warnings.setWordWrap(True)
        self.buttons = Qt.QDialogButtonBox(
            Qt.QDialogButtonBox.Ok | Qt.QDialogButtonBox.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout = Qt.QVBoxLayout(self)
        layout.addWidget(self.list)
        layout.addWidget(Qt.QLabel("Protocol (relative to the acq4 checkout):"))
        layout.addWidget(self.protocol)
        layout.addWidget(self.interactions)
        layout.addWidget(self.warnings)
        layout.addWidget(self.buttons)
        self._updateWarnings()

    def _buildInteractions(self):
        group = Qt.QGroupBox("Interactions")
        self.interactionsQuestion = Qt.QLabel()
        self.interactionsQuestion.setWordWrap(True)
        self.noInteractions = Qt.QRadioButton("No, they act independently")
        self.interactionsPossible = Qt.QRadioButton("Yes, they might")
        self.interactionNotes = Qt.QPlainTextEdit()
        self.interactionNotes.setPlaceholderText(
            "Optional: how they might interact, for the trial record"
        )
        for button in (self.noInteractions, self.interactionsPossible):
            button.toggled.connect(self._updateInteractions)
        layout = Qt.QVBoxLayout(group)
        for widget in (
            self.interactionsQuestion,
            self.noInteractions,
            self.interactionsPossible,
            self.interactionNotes,
        ):
            layout.addWidget(widget)
        return group

    def _updateInteractions(self, *args):
        chosen = self._chosen()
        asked = len(chosen) > 1
        self.interactions.setHidden(not asked)
        names = ", ".join(f.name for f in chosen)
        self.interactionsQuestion.setText(
            f"Could any of these change the effect of another: {names}? For example, "
            "one changes which cells reach the stage the other acts on, or both "
            "change the same measurement."
        )
        self.interactionNotes.setEnabled(self.interactionsPossible.isChecked())
        answered = (
            self.noInteractions.isChecked() or self.interactionsPossible.isChecked()
        )
        self.buttons.button(Qt.QDialogButtonBox.Ok).setEnabled(answered or not asked)

    def _chosen(self):
        items = (self.list.item(i) for i in range(self.list.count()))
        return [
            self.factors[item.text()]
            for item in items
            if item.text() in self.factors and item.checkState() == Qt.Qt.Checked
        ]

    def _updateWarnings(self, *args):
        self._updateInteractions()
        chosen = self._chosen()
        notes = []
        if chosen:
            result = catalogue.check_combination(chosen)
            notes += result.errors + result.warnings
            notes.append(scaffold.statistics_warning(chosen) or "")
        self.warnings.setText("\n".join(n for n in notes if n))

    def choice(self):
        """(factors, protocol, interactions_expected, interaction_notes)."""
        factors = self._chosen()
        if len(factors) < 2:
            expected = None
        elif self.interactionsPossible.isChecked():
            expected = True
        elif self.noInteractions.isChecked():
            expected = False
        else:
            expected = None
        notes = self.interactionNotes.toPlainText() if expected else ""
        return factors, self.protocol.text(), expected, notes


class CreateMutatorDialog(Qt.QDialog):
    """Pick a factor without a mutator, a base class and the tuning point the stub will answer."""

    def __init__(self, catalogue_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create mutator")
        self.factor = Qt.QComboBox()
        for f in catalogue.load(catalogue_path):
            if f.mutator is None:
                self.factor.addItem(f.name)
        self.base = Qt.QComboBox()
        self.base.addItems(scaffold.STUB_BASES)
        self.point = Qt.QComboBox()
        self.point.setEditable(True)
        self.param = Qt.QComboBox()
        self.param.setEditable(True)
        self.param.addItems(scaffold.profile_params())
        self.paramLabel = Qt.QLabel("Profile param (state.param):")
        self.pointHelp = Qt.QLabel()
        self.pointHelp.setWordWrap(True)
        self.problem = Qt.QLabel()
        self.problem.setWordWrap(True)
        self.problem.setStyleSheet("color: #b00020")
        self.buttons = Qt.QDialogButtonBox(
            Qt.QDialogButtonBox.Ok | Qt.QDialogButtonBox.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form = Qt.QFormLayout(self)
        form.addRow("Factor:", self.factor)
        form.addRow("Base class:", self.base)
        form.addRow("Tuning point:", self.point)
        form.addRow(self.paramLabel, self.param)
        form.addRow(self.pointHelp)
        form.addRow(self.problem)
        form.addRow(self.buttons)
        self.base.currentTextChanged.connect(self._offerPoints)
        self.point.editTextChanged.connect(self._updateOk)
        self.param.editTextChanged.connect(self._updateOk)
        self._offerPoints()

    def _isProfileParam(self):
        return self.base.currentText() == "ProfileParamMutator"

    def _offerPoints(self, *args):
        profile = self._isProfileParam()
        self.point.clear()
        self.param.setHidden(not profile)
        self.paramLabel.setHidden(not profile)
        if profile:
            scopes = [
                n
                for n, p in tuning_points.POINTS.items()
                if p.kind == "scope" and "ctx" in p.facts
            ]
            self.point.addItems(scopes)
            self.point.setCurrentText(next(iter(scaffold.ProfileParamMutator.wraps)))
            self.pointHelp.setText(
                "Pins one patch profile param for the length of a scope point. "
                "The scope must provide ctx; patching does. Pick the param, or "
                "type a new one as state.param."
            )
        else:
            kind = "value" if self.base.currentText() == "ValueMutator" else "scope"
            names = [n for n, p in tuning_points.POINTS.items() if p.kind == kind]
            self.point.addItems(names)
            self.pointHelp.setText(
                f"Pick a declared {kind} point or type a new name. A new point "
                "must be added to POINTS and asked at its site before the "
                "mutator can fire."
            )
        self._updateOk()

    def _problem(self):
        if self.factor.count() == 0:
            return "Every factor in the catalogue already has a mutator."
        if not self.point.currentText().strip():
            return "Name the tuning point this mutator answers."
        if self._isProfileParam():
            parts = self.param.currentText().strip().split(".")
            if len(parts) != 2 or not all(parts):
                return "Name the profile param as state.param, with one dot."
        return ""

    def _updateOk(self, *args):
        problem = self._problem()
        self.problem.setText(problem)
        self.buttons.button(Qt.QDialogButtonBox.Ok).setEnabled(not problem)

    def choice(self):
        """(factor_name, base, point, param); param is "state.param" for a profile-param mutator, else None."""
        param = self.param.currentText().strip() if self._isProfileParam() else None
        return (
            self.factor.currentText(),
            self.base.currentText(),
            self.point.currentText().strip(),
            param,
        )
