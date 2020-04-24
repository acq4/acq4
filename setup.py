from __future__ import print_function
DESCRIPTION = """\
ACQ4 is a python-based platform for experimental neurophysiology. 

It includes support for standard electrophysiology, multiphoton imaging, 
scanning laser photostimulation, and many other experimental techniques. ACQ4 is
highly modular and extensible, allowing support to be added for new types of
devices, techniques, user-interface modules, and analyses.
"""

import os, sys, re, shutil
from subprocess import check_output

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

import distutils.sysconfig as sysconfig



setupOpts = dict(
    name='acq4',
    description='Neurophysiology acquisition and analysis platform',
    long_description=DESCRIPTION,
    license='MIT',
    url='http://www.acq4.org',
    author='Luke Campagnola',
    author_email='luke.campagnola@gmail.com',
)

## generate list of all sub-packages
path = os.path.abspath(os.path.dirname(__file__))
n = len(path.split(os.path.sep))
subdirs = [i[0].split(os.path.sep)[n:] for i in os.walk(os.path.join(path, 'acq4')) if '__init__.py' in i[2]]
allPackages = ['.'.join(p) for p in subdirs]

## Make sure build directory is clean before installing
buildPath = os.path.join(path, 'build')
if os.path.isdir(buildPath):
    shutil.rmtree(buildPath)


## Determine current version string
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
            
        # is this commit an unchanged checkout of the last tagged version? 
        lastTag = gitCommit(lastTagName)
        head = gitCommit('HEAD')
        if head != lastTag:
            branch = re.search(r'\* (.*)', check_output(['git', 'branch'], universal_newlines=True)).group(1)
            version = version + "-%s-%s" % (branch, head[:10])
        
        # any uncommitted modifications?
        modified = False
        status = check_output(['git', 'status', '-s'], universal_newlines=True).strip().split('\n')
        for line in status:
            if line.strip() != '' and line[:2] != '??':
                modified = True
                break        
                    
        if modified:
            version = version + '+'
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

import distutils.command.build

class Build(distutils.command.build.build):
    def run(self):
        ret = distutils.command.build.build.run(self)
        
        # If the version in __init__ is different from the automatically-generated
        # version string, then we will update __init__ in the build directory
        global path, version, initVersion
        if initVersion == version:
            return ret
        
        initfile = os.path.join(path, self.build_lib, 'acq4', '__init__.py')
        if not os.path.isfile(initfile):
            sys.stderr.write("Warning: setup detected a git install and attempted "
                             "to generate a descriptive version string; however, "
                             "the expected build file at %s was not found. "
                             "Installation will use the original version string "
                             "%s instead.\n" % (initfile, initVersion)
                             )
        else:
            data = open(initfile, 'r').read()
            open(initfile, 'w').write(re.sub(r"__version__ = .*", "__version__ = '%s'" % version, data))


        # If this is windows, we need to update acq4.bat to reference the correct python executable.
        if sys.platform == 'win32':
            runner = os.path.join(path, self.build_scripts, 'acq4.bat')
            runcmd = "%s -m acq4" % sys.executable
            data = open(runner, 'r').read()
            open(runner, 'w').write(re.sub(r'python -m acq4', runcmd, data))
        return ret

# copy config tree to system location
# if sys.platform == 'win32':
#     dataRoot = os.path.join(os.environ['ProgramFiles'], 'acq4')
# elif sys.platform == 'darwin':
#     dataRoot = 'Library/Application Support/acq4'
# else:
#     dataRoot = '/etc/acq4'

# instead, just install config example to same path as package.
if sys.platform == 'win32':
    #dataRoot = distutils.sysconfig.get_python_lib().replace(sys.prefix, '')
    dataRoot = 'Lib/site-packages/acq4'
else:
    #dataRoot = 'python%d.%d/site-packages/acq4' % (sys.version_info.major, sys.version_info.minor)
    dataRoot = distutils.sysconfig.get_python_lib().replace(sys.prefix+'/', '') + '/acq4'

dataFiles = []
configRoot = os.path.join(path, 'config')
for subpath, _, files in os.walk(configRoot):
    endPath = subpath[len(path):].lstrip(os.path.sep) 
    files = [os.path.join(endPath, f) for f in files]
    dataFiles.append((os.path.join(dataRoot, endPath), files))
    # print dataFiles[-1]

packageData = []
pkgRoot = os.path.join(path, 'acq4')
for subpath, _, files in os.walk(pkgRoot):
    for f in files:
        addTo = None
        for ext in ['.png', '.cache', '.h', '.hpp', '.dll']:
            if f.endswith(ext):
                packageData.append(os.path.join(subpath, f)[len(pkgRoot):].lstrip(os.path.sep))


if sys.platform == 'win32':
    scripts = ['bin/acq4.bat']
else:
    scripts = ['bin/acq4']

setup(
    version=version,
    cmdclass={'build': Build},
    packages=allPackages,
    package_dir={},
    package_data={'acq4': packageData},
    data_files=dataFiles,
    classifiers = [
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Development Status :: 4 - Beta",
        "Environment :: Other Environment",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering",
        ],
    install_requires = [
        'numpy',
        'scipy',
        'h5py',
        'pillow',
        ],
    scripts = scripts,
    **setupOpts
)


