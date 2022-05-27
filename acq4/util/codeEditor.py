import sys, glob, os, subprocess
from acq4 import getManager


suggestedEditorOrder = ['vscode', 'sublime', 'pycharm']

editorCommands = {
    'pycharm': {
        'win32': {
            'bin_globs': [
                r"C:\Program Files\JetBrains\Pycharm*\bin\pycharm64.exe",
                r"C:\Users\{user}\AppData\Local\Programs\JetBrains\Pycharm*\bin\pycharm64.exe",
            ],
            'command': '"{bin}" --line {lineNum} {fileName}',
        },
        'linux': {
            'bin_globs': ['/snap/bin/pycharm-community'],
            'command': '"{bin}" --line {lineNum} {fileName}',
        }
    },
    'vscode': {
        'win32': {
            'command': 'code -g {fileName}:{lineNum}',
        },
        'linux': {
            'command': 'code -g {fileName}:{lineNum}',
        },
        'darwin': {
            'command': 'code -g {fileName}:{lineNum}',
        },
    },
    'sublime': {
        'win32': {
            'bin_globs': [
                'C:\Program Files\Sublime Text\subl.exe',
                'C:\Program Files (x86)\Sublime Text\subl.exe',
            ],
            'command': '"{bin}" {fileName}:{lineNum}',
        },
        'darwin': {
            'bin_globs': ['/Applications/Sublime Text.app/Contents/SharedSupport/bin/subl'],
            'command': '"{bin}" {fileName}:{lineNum}',
        },
        'linux': {
            'bin_globs': ['/usr/bin/subl', '/usr/local/bin/subl'],
            'command': '"{bin}" {fileName}:{lineNum}',
        },
    }
}


def codeEditorCommand():
    f"""Return a format string that generates a command to invoke a code editor.

    The format string must contain ``{{fileName}}`` and ``{{lineNum}}`` variables.
    
    By default, this function looks for a few common editors: {suggestedEditorOrder}.
    The return value can also be determined by the acq4 configuration, where it can 
    be either one of the editors shown above or a full command format string for any
    editor::
    
        <default.cfg>:
            misc:
                codeEditor: r'"C:\Program Files\MyEditor\editor.exe" {{fileName}}:{{lineNum}}'
    """
    man = getManager()
    cmd = man.config.get('misc', {}).get('codeEditor', None)
    if cmd is None:
        return suggestCodeEditor()
    if cmd in suggestedEditorOrder:
        return generateEditorCommand(cmd)
    else:
        return cmd


def suggestCodeEditor():
    """Suggest a command for invoking a code editor that is present on the system.
    """
    for editor in suggestedEditorOrder:
        try:
            cmd = generateEditorCommand(editor)
        except Exception:
            continue
        return cmd


def generateEditorCommand(editor):
    """Generate a command format string for a known code editor"""
    if editor not in editorCommands:
        raise ValueError(f"Unknown editor '{editor}'. See `editorCommands` in acq4/util/codeEditor.py.")
    plat = sys.platform
    if plat not in editorCommands[editor]:
        raise Exception(f"Invoking `{editor}` is not yet supported on this platform ({plat}). See `editorCommands` in acq4/util/codeEditor.py.")

    commandTemplate = editorCommands[editor][plat]['command']
    if '{bin}' in commandTemplate:
        for binGlob in editorCommands[editor][plat]['bin_globs']:
            candidates = glob.glob(binGlob.format(user=os.getlogin()))
            if len(candidates) > 0:
                break

        if len(candidates) == 0:
            return Exception(f"Could not find {editor} in default search paths. See `editorCommands` in acq4/util/codeEditor.py.")

        binPath = candidates[0]
    else:
        binPath = None

    return commandTemplate.format(bin=binPath, lineNum='{lineNum}', fileName='{fileName}')


def invokeCodeEditor(fileName, lineNum, command=None):
    if command is None:
        command = codeEditorCommand()
    subprocess.Popen(command.format(fileName=fileName, lineNum=lineNum), shell=True)
