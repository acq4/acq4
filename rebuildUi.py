import os, sys
uic = 'pyuic4'
if len(sys.argv) > 1 and sys.argv[1] == 'pyside':
    uic = 'pyside-uic'

for path, sd, files in os.walk('.'):
    for f in files:
        base, ext = os.path.splitext(f)
        if ext != '.ui':
            continue
        ui = os.path.join(path, f)
        py = os.path.join(path, base + '.py')
        if not os.path.exists(py) or os.stat(py).st_mtime < os.stat(ui).st_mtime:
            os.system('%s %s > %s' % (uic, ui, py))
            print py