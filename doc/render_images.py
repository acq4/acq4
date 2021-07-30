#!/usr/bin/python
import os, sys
print("Rendering SVG -> PNG")

for path, _, files in os.walk('.'):
    for f in files:
        if f.endswith('.svg'):
            svg = os.path.join(path, f)
            png = os.path.splitext(svg)[0] + ".png"
            if not os.path.isfile(png) or os.stat(svg).st_mtime > os.stat(png).st_mtime:
                print("  Rendering %s" % svg)
                os.system('inkscape --export-png="%s" "%s"' % (png, svg))
            else:
                print("  Skipping  %s" % svg)


print("Image rendering complete.")
