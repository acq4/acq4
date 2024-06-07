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
    parser.add_argument('-x', '--x', type=int, default=None, help='For a region, center on this X value')
    parser.add_argument('-y', '--y', type=int, default=None, help='For a region, center on this Y value')
    parser.add_argument('-r', '--r', type=int, default=None, help='Select the region described by a cylinder with radius R, centered on (X, Y)')
    parser.add_argument('-z', '--z', type=int, default=None, help='Pull a single frame at Z index')
    parser.add_argument('--info', action='store_true', help='Print info about the file and exit')
    args = parser.parse_args()
    ma = MetaArray(file=args.input)
    if args.info:
        print(ma.prettyInfo())
        exit(0)
    data = ma.view(np.ndarray)
    name_parts = [args.input[:-3]]

    if any((args.x, args.y, args.r)):
        if not all((args.x, args.y, args.r)):
            raise ValueError("Either all (x, y, r) must be specified, or none")
        data = data[:, args.y-args.r:args.y+args.r, args.x-args.r:args.x+args.r]
        name_parts.extend((f"{args.x:04d}x", f"{args.y:04d}y", f"{args.r:04d}r"))

    if args.z is not None:
        data = data[args.z]
        name_parts.append(f"{args.z:04d}")
    else:
        name_parts.append("3D")

    if args.output:
        output = args.output
    else:
        output = f"{'_'.join(name_parts)}.tiff"

    tifffile.imwrite(output, data)


if __name__ == '__main__':
    main()
