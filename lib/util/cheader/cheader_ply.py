# -*- coding: utf-8 -*-
## Used to parse C headers to retrieve definitions for macros, const variables, enums, function signatures, structs.

import os, re, sys, ctypes
import lib.util.ply.lex as lex
import lib.util.ply.cpp as cpp


class cParser:
    def __init__(self):
        self.variables = {}
        self.enums = {}
        self.enumVars = {}
        self.functions = {}
    
    def getDefs(self, headerFiles, replace=None):
        """Read a list of header files, interprets #DEFINE and enum. Returns a tuple (values, functions).
        - values is a dictionary of name:value pairs 
        - functions is a dictionary with function names as keys and lists describing the function signature as values.
            function signatures look like: (returnType, returnTypePtrs, [arguments])
            and each argument looks like: (argType, argPtrs, argName)
            
        The 'replace' argument can be used to perform string replacements before parsing each line. This is useful for including
        your own type definitions."""
        if replace is None:
                replace = {}
        variables = {}
        functions = {}
        
        if not isinstance(headerFiles, list): #type(headerFiles) is not types.ListType:
            headerFiles = [headerFiles]
            
        text = ''
        for hfile in headerFiles:
            fh = open(hfile)
            text = text + fh.read() + '\n'
            fh.close()
            
        # make requested replacements
        for s,r in replace.items():
            text = re.sub(s, r, text)
        
        # execute/remove preprocessor directives, tokenize resulting code, remove comments and line breaks:
        (self.tokens, self.macros) = cpp.preprocess(text)
        
        # Extract definitions
        startPtr = 0
        i = 0
        while i < len(self.tokens):
            tok = self.tokens[i]
            if tok.type == ';':
                startPtr = i + 1
            if tok.type == 'CPP_ID':
                if tok.value == 'typedef':
                    i = self.parseTypedef(startPtr)
                if tok.value == 'enum':
                    toks = self.getTokens(startPtr, ';')
                    i = startPtr + len(toks) - 1
                    self.parseEnum(toks)
                elif tok.value == 'struct':
                    i = self.findTokenType(i, '{')
                    i = self.findClosingToken(i+1, '{', '}')
                    self.parseStruct(self.tokens[startPtr:i])
                    
                    #i = startPtr + len(toks) - 1
                    #self.parseStruct(toks)
            elif tok.type == '=':
                toks = self.getTokens(startPtr, ';')
                i = startPtr + len(toks) - 1
                self.parseVariable(toks)
            elif tok.type == '(':
                #toks = self.getTokens(startPtr, ')')
                i = self.findClosingToken(i+1, '(', ')')
                #depth = 1
                #i += 1
                #while i < len(self.tokens):
                    #tok = self.tokens[i]
                    #if tok.type == '(':
                        #depth += 1
                    #elif tok.type == ')':
                        #depth -= 1
                    #if depth == 0:
                        #break
                    #i += 1
                self.parseFunction(self.tokens[startPtr:i])
                ## If a function definition follows, skip over it.
                depth = 0
                blockStarted = False
                while i < len(self.tokens):
                    tok = self.tokens[i]
                    if not blockStarted and tok.type == ';':
                        break
                    if tok.type == '{':
                        blockStarted = True
                        depth += 1
                    elif tok.type == '}':
                        depth -= 1
                    if depth == 0:
                        break
                    i += 1
            i += 1

            
    #return variables, functions

    def getTokens(self, start, endType):
        stop = self.findTokenType(start, endType)
        return self.tokens[start:stop]

    def findTokenType(self, start, typ, tokens=None, endOk=True):
        if tokens is None:
            tokens = self.tokens
        i = start
        while i < len(tokens):
            if tokens[i].type == typ:
                break
            i += 1
        if endOk:
            return i
        else:
            return None

    def findClosingToken(self, start, openToken, closeToken, tokens=None):
        if tokens is None:
            tokens = self.tokens
        i = start
        depth = 1
        while i < len(tokens):
            tok = tokens[i]
            if tok.type == openToken:
                depth += 1
            elif tok.type == closeToken:
                depth -= 1
            if depth == 0:
                break
            i += 1
        return i
        

    def parseVariable(self, tokens):
        try:
            eq = self.findTokenType('=', tokens)
            name = tokens[eq-1].value
            value = eval(tokens[(eq+1):])
            self.variables[name] = value
        except:
            print "Error parsing variable", tokens
            sys.excepthook(*sys.exc_info())
    
    def parseEnum(self, tokens):
        enum = {}
        try:
            i = self.findTokenType('{', tokens)
            enumName = None
            if i == 2:
                enumName = tokens[1].value
                self.enums[enumName] = {}
            curVal = 0
            while i < len(tokens):
                stop = self.findTokenType(',', i, tokens)
                eq = self.findTokenType('=', i, tokens, endOk=False)
                if eq is not None:
                    curVal = eval(tokens[eq+1].value)
                name = tokens[i].value
                self.enumVars[name] = curVal
                if enumName is not None:
                    self.enums[enumName][name] = curVal
                i = stop + 1
                curVal += 1
        except:
            print "Error parsing enum", tokens
            sys.excepthook(*sys.exc_info())
    
    def parseFunction(self, tokens):
        print "Function:", ' '.join([t.value for t in tokens])
    
    def parseStruct(self, tokens):
        enum = {}
        try:
            i = self.findTokenType('{', tokens)
            enumName = None
            if i == 2:
                enumName = tokens[1].value
                self.enums[enumName] = {}
            curVal = 0
            while i < len(tokens):
                stop = self.findTokenType(',', i, tokens)
                eq = self.findTokenType('=', i, tokens, endOk=False)
                if eq is not None:
                    curVal = eval(tokens[eq+1].value)
                name = tokens[i].value
                self.enumVars[name] = curVal
                if enumName is not None:
                    self.enums[enumName][name] = curVal
                i = stop + 1
                curVal += 1
        except:
            print "Error parsing enum", tokens
            sys.excepthook(*sys.exc_info())



    #def preprocess(self, text):
        #"""Runs C preprocessor directives and returns the resulting tokenized code as well as preprocessor macros. Removes all comments and line breaks."""
        #lexer = lex.lex()
        #p = cpp.Preprocessor(lexer)
        #p.parse(text)
        ##text = ''
        #tokens = []
        #while True:
            #tok = p.token()
            #if not tok: break
            #if tok.type not in ['CPP_COMMENT', 'CPP_WS']:
                ##text += tok.value
                ##if tok.type not in ['CPP_WS']:
                    ##print tok.type, '\t', tok.value
                #tokens.append(tok)
        ##print text
        ##print "\nMACROS:"
        ##for m in p.macros:
            ##print p.macros[m].name, "=", "".join([tok.value for tok in p.macros[m].value])
        #return (tokens, p.macros)




