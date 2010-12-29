import os

def listModules():
    d = os.path.split(__file__)[0]
    files = []
    for f in os.listdir(d):
        if os.path.isdir(f):
            files.append(f)
        elif files[-3:] == '.py':
            files.append(f[:-3])
    return files
    
def getModuleClass(modName):
    mod = __import__(modName, fromlist=['*'])
    cls = getattr(mod, modName)
    return cls

