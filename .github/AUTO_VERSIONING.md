# Auto-Versioning

This repository uses GitHub Actions to automatically increment the version number whenever code is merged to the `main` branch.

## How It Works

1. **Trigger**: The workflow runs on every push to `main` (including PR merges and direct commits)
2. **Version Increment**: The patch version is automatically incremented (e.g., 0.9.3 → 0.9.4)
3. **Commit**: The new version is committed back to `main` with message `chore: bump version to X.Y.Z [skip-version]`
4. **Tag**: A git tag is created in the format `acq4-X.Y.Z`

## Version Location

The version is stored in `acq4/__init__.py` as:
```python
__version__ = 'X.Y.Z'
```

## Skipping Auto-Versioning

To skip version incrementing for a specific commit, include `[skip-version]` in your commit message:
```bash
git commit -m "docs: update README [skip-version]"
```

## Manual Version Changes

If you need to manually change the major or minor version:
1. Edit `acq4/__init__.py` directly
2. Commit with `[skip-version]` to prevent automatic incrementing
3. The next automatic bump will increment from your new version

## Workflow File

The workflow is defined in `.github/workflows/auto-version.yml`
