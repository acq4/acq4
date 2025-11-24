# Auto-Versioning

This repository uses GitHub Actions to automatically increment the version number whenever code is merged to the `main` branch.

## How It Works

1. **Trigger**: The workflow runs on every push to `main` (including PR merges and direct commits)
2. **Version Detection**: The workflow analyzes commit messages (and PR titles/bodies for merge commits) to determine the version bump type
3. **Version Increment**: By default, the patch version is incremented (e.g., 0.9.3 → 0.9.4), but major and minor bumps can be requested
4. **Commit**: The new version is committed back to `main` with message `chore: bump version to X.Y.Z [skip-version]`
5. **Tag**: A git tag is created in the format `acq4-X.Y.Z`

## Version Location

The version is stored in `acq4/__init__.py` as:
```python
__version__ = 'X.Y.Z'
```

## Controlling Version Bumps

### Patch Version (Default)

By default, every push to `main` increments the patch version (e.g., 0.9.3 → 0.9.4).

### Minor Version

To trigger a minor version bump (e.g., 0.9.3 → 0.10.0), include one of these patterns in your commit message or PR title/body:
- `[minor]`
- `[minor-version]`
- `#minor`
- `minor bump`

Example:
```bash
git commit -m "feat: add new pipette control features [minor]"
```

### Major Version

To trigger a major version bump (e.g., 0.9.3 → 1.0.0), include one of these patterns in your commit message or PR title/body:
- `[major]`
- `[major-version]`
- `#major`
- `major bump`

Example:
```bash
git commit -m "feat: redesigned device interface [major]"
```

### Skipping Auto-Versioning

To skip version incrementing entirely, include `[skip-version]` in your commit message:
```bash
git commit -m "docs: update README [skip-version]"
```

## Automatic Skip Conditions

The workflow will automatically skip version bumping in these cases:
- The commit was made by the `github-actions[bot]` user
- The latest commit already modified the version in `acq4/__init__.py`
- A `[skip-version]` tag is present in any commit message in the push

## Pull Request Behavior

For merge commits created by GitHub when merging pull requests:
- The workflow checks both the commit messages in the PR branch AND the PR title/body
- This allows you to control versioning from the PR title without needing special commit messages

Example PR title:
```
Add multi-channel recording support [minor]
```

## Workflow File

The workflow is defined in `.github/workflows/auto-version.yml`
