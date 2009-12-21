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
        
        replace = self.initOpts['replace']
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
            if cache is not None and self.loadCache(cache, checkValidity=True):
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
        ppDefine = Keyword("#define") + ident.setWhitespaceChars(' \t')("macro") + Optional(lparen + delimitedList(ident) + rparen).setWhitespaceChars(' \t')('args') + restOfLine("value")
        # attach parse actions to expressions
        ppDefine.setParseAction(self.processMacroDefn)
        
        self.updateMacroDefns()

        # define pattern for scanning through the input string
        self.macroExpander = (self.macroExpr | self.fnMacroExpr | ppDefine.suppress() | ppDirective.suppress()).ignore(quotedString)
        self.files[file] =  self.macroExpander.transformString(text)

    def updateMacroDefns(self):
        self.macroExpr << MatchFirst( [Keyword(m)('macro') for m in self.defs['macros']] )
        self.macroExpr.setParseAction(self.processMacroRef)

        self.fnMacroExpr << MatchFirst( [(Keyword(m)('macro') + lparen + Group(delimitedList(expression))('args') + rparen) for m in self.defs['fnmacros']] )
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
        self.typeSpec = (typeQualifier + (
            fundType | 
            Optional(kwl(sizeModifiers + signModifiers)) + self.definedType | 
            self.structType | 
            enumType
        ) + typeQualifier).setParseAction(recombine)
        self.argList = Forward()
        
        ### Abstract declarators for use in function pointer arguments
        #   Thus begins the extremely hairy business of parsing C declarators. 
        #   Whomever decided this was a reasonable syntax should probably never breed.
        #   The following parsers combined with the processDeclarator function
        #   allow us to turn a nest of type modifiers into a correctly
        #   ordered list of modifiers.
        
        self.declarator = Forward()
        self.abstractDeclarator = Forward()
        
        ## abstract declarators look like:
        #     <empty string>
        #     *
        #     **[num]
        #     (*)(int, int)
        #     *( )(int, int)[10]
        #     ...etc...
        self.abstractDeclarator << Group(
            Group(ZeroOrMore('*'))('ptrs') + 
            ((Optional('&')('ref')) | (lparen + self.abstractDeclarator + rparen)('center')) + 
            Optional(lparen + Optional(delimitedList(Group(self.typeSpec('type') + self.abstractDeclarator)), default=None) + rparen)('args') + 
            Group(ZeroOrMore(lbrack + Optional(number, default='-1') + rbrack))('arrays')
        )('decl')
        
        ## Argument list may consist of declarators or abstract declarators
        self.argList << delimitedList(Group(
            self.typeSpec('type') + 
            (self.declarator('decl') | self.abstractDeclarator('decl')) + 
            Optional(Keyword('=')) + expression
        ))

        ## declarators look like:
        #     varName
        #     *varName
        #     **varName[num]
        #     (*fnName)(int, int)
        #     * fnName(int arg1=0)[10]
        #     ...etc...
        self.declarator << Group(
            Group(ZeroOrMore('*'))('ptrs') + 
            ((Optional('&')('ref') + ident('name')) | (lparen + self.declarator + rparen)('center')) + 
            Optional(lparen + Optional(delimitedList(Group(self.typeSpec('type') + (self.declarator | self.abstractDeclarator))), default=None) + rparen)('args') + 
            Group(ZeroOrMore(lbrack + Optional(number, default='-1') + rbrack))('arrays')
        )('decl')
        self.declaratorList = Group(delimitedList(self.declarator))
        
        

        ## typedef
        self.typeDecl = Keyword('typedef') + self.typeSpec('type') + self.declaratorList('declList') + semi
        self.typeDecl.setParseAction(self.processTypedef)

        ## variable declaration
        self.variableDecl = Group(self.typeSpec('type') + self.declaratorList('declList')) + Optional(Literal('=').suppress() + (expression('value') | (lbrace + Group(delimitedList(expression))('arrayValues') + rbrace))) + semi
        
        self.variableDecl.setParseAction(self.processVariable)
        
        ## Struct definition
        self.structDecl = Forward()
        self.updateStructDefn()
        
        self.structDecl = self.structType + semi

        ## enum definition
        enumVarDecl = Group(ident('name')  + Optional(Literal('=').suppress() + integer('value')))
        
        enumType << Keyword('enum') + (self.definedEnum('name') | Optional(ident)('name') + lbrace + Group(delimitedList(enumVarDecl))('members') + rbrace)
        enumType.setParseAction(self.processEnum)
        
        enumDecl = enumType + semi

        ## function definition
        #self.paramDecl = Group(self.typeSpec + (self.declarator | self.abstractDeclarator)) + Optional(Literal('=').suppress() + expression('value'))
        functionDecl = self.typeSpec('type') + self.declarator('decl') + nestedExpr('{', '}').suppress()
        functionDecl.setParseAction(self.processFunction)
        
        return (self.typeDecl ^ self.structDecl ^ enumDecl ^ self.variableDecl ^ functionDecl)
    
    def updateStructDefn(self):
        structKW = (Keyword('struct') | Keyword('union'))
        self.definedStruct << kwl(self.defs['structs'].keys())
        self.structType << structKW + (self.definedStruct('name') | Optional(ident)('name') + lbrace + Group(ZeroOrMore( Group(self.variableDecl.copy().setParseAction(lambda: None)) ))('members') + rbrace)
        self.structType.setParseAction(self.processStruct)
    
    def processDeclarator(self, decl):
        """Take a declarator (without type) and return a serialized modifier description
        *x[10]            =>  ('x', [10, '*'])
        fn(int x)         =>  ('fn', [[('x', ['int'])]])
        (*)(int, int*)   =>  (None, [[(None, ['int']), (None, ['int', '*'])]], '*')
        """
        if 'decl' in decl:
            decl = decl['decl']
        toks = []
        name = None
        #print "DECL:", decl
        if 'ptrs' in decl and len(decl['ptrs']) > 0:
            toks.append('*' * len(decl['ptrs']))
        if 'arrays' in decl and len(decl['arrays']) > 0:
            toks.append([self.evalExpr(x) for x in decl['arrays']])
        if 'args' in decl and len(decl['args']) > 0:
            if decl['args'][0] is None:
                toks.append([])
            else:
                toks.append([self.processType(a['type'], a['decl']) for a in decl['args']])
        if 'ref' in decl:
            toks.append('&')
        if 'center' in decl:
            (n, t) = self.processDeclarator(decl['center'])
            if n is not None:
                name = n
            toks.extend(t)
        if 'name' in decl:
            name = decl['name']
        return (name, toks)
    
    def processType(self, typ, decl):
        """Take a name/type declaration, return the name and serialized type description
        int *x[10]            =>  ('x', ['int', 10, '*'])
        int fn(int x)         =>  ('fn', ['int', [('x', ['int'])]])
        void (*)(int, int*)   =>  (None, ['void', [(None, ['int']), (None, ['int', '*'])]], '*')
        """
        (name, decl) = self.processDeclarator(decl)
        return (name, [typ] + decl)
        
    
    # parse action for macro definitions
    def processMacroDefn(self, s,l,t):
        print "MACRO:", t
        macroVal = self.macroExpander.transformString(t.value).strip()
        if t.args == '':
            self.addDef('macros', t.macro, macroVal)
            print "  Add macro:", t.macro, self.defs['macros'][t.macro]
        else:
            self.addDef('fnmacros', t.macro,  (macroVal, [x for x in t.args]))
            print "  Add fn macro:", t.macro, t.args, self.defs['fnmacros'][t.macro]
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
        print "FUNCTION", t, t.keys()
        
        try:
            (name, decl) = self.processType(t.type, t.decl)
            print "  ", name, decl
            #rType = (t.type.type[0], len(t.type.ptrs))
            #args = []
            #for a in t.args:
                #args.append((a.name, a.type[0], len(a.ptrs)))
            self.addDef('functions', name, (decl[:-1], decl[-1]))
            
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
            if isinstance(toks, basestring):
                #print "  as string"
                val = eval(toks)
            elif toks.arrayValues != '':
                #print "  as list:", toks.arrayValues
                val = [eval(x) for x in toks.arrayValues]
            elif toks.value != '':
                #print "  as value"
                val = eval(toks.value)
            else:
                #print "  as None"
                val = None
            return val
        except:
            print "failed eval:", toks
            return None

    def processStruct(self, s, l, t):
        print "STRUCT", t.name, t
        try:
            if t.name == '':
                n = 0
                while True:
                    sname = 'anonStruct%d' % n
                    if sname not in self.defs['structs']:
                        break
                    n += 1
            else:
                if type(t.name) is str:
                    sname = t.name
                else:
                    sname = t.name[0]
            print "  NAME:", sname
            if sname not in self.defs['structs']:
                print "  NEW STRUCT"
                struct = {}
                for m in t.members:
                    typ = m[0].type
                    val = self.evalExpr(m)
                    print "    member:", m, m[0].keys(), m[0].declList
                    for d in m[0].declList:
                        (name, decl) = self.processType(typ, d)
                        struct[name] = (decl, val)
                        print "      ", name, decl, val
                    #struct[m[0].name] = (m[0].type.type[0], len(m[0].type.ptrs), [int(x) for x in m[0].arr], self.evalExpr(m))
                self.addDef('structs', sname, struct)
                #self.definedStruct << kwl(self.defs['structs'].keys())
                self.updateStructDefn()
                #print "Added struct %s:", name
                #print "   definedStruct:", self.definedStruct
            return ('struct:'+sname)
        except:
            #print t
            sys.excepthook(*sys.exc_info())

    def processVariable(self, s, l, t):
        print "VARIABLE:", t
        try:
            val = self.evalExpr(t)
            for d in t[0].declList:
                (name, typ) = self.processType(t[0].type, d)
                print "  Add variable:", name, typ, val
                self.addDef('variables', name, val)
                self.addDef('values', name, val)
        except:
            #print t, t[0].name, t.value
            sys.excepthook(*sys.exc_info())

    def processTypedef(self, s, l, t):
        print "TYPE:", l, t
        typ = t.type
        #print t, t.type
        for d in t.declList:
            (name, decl) = self.processType(typ, d)
            print "  ", name, decl
            self.addDef('types', name, decl)
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
        """Add a definition of a specific type to both the definition set for the current file and the global definition set."""
        self.defs[typ][name] = val
        if self.currentFile not in self.fileDefs:
            self.fileDefs[self.currentFile] = {}
            for k in self.dataList:
                self.fileDefs[self.currentFile][k] = {}
        self.fileDefs[self.currentFile][typ][name] = val

    def isFundType(self, typ):
        """Return True if this type is a fundamental C type, struct, or union"""
        if type(typ) in [dict, tuple]:
            return True  ## function, struct, or union
        elif type(typ) is list:
            names = baseTypes + sizeModifiers + signModifiers
            for w in typ[0].split():
                if w not in names:
                    return False
            return True
        else:
            raise Exception("Not sure what to make of type '%s'" % str(t))

    def evalType(self, typ):
        """evaluate a named type into its fundamental types"""
        used = [typ]
        while True:
            if isFundType(typ):
                return typ
            parent = typ[0]
            if parent in used:
                raise Exception('Recursive loop while tracing types.')
            used.append(parent)
            pt = self.types[parent]
            typ = pt + typ[1:]

    def ctype(self, typ, val=None):
        """return a ctype object representing the named type"""
        # Create the initial type
        fn = CParser.cTypeDict[typ[0]]
        if val is None:
            obj = fn()
        else:
            obj = fn(val)
            
        # apply pointers and arrays
        for p in typ[1:]:
            if p in ['*', '&']:
                obj = POINTER(obj)
            elif type(p) is int:
                obj = obj * p
        return obj




    def makeCInst(self, typ, data):
        """Make a ctypes instance """

            
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
#stars = Optional(Word('*&'), default='')('ptrs')  ## may need to separate & from * later?
typeQualifier = ZeroOrMore(kwl(qualifiers)).suppress()
pointerOperator = (
    '*' + typeQualifier |
    '&' + typeQualifier |
    '::' + ident + typeQualifier
)


