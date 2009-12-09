# -*- coding: utf-8 -*-
from pyparsing import *
import sys, re, os
import ctypes
ParserElement.enablePackrat()

#__all__ = ['parseFiles', 'CParser']

def parseFiles(files, cache=None, **args):
    """Convenience function allowing one-line parsing of C files. 
    Returns a dictionary of all data processed.
    The 'cache' argument is passed to CParser.processAll.
    All extra arguments are passed to CParser.__init__"""
    p = CParser(files, **args)
    p.processAll(cache)
    data = {}
    for k in p.dataList:
        data[k] = getattr(p, k)
    return data

class CParser():
    """Class for parsing C code to extract variable, struct, enum, and function declarations as well as preprocessor macros. This is not a complete C parser; instead, it is meant to simplify the process
    of extracting definitions from header files in the absence of a complete build system. Many files 
    will require some amount of manual intervention to parse properly (see 'replace' and extra arguments 
    to __init__)
    
    Usage:
        ## create parser object, load two files
        p = CParser(['header1.h', 'header2.h'])
        
        ## remove comments, preprocess, and search for declarations
        p.processAll()
        
        ## just to see what was successfully parsed from the files
        p.printAll() 
        
        ## access parsed declarations 
        allValues = p.defs['values']
        functionSignatures = p.defs['functions']
        ...
        
        ## To see what was not successfully parsed:
        unp = p.processAll(returnUnparsed=True)
        for s in unp:
            print s
    """
    
    def __init__(self, files=None, replace=None, copyFrom=None, **args):
        """Create a C parser object fiven a file or list of files. Files are read to memory and operated
        on from there.
            'replace' may be specified to perform string replacements before parsing.
               format is {'searchStr': 'replaceStr', ...}
            Extra parameters may be used to specify the starting state of the parser. For example,
            one could provide a set of missing type declarations by
                types={'UINT': ('unsigned int'), 'STRING': ('char', 1)}
            Similarly, preprocessor macros can be specified:
                macros={'WINAPI': ''}
        """
        
        self.defs = {}  ## holds all definitions
        self.fileDefs = {}  ## holds definitions grouped by the file they came from
        
        self.initOpts = args.copy()
        self.initOpts['files'] = files
        self.initOpts['replace'] = replace
        
        self.dataList = ['types', 'variables', 'fnmacros', 'macros', 'structs', 'enums', 'functions', 'values']
            
            
        # placeholders for definitions that change during parsing
        self.macroExpr = Forward()
        self.fnMacroExpr = Forward()
        self.definedType = Forward()
        self.definedStruct = Forward()
        self.definedEnum = Forward()
        
        
        self.files = {}
        if files is not None:
            if type(files) is str:
                files = [files]
            self.fileOrder = files
            for f in files:
                self.loadFile(f)
                    
        ## initialize empty definition lists
        for k in self.dataList:
            self.defs[k] = {}
            #for f in files:
                #self.fileDefs[f][k] = {}
                
        self.currentFile = None
        
        # Import extra arguments if specified
        for t in args:
            for k in args[t].keys():
                self.addDef(t, k, args[t][k])
        
        # Import from other CParsers if specified
        if copyFrom is not None:
            if type(copyFrom) not in [list, tuple]:
                copyFrom = [copyFrom]
            for p in copyFrom:
                self.importDict(p.fileDefs)
    
    def loadFile(self, file):
        fd = open(file)
        self.files[file] = fd.read()
        fd.close()
        #self.fileDefs[f] = {}
        
        if replace is not None:
            for s in replace:
                self.files[file] = re.sub(s, replace[s], self.files[file])
    
    def processAll(self, file=None, cache=None, returnUnparsed=False, printAfterPreprocess=False, noCacheWarning=False):
        """Remove comments, preprocess, and parse for declarations. Operates on the file named
        or all files in series if not specified. (operates in memory; does not alter the original files)
        Returns a list of the results from parseDefs.
           'cache' may specify a file where cached results are be stored or retreved. The cache
               is automatically invalidated if any of the arguments to __init__ are changed, or if the 
               C files are newer than the cache. Only valid if 'file' is None.
           'returnUnparsed' is passed directly to parseDefs."""
        if file is None:
            if self.loadCache(cache, checkValidity=True):
                #print "used cache"
                return  ## cached values loaded successfully, nothing left to do here
            else:
                #print "ignored cache"
                files = self.fileOrder
        else:
            files = [file]
        
        results = []
        if noCacheWarning:
            print "Parsing C header files (no valid cache found). This could take several minutes..."
        for f in files:
            self.removeComments(f)
            self.preprocess(f)
            if printAfterPreprocess:
                print "===== PREPROCSSED %s =======" % f
                print self.files[f]
            results.append(self.parseDefs(f, returnUnparsed))
        
        if cache is not None:
            self.writeCache(cache)
            #print "wrote cache"
            
        return results
        
            
    def loadCache(self, cacheFile, checkValidity=False):
        """Load a cache file
        if checkValidity=True, then run several checks before loading the cache:
           - cache file must not be older than any source files
           - cache file must not be older than this library file
           - options recorded in cache must match options used to initialize CParser"""
        
        ## make sure cache file exists 
        if type(cacheFile) is not str:
            raise Exception("cache file option myst be a string.")
        if not os.path.isFile(cacheFile):
            d = os.path.dirname(__file__)  ## If file doesn't exist, search for it in this module's path
            cacheFile = os.path.join(d, cacheFile)
            if not os.path.isFile(cacheFile):
                return False
        
        ## make sure cache is newer than all input files and this code
        if checkValidity:
            mtime = os.stat(cacheFile).st_mtime
            if os.stat(__file__).st_mtime > mtime:
                return False
            for f in self.fileOrder:
                if os.stat(f).st_mtime > mtime:
                    return False
        
        try:
            ## read cache file
            import pickle
            cache = pickle.load(open(cacheFile))
            
            ## make sure __init__ options match
            if checkValidity and (cache['opts'] != self.initOpts):
                return False
                
            ## import all parse results
            self.importDict(cache['fileDefs'])
            #for k in self.dataList:
                #setattr(self, k, cache[k])
            return True
        except:
            print "Warning--cache is invalid, ignoring."
            return False

    def importDict(self, data):
        for f in data.keys():
            self.currentFile = f
            for k in self.dataList:
                for n in data[f][k]:
                    self.addDef(k, n, data[f][k][n])

    def writeCache(self, cacheFile):
        """Store all parsed declarations to cache."""
        cache = {}
        cache['opts'] = self.initOpts
        cache['fileDefs'] = self.fileDefs
        #for k in self.dataList:
            #cache[k] = getattr(self, k)
        import pickle
        pickle.dump(cache, open(cacheFile, 'w'))


    def removeComments(self, file):
        """Remove all comments from file. (operates in memory; does not alter the original files)"""
        text = self.files[file]
        cplusplusLineComment = Literal("//") + restOfLine
        self.files[file] = (cStyleComment | cplusplusLineComment).ignore(quotedString).suppress().transformString(text)
        
    
    def preprocess(self, file):
        """Scan named file for preprocessor directives, removing them while expanding macros. (operates in memory; does not alter the original files)"""
        self.currentFile = file
        text = self.files[file]
        ppDirective = Combine("#" + Word(alphas)) + restOfLine
        
        # define the structure of a macro definition (the empty term is used 
        # to advance to the next non-whitespace character)
        ppDefine = Keyword("#define") + ident.setWhitespaceChars(' \t').setResultsName("macro") + Optional(lparen + delimitedList(ident) + rparen).setWhitespaceChars(' \t').setResultsName('args') + restOfLine.setResultsName("value")
        # attach parse actions to expressions
        ppDefine.setParseAction(self.processMacroDefn)
        
        self.updateMacroDefns()

        # define pattern for scanning through the input string
        self.macroExpander = (self.macroExpr | self.fnMacroExpr | ppDefine.suppress() | ppDirective.suppress()).ignore(quotedString)
        self.files[file] =  self.macroExpander.transformString(text)

    def updateMacroDefns(self):
        self.macroExpr << MatchFirst( [Keyword(m).setResultsName('macro') for m in self.defs['macros']] )
        self.macroExpr.setParseAction(self.processMacroRef)

        self.fnMacroExpr << MatchFirst( [(Keyword(m).setResultsName('macro') + lparen + Group(delimitedList(expression)).setResultsName('args') + rparen) for m in self.defs['fnmacros']] )
        self.fnMacroExpr.setParseAction(self.processFnMacroRef)        
        
    def parseDefs(self, file, returnUnparsed=False):
        """Scan through the named file for variable, struct, enum, and function declarations.
        Returns the entire tree of successfully parsed tokens.
        If returnUnparsed is True, return a string of all lines that failed to match (for debugging)."""
        self.currentFile = file
        self.definedType << kwl(self.defs['types'].keys())
    
        parser = self.buildParser()
        if returnUnparsed:
            text = parser.suppress().transformString(self.files[file])
            return re.sub(r'\n\s*\n', '\n', text)
        else:
            return [x[0] for x in parser.scanString(self.files[file])]

    def buildParser(self):
        self.structType = Forward()
        enumType = Forward()
        self.typeSpec = typeQualifier + Group(fundType | Optional(kwl(sizeModifiers + signModifiers)) + self.definedType | self.structType | enumType).setResultsName('type') + typeQualifier

        ## typedef
        self.typeDecl = Keyword('typedef') + Group(self.typeSpec) + Group(delimitedList(Group(typeQualifier + stars.setResultsName('ptrs') + typeQualifier + ident.setResultsName('newType') + ZeroOrMore(arrayOp).setResultsName('arr')))) + semi
        self.typeDecl.setParseAction(self.processTypedef)

        ## variable declaration
        variableSingleDecl = Group(self.typeSpec + stars + typeQualifier + ident.setResultsName('name')) + Optional(Literal('=').suppress() + expression.setResultsName('value'))

        self.variableDecl = Group(self.typeSpec.setResultsName('type') + stars + typeQualifier + ident.setResultsName('name') + ZeroOrMore(arrayOp).setResultsName('arr')) + Optional(Literal('=').suppress() + (expression.setResultsName('value') | (lbrace + Group(delimitedList(expression)).setResultsName('arrayValue') + rbrace))) + semi
        self.variableDecl.setParseAction(self.processVariable)
        
        ## Struct definition
        self.structDecl = Forward()
        self.updateStructDefn()
        
        self.structDecl = self.structType + semi

        ## enum definition
        enumVarDecl = Group(ident.setResultsName('name')  + Optional(Literal('=').suppress() + integer.setResultsName('value')))
        
        enumType << Keyword('enum') + (self.definedEnum.setResultsName('name') | Optional(ident).setResultsName('name') + lbrace + Group(delimitedList(enumVarDecl)).setResultsName('members') + rbrace)
        enumType.setParseAction(self.processEnum)
        
        enumDecl = enumType + semi

        ## function definition
        functionDecl = self.typeSpec.setResultsName('type') + stars + ident.setResultsName('name') + lparen + Group(Optional(delimitedList(variableSingleDecl))).setResultsName('args') + rparen + (nestedExpr('{', '}').suppress() | semi)
        functionDecl.setParseAction(self.processFunction)
        
        return (self.typeDecl ^ self.structDecl ^ enumDecl ^ self.variableDecl ^ functionDecl)
    
    def updateStructDefn(self):
        structKW = (Keyword('struct') | Keyword('union'))
        self.definedStruct << kwl(self.defs['structs'].keys())
        self.structType << structKW + (self.definedStruct.setResultsName('name') | Optional(ident).setResultsName('name') + lbrace + Group(ZeroOrMore( Group(self.variableDecl.copy().setParseAction(lambda: None)) )).setResultsName('members') + rbrace)
        self.structType.setParseAction(self.processStruct)
    
    
    # parse action for macro definitions
    def processMacroDefn(self, s,l,t):
        macroVal = self.macroExpander.transformString(t.value).strip()
        if t.args == '':
            self.addDef('macros', t.macro, macroVal)
            #print "Add macro:", t.macro, self.defs['macros'][t.macro]
        else:
            self.addDef('fnmacros', t.macro,  (macroVal, [x for x in t.args]))
            #print "Add fn macro:", t.macro, t.args, self.defs['fnmacros'][t.macro]
        self.addDef('values', t.macro, self.evalExpr(macroVal))
        self.updateMacroDefns()
        #self.macroExpr << MatchFirst( map(Keyword,self.defs['macros'].keys()) )
        return "#define " + t.macro + " " + macroVal
        
    # parse action to replace macro references with their respective definition
    def processMacroRef(self, s,l,t):
        return self.defs['macros'][t.macro]
            
    def processFnMacroRef(self, s,l,t):
        m = self.defs['fnmacros'][t.macro]
        #print "=====>>"
        #print "Process FN MACRO:", t
        #print "  macro defn:", t.macro, m
        #print "  macro call:", t.args
        ## m looks like ('a + b', ('a', 'b'))
        newStr = m[0][:]
        #print "  starting str:", newStr
        try:
            for i in range(len(m[1])):
                #print "  step", i
                arg = m[1][i]
                #print "    arg:", arg, '=>', t.args[i]
                
                newStr = Keyword(arg).setParseAction(lambda: t.args[i]).transformString(newStr)
                #print "    new str:", newStr
        except:
            #sys.excepthook(*sys.exc_info())
            raise
        #print "<<====="
        return newStr
            

    def processEnum(self, s, l, t):
        try:
            if t.name == '':
                n = 0
                while True:
                    name = 'anonEnum%d' % n
                    if name not in self.defs['enums']:
                        break
                    n += 1
            else:
                name = t.name[0]
                
            if name not in self.defs['enums']:
                i = 0
                enum = {}
                for v in t.members:
                    if v.value != '':
                        i = int(v.value)
                    enum[v.name] = i
                    self.addDef('values', v.name, i)
                    i += 1
                self.addDef('enums', name, enum)
            return ('enum:'+name)
        except:
            print t
            sys.excepthook(*sys.exc_info())

    def processFunction(self, s, l, t):
        try:
            rType = (t.type.type[0], len(t.type.ptrs))
            args = []
            for a in t.args:
                args.append((a.name, a.type[0], len(a.ptrs)))
            self.addDef('functions', t.name, (rType, args))
        except:
            print t
            sys.excepthook(*sys.exc_info())

    def evalExpr(self, toks):
        ## Evaluates expressions. Currently only works for expressions that also 
        ## happen to be valid python expressions.
        ## This function does not currently include previous variable
        ## declarations, but that should not be too difficult to implement..
        #print "Eval:", toks
        try:
            if type(toks) is str:
                val = eval(toks)
            elif toks.arrayValue != '':
                val = [eval(x) for x in toks.arrayValue]
            elif toks.value != '':
                val = eval(' '.join(toks.value))
            else:
                val = None
            return val
        except:
            #print "failed eval:", toks
            return None

    def processStruct(self, s, l, t):
        try:
            if t.name == '':
                n = 0
                while True:
                    name = 'anonStruct%d' % n
                    if name not in self.defs['structs']:
                        break
                    n += 1
            else:
                if type(t.name) is str:
                    name = t.name
                else:
                    name = t.name[0]
            if name not in self.defs['structs']:
                #print "STRUCT", name, t
                struct = {}
                for m in t.members:
                    #print m
                    struct[m[0].name] = (m[0].type.type[0], len(m[0].type.ptrs), [int(x) for x in m[0].arr], self.evalExpr(m))
                self.addDef('structs', name, struct)
                #self.definedStruct << kwl(self.defs['structs'].keys())
                self.updateStructDefn()
                #print "Added struct %s:", name
                #print "   definedStruct:", self.definedStruct
            return ('struct:'+name)
        except:
            print t
            sys.excepthook(*sys.exc_info())

    def processVariable(self, s, l, t):
        #print "VARIABLE:", l, t
        try:
            name = t[0].name
            #print "Add variable:", name, t.value
            self.addDef('variables', name, self.evalExpr(t))
            self.addDef('values', name, self.defs['variables'][name])
        except:
            #print t, t[0].name, t.value
            sys.excepthook(*sys.exc_info())

    def processTypedef(self, s, l, t):
        #print "TYPE:", l, t, t[1].type
        typ = t[1].type[0]
        #print t, t.type
        for d in t[2]:
            #print "  ",d, d.newType, d.ptrs, d.arr
            self.addDef('types', d.newType, (typ, len(d.ptrs), [int(x) for x in d.arr]))
            self.definedType << MatchFirst( map(Keyword,self.defs['types'].keys()) )
        
    def printAll(self, file=None):
        """Print everything parsed from files. Useful for debugging."""
        from pprint import pprint
        for k in self.dataList:
            print "============== %s ==================" % k
            if file is None:
                pprint(self.defs[k])
            else:
                pprint(self.fileDefs[file][k])
                
    def addDef(self, typ, name, val):
        self.defs[typ][name] = val
        if self.currentFile not in self.fileDefs:
            self.fileDefs[self.currentFile] = {}
            for k in self.dataList:
                self.fileDefs[self.currentFile][k] = {}
        self.fileDefs[self.currentFile][typ][name] = val
            
            
