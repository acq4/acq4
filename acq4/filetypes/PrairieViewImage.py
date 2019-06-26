import acq4.util.DataManager
import os
from acq4.util.metaarray import MetaArray
from .FileType import FileType

try:
    from optoanalysis import xml_parse
    HAVE_XML_PARSE = True
except:
    HAVE_XML_PARSE = False

class PrairieViewImage(FileType):

    extensions = []   ## list of extensions handled by this class
    dataTypes = []    ## list of python types handled by this class
    priority = 0

    @classmethod
    def read(cls, dirHandle):
        """Read a file, return a data object"""
        #from ..modules.MultiPatch.logfile import MultiPatchLog
        #return PhotostimLog(fileHandle.name())
        global HAVE_XML_PARSE
        if not HAVE_XML_PARSE:
            raise Exception("There was an error importing xml_parse from optoanalysis.")

        xmls = [f for f in dirHandle.ls() if f.endswith('.xml') and 'MarkPoints' not in f] # Don't want MP XML
        if len(xmls) > 1:
            raise Exception("Found more than one .xml file.")
        xml_file = os.path.join(dirHandle.name(), xmls[0])
        xml_attrs = xml_parse.parse_prairieView_xml(xml_file, dirHandle.name())

        #xml_attrs = xml_parse.parse_prairieView_xml(dirHandle.getFile(xmls[0]).name(), dirHandle.name())

        if 'ZSeries' in dirHandle.shortName():
            return xml_parse.load_zseries(xml_attrs, dirHandle)

        elif 'SingleImage' in dirHandle.shortName():
            data = xml_parse.load_images(xml_attrs, dirHandle.name())
            return MetaArray(data, info=[None]*len(data.shape)+[{'prairie_view_info':xml_attrs}])
        

        
    @classmethod
    def acceptsFile(cls, fileHandle):
        """Return priority value if the file can be read by this class.
        Otherwise return False.
        The default implementation just checks for the correct name extensions."""
        name = fileHandle.shortName()
        if isinstance(fileHandle, acq4.util.DataManager.DirHandle) and (('ZSeries-' in name) or ('SingleImage-' in name)):
            return 100
        return False

