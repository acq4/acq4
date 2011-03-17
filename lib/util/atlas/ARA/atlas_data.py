# -*- coding: utf-8 -*-
import csv, os, re, pickle
import numpy as np
libDir = os.path.dirname(os.path.abspath(__file__))
structFile = os.path.join(libDir, 'data', 'brainstructures.csv')
atlasFile = os.path.join(libDir, 'data', 'AtlasAnnotation25.sva')
cacheFile = os.path.join(libDir, 'data', 'cache.pickle')


class Atlas:
    def __init__(self):
        self.readAtlas()
    
    def readAtlas(self):
        if os.path.isfile(cacheFile):
            print "Reading cache.."
            data = pickle.load(open(cacheFile, 'rb'))
            for k in data:
                setattr(self, k, data[k])
            return
            
        ## no cache file; read raw data
        ## read list of structures
        print "Reading data.."
        fh = open(structFile, 'rb')
        header = fh.readline()
        r = csv.reader(fh)
        self.names = ''
        self.nameIndex = {}
        self.structs = {}
        for row in r:
            (name, abbrev, parent, r, g, b, iid, sid) = row
            self.structs[int(iid)] = {
                'name': name, 
                'abbrev': abbrev, 
                'parent': parent, 
                'color': (int(r), int(g), int(b)), 
                'IID': int(iid), 
                'SID': int(sid), 
                #'coords': [],
            }
            ind = len(self.names)
            self.nameIndex[ind] = int(iid)
            self.names += name + "\n"
        
        ## read atlas
        fh = open(atlasFile, 'rb')
        fh.readline()
        dims = fh.readline().split(':')[1].split(',')
        dims = map(int, dims)
        r = csv.reader(fh)
        self.atlas = np.zeros(dims, dtype=np.ubyte)
        for row in r:
            coords = tuple(map(int, row[:3]))
            iid = int(row[3])
            self.atlas[coords] = iid
            #self.structs[iid]['coords'].append(coords)
            
        cache = {}
        for k in ['names', 'nameIndex', 'atlas', 'structs']:
            cache[k] = getattr(self, k)
        print "Writing cache.."
        pickle.dump(cache, open(cacheFile, 'wb'))
    
    def findName(self, name):
        iids = []
        for m in re.finditer(r'^[^\n]*%s[^\n]*$' % name, self.names, re.M|re.I):
            iid = self.nameIndex[m.start()]
            iids.append(iid)
        return iids
        


if __name__ == '__main__':
    atlas = Atlas()
    from pyqtgraph.graphicsWindows import *
    w = ImageWindow()
    w.setImage(atlas.atlas)
    