## Some basic definitions
numTypes = ['int', 'float', 'double']
baseTypes = ['char', 'bool', 'void'] + numTypes
sizeModifiers = ['short', 'long']
signModifiers = ['signed', 'unsigned']
qualifiers = ['const', 'static', 'volatile', 'inline', 'restrict', 'near', 'far']
keywords = ['struct', 'enum', 'union'] + qualifiers + baseTypes + sizeModifiers + signModifiers

def kwl(strs):
    """Generate a match-first list of keywords given a list of strings."""
    return MatchFirst(map(Keyword,strs))

keyword = kwl(keywords)
ident = (~keyword + Word(alphas+"_",alphanums+"_$")).setParseAction(lambda t: t[0])
integer = Combine(Optional("-") + (Word( nums ) | Combine("0x" + Word(hexnums)))) 
semi = Literal(";").ignore(quotedString).suppress()
lbrace = Literal("{").ignore(quotedString).suppress()
rbrace = Literal("}").ignore(quotedString).suppress()
lbrack = Literal("[").ignore(quotedString).suppress()
rbrack = Literal("]").ignore(quotedString).suppress()
lparen = Literal("(").ignore(quotedString).suppress()
rparen = Literal(")").ignore(quotedString).suppress()
number = Word(hexnums + ".-+x")
stars = Optional(Word('*'), default='').setResultsName('ptrs')

## language elements
fundType = OneOrMore(kwl(signModifiers + sizeModifiers + baseTypes)).setParseAction(lambda t: ' '.join(t))
    
typeQualifier = ZeroOrMore(kwl(qualifiers)).suppress()

bitfieldspec = ":" + integer
arrayOp = bitfieldspec | ( lbrack + integer + rbrack )
varNameSpec = Group(stars + ident + ZeroOrMore(arrayOp))
operator = oneOf("+ - / * | & || && ^ % ++ -- == != > < >= <=")
functionCall = Forward()
expression = OneOrMore(operator | functionCall | ident | quotedString | number)
functionCall << ident + '(' + Optional(delimitedList(expression)) + ')'

if __name__ == '__main__':
    files = sys.argv[1:]
    #text = ''
    #for f in files:
        #fd = open(f)
        #text += fd.read()
        #fd.close()
    p = CParser(files)
    p.processAll()
    p.printAll()
    