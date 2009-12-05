# -*- coding: utf-8 -*-
from pyparsing import *
import pprint, sys

__all__ = []

## Global variables, yuck.
global types, variables, structs, enums, functions
def reset():
    global types, variables, structs, enums, functions
    types = {}
    variables = {}
    functions = {}
    structs = {}
    enums = {}
reset()

## Some basic definitions
ident = Word(alphas+"_",alphanums+"_$")
cplusplusLineComment = Literal("//") + restOfLine
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
definedType = Forward()  ## Matches types previously declared in a typedef

#typeSpec = OneOrMore(oneOf("const static unsigned signed int long short float double char void *")) 

fundType = Optional(Keyword('unsigned') | Keyword('signed')) + (Keyword('void') | (ZeroOrMore('long') + MatchFirst(map(Keyword,["int", 'float', 'double', 'char'])) ) | OneOrMore(oneOf("long short")))
typeQualifier = ZeroOrMore(MatchFirst(map(Keyword,['const', 'static', 'volatile', 'inline']))).suppress()
typeSpec = typeQualifier + (fundType|definedType).setResultsName('type') + typeQualifier + stars + typeQualifier


arraySizeSpecifier = integer | ident  
bitfieldspec = ":" + arraySizeSpecifier
arrayOp = bitfieldspec | ( lbrack + arraySizeSpecifier + rbrack )
varNameSpec = Group( ident + Optional(arrayOp))
operator = oneOf("+ - / * | & || && ^ % ++ -- == != > < >= <=")
expression = OneOrMore(operator | functionCall | ident | quotedString | number)
functionCall << ident + '(' + ZeroOrMore(expression) + ')'

## typedef
def processType(s, l, t):
    global types
    typ = t.type
    for d in t[2:]:
        types[d.newType] = (typ, len(d.ptrs), [int(x) for x in d.arr])
        definedType << MatchFirst( map(Keyword,types.keys()) )
typeDecl = Keyword('typedef') + (fundType | definedType).setResultsName('type') + delimitedList(Group(Combine(ZeroOrMore('*')).setResultsName('ptrs') + ident.setResultsName('newType') + ZeroOrMore(arrayOp).setResultsName('arr'))) + semi
typeDecl.setParseAction(processType)

## variable definition

def evalExpr(toks):
    #print "values:", toks.value, toks.arrayValue
    if toks.arrayValue != '':
        var = [eval(x) for x in toks.arrayValue]
    elif toks.value != '':
        var = eval(toks.value[0])
    else:
        var = None
    return var

def processVariable(s, l, t):
    global variables
    try:
        name = t[0].name
        #print t, name, t.value
        variables[name] = evalExpr(t)
    except:
        #print t, t[0].name, t.value
        sys.excepthook(*sys.exc_info())
variableSingleDecl = Group(typeSpec + ident.setResultsName('name')) + Optional(Literal('=').suppress() + expression.setResultsName('value'))

variableDecl = Group(typeSpec.setResultsName('type') + ident.setResultsName('name') + ZeroOrMore(arrayOp).setResultsName('arr')) + Optional(Literal('=').suppress() + (expression.setResultsName('value') | (lbrace + Group(delimitedList(expression)).setResultsName('arrayValue') + rbrace))) + semi

## Struct definition
def processStruct(s, l, t):
    global structs
    try:
        if t.name != '':
            struct = {}
            for m in t.members:
                struct[m[0].name] = (m[0].type.type, len(m[0].type.ptrs), [int(x) for x in m[0].arr], evalExpr(m))
            structs[t.name] = struct
    except:
        print t
        sys.excepthook(*sys.exc_info())
    
structDecl = Forward()
memberDecl = (Group(variableDecl) | structDecl)
structDecl << (Keyword('struct') | Keyword('union')) + Optional(ident).setResultsName('name') + lbrace + Group(ZeroOrMore( memberDecl )).setResultsName('members') + rbrace + Optional(Word("*"), default="") + Optional(varNameSpec) + semi

