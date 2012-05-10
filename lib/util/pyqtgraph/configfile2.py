import re, weakref, collections, sys, copy
import units
FILES = weakref.WeakValueDictionary()
GLOBAL_PATH = None # so not thread safe.

def readConfigFile(fileName, preload=True, parentLine=None):
    global FILES
    #, GLOBAL_PATH
    #if GLOBAL_PATH is not None:
        #fname2 = os.path.join(GLOBAL_PATH, fileName)
        #if os.path.exists(fname2):
            #fileName = fname2
    #GLOBAL_PATH = os.path.dirname(os.path.abspath(fileName))
    if parentLine is not None:  ## If this file was loaded directly from another config file, try checking the relative file path first.
        parentPath = os.path.split(parentLine.configFile().fileName())[0]
        fname2 = os.path.join(parentPath, fileName)
        if os.path.exists(fname2):
            fileName = fname2
        
    if fileName not in FILES:
        cfg = ConfigFile(fileName, key="Do not copy; use readConfigFile() instead.", parentLine=parentLine)
        FILES[fileName] = cfg
    return cfg



class ParseError(Exception):
    def __init__(self, message, line):
        self.lineNum = line.lineNum()
        self.line = line.text()
        #self.message = message
        self.fileName = line.configFile().fileName()
        Exception.__init__(self, message)
    
    def __str__(self):
        if self.fileName is None:
            msg = "Error parsing string at line %d:\n" % self.lineNum
        else:
            msg = "Error parsing config file '%s' at line %d:\n" % (self.fileName, self.lineNum)
        msg += "%s%s" % (self.line, self.message)
        return msg
        #raise Exception()


class ConfigLine:
    def __init__(self, line, lineNum, cfgFile):
        self._line = line
        self._lineNum = lineNum
        self._cfgFile = cfgFile
        self._stripped = line.lstrip()
        self._indent = len(line) - len(self._stripped)
        self._key = None
        self._valueStr = None
        self._value = None
    
    def indent(self):
        return self._indent
    
    def isComment(self):
        return len(self._stripped) == 0 or self._stripped[0] == '#'

    def key(self):
        if self._key is None:
            self.splitLine()
        return self._key
    
    def value(self):
        if self._value is None:
            if self._valueStr is None:
                self.splitLine()
            v = self._valueStr
            
            ## set up local variables to use for eval
            local = units.allUnits.copy()
            local['OrderedDict'] = collections.OrderedDict
            local['readConfigFile'] = lambda *args: readConfigFile(*args, parentLine=self)
            if re.search(r'\S', v) and v[0] != '#':  ## eval the value
                try:
                    val = eval(v, local)
                except:
                    ex = sys.exc_info()[1]
                    raise ParseError("Error evaluating expression '%s': [%s: %s]" % (v, ex.__class__.__name__, str(ex)), self)
            else:
                val = None
            self._value = val
        return self._value
    
    
    def splitLine(self):
        ## split line into key and value; evaluate key if needed
        if ':' not in self._stripped:
            raise ParseError('Missing colon', self)
        (k, p, v) = self._stripped.partition(':')
        k = k.strip()
        if len(k) < 1:
            raise ParseError('Missing name preceding colon', self)
        if k[0] == '(' and k[-1] == ')':  ## If the key looks like a tuple, try evaluating it.
            try:
                k1 = eval(k, local)
                if type(k1) is tuple:
                    k = k1
            except:
                pass
        self._key = k
        self._valueStr = v.strip()

    def text(self):
        return self._line
        
    def lineNum(self):
        return self._lineNum
        
    def configFile(self):
        return self._cfgFile

    def __repr__(self):
        return "[%s, %03d] %s" % (self.configFile().fileName(), self.lineNum(), self.text())
        

