# Recent Test Changes And Commit Audit

Audited 2026-10-23 at `853c7647` on `master`. The six entries are the six newest
commits from `git log -6`; this is not a first-parent-only list. The leading
commit is a merge, so its aggregate test delta overlaps the upstream feature
commits listed below.

## Commits

| Commit | Date | Subject | Test impact |
| --- | --- | --- | --- |
| `853c7647` | 2026-10-23 | Merge remote-tracking branch `upstream/master` | Integrates upstream Plotly changes. Its aggregate test delta includes Planar Imaging coverage and the MTF, ACR, CBCT and Winston-Lutz changes below. |
| `4bd35fee` | 2026-10-22 | Merge version 3.50.0 PR #751 | No test files changed relative to its first parent. |
| `065f8475` | 2026-10-22 | Bump version to 3.50.0 | Version-only change; no test files changed. |
| `8096895a` | 2026-10-14 | Merge Winston-Lutz Plotly improvements PR #749 | Updates two Winston-Lutz trace-count expectations from 7 to 8 for the added plot overlays. |
| `75c926a9` | 2026-10-14 | Merge CT Plotly improvements PR #750 | Adds MTF pair-distance-axis tests and updates ACR/CBCT Plotly figure and trace expectations. |
| `6496e777` | 2026-10-13 | Update `HUMAN_TASKS.md` | Task-documentation change; no test files changed. |

## Test Changes Reviewed

- [tests_basic/core/test_mtf.py](tests_basic/core/test_mtf.py) adds coverage for the
  secondary pair-distance axis, its reciprocal-frequency labels, exclusion of
  nonpositive frequencies, and multiple MTF curves sharing the axis.
- [tests_basic/test_acr.py](tests_basic/test_acr.py) updates relative-MTF trace
  counts from 1 to 2 and from 2 to 4. The implementation adds one hidden
  secondary-axis trace per MTF curve.
- [tests_basic/test_cbct.py](tests_basic/test_cbct.py) expects one additional
  figure, `Uniformity Profiles`, with two profile traces and Pixel/HU axes.
- [tests_basic/test_planar_imaging.py](tests_basic/test_planar_imaging.py) adds
  checks for low- and high-contrast thresholds, contrast/CNR values, the Las Vegas
  visibility axis and threshold, and suppression of display, legends and colorbars.
- [tests_basic/test_winstonlutz.py](tests_basic/test_winstonlutz.py) and
  [tests_basic/test_winstonlutz_mtmf.py](tests_basic/test_winstonlutz_mtmf.py)
  each update a representative Plotly trace count from 7 to 8.

## Adaptation Review

Static comparison with the production diffs found the changed expectations aligned
with the implementation: MTF adds a hidden trace for its secondary axis; CatPhan
adds uniformity-profile figures; planar-imaging plots add configured thresholds
and a visibility axis; and Winston-Lutz plots add overlay traces. No behavioral
mismatch was identified in the reviewed test changes. The malformed spacing in
the Planar Imaging `unittest` import was normalized; this is formatting-only.

No pytest command was run during this audit. Human runtime review remains pending
in [HUMAN_TASKS.md](HUMAN_TASKS.md). The focused command is:

```powershell
uv run pytest tests_basic/core/test_mtf.py tests_basic/test_acr.py tests_basic/test_cbct.py tests_basic/test_planar_imaging.py tests_basic/test_winstonlutz.py tests_basic/test_winstonlutz_mtmf.py
```

Some tests may require the repository's configured local test-data cache or GCP
credentials.