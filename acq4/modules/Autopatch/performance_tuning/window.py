"""The performance tuning review window: trials by run group, with dialogs over the lifecycle steps."""

import json
from pathlib import Path

from acq4.util import Qt
from acq4.util.codeEditor import invokeCodeEditor

from . import brief, catalogue, lifecycle, record, report, scaffold
from .lifecycle import REFUSALS, Refused

DEFAULT_PROTOCOL = "acq4/modules/Autopatch/example_protocols/example_patch.py"
STANDALONE_TOOLTIP = (
    "Arming needs a running Autopatch window: open this from its "
    "Performance tuning button."
)
TRIAL_COLUMNS = ("Trial", "Title", "Primary factor", "Status", "Cells", "Days", "")


class TuningWindow(Qt.QMainWindow):
    def __init__(
        self,
        autopatch=None,
        trials_dir=record.TRIALS_DIR,
        catalogue_path=catalogue.DEFAULT_PATH,
        manager=None,
    ):
        super().__init__()
        self.autopatch = autopatch
        self.trials_dir = Path(trials_dir)
        self.catalogue_path = Path(catalogue_path)
        if manager is None and autopatch is not None:
            manager = autopatch.manager
        self.manager = manager
        self.tuningWarnings = []
        self._warnings = lifecycle.WarningCollector(self._addTuningWarning)
        self._openUrl = Qt.QDesktopServices.openUrl
        self.setWindowTitle("Autopatch performance tuning")
        self._buildUi()
        if autopatch is None:
            for btn in (self.armBtn, self.disarmBtn):
                btn.setEnabled(False)
                btn.setToolTip(STANDALONE_TOOLTIP)
        self.refresh()

    # -- lifecycle -------------------------------------------------------

    def newRunGroup(self, factors, protocol, signoff, run_id=None):
        trials = scaffold.new_run_group(
            factors,
            protocol,
            signoff,
            run_id=run_id,
            trials_dir=self.trials_dir,
            catalogue_path=self.catalogue_path,
        )
        self.refresh()
        return trials

    def armWarnings(self, trial):
        return lifecycle.arm_warnings(trial)

    def arm(self, trial):
        if self.autopatch is None:
            raise Refused(STANDALONE_TOOLTIP)
        lifecycle.arm(self.autopatch, self.manager, self.trials_dir, trial)
        self._warnings.start()
        self.refresh()

    def disarm(self):
        if self.autopatch is None:
            raise Refused(STANDALONE_TOOLTIP)
        lifecycle.disarm(self.autopatch)
        self._warnings.stop()
        self.refresh()

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
        if (analysis_dir / lifecycle.SCRIPT_NAME).exists():
            return lifecycle.run_script(analysis_dir)
        notebook = analysis_dir / lifecycle.NOTEBOOK_NAME
        if not notebook.exists():
            raise lifecycle.missing_analysis(analysis_dir)
        self._openUrl(Qt.QUrl.fromLocalFile(str(notebook)))
        return None

    def accept(self, trial, analysis_dir, verdict):
        lifecycle.accept(self.catalogue_path, trial, analysis_dir, verdict)
        self.refresh()

    def reject(self, trial, note):
        lifecycle.reject(trial, note)
        self.refresh()

    def abandon(self, trial, reason):
        lifecycle.abandon(self.catalogue_path, trial, reason)
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

        buttons = Qt.QGridLayout()
        actions = [
            ("newRunGroupBtn", "New run group…", self._onNewRunGroup),
            ("armBtn", "Arm", self._onArm),
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

        right = Qt.QWidget()
        layout = Qt.QVBoxLayout(right)
        layout.addWidget(self.details, 2)
        layout.addLayout(buttons)
        layout.addWidget(Qt.QLabel("Analyses (newest first)"))
        layout.addWidget(self.analysesList, 1)
        layout.addWidget(self.analysisView, 3)
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
        for run_id, group in groups.items():
            node = Qt.QTreeWidgetItem([run_id])
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
                    f"Signoff: {trial.interaction_signoff.strip() or 'none'}",
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
                Qt.QMessageBox.warning(self, "Refused", str(exc))

        return run

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

    def _onArm(self):
        def arm():
            trial = self._needTrial()
            found = self.armWarnings(trial)
            if found:
                answer = Qt.QMessageBox.question(
                    self,
                    "Arm with warnings?",
                    "\n".join(found)
                    + f"\n\nSignoff: {trial.interaction_signoff.strip() or 'none'}",
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
            self._onTrialSelected()

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

    def closeEvent(self, event):
        self._warnings.stop()
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
    """Pick factors from the catalogue, a protocol and an interaction signoff."""

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
        self.signoff = Qt.QPlainTextEdit()
        self.warnings = Qt.QLabel()
        self.warnings.setWordWrap(True)
        box = Qt.QDialogButtonBox(Qt.QDialogButtonBox.Ok | Qt.QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout = Qt.QVBoxLayout(self)
        layout.addWidget(self.list)
        layout.addWidget(Qt.QLabel("Protocol (relative to the acq4 checkout):"))
        layout.addWidget(self.protocol)
        layout.addWidget(Qt.QLabel("Interaction signoff:"))
        layout.addWidget(self.signoff)
        layout.addWidget(self.warnings)
        layout.addWidget(box)
        self._updateWarnings()

    def _chosen(self):
        items = (self.list.item(i) for i in range(self.list.count()))
        return [
            self.factors[item.text()]
            for item in items
            if item.text() in self.factors and item.checkState() == Qt.Qt.Checked
        ]

    def _updateWarnings(self, *args):
        chosen = self._chosen()
        notes = []
        if chosen:
            result = catalogue.check_combination(chosen)
            notes += result.errors + result.warnings
            notes.append(scaffold.statistics_warning(chosen) or "")
        self.warnings.setText("\n".join(n for n in notes if n))

    def choice(self):
        return self._chosen(), self.protocol.text(), self.signoff.toPlainText()