class ConfigData:
    def __init__(self, parent, lines):
        self._parent = parent
        self._lines = lines
        self._first = None  ## the first line containing data, usually the 'header' for this block
        self._blockLines = []  ## all lines after _first
        self._blocks = None
        self._isComment = True
        self._blockDict = None
        for i, l in enumerate(lines):
            if not l.isComment():
                self._first = l
                self._isComment = False
                self._blockLines = lines[i+1:]
                break

    def __getitem__(self, key):
        return self.blockDict()[key]
        
    def __len__(self):
        return len(self.dataBlocks())

    def items(self):
        return [(block.name(), block.value()) for block in self.dataBlocks()]
        
    def keys(self):
        return [block.name() for block in self.dataBlocks()]
        
    def values(self):
        [block.value() for block in self.dataBlocks()]
        
    def __iter__(self):
        for k in self.keys():
            yield k
            
    def iteritems(self):
        for block in self.dataBlocks():
            yield (block.name(), block.value())
            
    def iterkeys(self):
        for block in self.dataBlocks():
            yield block.name()
            
    def itervalues(self):
        for block in self.dataBlocks():
            yield block.value()
        
        
    def name(self):
        if self._isComment:
            return None
        return self._first.key()
    
    def isComment(self):
        return self._isComment
        
    def isDataBlock(self):
        return not self._isComment
        
    def indent(self):
        ## indentation level of this block
        return self._first.indent()
        
    def dataBlocks(self):
        return filter(ConfigData.isDataBlock, self.blocks())
        
    def blocks(self):
        ## return sub-blocks, one for each key at this level
        indent = None
        if self._blocks is None:
            self._blocks = []
            block = []
            for l in self._blockLines:  ## iterate over all lines after _firstLine
                if not l.isComment():
                    ind = l.indent()
                    if indent is None:
                        indent = ind
                    if ind < indent:
                        raise ParseError("Indentation error", l)
                    if ind == indent:
                        if len(block) > 0:
                            self._blocks.append(ConfigData(self, block))
                        block = []
                block.append(l)
            if len(block) > 0:
                self._blocks.append(ConfigData(self, block))
        return self._blocks
        
    def blockDict(self):
        ## return dictionary of sub-blocks
        if self._blockDict is None:
            self._blockDict = collections.OrderedDict()
            for b in self.dataBlocks():
                self._blockDict[b.name()] = b.value()
        return self._blockDict
        
    def value(self):
        if len(self) == 0:
            return self._first.value()
        else:
            return self
            
    def deepcopy(self, memo=None):
        if len(self) == 0:
            return copy.deepcopy(self.value(), memo=memo)
        else:
            return collections.OrderedDict([(block.name(), block.deepcopy(memo=memo)) for block in self.dataBlocks()])

    def __deepcopy__(self, memo):
        return self.deepcopy(memo)
            
    def preload(self):
        self.values()
        for block in self.dataBlocks():
            block.preload()
            
class ConfigFile(ConfigData):
    def __init__(self, fileName, key, preload=True, parentLine=None):
        if key != "Do not copy; use readConfigFile() instead.":
            raise Exception("ConfigFile should not be instantiated manually; use configfile.readConfigFile() instead.")
        self._fileName = fileName
        self._lines = []
        for n, line in enumerate(open(fileName, 'rb').readlines()):
            self._lines.append(ConfigLine(line, n+1, self))
        ConfigData.__init__(self, self, self._lines)
        self._blockLines = self._lines
        self._first = parentLine
        if preload:
            self.preload()
            
        
    def indent(self):
        return -1
        
    def name(self):
        if self._first is None:
            return None
        else:
            return self._first.key()
        
    def fileName(self):
        return self._fileName




if __name__ == '__main__':
    import tempfile, os
    
    def writeFile(text):
        fn = tempfile.mktemp()
        tf = open(fn, 'w')
        tf.write(text)
        tf.close()
        print "====== %s ======" % fn
        num = 1
        for line in cf.split('\n'):
            print "%02d   %s" % (num, line)
            num += 1
        print "============"
        return fn
    
    cf = """
key: 'value'
key2:              ##comment
                ##comment
    key21: 'value' ## comment
                ##comment
    key22: [1,2,3]
    key23: 234  #comment
    """
    fn1 = writeFile(cf)

    cf = """
key: 'value'
key2:              ##comment
                   ##comment
    key21: readConfigFile('%s')
    """ % os.path.split(fn1)[1]
    fn2 = writeFile(cf)
    
    
    data = readConfigFile(fn2)
    os.remove(fn1)
    os.remove(fn2)
    
    print data
    print data.keys()
    