import os
import yaml

from .FileType import FileType


class YamlFile(FileType):
    @classmethod
    def write(cls, data, dirHandle, fileName, **args):
        if not next((True for ext in cls.extensions if ext in fileName), None):
            fileName = f"{fileName}.yaml"
        with open(os.path.join(dirHandle.name(), fileName), "w") as fh:
            yaml.dump(data, fh)
        return fileName

    @classmethod
    def read(cls, fileHandle):
        with open(fileHandle.name()) as fh:
            return yaml.load(fh, yaml.CLoader)

    extensions = [".yml", ".yaml"]  # list of extensions handled by this class
    dataTypes = [dict, list, tuple]  # list of python types handled by this class
    priority = 50
