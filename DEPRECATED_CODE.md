# Deprecated Code: Summary and Recommendations

Reviewed: 2026-10-13. Scope: explicit deprecation markers in `pylinac/`,
checked dependency APIs, and behavior-safe updates verified below.

## Enhanced Summary

Legacy APIs remain available. Safe updates reduce repeated array work and remove
unused warning objects. Quart documentation now matches its code. Nuclear
morphology keeps the original results on both tested dependency versions.
Changes that alter values are skipped. No library support limits were changed.

## Tracked Items

| Item and source                                                                                                                                      | Status                                                                                 | Recommended replacement or action                                                                                                     |
| ---------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `pylinac.core.metrics` ([metrics.py](pylinac/core/metrics.py#L7))                                                                                    | Deprecated; warns on import.                                                           | Use `pylinac.metrics.image`, `.features`, or `.utils`.                                                                                |
| `pylinac.core.profile.stretch()` ([profile.py](pylinac/core/profile.py#L44))                                                                         | Deprecated since 3.11; still called by [load_multiples()](pylinac/core/image.py#L349). | Use `array_utils.stretch()`, but preserve data type behavior: it has no `fill_dtype` argument and handles minimum values differently. |
| `ProfileBase.x_at_x()` ([profile.py](pylinac/core/profile.py#L243))                                                                                  | Deprecated alias; warns on use.                                                        | Use `x_at_x_idx()`.                                                                                                                   |
| `LowContrastDiskROI.cnr_constant` and `.contrast_constant` ([first property](pylinac/core/roi.py#L331), [second property](pylinac/core/roi.py#L352)) | Planned deprecations; neither emits its warning.                                       | Use `visibility`; review limits because the formulas differ. Related pass/fail and plot-color properties still use the old values.    |
| `CatPhanBase.analyze(cnr_threshold=...)` ([ct.py](pylinac/ct.py#L2768))                                                                              | Deprecated since 3.0 in the docstring.                                                 | Use `visibility_threshold` with a reviewed limit, not the old CNR value.                                                              |
| `QuartDVT.analyze(cnr_threshold=...)` ([quart.py](pylinac/quart.py#L536))                                                                            | Deprecated in the docstring; unused argument.                                          | Note corrected. The argument remains accepted and unused; no visibility argument was added.                                          |
| `HypersightQuartDVT` ([quart.py](pylinac/quart.py#L861))                                                                                             | Deprecated; warns during construction.                                                 | Use `QuartDVT`, which supports the water vial.                                                                                        |
| `WinstonLutz2D.bb` and `.field_cax` ([winston_lutz.py](pylinac/winston_lutz.py#L1217))                                                               | Comment-only deprecation; no warning or removal date.                                  | Internally use `arrangement_matches["Iso"].bb` and `.field`. Keep public attributes for existing users.                               |

### Dependency Items

[pyproject.toml](pyproject.toml) allows scikit-image 0.26+, but requires pydicom below 3.

| Used API and locations                                                                                                                                                                                                                                                                                      | Status                                                                                                 | Recommended action                                                                             |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| `morphology.binary_closing()` ([planar_imaging.py](pylinac/planar_imaging.py#L3898))                                                                                                                                                                                                                        | Deprecated in scikit-image 0.26; migration skipped.                                                     | Kept unchanged: the proposed replacement changed one of 192 checked masks.                    |
| `remove_small_objects()` ([nuclear.py](pylinac/nuclear.py#L463))                                                                                                                                                                                                                                          | Updated when supported; older argument kept as a fallback.                                             | Runtime-verified `max_size=2` on 0.26; `min_size=2` on older versions.                          |
| `remove_small_holes()` ([nuclear.py](pylinac/nuclear.py#L464))                                                                                                                                                                                                                                            | Updated when supported; older argument kept as a fallback.                                             | Runtime-verified `max_size=2` on 0.26; `area_threshold=2` on older versions.                    |
| `save_as(write_like_original=False)` ([array_utils.py](pylinac/core/array_utils.py#L361), [simulators.py](pylinac/core/image_generator/simulators.py#L77), [dicom.py](pylinac/plan_generator/dicom.py#L652), [Winston-Lutz call 1](pylinac/winston_lutz.py#L1410), [call 2](pylinac/winston_lutz.py#L1541)) | Five calls; deprecated in pydicom 3.0, removed in 4.0. Not deprecated under the current version limit. | When adding 3.x support, use `enforce_file_format=True` through a compatible writer.           |
| `pydicom.pixel_data_handlers.apply_rescale` ([image.py](pylinac/core/image.py#L27))                                                                                                                                                                                                                         | Namespace deprecated in 3.0; guarded fallback for 2.x.                                                 | Keep the fallback while supporting 2.x. The modern `pydicom.pixels` import is already present. |

Runtime checks showed that the original deprecated calls match `max_size=2`, not
`1`, in the installed 0.26 release. Older versions keep their original arguments.
Results are preserved within each tested dependency version, not made identical
across different versions.

### Legacy, Not Deprecated

- `interp1d`: used in [profiles](pylinac/core/profile.py#L282), [gamma](pylinac/core/gamma.py#L427), and [Quart](pylinac/quart.py#L430). Choose a modern replacement for each interpolation mode; preserve sorting and edge behavior.
- `UnivariateSpline` and `InterpolatedUnivariateSpline`: used in [profiles](pylinac/core/profile.py#L256) and [profile metrics](pylinac/metrics/profile.py#L542). Consider `make_interp_spline` for exact fits or `make_splrep` for smoothing; the latter needs SciPy 1.15+, above the current 1.11 minimum.

SciPy has no planned removal for these APIs. They are a lower priority.

## Recommended Steps

1. Keep old wrappers and public attributes until an approved removal release.
2. Keep the existing stretch formula, data types, and warning behavior.
3. Leave binary closing and legacy SciPy interpolation unchanged.
4. Verify dependency arguments at runtime; do not rely only on release notes.
5. Compare approved QA images before accepting these changes for use.

References: [scikit-image 0.26 changes](https://scikit-image.org/docs/stable/release_notes/release_0.26.html), [pydicom writing](https://pydicom.github.io/pydicom/stable/reference/generated/pydicom.filewriter.dcmwrite.html), [pydicom handlers](https://pydicom.github.io/pydicom/stable/reference/handlers.pixel_data.html), [SciPy interpolation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.interp1d.html), [spline APIs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.UnivariateSpline.html).

## Implementation Checklist

Public APIs and numerical results stay unchanged. Existing pylinac warnings stay;
the updated nuclear calls no longer emit dependency deprecation warnings.

- [x] Remove unused ROI warning allocations; 18 ROI tests passed with unchanged values and warnings.
- [x] Correct the Quart parameter note without changing its accepted arguments.
- [x] Reuse the legacy stretch minimum; 9 stretch tests passed with the old ranges, data types, and warning.
- [x] Update nuclear size arguments; 4 tests and 11 boundary cases passed on both versions.
- [x] Remove duplicate profile interpolation evaluations; 10 local profile tests passed.
- [x] Measure the changed paths against the original code with exact output checks.
- [x] Run 41 focused tests on scikit-image 0.25.2 and 0.26.0.
- [x] Pass repository file checks; skip only the commit guard because no commit was requested.

### Skipped Changes

- [ ] Replace binary closing: one of 192 checked masks changed with a rotated footprint.
- [ ] Replace legacy stretch with modern stretch: ranges and `fill_dtype` behavior differ.
- [ ] Add ROI warnings or change visibility calculations: warning or measurement behavior would change.
- [ ] Remove aliases, change Winston-Lutz attributes, or replace phantom classes: public behavior could change.
- [ ] Replace SciPy interpolation or widen pydicom support: not verified as value-safe.

These items are excluded, not waiting for automatic implementation.

## Performance Checks

Local microbenchmarks used five repeats of 40 calls. Outputs matched the original
code exactly. These are path-level gains, not whole-library speed claims.

| Checked path | Old ms/call | New ms/call | Speedup |
| --- | --- | --- | --- |
| Legacy stretch, 1024 x 1280 float32 image | 3.326 | 2.874 | 1.16x |
| `x_at_x_idx()`, 8192 points | 0.184 | 0.101 | 1.82x |
| `x_at_y()`, 8192 points | 0.071 | 0.040 | 1.79x |

## Verification

Verified with Python 3.12.8, NumPy 2.5.4, SciPy 1.18.1, pydicom 2.4.5, and
scikit-image 0.25.2 / 0.26.0. All 41 focused tests passed on both scikit-image
versions. Two expected divide-by-zero warnings remain in the ROI edge tests.

Ruff, formatting, AST, and applicable file checks passed. Existing tuple-return
annotation diagnostics in nuclear code and profile tests were left unchanged.

Full cloud-backed suites were not run. Profile test collection needs cloud data;
the 19 local profile tests were run directly without those classes.
Human QA and acceptance remain open in [HUMAN_TASKS.md](HUMAN_TASKS.md).
