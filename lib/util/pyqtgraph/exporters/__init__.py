from Exporter import SVGExporter, ImageExporter
Exporters = [SVGExporter, ImageExporter]

def listExporters():
    return Exporters[:]

