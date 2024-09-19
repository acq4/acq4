DESCRIPTION = """\
ACQ4 is a python-based platform for experimental neurophysiology. 

It includes support for standard electrophysiology, multiphoton imaging, 
scanning laser photostimulation, and many other experimental techniques. ACQ4 is
highly modular and extensible, allowing support to be added for new types of
devices, techniques, user-interface modules, and analyses.
"""

import os, sys, re
from subprocess import check_output
from setuptools import setup, find_packages

packages = [x for x in find_packages('.') if x.startswith('acq4')]


## Determine current version string
path = os.path.dirname(os.path.abspath(__file__))
initfile = os.path.join(path, 'acq4', '__init__.py')
init = open(initfile).read()
m = re.search(r'__version__ = (\S+)\n', init)
if m is None or len(m.groups()) != 1:
    raise Exception("Cannot determine __version__ from init file: '%s'!" % initfile)
version = m.group(1).strip('\'\"')
initVersion = version

# If this is a git checkout, try to generate a more decriptive version string
try:
    if os.path.isdir(os.path.join(path, '.git')):
        def gitCommit(name):
            commit = check_output(['git', 'show', name], universal_newlines=True).split('\n')[0]
            assert commit[:7] == 'commit '
            return commit[7:]
        
        # Find last tag matching "acq4-.*"
        tagNames = check_output(['git', 'tag'], universal_newlines=True).strip().split('\n')
        while True:
            if len(tagNames) == 0:
                raise Exception("Could not determine last tagged version.")
            lastTagName = tagNames.pop()
            if re.match(r'acq4-.*', lastTagName):
                break
            
        localVersion = []

        # is this commit an unchanged checkout of the last tagged version? 
        lastTag = gitCommit(lastTagName)
        head = gitCommit('HEAD')
        if head != lastTag:
            branch = re.search(r'\* (.*)', check_output(['git', 'branch'], universal_newlines=True)).group(1)
            localVersion.extend([branch, head[:10]])
        
        # any uncommitted modifications?
        modified = False
        status = check_output(['git', 'status', '-s'], universal_newlines=True).strip().split('\n')
        for line in status:
            if line.strip() != '' and line[:2] != '??':
                modified = True
                break        
                    
        if modified:
            version = localVersion.append('modified')

        if localVersion:
            version = version + '+' + '.'.join(localVersion)

    sys.stderr.write("Detected git commit; will use version string: '%s'\n" % version)
except:
    version = initVersion
    sys.stderr.write("This appears to be a git checkout, but an error occurred "
                     "while attempting to determine a version string for the "
                     "current commit.\nUsing the unmodified version string "
                     "instead: '%s'\n" % version)
    sys.excepthook(*sys.exc_info())

print("__init__ version: %s  current version: %s" % (initVersion, version))
if 'upload' in sys.argv and version != initVersion:
    print("Base version does not match current; stubbornly refusing to upload.")
    exit()




setup(
    name='acq4',
    description='Neurophysiology acquisition and analysis platform',
    long_description=DESCRIPTION,
    license='MIT',
    url='http://www.acq4.org',
    author='Luke Campagnola',
    author_email='luke.campagnola@gmail.com',
    version=version,
    packages=packages,
)