## language elements
fundType = OneOrMore(kwl(signModifiers + sizeModifiers + baseTypes)).setParseAction(lambda t: ' '.join(t))

bitfieldspec = ":" + integer
biOperator = oneOf("+ - / * | & || && ! ~ ^ % == != > < >= <= -> . :: << >> = ? :")
uniRightOperator = oneOf("++ --")
uniLeftOperator = oneOf("++ -- - + * sizeof new")
name = Word(alphas,alphanums + '_')

expression = Forward()
atom = (
    ZeroOrMore(uniLeftOperator) + 
    ((
        name + '(' + Optional(delimitedList(expression)) + ')' | 
        name + OneOrMore('[' + expression + ']') | 
        name | number | quotedString
    )  |
    ('(' + expression + ')')) + 
    ZeroOrMore(uniRightOperator)
)

expression << Group(
    atom + ZeroOrMore(biOperator + atom)
)
arrayOp = lbrack + expression + rbrack

#def parseExpr(s, l, t):
    #print "EXPRESSION:", l, s[l:l+10], "..."
#expression.setParseAction(parseExpr)

def recombine(tok):
    s = []
    for t in tok:
        if isinstance(t, basestring):
            s.append(t)
        else:
            s.append(recombine(t))
    return " ".join(s)
expression.setParseAction(recombine)
        

def printParseResults(pr, depth=0, name=''):
    start = name + " "*(20-len(name)) + ':'+ '..'*depth    
    if isinstance(pr, ParseResults):
        print start
        for i in pr:
            name = ''
            for k in pr.keys():
                if pr[k] is i:
                    name = k
                    break
            printParseResults(i, depth+1, name)
    else:
        print start  + str(pr)

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
    