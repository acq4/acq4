# Autopatch validation scripts

Scripts a person runs on real acq4 data to check the autopatch survey record.
Data recorded before phase A is expected to show missing uuids.

## uuid_audit.py

Run `$PY tools/autopatch_validation/uuid_audit.py <dir>`. It reads every
`.index` under `<dir>` and every `*_detections.yaml` record. It prints the
count of indexed entries, then the entries with no `__uuid__`, any uuid used
more than once, and Cell directories whose `candidate_id` or `tile_id` match no
detection record or `survey_manual.yaml` manual entry. A passing result has all three lists empty and exits 0; any
finding exits 1; a root that is not a directory exits 2. A root made with
`getDirHandle(create=True)` has no uuid of its own, so audit a slice directory
in that case.

## spacing_report.py

Run `$PY tools/autopatch_validation/spacing_report.py <slice_dir> [--spacing 30e-6] [--try 10e-6 20e-6 ...] [--out spacing.png] [--live]`.
It reads the slice's `tiles/*_detections.yaml` records and prints a
nearest-neighbour histogram of the queued cells, any queued pairs closer than
the spacing, and how many cells other spacings would have queued. It writes a
PNG of the detections coloured by disposition. A pass is zero close pairs, plus
red (`too_close`) points that sit on top of green ones in the plot; any close
pair exits 1, and a slice directory that is not a directory exits 2.
`--live` instead replays the live selector over the slice (tile records,
`survey_manual.yaml` and `regions.yaml`) and prints one line per pick: index,
candidate id, source, score and position in µm. Manual entries come first.
`--spacing` (or the recorded spacing) sets the spacing; it exits 0.

## tile_transforms.py

Run `$PY tools/autopatch_validation/tile_transforms.py <slice_dir> [--pixel 1e-6] [--out mosaic.png]`.
It places each saved tile stack in global coordinates using the transform on
its index entry, compares that with the transform written into the `.ma` file,
and uses phase cross-correlation to measure how far each overlapping pair is
out of register. It writes a mosaic PNG with tile outlines and detections. A
pass is:
- the index and file transforms agree to within a nanometre;
- every overlap shift is under 2 px (2 µm at the default `--pixel`; the output states both);
- the red detection dots sit on cells in the mosaic.

Each shift is `(dy, dx)` in grid pixels: the amount that moves tile j onto
tile i (so it is the negative of how far j sits from where it should). Overlaps
are registered over their true shared area, so rotated tiles work. A shift of 2
px or more, a transform disagreement over a nanometre, or no measurable overlap
exits 1. A slice directory that is not a directory, has no `tiles/` index, has
no tiles with a transform, or would need a grid over 4096x4096 (raise
`--pixel`) exits 2. A tile with no transform in its `.ma` header is reported
and does not fail.
