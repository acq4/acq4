## Shell functions
import sys, os, re, threading, types, subprocess, glob, socket, __main__, copy, time, traceback

ADMIN_EMAIL = 'root'

HOST_INFO = {
  'rock': {'color': 1},
  'slate': {'color': 2},
  'underwood': {'color': 3},
  'ishmael': {'color': 4},
  'slice': {'color': 5},
  'laketahoe': {'color': 6},
  'mokelumne': {'color': 7},
  'noyo': {'color': 8},
  'tulare': {'color': 9}
}

HOSTS = HOST_INFO.keys()

HOST_GROUPS = {
  'work': ['laketahoe', 'mokelumne', 'noyo', 'tulare', 'underwood'],
  'personal': ['rock', 'slate', 'underwood']
}

FILE_GROUPS = {
  'settings': ['/home/lcampagn/.bashrc', '/home/lcampagn/.kde/share/*/kate*'],
  'libraries': ['/usr/local/lib/python2.5/site-packages/*']
}



def ls(d='.', full=False):
  if full: 
    d = os.path.abspath(d)
  if '*' in d:
    return glob.glob(d)
  if os.path.isdir(d):
    l = os.listdir(d)
    if full:
      return map(lambda s: d+'/'+s, l)
    else:
      return l
  if os.path.isfile(d):
    return [d]

def cd(*args, **kwargs):
  return os.chdir(*args, **kwargs)

#pre = dir(__main__) + dir(__main__.__builtins__)
#for p in os.environ['PATH'].split(':'):
  #files = map(os.path.realpath, ls(p, full=True))
  #for f in files:
    #if os.path.isfile(f) and os.access(f, os.X_OK) and f not in pre:
      #fn = os.path.basename(f)
      #if fn not in pre:
        #print fn, f
        #setattr(__main__, fn, lambda *args: os.system("%s %s" % (copy.copy(f), ' '.join(args))))

def date():
  lt = time.localtime()
  return "%04d.%02d.%02d" % (lt[0], lt[1], lt[2])





def color(fore=None, back=None, dim=None, bold=None, under=None, reverse=None):
  fColors = range(30, 38)
  bColors = range(40, 48)
  codes = []
  if fore is None and back is None and dim is None and bold is None and under is None and reverse is None:
    codes = [0]
  else:
    if fore is not None:
      if fore == -1:
        codes.append(39)
      fore = fore % 16
      if fore > 7:
        fore = fore % 8
        dim = True
      codes.append(fColors[fore])
    if back is not None:
      if back == -1:
        codes.append(49)
      fore = fore % 8
      codes.append(fColors[fore])
    
    if bold is True:
      codes.append(1)
    elif bold is False:
      codes.append(21)
    if dim is True:
      codes.append(2)
    elif dim is False:
      codes.append(22)
    if under is True:
      codes.append(4)
    elif under is False:
      codes.append(24)
    if reverse is True:
      codes.append(7)
    elif reverse is False:
      codes.append(27)
  
  return chr(0x1B) + '[' + ';'.join(map(str, codes)) + 'm'

def hostColor(h):
  if HOST_INFO.has_key(h) and HOST_INFO[h].has_key('color'):
    return color(HOST_INFO[h]['color'], bold=True)
  else:
    return color(-1, bold=True) 
  
def hostColored(host):
  return hostColor(host) + host + color()

class Prompt:
  def __init__(self, format="%h:%d%p "):
    if type(format) is not types.StringType:
      raise Exception("Format must be a string.")
    self.format = format
    
  def __str__(self):
    p = ''
    ctrl = False
    for c in self.format:
      if ctrl:
        ctrl = False
        if c == 'h':
          h = socket.gethostname()
          p += hostColored(h)
        elif c == 'd':
          p += color(6, dim=True) + os.getcwd() + color()
        elif c == 'p':
          if os.geteuid() == 0:
            p += color(1) + '#' + color()
          else:
            p += color(6, dim=True) + '$' + color()
        else:
          p += c
      else:
        if c == '%':
          ctrl = True
        else:
          p += c
    return p

def hostname():
  from socket import gethostname
  return gethostname()

def setPrompt():
  sys.ps1 = Prompt()

