"""Simple script for testing pymmcore with a specific camera adapter and device name.
"""
import glob
import sys, argparse
import time
from acq4.util.micromanager import getMMCorePy
import pymmcore

parser = argparse.ArgumentParser(
    description="Test pymmcore with a specific camera adapter and device name.",
)
parser.add_argument("adapter", type=str, help="Camera adapter name")
parser.add_argument("device", type=str, help="Camera device name")
parser.add_argument("--no-acq4", action="store_true", help="Do not use acq4's micromanager wrapper")
parser.add_argument("--path", type=str, default=None, 
                    help="Path to the MicroManager installation (if not using acq4's wrapper)")
args = parser.parse_args()


if args.no_acq4:
    mmc = pymmcore.CMMCore()
else:
    # ACQ4's micromanager wrapper provides better error reporting,
    # automatically sets the device adapter search paths
    mmc = getMMCorePy()


# Set device adapter search paths
if args.path:
    paths = [args.path]
else:
    paths = glob.glob("C:\\Program Files\\Micro-Manager-2*")
print(f"Using MicroManager device search paths {'' if args.path else '(override with --path)'}: {paths}")
mmc.setDeviceAdapterSearchPaths(paths)


# Check adapter name
allAdapters = mmc.getDeviceAdapterNames()
if args.adapter not in allAdapters:
    print(f"Adapter name '{args.adapter}' is not valid.\nOptions are: {allAdapters}")
    sys.exit(1)
print(f"Using adapter: {args.adapter}")

# List devices available for the specified adapter
try:
    allDevices = mmc.getAvailableDevices(args.adapter)
except Exception as e:
    print(f"Error getting available devices for MicroManager adapter '{args.adapter}'.")
    print(f"  -> Check that the MicroManager API version number (help->about in the MicroManager GUI)"
          f"     matches the pymmcore API version number ({pymmcore.__version__.split('.')[3]}")
    print(f"  -> Error details: {e}")
    sys.exit(1)

# Check device name
if args.device not in allDevices:
    print(f"Device name '{args.device}' is not valid for adapter '{args.adapter}'.\nOptions are: {allDevices}")
    sys.exit(1)

print(f"Using device: {args.device}")

camName = "Camera"
mmc.loadDevice(camName, args.adapter, args.device)
mmc.initializeDevice(camName)
mmc.setCameraDevice(camName)
print(f"Camera '{camName}' successfully initialized with adapter '{args.adapter}' and device '{args.device}'.")


# test acquisition
print("Testing camera acquisition...")
n_frames = 3
mmc.startSequenceAcquisition(n_frames, 0, True)
frames = []
timeoutStart = time.time()
while mmc.isSequenceRunning() or mmc.getRemainingImageCount() > 0:
    if mmc.getRemainingImageCount() > 0:
        timeoutStart = time.time()
        frames.append(mmc.popNextImage())
    elif time.time() - timeoutStart > 10.0:
        raise TimeoutError("Timed out waiting for camera frame.")
    else:
        time.sleep(0.005)

if len(frames) < n_frames:
    print(f"Fixed-frame camera acquisition ended before all frames received ({len(frames)}/{n})")
else:
    print(f"Acquired {len(frames)} frames successfully.")
    print(f"Frame shape: {frames[0].shape}")
    print(f"Frame dtype: {frames[0].dtype}")    
mmc.stopSequenceAcquisition()