#def getCType(obj, ptr=0):
    #if type(obj) is typedesc.FundamentalType:
        #return (cTypeNames[obj.name], ptr)
    #elif type(obj) is typedesc.FunctionType:
        #return (funcCType(obj), ptr)
    #elif type(obj) is typedesc.PointerType:
        #return getCType(obj.typ, ptr+1)
    #else:
        #return getCType(obj.typ, ptr)

#def funcCType(func):
    #return None
    #args = []
    #for arg in func.arguments:
        #args.append(getattr(ctypes, getCType(arg.atype)))
    #print args
    #if 'win' in sys.platform:
        #return ctypes.WINFUNCTYPE(*args)
    #else:
        #return ctypes.CFUNCTYPE(*args)
        



#cTypeNames = {
        #"unsigned char": "c_ubyte",
        #"signed char": "c_byte",
        #"char": "c_char",

        #"wchar_t": "c_wchar",

        #"short unsigned int": "c_ushort",
        #"short int": "c_short",

        #"long unsigned int": "c_ulong",
        #"long int": "c_long",
        #"long signed int": "c_long",

        #"unsigned int": "c_uint",
        #"int": "c_int",

        #"long long unsigned int": "c_ulonglong",
        #"long long int": "c_longlong",

        #"double": "c_double",
        #"float": "c_float",

        #"long double": "c_longdouble",

        #"void": "c_void_p",
#}



#def getFuncs(headerFiles):
    #"""Read a list of header files or gccxml files, return a dictionary of function signatures.
        #If the file extension is .h, it will be converted to a temporary XML file (requires gccxml) before parsing
        #If the file extension is .xml, it will be parsed directly 
        
        #Returns a dictionary of signatures like:
            #{funcName: (returnType, [(arg1Name, arg1Type), ...]), ...}
        #Types are given as ctypes.
    #"""
    #if type(headerFiles) is not types.ListType:
        #headerFiles = [headerFiles]
    #functions = {}
    #for hf in headerFiles:
        #if os.path.splitext(hf)[1] == '.h':
            #try:
                #xmlf = tempfile.mkstemp(".xml")[1]
                #os.system("gccxml %s -fxml=%s" % (hf, xmlf))
            #except:
                #print "Can not generate XML from header file, aborting"
                #raise
        #else:
            #xmlf = hf
            
        ##print "Parsing", xmlf
        #xmlfData = gccxmlparser.parse(xmlf)
        #for d in xmlfData:
            #if type(d) is typedesc.Function and d.name[:9] != '__builtin':
                #args = []
                #for arg in d.arguments:
                    #typ, ptr = getCType(arg.atype)
                    #args.append((arg.name, typ, ptr))
                #functions[d.name] = (getCType(d.returns), args)

    #return functions