def mail(subject, body, addr=ADMIN_EMAIL, sender="SomeDude"):
  msg = "To: %s\nFrom: %s\nSubject: %s\n\n%s" % (addr, sender, subject, body)
  p = subprocess.Popen(['/usr/sbin/sendmail', addr], stdin=subprocess.PIPE, stdout=subprocess.PIPE, 
stderr=subprocess.PIPE)
  p.stdin.write(msg)
  p.stdin.close()
  r = p.wait()
  if r != 0:
    raise Exception("Failed to send email to %s" % addr, p.stdout.read())


def runCmd(cmd, printCmd=False, debug=True, shell=True, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.STDOUT):
  if printCmd:
    sys.stderr.write(cmd + '\n')
  c = subprocess.Popen(cmd, stdout=stdout, stderr=stderr, shell=shell)
  rval = c.wait()
  stdout = c.stdout.read()
  #stderr = c.stderr.read()
  if debug and rval != 0:
    sys.stderr.write("WARNING--Command failed (returned %d):\n  %s\n" % (rval, cmd))
    if type(cmd) is types.StringType and ' ' in cmd and not shell:
      print "  (Perhaps you want to run this command with shell=True?)"
    sys.stderr.write("--OUTPUT--\n" + stdout)
    #sys.stderr.write("\n--STDERR--\n" + stderr)
  return (rval, stdout)

def runParallel(template, values, *args, **kwargs):
  kwargs['shell'] = True
  if type(values) in [types.ListType, types.TupleType]:
    threads = []
    results = []
    for i in values:
      threads.append(CmdThread(template % i, *args, **kwargs))
      threads[-1].start()
    for i in threads:
      i.join()
      results.append((i.rval, i.stdout, i.stderr))
  elif type(values) is types.DictType:
    threads = {}
    results = {}
    for i in values.keys():
      threads[i] = CmdThread(template % i, *args, **kwargs)
      threads[i].start()
    for i in threads.keys():
      threads[i].join()
      results[i] = (threads[i].rval, threads[i].stdout, threads[i].stderr)
  else:
    raise Exception("Only list, tuple, or dict types accepted for values argument")
  return results
  
  
#def callParallel(func, values, *args, **kwargs):
  #if type(values) in [types.ListType, types.TupleType]:
    #threads = []
    #results = []
    #for i in values:
      #if type(i) in [types.ListType, types.TupleType]:
        #args2 = tuple(i) + tuple(args)
        #threads.append(FuncThread(func, args2, kwargs))
      #elif type(i) is types.DictType:
        #kwargs2 = kwargs.copy()
        #for k in i.keys():
          #kwargs2[k] = i[k]
        #threads.append(FuncThread(func, args, kwargs2))
      #else:
        #args2 = (i,) + args
        #threads.append(FuncThread(func, args2, kwargs))
      #threads[-1].start()
    #for i in threads:
      #i.join()
      #results.append(i.result)
  #elif type(values) is types.DictType:
    #threads = {}
    #results = {}
    #for i in values.keys():
      #if type(values[i]) in [types.ListType, types.TupleType]:
        #args2 = tuple(values[i]) + tuple(args)
        #threads[i] = FuncThread(func, args2, kwargs)
      #elif type(values[i]) is types.DictType:
        #kwargs2 = kwargs.copy()
        #for k in values[i].keys():
          #kwargs2[k] = values[i][k]
        #threads[i] = FuncThread(func, args, kwargs2)
      #else:
        #args2 = (values[i],) + tuple(args)
        #threads[i] = FuncThread(func, args2, kwargs)
      #threads[i].start()
    #for i in threads.keys():
      #threads[i].join()
      #results[i] = (threads[i].result)
  #else:
    #raise Exception("Only list, tuple, or dict types accepted for values argument")
  #return results
  
  
class CmdThread(threading.Thread):
  def __init__(self, *args, **kwargs):
    self.args = args
    self.kwargs = kwargs
    threading.Thread.__init__(self)
    
  def run(self):
    (self.rval, self.stdout, self.stderr) = runCmd(*self.args, **self.kwargs)
    
    
class FuncThread(threading.Thread):
  def __init__(self, func, *args, **kwargs):
    self.func = func
    self.args = args
    self.kwargs = kwargs
    threading.Thread.__init__(self)
    
  def run(self):
    self.result = self.func(*self.args, **self.kwargs)
    
    
def ping(host, timeout=5, tries=1, *args, **kwargs):
  return runCmd(('/bin/ping', '-c%d' % tries, '-W%0.2f' % timeout, host), *args, **kwargs)