## enum definition
def processEnum(s, l, t):
    global enums
    try:
        if t.name != '':
            i = 0
            enum = {}
            for v in t.names:
                if v.value != '':
                    i = int(v.value)
                enum[v.name] = i
                i += 1
            enums[t.name] = enum
    except:
        print t
        sys.excepthook(*sys.exc_info())
    
enumVarDecl = Group(ident.setResultsName('name')  + Optional(Literal('=').suppress() + integer.setResultsName('value')))
enumDecl = Keyword('enum') + Optional(ident).setResultsName('name') + lbrace + Group(delimitedList(enumVarDecl)).setResultsName('names') + rbrace + Optional(ident) + semi

## function definition
def processFunction(s, l, t):
    global functions
    try:
        rType = (t.type.type, len(t.type.ptrs))
        args = []
        for a in t.args:
            args.append((a.name, a.type, len(a.ptrs)))
        functions[t.name] = (rType, args)
    except:
        print t
        sys.excepthook(*sys.exc_info())
    
functionDecl = typeSpec.setResultsName('type') + ident.setResultsName('name') + lparen + Group(Optional(delimitedList(variableSingleDecl))).setResultsName('args') + rparen + (nestedExpr('{', '}').suppress() | semi)

 
def removeComments(text):
    return (cStyleComment | cplusplusLineComment).ignore(quotedString).suppress().transformString(text)
    
 
def preprocess(text):
    # define the structure of a macro definition (the empty term is used 
    # to advance to the next non-whitespace character)
    ppDefine = Keyword("#define") + ident.setResultsName("macro") + empty + restOfLine.setResultsName("value")
    ppDirective = Combine("#" + Word(alphas)) + restOfLine
    
    #ppIfndefBlock = ppIfndef + Optional(ppElse) + 
                    
    # define a placeholder for defined macros - initially nothing
    macroExpr = Forward()

    # dictionary for macro definitions
    macros = {}

    # parse action for macro definitions
    def processMacroDefn(s,l,t):
        macroVal = macroExpander.transformString(t.value)
        macros[t.macro] = macroVal
        macroExpr << MatchFirst( map(Keyword,macros.keys()) )
        return "#define " + t.macro + " " + macroVal

    # parse action to replace macro references with their respective definition
    def processMacroRef(s,l,t):
        return macros[t[0]]

    # attach parse actions to expressions
    macroExpr.setParseAction(processMacroRef)
    ppDefine.setParseAction(processMacroDefn)

    # define pattern for scanning through the input string
    macroExpander = (macroExpr | ppDefine.suppress() | ppDirective.suppress()).ignore(quotedString)
    return macroExpander.transformString(text), macros 


def parseDefs(text):
    return [x[0] for x in (
        typeDecl | 
        enumDecl.setParseAction(processEnum) | 
        structDecl.setParseAction(processStruct) | 
        variableDecl.setParseAction(processVariable) | 
        functionDecl.setParseAction(processFunction)
    ).scanString(text)]
    
def getDefs(files, types=None, replace=None):
    pass


if __name__ == '__main__':
    #global types
    #global variables
    files = sys.argv[1:]
    text = ''
    for f in files:
        fd = open(f)
        text += fd.read()
        fd.close()
    
    text = removeComments(text)
    #print "==============REM COMMENTS=================="
    #print text
    
    text, macros = preprocess(text)
    print "==============PREPROCESSED=================="
    print text
    
    print "==============MACROS=================="
    pprint.pprint(macros)
    
    matches = parseDefs(text)
    
    print "==============MATCHES========================"
    pprint.pprint(matches)
    print "==============TYPES==================="
    pprint.pprint(types)
    print "==============VARIABLES==================="
    pprint.pprint(variables)
    print "==============FUNCTIONS==================="
    pprint.pprint(functions)
    print "==============ENUMS==================="
    pprint.pprint(enums)
    print "==============STRUCTS==================="
    pprint.pprint(structs)
