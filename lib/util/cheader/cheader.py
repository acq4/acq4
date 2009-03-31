import gccxmlparser, types, os, tempfile, typedesc, re, sys, ctypes
  
def decomment(string):
  return re.sub(r'/\*.*\*/', '', re.sub(r'//.*', '', string))


def getDefs(headerFiles):
  """Read a list of header files, interprets #DEFINE and enum. Returns a dictionary of name:values"""
  variables = {}
  
  if type(headerFiles) is not types.ListType:
    headerFiles = [headerFiles]
    
  for hfile in headerFiles:
    fh = open(hfile)
    data = fh.readlines()
    fh.close()
    
    for i in range(0, len(data)):
      l = decomment(data[i])
      
      # Search for #define, set variable
      m = re.match(r'\s*\#define\s+(\S+)\s+(.*)', l)
      if m is not None:
        var = m.groups()[0]
        expr = m.groups()[1]
        if len(var) > 0 and len(expr) > 0:
          try:
            variables[var] = eval(expr, variables)
          except:
            variables[var] = None

      # search for enum
      if re.match(r'\s*enum\s+', l):
        # concatenate lines until the end of the enum
        ind = i
        enum = ''
        while True:
          enum += decomment(data[ind])
          if re.search('}', data[ind]):
            break
          ind += 1

        # Pull out variables
        enum = re.sub('(\n|\s)', '', enum)
        enum = re.sub(r'.*{', '', enum)
        enum = re.sub(r'}.*', '', enum)
        ind = 0
        for var in enum.split(','):
          variables[var] = ind
          ind += 1
  return variables


def getCType(obj, ptr=0):
  if type(obj) is typedesc.FundamentalType:
    return (cTypeNames[obj.name], ptr)
  elif type(obj) is typedesc.FunctionType:
    return (funcCType(obj), ptr)
  elif type(obj) is typedesc.PointerType:
    return getCType(obj.typ, ptr+1)
  else:
    return getCType(obj.typ, ptr)

def funcCType(func):
  return None
  args = []
  for arg in func.arguments:
    args.append(getattr(ctypes, getCType(arg.atype)))
  print args
  if 'win' in sys.platform:
    return ctypes.WINFUNCTYPE(*args)
  else:
    return ctypes.CFUNCTYPE(*args)
    



cTypeNames = {
    "unsigned char": "c_ubyte",
    "signed char": "c_byte",
    "char": "c_char",

    "wchar_t": "c_wchar",

    "short unsigned int": "c_ushort",
    "short int": "c_short",

    "long unsigned int": "c_ulong",
    "long int": "c_long",
    "long signed int": "c_long",

    "unsigned int": "c_uint",
    "int": "c_int",

    "long long unsigned int": "c_ulonglong",
    "long long int": "c_longlong",

    "double": "c_double",
    "float": "c_float",

    "long double": "c_longdouble",

    "void": "c_void_p",
}



def getFuncs(headerFiles):
  """Read a list of header files or gccxml files, return a dictionary of function signatures.
    If the file extension is .h, it will be converted to a temporary XML file (requires gccxml) before parsing
    If the file extension is .xml, it will be parsed directly 
    
    Returns a dictionary of signatures like:
      {funcName: (returnType, [(arg1Name, arg1Type), ...]), ...}
    Types are given as ctypes.
  """
  if type(headerFiles) is not types.ListType:
    headerFiles = [headerFiles]
  functions = {}
  for hf in headerFiles:
    if os.path.splitext(hf)[1] == '.h':
      try:
        xmlf = tempfile.mkstemp(".xml")[1]
        os.system("gccxml %s -fxml=%s" % (hf, xmlf))
      except:
        print "Can not generate XML from header file, aborting"
        raise
    else:
      xmlf = hf
      
    #print "Parsing", xmlf
    xmlfData = gccxmlparser.parse(xmlf)
    for d in xmlfData:
      if type(d) is typedesc.Function and d.name[:9] != '__builtin':
        args = []
        for arg in d.arguments:
          typ, ptr = getCType(arg.atype)
          args.append((arg.name, typ, ptr))
        functions[d.name] = (getCType(d.returns), args)

  return functions
