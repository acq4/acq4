# -*- coding: utf-8 -*-
from pyparsing import *
import sys, re, os
import ctypes

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
        allValues = p.values
        functionSignatures = p.functions
        ...
        
        ## To see what was not successfully parsed:
        unp = p.processAll(returnUnparsed=True)
        for s in unp:
            print s
    """
    
    def __init__(self, files, replace=None, **args):
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
        self.macros = {}
        self.types = {}
        self.variables = {}
        self.functions = {}
        self.structs = {}
        self.enums = {}
        self.values = {}  ## holds all variables, macros, and enum values
        
        self.initOpts = (files, types, replace)
        self.dataList = ['types', 'variables', 'macros', 'structs', 'enums', 'functions', 'values']
        
        # define a placeholder for macros and typedefs
        self.macroExpr = Forward()
        self.definedType = Forward()
        
        if types is not None:
            self.types = types
        
        self.files = {}
        if type(files) is str:
            files = [files]
        self.fileOrder = files
        for f in files:
            fd = open(f)
            self.files[f] = fd.read()
            fd.close()
            
            if replace is not None:
                for s in replace:
                    self.files[f] = re.sub(s, replace[s], self.files[f])
    
    def processAll(self, file=None, cache=None, returnUnparsed=False):
        """Remove comments, preprocess, and parse for declarations. Operates on the file named
        or all files in series if not specified. (operates in memory; does not alter the original files)
        Returns a list of the results from parseDefs.
           'cache' may specify a file where cached results are be stored or retreved. The cache
               is automatically invalidated if any of the arguments to __init__ are changed, or if the 
               C files are newer than the cache. Only valid if 'file' is None.
           'returnUnparsed' is passed directly to parseDefs."""
        if file is None:
            if self.loadCache(cache):
                #print "used cache"
                return  ## cached values loaded successfully, nothing left to do here
            else:
                #print "ignored cache"
                files = self.fileOrder
        else:
            files = [file]
        
        results = []
        for f in files:
            self.removeComments(f)
            self.preprocess(f)
            results.append(self.parseDefs(f, returnUnparsed))
        
        if cache is not None:
            self.writeCache(cache)
            #print "wrote cache"
            
        return results
        
            
    def loadCache(self, cacheFile, force=False):
        """Load a cache file, but only if it appears to be a valid cache for this CParser.
        if 'force' is True, then skip the validity tests."""
        
        ## make sure cache file exists and 
        if (type(cacheFile) is not str) or (not os.path.isfile(cacheFile)):
            return False
        
        ## make sure cache is newer than all input files and this code
        if not force:
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
            if (not force) and (cache['opts'] != self.initOpts):
                return False
                
            ## import all parse results
            for k in self.dataList:
                setattr(self, k, cache[k])
            return True
        except:
            print "Warning--cache is invalid, ignoring."
            return False


    def writeCache(self, cacheFile):
        """Store all parsed declarations to cache."""
        cache = {}
        cache['opts'] = self.initOpts
        for k in self.dataList:
            cache[k] = getattr(self, k)
        import pickle
        pickle.dump(cache, open(cacheFile, 'w'))


    def removeComments(self, file):
        """Remove all comments from file. (operates in memory; does not alter the original files)"""
        text = self.files[file]
        cplusplusLineComment = Literal("//") + restOfLine
        self.files[file] = (cStyleComment | cplusplusLineComment).ignore(quotedString).suppress().transformString(text)
        
    
    def preprocess(self, file):
        """Scan named file for preprocessor directives, removing them while expanding macros. (operates in memory; does not alter the original files)"""
        text = self.files[file]
        ident = Word(alphas+"_",alphanums+"_$")
        
        # define the structure of a macro definition (the empty term is used 
        # to advance to the next non-whitespace character)
        ppDefine = Keyword("#define") + ident.setResultsName("macro") + empty + restOfLine.setResultsName("value")
        ppDirective = Combine("#" + Word(alphas)) + restOfLine
        
        self.macroExpr << MatchFirst( map(Keyword,self.macros.keys()) )

        # attach parse actions to expressions
        self.macroExpr.setParseAction(self.processMacroRef)
        ppDefine.setParseAction(self.processMacroDefn)

        # define pattern for scanning through the input string
        self.macroExpander = (self.macroExpr | ppDefine.suppress() | ppDirective.suppress()).ignore(quotedString)
        self.files[file] =  self.macroExpander.transformString(text)

        
    def parseDefs(self, file, returnUnparsed=False):
        """Scan through the named file for variable, struct, enum, and function declarations.
        Returns the entire tree of successfully parsed tokens.
        If returnUnparsed is True, return a string of all lines that failed to match (for debugging)."""
        
        ## Some basic definitions
        ident = Word(alphas+"_",alphanums+"_$")
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
        functionCall = Forward()

        #typeSpec = OneOrMore(oneOf("const static unsigned signed int long short float double char void *")) 
        self.definedType << MatchFirst( map(Keyword,self.types.keys()) )

        fundType = Optional(Keyword('unsigned') | Keyword('signed')) + (Keyword('void') | (ZeroOrMore('long') + MatchFirst(map(Keyword,["int", 'float', 'double', 'char', 'bool'])) ) | OneOrMore(oneOf("long short")))
        typeQualifier = ZeroOrMore(MatchFirst(map(Keyword,['const', 'static', 'volatile', 'inline']))).suppress()
        typeSpec = typeQualifier + (fundType|self.definedType).setResultsName('type') + typeQualifier + stars + typeQualifier

        arraySizeSpecifier = integer | ident  
        bitfieldspec = ":" + arraySizeSpecifier
        arrayOp = bitfieldspec | ( lbrack + arraySizeSpecifier + rbrack )
        varNameSpec = Group( ident + Optional(arrayOp))
        operator = oneOf("+ - / * | & || && ^ % ++ -- == != > < >= <=")
        expression = OneOrMore(operator | functionCall | ident | quotedString | number)
        functionCall << ident + '(' + ZeroOrMore(expression) + ')'

        ## typedef
        typeDecl = Keyword('typedef') + (fundType | self.definedType).setResultsName('type') + delimitedList(Group(Combine(ZeroOrMore('*')).setResultsName('ptrs') + ident.setResultsName('newType') + ZeroOrMore(arrayOp).setResultsName('arr'))) + semi
        typeDecl.setParseAction(self.processType)

        ## variable definition
        variableSingleDecl = Group(typeSpec + ident.setResultsName('name')) + Optional(Literal('=').suppress() + expression.setResultsName('value'))

        variableDecl = Group(typeSpec.setResultsName('type') + ident.setResultsName('name') + ZeroOrMore(arrayOp).setResultsName('arr')) + Optional(Literal('=').suppress() + (expression.setResultsName('value') | (lbrace + Group(delimitedList(expression)).setResultsName('arrayValue') + rbrace))) + semi

        ## Struct definition
        structDecl = Forward()
        memberDecl = (Group(variableDecl) | structDecl)
        structDecl << (Keyword('struct') | Keyword('union')) + Optional(ident).setResultsName('name') + lbrace + Group(ZeroOrMore( memberDecl )).setResultsName('members') + rbrace + Optional(Word("*"), default="") + Optional(varNameSpec) + semi

        ## enum definition
        enumVarDecl = Group(ident.setResultsName('name')  + Optional(Literal('=').suppress() + integer.setResultsName('value')))
        enumDecl = Keyword('enum') + Optional(ident).setResultsName('name') + lbrace + Group(delimitedList(enumVarDecl)).setResultsName('names') + rbrace + Optional(ident) + semi

        ## function definition
        functionDecl = typeSpec.setResultsName('type') + ident.setResultsName('name') + lparen + Group(Optional(delimitedList(variableSingleDecl))).setResultsName('args') + rparen + (nestedExpr('{', '}').suppress() | semi)

        
        if returnUnparsed:
            text = (
                typeDecl.suppress() | 
                enumDecl.setParseAction(self.processEnum).suppress() | 
                structDecl.setParseAction(self.processStruct).suppress() | 
                variableDecl.setParseAction(self.processVariable).suppress() | 
                functionDecl.setParseAction(self.processFunction).suppress()
            ).transformString(self.files[file])
            return re.sub(r'\n\s*\n', '\n', text)
        else:
            return [x[0] for x in (
                typeDecl | 
                enumDecl.setParseAction(self.processEnum) | 
                structDecl.setParseAction(self.processStruct) | 
                variableDecl.setParseAction(self.processVariable) | 
                functionDecl.setParseAction(self.processFunction)
            ).scanString(self.files[file])]

    
    
        
    # parse action for macro definitions
    def processMacroDefn(self, s,l,t):
        macroVal = self.macroExpander.transformString(t.value)
        self.macros[t.macro] = macroVal
        self.values[t.macro] = self.evalExpr(macroVal)
        self.macroExpr << MatchFirst( map(Keyword,self.macros.keys()) )
        return "#define " + t.macro + " " + macroVal
        
    # parse action to replace macro references with their respective definition
    def processMacroRef(self, s,l,t):
        return self.macros[t[0]]

    def processEnum(self, s, l, t):
        try:
            if t.name != '':
                i = 0
                enum = {}
                for v in t.names:
                    if v.value != '':
                        i = int(v.value)
                    enum[v.name] = i
                    self.values[v.name] = i
                    i += 1
                self.enums[t.name] = enum
        except:
            print t
            sys.excepthook(*sys.exc_info())

    def processFunction(self, s, l, t):
        try:
            rType = (t.type.type, len(t.type.ptrs))
            args = []
            for a in t.args:
                args.append((a.name, a.type, len(a.ptrs)))
            self.functions[t.name] = (rType, args)
        except:
            print t
            sys.excepthook(*sys.exc_info())

    def evalExpr(self, toks):
        ## Evaluates expressions. Currently only works for expressions that also 
        ## happen to be valid python expressions.
        ## This function does not currently include previous variable
        ## declarations, but that should not be too difficult to implement..
        
        try:
            if type(toks) is str:
                val = eval(toks)
            elif toks.arrayValue != '':
                val = [eval(x) for x in toks.arrayValue]
            elif toks.value != '':
                val = eval(toks.value[0])
            else:
                val = None
            return val
        except:
            #print "failed eval:", toks
            return None

    def processStruct(self, s, l, t):
        try:
            if t.name != '':
                struct = {}
                for m in t.members:
                    struct[m[0].name] = (m[0].type.type, len(m[0].type.ptrs), [int(x) for x in m[0].arr], self.evalExpr(m))
                self.structs[t.name] = struct
        except:
            print t
            sys.excepthook(*sys.exc_info())

    def processVariable(self, s, l, t):
        try:
            name = t[0].name
            #print t, name, t.value
            self.variables[name] = self.evalExpr(t)
            self.values[name] = self.variables[name]
        except:
            #print t, t[0].name, t.value
            sys.excepthook(*sys.exc_info())

    def processType(self, s, l, t):
        typ = t.type
        for d in t[2:]:
            self.types[d.newType] = (typ, len(d.ptrs), [int(x) for x in d.arr])
            self.definedType << MatchFirst( map(Keyword,self.types.keys()) )

    def printAll(self):
        """Print everything parsed from files. Useful for debugging."""
        from pprint import pprint
        print "==============MACROS=================="
        pprint(self.macros)
        print "==============TYPES==================="
        pprint(self.types)
        print "==============VARIABLES==================="
        pprint(self.variables)
        print "==============FUNCTIONS==================="
        pprint(self.functions)
        print "==============ENUMS==================="
        pprint(self.enums)
        print "==============STRUCTS==================="
        pprint(self.structs)
        print "==============ALL VALUES==================="
        print self.values
        

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
    