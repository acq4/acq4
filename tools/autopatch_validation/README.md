# Autopatch validation scripts

Scripts a person runs on real acq4 data to check the autopatch survey record.
Data recorded before phase A is expected to show missing uuids.

## uuid_audit.py

Run `$PY tools/autopatch_validation/uuid_audit.py <dir>`. It reads every
`.index` under `<dir>` and every `*_detections.yaml` record. It prints the
count of indexed entries, then the entries with no `__uuid__`, any uuid used
more than once, and Cell directories whose `candidate_id` or `tile_id` match no
detection record. A passing result has all three lists empty and exits 0; any
finding exits 1; a root that is not a directory exits 2. A root made with
`getDirHandle(create=True)` has no uuid of its own, so audit a slice directory
in that case.

## spacing_report.py

Run `$PY tools/autopatch_validation/spacing_report.py <slice_dir> [--spacing 30e-6] [--try 10e-6 20e-6 ...] [--out spacing.png]`.
It reads the slice's `tiles/*_detections.yaml` records and prints a
nearest-neighbour histogram of the queued cells, any queued pairs closer than
the spacing, and how many cells other spacings would have queued. It writes a
PNG of the detections coloured by disposition. A pass is zero close pairs, plus
red (`too_close`) points that sit on top of green ones in the plot; any close
pair exits 1, and a slice directory that is not a directory exits 2.
