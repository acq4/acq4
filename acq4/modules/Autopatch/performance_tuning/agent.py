"""Launches a configured agent command in an analysis directory, or falls back to the code editor."""

import shlex
import subprocess
from pathlib import Path

FIXED_PROMPT = "Read BRIEF.md and build the analysis it asks for."


def agent_command(config):
    return config.get("misc", {}).get("analysisAgent")


def launch(analysis_dir, config, open_editor):
    command = agent_command(config)
    if command is None:
        open_editor(str(Path(analysis_dir) / "BRIEF.md"))
        return "editor"
    subprocess.Popen(command.format(dir=shlex.quote(str(analysis_dir))), shell=True)
    return "agent"
