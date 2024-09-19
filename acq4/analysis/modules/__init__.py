import os


def listModules():
    d = os.path.dirname(__file__)
    files = []
    for f in os.listdir(d):
        if os.path.isdir(os.path.join(d, f)):
            files.append(f)
        elif f[-3:] == '.py' and f != '__init__.py':
            files.append(f[:-3])
    files.sort()
    return files


def getModuleClass(modName):
    mod = __import__(f'acq4.analysis.modules.{modName}', fromlist=['*'])
    return getattr(mod, modName)


def load(modName, host):
    cls = getModuleClass(modName)
    return cls(host)
