import os


def listAtlases():
    d = os.path.split(__file__)[0]
    files = []
    ignores = ['__init__.py', 'Atlas.py', 'atlasCtrlTemplate.py']
    for f in os.listdir(d):
        if os.path.isdir(os.path.join(d, f)):
            files.append(f)
        elif f[-3:] == '.py' and f not in ignores:
            files.append(f[:-3])
    return files


def getAtlasClass(modName):
    mod = __import__('acq4.util.atlas.' + modName, fromlist=['*'])
    return getattr(mod, modName)
