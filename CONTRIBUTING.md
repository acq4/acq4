# Contributing to acq4

Contributions to acq4 are welcome!

Please use the following guidelines when preparing changes:

## Submitting Code Changes

* The preferred method for submitting changes is by github pull request against the "develop" branch.
* Pull requests should include only a focused and related set of changes. Mixed features and unrelated changes are more likely to be rejected.
* For major changes, it is recommended to discuss your plans on the mailing list or in a github issue before putting in too much effort.
* Many changes (especially new devices and user interface modules) can be implemented as an extension module rather than modifying the
  acq4 codebase; this can be a faster way to make your code available to the world.

## Documentation

* Writing proper documentation and unit tests is highly encouraged. acq4 uses pytest style testing, so tests should usually be included in a tests/ directory adjacent to the relevant code.
* Documentation is generated with sphinx; please check that docstring changes compile correctly

## Style guidelines

### Rules

* Acq4 prefers PEP8 for most style issues, but this is not enforced rigorously as long as the code is clean and readable.
* We use the numpy docstring format.
* Exception 1: All variable names should use camelCase rather than underscore_separation. This is done for consistency with Qt

