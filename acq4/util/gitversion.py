from __future__ import print_function
import os, re, subprocess


def getGitVersion(tagPrefix, repoDir):
    """Return a version string with information about this git checkout.
    If the checkout is an unmodified, tagged commit, then return the tag version.
    If this is not a tagged commit, return the output of ``git describe --tags``.
    If this checkout has been modified, append "+" to the version.
    """
    if not os.path.isdir(os.path.join(repoDir, '.git')):
        return None
        
    v = subprocess.check_output(['git', '-C', repoDir, 'describe', '--tags', '--dirty', '--match=%s*'%tagPrefix]).strip().decode('utf-8')
    
    # chop off prefix
    assert v.startswith(tagPrefix)
    v = v[len(tagPrefix):]
    v = v.lstrip('-')

    # split up version parts
    parts = v.split('-')
    
    # has working tree been modified?
    modified = False
    if parts[-1] == 'dirty':
        modified = True
        parts = parts[:-1]
        
    # have commits been added on top of last tagged version?
    # (git describe adds -NNN-gXXXXXXX if this is the case)
    local = None
    if len(parts) > 2 and re.match(r'\d+', parts[-2]) and re.match(r'g[0-9a-f]{7}', parts[-1]):
        local = parts[-1]
        parts = parts[:-2]
        
    gitVersion = '-'.join(parts)
    if local is not None:
        gitVersion += '+' + local
    if modified:
        gitVersion += 'm'

    return gitVersion

