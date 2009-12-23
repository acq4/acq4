# -*- coding: utf-8 -*-
import sys, re, os
import ctypes
#ParserElement.enablePackrat()  ## Don't do this--actually makes the parse take longer!

__all__ = ['parseFiles', 'winDefs', 'CParser']

def parseFiles(files, cache=None, **args):
    """Convenience function allowing one-line parsing of C files. 
    Returns a dictionary of all data processed.
    The 'cache' argument is passed to CParser.processAll.
    All extra arguments are passed to CParser.__init__"""
    p = CParser(files, **args)
    p.processAll(cache)
    return p

def winDefs():
    """Convenience function. Returns a parser which loads a selection of windows headers included with 
    CParser. These definitions can either be accessed directly or included before parsing
    another file like this:
        windefs = CParser.winDefs()
        p = CParser.CParser("headerFile.h", copyFrom=windefs)
    Definitions are pulled from a selection of header files included in Visual Studio
    (possibly not legal to distribute? Who knows.), some of which have been abridged
    because they take so long to parse. 
    """
    headerFiles = ['WinNtTypes.h', 'BaseTsd.h', 'WinDef.h', 'WTypes.h', 'WinUserAbridged.h']
    d = os.path.dirname(__file__)
    p = CParser(
        [os.path.join(d, 'headers', h) for h in headerFiles],
        types={'__int64': ('long long')}
    )
    p.processAll(cache=os.path.join(d, 'headers', 'WinDefs.cache'), noCacheWarning=True)
    return p


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
    
    cacheVersion = 2    ## increment every time cache structure or parsing changes to invalidate old cache files.
    
    def __init__(self, files=None, replace=None, copyFrom=None, **args):
        """Create a C parser object fiven a file or list of files. Files are read to memory and operated
        on from there.
            'copyFrom' may be another CParser object from which definitions should be copied.
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
        
        self.dataList = ['types', 'variables', 'fnmacros', 'macros', 'structs', 'unions', 'enums', 'functions', 'values']
            
        self.verbose = False
            
        # placeholders for definitions that change during parsing
        self.macroExpr = Forward()
        self.fnMacroExpr = Forward()
        self.definedType = Forward()
        #self.definedStruct = Forward()
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
                
        self.compiledTypes = {}  ## holds translations from typedefs/structs/unions to fundamental types
                
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
    
    def processAll(self, cache=None, returnUnparsed=False, printAfterPreprocess=False, noCacheWarning=False, verbose=False):
        """Remove comments, preprocess, and parse declarations from all files. (operates in memory; does not alter the original files)
        Returns a list of the results from parseDefs.
           'cache' may specify a file where cached results are be stored or retrieved. The cache
               is automatically invalidated if any of the arguments to __init__ are changed, or if the 
               C files are newer than the cache.
           'returnUnparsed' is passed directly to parseDefs.
           'printAfterPreprocess' is for debugging; prints the result of preprocessing each file."""
        self.verbose = verbose
        if cache is not None and self.loadCache(cache, checkValidity=True):
            if verbose:
                print "Loaded cached definitions; will skip parsing."
            return  ## cached values loaded successfully, nothing left to do here
            
        
        results = []
        if noCacheWarning or verbose:
            print "Parsing C header files (no valid cache found). This could take several minutes..."
        for f in self.fileOrder:
            if self.files[f] is None:
                ## This means the file could not be loaded and there was no cache.
                raise Exception('Could not find header file "%s" or a suitable cache file.' % f)
            if verbose:
                print "Removing comments from file '%s'..." % f
            self.removeComments(f)
            if verbose:
                print "Preprocessing file '%s'..." % f
            self.preprocess(f)
            if printAfterPreprocess:
                print "===== PREPROCSSED %s =======" % f
                print self.files[f]
            if verbose:
                print "Parsing definitions in file '%s'..." % f
            results.append(self.parseDefs(f, returnUnparsed))
        
        if cache is not None:
            if verbose:
                print "Writing cache file '%s'" % cache
            self.writeCache(cache)
            
        return results
        
            
    def loadCache(self, cacheFile, checkValidity=False):
        """Load a cache file. Used internally if cache is specified in processAll().
        if checkValidity=True, then run several checks before loading the cache:
           - cache file must not be older than any source files
           - cache file must not be older than this library file
           - options recorded in cache must match options used to initialize CParser"""
        
        ## make sure cache file exists 
        if type(cacheFile) is not str:
            raise Exception("cache file option myst be a string.")
        if not os.path.isfile(cacheFile):
            d = os.path.dirname(__file__)  ## If file doesn't exist, search for it in this module's path
            cacheFile = os.path.join(d, "headers", cacheFile)
            if not os.path.isfile(cacheFile):
                return False
        
        ## make sure cache is newer than all input files
        if checkValidity:
            mtime = os.stat(cacheFile).st_mtime
            for f in self.fileOrder:
                ## if file does not exist, then it does not count against the validity of the cache.
                if os.path.isfile(f) and os.stat(f).st_mtime > mtime:
                    return False
        
        try:
            ## read cache file
            import pickle
            cache = pickle.load(open(cacheFile))
            
            ## make sure __init__ options match
            if checkValidity:
                if cache['opts'] != self.initOpts:
                    return False
                if cache['version'] < self.cacheVersion:
                    return False
                
            ## import all parse results
            self.importDict(cache['fileDefs'])
            return True
        except:
            print "Warning--cache is invalid, ignoring."
            return False

    def importDict(self, data):
        """Import definitions from a dictionary. The dict format should be the
        same as CParser.fileDefs. Used internally; does not need to be called
        manually."""
        for f in data.keys():
            self.currentFile = f
            for k in self.dataList:
                for n in data[f][k]:
                    self.addDef(k, n, data[f][k][n])

    def writeCache(self, cacheFile):
        """Store all parsed declarations to cache. Used internally."""
        cache = {}
        cache['opts'] = self.initOpts
        cache['fileDefs'] = self.fileDefs
        cache['version'] = self.cacheVersion
        #for k in self.dataList:
            #cache[k] = getattr(self, k)
        import pickle
        pickle.dump(cache, open(cacheFile, 'w'))

    def loadFile(self, file):
        """Read a file, make replacements if requested. Called by __init__, should
        not be called manually."""
        if not os.path.isfile(file):
            ## Not a fatal error since we might be able to function properly if there is a cache file..
            #raise Exception("File %s not found" % file)
            print "Warning: C header '%s' is missing; this may cause trouble." % file
            self.files[file] = None
            return False
            
        fd = open(file, 'rU')  ## U causes all newline types to be converted to \n
        self.files[file] = fd.read()
        fd.close()
        
        replace = self.initOpts['replace']
        if replace is not None:
            for s in replace:
                self.files[file] = re.sub(s, replace[s], self.files[file])
        return True
    




    #### Beginning of processing functions
    
    def assertPyparsing(self):
        """Make sure pyparsing module is available."""
        global hasPyParsing
        if not hasPyParsing:
            raise Exception("CParser class requires 'pyparsing' library for actual parsing work. Without this library, CParser can only be used with previously cached parse results.")
    

    def removeComments(self, file):
        """Remove all comments from file. (operates in memory; does not alter the original files)"""
        self.assertPyparsing()
        text = self.files[file]
        cplusplusLineComment = Literal("//") + restOfLine
        # match quoted strings first to prevent matching comments inside quotes
        self.files[file] = (quotedString | cStyleComment.suppress() | cplusplusLineComment.suppress()).transformString(text)
        
    
    def preprocess(self, file):
        """Scan named file for preprocessor directives, removing them while expanding macros. (operates in memory; does not alter the original files)"""
        self.assertPyparsing()
        self.currentFile = file
        self.ppDirective = Combine("#" + Word(alphas).leaveWhitespace()) + restOfLine
        
        # define the structure of a macro definition (the empty term is used 
        # to advance to the next non-whitespace character)
        self.ppDefine = Keyword("#define") + ident.setWhitespaceChars(' \t')("macro") + Optional(lparen + delimitedList(ident) + rparen).setWhitespaceChars(' \t')('args') + SkipTo(LineEnd(), ignore=(Literal('\\').leaveWhitespace()+LineEnd()))('value')
        # attach parse actions to expressions
        self.ppDefine.setParseAction(self.processMacroDefn)
        #ppDefine.setDebug(True)
        self.updateMacroDefns()

        # define pattern for scanning through the input string
        self.macroExpander = (self.macroExpr | self.fnMacroExpr | self.ppDefine.suppress() | self.ppDirective.suppress())
        
        text = self.files[file]
        ## Match quoted strings first to prevent matching macros inside strings.
        ## do NOT use .ignore(quotedString) -- this has drastic side effects!
        self.files[file] =  (quotedString | self.macroExpander).transformString(text)

    def updateMacroDefns(self):
        self.macroExpr << MatchFirst( [Keyword(m)('macro') for m in self.defs['macros']] )
        self.macroExpr.setParseAction(self.processMacroRef)

        self.fnMacroExpr << MatchFirst( [(Keyword(m)('macro') + lparen + Group(delimitedList(expression))('args') + rparen) for m in self.defs['fnmacros']] )
        self.fnMacroExpr.setParseAction(self.processFnMacroRef)        
        
    def parseDefs(self, file, returnUnparsed=False):
        """Scan through the named file for variable, struct, enum, and function declarations.
        Returns the entire tree of successfully parsed tokens.
        If returnUnparsed is True, return a string of all lines that failed to match (for debugging)."""
        self.assertPyparsing()
        self.currentFile = file
        self.definedType << kwl(self.defs['types'].keys())
    
        parser = self.buildParser()
        if returnUnparsed:
            text = parser.suppress().transformString(self.files[file])
            return re.sub(r'\n\s*\n', '\n', text)
        else:
            return [x[0] for x in parser.scanString(self.files[file])]

    def buildParser(self):
        self.assertPyparsing()
        
        
        self.structType = Forward()
        enumType = Forward()
        self.typeSpec = (typeQualifier + (
            fundType | 
            Optional(kwl(sizeModifiers + signModifiers)) + self.definedType | 
            self.structType | 
            enumType
        ) + typeQualifier + msModifier).setParseAction(recombine)
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
            Group(ZeroOrMore('*' + typeQualifier))('ptrs') + 
            ((Optional('&')('ref')) | (lparen + self.abstractDeclarator + rparen)('center')) + 
            Optional(lparen + Optional(delimitedList(Group(self.typeSpec('type') + self.abstractDeclarator('decl'))), default=None) + rparen)('args') + 
            Group(ZeroOrMore(lbrack + Optional(number, default='-1') + rbrack))('arrays')
        )
        
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
            Group(ZeroOrMore('*' + typeQualifier))('ptrs') + 
            ((Optional('&')('ref') + ident('name')) | (lparen + self.declarator + rparen)('center')) + 
            Optional(lparen + Optional(delimitedList(Group(self.typeSpec('type') + (self.declarator | self.abstractDeclarator)('decl'))), default=None) + rparen)('args') + 
            Group(ZeroOrMore(lbrack + Optional(number, default='-1') + rbrack))('arrays')
        )
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
        
        return (self.typeDecl | self.variableDecl | self.structDecl | enumDecl | functionDecl)
    
    def updateStructDefn(self):
        structKW = (Keyword('struct') | Keyword('union'))
        
        ## We could search only for previously defined struct names, 
        ## but then we would miss incomplete type declarations.
        #self.definedStruct << kwl(self.defs['structs'].keys())
        #self.structType << structKW + (self.definedStruct('name') | Optional(ident)('name') + lbrace + Group(ZeroOrMore( Group(self.variableDecl.copy().setParseAction(lambda: None)) ))('members') + rbrace)
        
        self.structType << structKW('structType') + (Optional(ident)('name') + lbrace + Group(ZeroOrMore( Group(self.variableDecl.copy().setParseAction(lambda: None)) ))('members') + rbrace | ident('name'))
        self.structType.setParseAction(self.processStruct)
    
    def processDeclarator(self, decl):
        """Process a declarator (without base type) and return a tuple (name, [modifiers])
        See processType(...) for more information."""
        toks = []
        name = None
        #print "DECL:", decl
        if 'ptrs' in decl and len(decl['ptrs']) > 0:
            toks.append('*' * len(decl['ptrs']))
        if 'arrays' in decl and len(decl['arrays']) > 0:
            toks.append([self.evalExpr(x) for x in decl['arrays']])
        if 'args' in decl and len(decl['args']) > 0:
            #print "  process args"
            if decl['args'][0] is None:
                toks.append(())
            else:
                toks.append(tuple([self.processType(a['type'], a['decl']) for a in decl['args']]))
        if 'ref' in decl:
            toks.append('&')
        if 'center' in decl:
            (n, t) = self.processDeclarator(decl['center'][0])
            if n is not None:
                name = n
            toks.extend(t)
        if 'name' in decl:
            name = decl['name']
        return (name, toks)
    
    def processType(self, typ, decl):
        """Take a declarator + base type and return a serialized name/type description.
        The description will be a list of elements (name, [basetype, modifier, modifier, ...])
          - name is the string name of the declarator or None for an abstract declarator
          - basetype is the string representing the base type
          - modifiers can be:
             '*'    - pointer (multiple pointers "***" allowed)
             '&'    - reference
             list   - array. Value(s) indicate the length of each array, -1 for incomplete type.
             tuple  - function, items are the output of processType for each function argument.
        int *x[10]            =>  ('x', ['int', [10], '*'])
        char fn(int x)         =>  ('fn', ['char', [('x', ['int'])]])
        struct s (*)(int, int*)   =>  (None, ["struct s", ((None, ['int']), (None, ['int', '*'])), '*'])
        """
        #print "PROCESS TYPE/DECL:", typ, decl
        (name, decl) = self.processDeclarator(decl)
        return (name, [typ] + decl)
        
    
    # parse action for macro definitions
    def processMacroDefn(self, t):
        if self.verbose:
            print "MACRO:", t
        macroVal = self.macroExpander.transformString(t.value).strip()
        macroVal = Literal('\\\n').suppress().transformString(macroVal) ## remove escaped newlines
        if t.args == '':
            val = self.evalExpr(macroVal)
            self.addDef('macros', t.macro, macroVal)
            self.addDef('values', t.macro, val)
            if self.verbose:
                print "  Add macro:", t.macro, "("+str(val)+")", self.defs['macros'][t.macro]
        else:
            self.addDef('fnmacros', t.macro,  (macroVal, [x for x in t.args]))
            if self.verbose:
                print "  Add fn macro:", t.macro, t.args, self.defs['fnmacros'][t.macro]
        self.updateMacroDefns()
        #self.macroExpr << MatchFirst( map(Keyword,self.defs['macros'].keys()) )
        return "#define " + t.macro + " " + macroVal
        
    # parse action to replace macro references with their respective definition
    def processMacroRef(self, t):
        return self.defs['macros'][t.macro]
            
    def processFnMacroRef(self, t):
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
                
                newStr = Keyword(arg).copy().setParseAction(lambda: t.args[i]).transformString(newStr)
                #print "    new str:", newStr
        except:
            #sys.excepthook(*sys.exc_info())
            raise
        #print "<<====="
        return newStr
            

    def processEnum(self, s, l, t):
        try:
            if self.verbose:
                print "ENUM:", t
            if t.name == '':
                n = 0
                while True:
                    name = 'anonEnum%d' % n
                    if name not in self.defs['enums']:
                        break
                    n += 1
            else:
                name = t.name[0]
                
            if self.verbose:
                print "  name:", name
                
            if name not in self.defs['enums']:
                i = 0
                enum = {}
                for v in t.members:
                    if v.value != '':
                        i = int(v.value)
                    enum[v.name] = i
                    self.addDef('values', v.name, i)
                    i += 1
                if self.verbose:
                        print "  members:", enum
                self.addDef('enums', name, enum)
                self.addDef('types', 'enum '+name, ('enum', name))
            return ('enum:'+name)
        except:
            if self.verbose:
                print "Error processing enum:", t
            sys.excepthook(*sys.exc_info())


    def processFunction(self, s, l, t):
        if self.verbose:
            print "FUNCTION", t, t.keys()
        
        try:
            (name, decl) = self.processType(t.type, t.decl[0])
            if self.verbose:
                print "  name:", name
                print "  sig:", decl
            self.addDef('functions', name, (decl[:-1], decl[-1]))
            
        except:
            if self.verbose:
                print "Error processing function:", t
            sys.excepthook(*sys.exc_info())


    def processStruct(self, s, l, t):
        try:
            strTyp = t.structType  # struct or union
            if self.verbose:
                print strTyp.upper(), t.name, t
            if t.name == '':
                n = 0
                while True:
                    sname = 'anonStruct%d' % n
                    if sname not in self.defs[strTyp+'s']:
                        break
                    n += 1
            else:
                if type(t.name) is str:
                    sname = t.name
                else:
                    sname = t.name[0]
            if self.verbose:
                print "  NAME:", sname
            if sname not in self.defs[strTyp+'s'] or self.defs[strTyp+'s'][sname] == {}:
                if self.verbose:
                    print "  NEW " + strTyp.upper()
                struct = {}
                for m in t.members:
                    typ = m[0].type
                    val = self.evalExpr(m)
                    if self.verbose:
                        print "    member:", m, m[0].keys(), m[0].declList
                    for d in m[0].declList:
                        (name, decl) = self.processType(typ, d)
                        struct[name] = (decl, val)
                        if self.verbose:
                            print "      ", name, decl, val
                self.addDef(strTyp+'s', sname, struct)
                self.addDef('types', strTyp+' '+sname, (strTyp, sname))
                self.updateStructDefn()
            return (strTyp+' '+sname)
        except:
            #print t
            sys.excepthook(*sys.exc_info())

    def processVariable(self, s, l, t):
        if self.verbose:
            print "VARIABLE:", t
        try:
            val = self.evalExpr(t)
            for d in t[0].declList:
                (name, typ) = self.processType(t[0].type, d)
                if type(typ[-1]) is tuple:  ## this is a function prototype
                    if self.verbose:
                        print "  Add function prototype:", name, typ, val
                    self.addDef('functions', name, (typ[:-1], typ[-1]))
                else:
                    if self.verbose:
                        print "  Add variable:", name, typ, val
                    self.addDef('variables', name, (val, typ))
                    self.addDef('values', name, val)
        except:
            #print t, t[0].name, t.value
            sys.excepthook(*sys.exc_info())

    def processTypedef(self, s, l, t):
        if self.verbose:
            print "TYPE:", t
        typ = t.type
        #print t, t.type
        for d in t.declList:
            (name, decl) = self.processType(typ, d)
            if self.verbose:
                print "  ", name, decl
            self.addDef('types', name, decl)
            self.definedType << MatchFirst( map(Keyword,self.defs['types'].keys()) )
        
    def evalExpr(self, toks):
        ## Evaluates expressions. Currently only works for expressions that also 
        ## happen to be valid python expressions.
        ## This function does not currently include previous variable
        ## declarations, but that should not be too difficult to implement..
        #print "Eval:", toks
        try:
            if isinstance(toks, basestring):
                #print "  as string"
                val = self.eval(toks, None, self.defs['values'])
            elif toks.arrayValues != '':
                #print "  as list:", toks.arrayValues
                val = [self.eval(x, None, self.defs['values']) for x in toks.arrayValues]
            elif toks.value != '':
                #print "  as value"
                val = self.eval(toks.value, None, self.defs['values'])
            else:
                #print "  as None"
                val = None
            return val
        except:
            if self.verbose:
                print "    failed eval:", toks
                print "                ", sys.exc_info()[1]
            return None
            
    def eval(self, expr, *args):
        """Just eval with a little extra robustness."""
        expr = expr.strip()
        if expr == '':
            return None
        return eval(expr, *args)
        
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
        """evaluate a named type into its fundamental type"""
        used = [typ]
        while True:
            if self.isFundType(typ):
                return typ
            parent = typ[0]
            if parent in used:
                raise Exception('Recursive loop while tracing types.')
            used.append(parent)
            pt = self.defs['types'][parent]
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

hasPyParsing = False
try: 
    from pyparsing import *
    hasPyParsing = True
except:
    pass  ## no need to do anything yet as we might not be using any parsing functions..


## Define some common language elements if pyparsing is available.
if hasPyParsing:
    ## Some basic definitions
    expression = Forward()
    pexpr = '(' + expression + ')'
    numTypes = ['int', 'float', 'double']
    baseTypes = ['char', 'bool', 'void'] + numTypes
    sizeModifiers = ['short', 'long']
    signModifiers = ['signed', 'unsigned']
    qualifiers = ['const', 'static', 'volatile', 'inline', 'restrict', 'near', 'far']
    msModifiers = ['__based', '__declspec', '__stdcall', '__cdecl', '__fastcall', '__restrict', '__sptr', '__uptr', '__w64', '__unaligned']
    keywords = ['struct', 'enum', 'union'] + qualifiers + baseTypes + sizeModifiers + signModifiers

    def kwl(strs):
        """Generate a match-first list of keywords given a list of strings."""
        return MatchFirst(map(Keyword,strs))

    keyword = kwl(keywords)
    ident = (~keyword + Word(alphas+"_",alphanums+"_$")).setParseAction(lambda t: t[0])
    integer = Combine(Optional("-") + (Word( nums ) | Combine("0x" + Word(hexnums)))) 
    semi   = Literal(";").ignore(quotedString).suppress()
    lbrace = Literal("{").ignore(quotedString).suppress()
    rbrace = Literal("}").ignore(quotedString).suppress()
    lbrack = Literal("[").ignore(quotedString).suppress()
    rbrack = Literal("]").ignore(quotedString).suppress()
    lparen = Literal("(").ignore(quotedString).suppress()
    rparen = Literal(")").ignore(quotedString).suppress()
    number = Word(hexnums + ".-+x")
    #stars = Optional(Word('*&'), default='')('ptrs')  ## may need to separate & from * later?
    typeQualifier = ZeroOrMore(kwl(qualifiers)).suppress()
    msModifier = ZeroOrMore(kwl(msModifiers) + Optional(pexpr)).suppress()
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

    def recombine(tok):
        """Flattens a tree of tokens and joins into one big string."""
        s = []
        for t in tok:
            if isinstance(t, basestring):
                s.append(t)
            else:
                s.append(recombine(t))
        return " ".join(s)
    expression.setParseAction(recombine)
            

    def printParseResults(pr, depth=0, name=''):
        """For debugging; pretty-prints parse result objects."""
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



## Just for fun..
if __name__ == '__main__':
    files = sys.argv[1:]
    p = CParser(files)
    p.processAll()
    p.printAll()
    