def sshTest(hosts, timeout=5, *args, **kwargs):
  if type(hosts) is types.StringType:
    hosts = [hosts]
  res = runParallel('ssh -o ConnectTimeout=%d %%s true' % timeout, hosts, *args, **kwargs)
  up = []
  for i in range(0, len(hosts)):
    if res[i][0] == 0:
      up.append(hosts[i])
  return up


def blast(files, hosts=None):
  ckFiles = []
  if type(files) is not types.ListType:
    files = [files]
  for f in files:
    f1 = glob.glob(os.path.abspath(f))
    if len(f1) == 0:
      sys.stderr.write("Warning: Can not find file '%s', skipping.\n" % f)
    else:
      ckFiles.extend(f1)
  if len(ckFiles) == 0:
    return
  
  if hosts is None:
    hosts = HOSTS 
  hosts = sshTest(hosts)
  
  print "Blasting files: %s\nTo hosts: %s" % (str(ckFiles), str(hosts))
  for f in ckFiles:
    cmd = "scp -pr %s %%s:%s" % (f, f)
    res = runParallel(cmd, hosts) 
    fail = {}
    for i in range(0, len(hosts)):
      if res[i][0] != 0:
        fail[hosts[i]] = res
        print color(1) + "[FAIL] %s:%s\n  %s" % (hostColored(hosts[i]), f, res[2])
    if len(fail) == 0:
      print color(2) + "[ OK ] %s" % f + color()
      
def remoteRun(cmd, hosts=HOSTS):
  hosts = sshTest(hosts)
  sshCmd = 'ssh %%s "cd %s; %s"' % (os.getcwd(), cmd)
  print "Running command: %s\nOn hosts: %s" % (sshCmd, str(hosts))
  res = runParallel(sshCmd, hosts)
  fail = {} 
  for i in range(0, len(hosts)):
    if res[i][0] != 0:
      fail[hosts[i]] = res
      print color(1) + "[FAIL] %s:" % (hostColored(hosts[i]))
    else:
      print color(2) + "[ OK ] %s:" % (hostColored(hosts[i]))
    
    if len(res[i][1]) > 0:
      print res[i][1]
    if len(res[i][2]) > 0:
      print "  %s--stderr--%s\n%s" % (color(1), color(), res[i][2])
      
  if len(fail) == 0:
    print color(2) + "[ ALL OK ]" + color()
  
      

def openSsh(host, user=None, port=None):
  return socket

def closeSsh(socket, host):
  pass

def backup(backupHost, dataHost, baseDir, dirList, excludes, logFile, bwLimit=None):
  today = date()
  
  backupDir = baseDir + '/current/'
  if backupHost is not None:
    backupDir = backupHost + ':' + backupDir
  
  trash = baseDir + '/' + today
  
  excludeStr = ''
  for ex in excludes:
    excludeStr += " --exclude '%s'" % ex
  
  if dataHost is None:
    dirList = ["'" + "' '".join(dirList) + "'"]
  else:
    for i in range(0, len(dirList)):
      dirList[i] = "'" + dataHost + ':' + dirList[i] + "'"
  
  if bwLimit is None:
    bwLimit = ''
  else:
    bwLimit = "--bwlimit=%d" % bwLimit
  
  log = open(logFile, 'a')
  log.write('\n----------- Starting backup log for %s --------------\n'%today)
  log.flush()
  
  try:
    for d in dirList:
      cmd = "rsync -rltDvR --chmod=o-rwx,u+w %s --itemize-changes --delete %s --backup --backup-dir='%s' %s '%s'" % (bwLimit, excludeStr, trash, d, backupDir)
      log.write("Running command for [%s]: %s\n" % (d, cmd))
      p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
      while True:
        l = p.stdout.read(1)
        if l == '':
          break
        log.write(l)
        log.flush()
      ret = p.wait()
    
      if ret != 0:
        raise Exception("rsync returned %d" % ret)
  except:
    log.write("Exception during backup: %s\nBacktrace:\n" % str(sys.exc_info()[1].args))
    traceback.print_exc(file=log)
    try:
      mail(subject="Backup for %s failed"%hostname(), body='fail.\nPlease check log file %s' % (logFile), sender="backups@%s" % hostname())
    except:
      print "Could not send mail."
      traceback.print_exc()
  log.write('----------- backup for %s finished ------------------\n'%today)
  log.close()
  
  
