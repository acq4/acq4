# Autopatch validation scripts

Scripts a person runs on real acq4 data to check the autopatch survey record.
Data recorded before phase A is expected to show missing uuids.

## uuid_audit.py

Run `$PY tools/autopatch_validation/uuid_audit.py <dir>`. It reads every
`.index` under `<dir>` and every `*_detections.yaml` record. It prints the
count of indexed entries, then the entries with no `__uuid__`, any uuid used
more than once, and Cell directories whose `candidate_id` or `tile_id` match no
detection record. A passing result has all three lists empty and exits 0; any
finding exits 1. Audit a slice directory rather than the Data Manager root,
which has no uuid of its own.
