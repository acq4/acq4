"""Convert MetaArray files into tiff images."""

import argparse
import numpy as np
import tifffile
from MetaArray import MetaArray


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('input', help='MetaArray file')
    parser.add_argument('output', nargs='?', help='Output file for tiff image')
    parser.add_argument('-z', '--z', type=int, default=None, help='Pull a single frame at Z index')
    parser.add_argument('--info', action='store_true', help='Print info about the file and exit')
    args = parser.parse_args()
    ma = MetaArray(file=args.input)
    if args.info:
        print(ma.prettyInfo())
        exit(0)
    data = ma.view(np.ndarray)
    if args.z is not None:
        data = data[args.z]
        output = args.output or f"{args.input[:-3]}_{args.z:03d}.tiff"
    else:
        output = args.output or f"{args.input[:-3]}_3D.tiff"
    tifffile.imwrite(output, data)


if __name__ == '__main__':
    main()
