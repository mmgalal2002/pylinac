# Common Chart Inventory

## Scope

- [x] Scope is limited to reusable chart types already plotted in the codebase; this is not an inventory of phantom analysis or image rendering.
- [x] Excluded: image pixels, heatmaps, phantom/ROI overlays, radiographic views, and analyzer-specific composite layouts.
- [x] Goal: make common chart data reproducible in a front end without coupling the chart payload to Matplotlib figure objects.

## Chart Types

- [x] Line charts: ordered X/Y data series, including profiles, MTF curves, and noise-power spectra. ([pylinac/core/profile.py](pylinac/core/profile.py#L440)) ([pylinac/core/mtf.py](pylinac/core/mtf.py#L216)) ([pylinac/core/nps.py](pylinac/core/nps.py#L124))
- [x] Scatter charts: independent X/Y points, optionally connected by lines or markers. ([pylinac/core/profile.py](pylinac/core/profile.py#L440)) ([pylinac/core/mtf.py](pylinac/core/mtf.py#L135))
- [x] Bar charts: category/value pairs, including horizontal or vertical orientation. ([pylinac/log_analyzer.py](pylinac/log_analyzer.py#L1334))
- [x] Histograms: a distribution rendered from raw samples or precomputed bin edges and counts. ([pylinac/log_analyzer.py](pylinac/log_analyzer.py#L1323))
- [x] Box-and-whisker charts: grouped distributions with whiskers and outliers. ([pylinac/picketfence.py](pylinac/picketfence.py#L1369))
- [x] Multi-series charts: multiple named series on shared axes, such as measured data and a comparison or fitted curve. ([pylinac/core/profile.py](pylinac/core/profile.py#L516))
- [x] Secondary axes: a second labeled scale for a related unit or measure. ([pylinac/core/mtf.py](pylinac/core/mtf.py#L135)) ([pylinac/core/profile.py](pylinac/core/profile.py#L877))
- [x] Common chart annotations: title, axis labels and units, legend, grid, thresholds/reference lines, and highlighted data points.

## JSON Rebuildability

- [x] `results_data(as_json=True)` serializes result models, but there is no shared chart-data contract in the result base. ([pylinac/core/utilities.py](pylinac/core/utilities.py#L48)) ([pylinac/core/utilities.py](pylinac/core/utilities.py#L72))
- [x] Some specialized result models contain chart-like data, but the schema is not a common contract for all chart types.
- [ ] Results containing only summary measurements are insufficient to reconstruct the original chart; the front end needs the plotted series or distribution data.
- [ ] Each chart payload should identify its `kind`, title, axis labels and units, series, legend, axis limits/scales, and annotations.
- [ ] Line and scatter series should include numeric X/Y values, series names, and optional marker/line styling.
- [ ] Bar series should include category labels, values, orientation, and grouping/stacking mode when applicable.
- [ ] Histograms should include bin edges and counts, or raw samples plus the exact binning rule.
- [ ] Box plots should include raw observations or quartiles, whisker rule, and outlier values so the front end can reproduce the same summary.
- [ ] Multi-axis charts should identify which axis each series uses and provide that axis's label, unit, scale, and limits.
- [ ] Keep image pixels, phantom geometry, and image-specific overlays out of this chart payload.

## Recommendation

- [ ] Keep existing measurement JSON stable; add an opt-in, versioned `charts` payload containing data and presentation metadata for common charts only.
- [ ] Use a backend-neutral schema with one object per chart and typed series, so a front end can map `line`, `scatter`, `bar`, `histogram`, and `box` to its chart library.
- [ ] Use Plotly.js or Apache ECharts for interactive charts; render each chart in its own responsive component instead of packing unrelated plots into a fixed Matplotlib composite.
- [ ] Validate chart equivalence by comparing series values, categories, units, bin edges, and axis behavior; pixel-identical screenshots are not required for data-driven charts.
