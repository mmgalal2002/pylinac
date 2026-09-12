.. _ge-ct-qa:

========================
GE 20 cm CT QA Phantom
========================

Overview
--------

The :class:`~pylinac.ge_ct_qa.GECTQA` analyzer provides a pylinac-native
framework for the GE CT Quality Assurance Phantom, also called the GE 20 cm
QA Phantom.  It follows the same load / analyze / results / visualization
pattern as the GE Helios and CatPhan analyzers.

.. warning::

    This is a research and development implementation.  The default profile
    is based on the supplied GE CT Technical Reference Manual
    ``5800010-1ENr2``, Chapter 12.  Local physicist validation is still
    required before clinical use, especially for visual low-contrast scoring,
    slice-thickness hole counting, and local action limits.

The supplied ``CT.TPSQA2017`` series was used to validate the complete default
path.  It contains 104 CT slices with 0.976562 mm pixels, 2.5 mm slice
thickness, and a ``LightSpeed16`` scanner model.  The automatic circular-body
estimate is approximately 214 mm in diameter.  In stack order, this scan
places the detected Section 1 bar-pattern slice at index 36, the uniform-water
slice at index 42, and the low-contrast target slice at index 25.  These are
scan observations, not fixed indices for other acquisitions.

The supplied DICOM identifies the scanner as ``LightSpeed16`` rather than
``Optima``.  The analyzer reports that applicability explicitly and applies
the GE phantom procedure reference values without inventing Optima-specific
calibration constants.
Typical Use
-----------

The normal production input is a complete DICOM series.  A single DICOM image
is accepted for measurements that can legitimately use one slice, and a ZIP
archive follows the same convention as other pylinac CT analyzers.

.. code-block:: python

    from pylinac import GECTQA

    qa = GECTQA(r"C:/CT/GE_Set_1")
    qa.analyze()

    print(qa.results())
    result = qa.results_data()
    result_dict = qa.results_data(as_dict=True)
    result_json = qa.results_data(as_json=True)

    qa.plot_analyzed_image()
    qa.plotly_analyzed_images()
    qa.publish_pdf("ge_ct_qa_report.pdf")

ZIP input is supported with:

.. code-block:: python

    qa = GECTQA.from_zip(r"C:/CT/ge_set_1.zip")

Configuration
-------------

The no-argument constructor uses ``GECTQAConfig.from_ge_manual()``.  It
includes the GE manual references for water, Plexiglass-to-water contrast,
noise, uniformity, the 1.6 mm bar standard-deviation check, the documented bar
sizes, and the 2 mm positioning reference.  It also includes the existing
Helios-compatible ROI dimensions.  Section 1 and Section 3 are detected from
image content; the manual's ``S0`` and ``S60`` labels are retained as
scan-location metadata rather than treated as universal DICOM z offsets.

For a local phantom revision or validated worksheet, pass an explicit
configuration.  ROI coordinates remain phantom-relative physical millimetres,
not hard-coded pixels.

.. code-block:: python

    from pylinac import GECTQA
    from pylinac.ge_ct_qa import GECTQAConfig, GECTQAMaterialROI, GECTQAROI

    config = GECTQAConfig(
        automatic_module_detection=False,
        ct_number_offset_mm=0,
        ct_number_rois={
            "water": GECTQAMaterialROI(
                x_mm=0,
                y_mm=0,
                radius_mm=10,
                nominal_hu=0,
                tolerance_hu=40,
            ),
        },
        noise_roi=GECTQAROI(x_mm=0, y_mm=0, radius_mm=12),
        noise_tolerance_hu=10,
    )

    qa = GECTQA(r"C:/CT/ge_set_1", config=config)
    qa.analyze(angle_override=0)

The coordinates and values in this custom example are API examples only.  They
are not a replacement for a validated local worksheet.

Inputs and validation
---------------------

Before analysis, the module checks that:

* the input contains CT image storage objects with pixel data;
* all images belong to one Series Instance UID and Study Instance UID;
* matrix dimensions and pixel spacing are consistent;
* Image Position (Patient) is available for z sorting;
* duplicate slices are rejected;
* inconsistent slice spacing is reported as a warning;
* manufacturer and model metadata are retained and missing values are warned.

DICOM rescale slope and intercept are applied by pylinac's
:class:`~pylinac.core.image.DicomImageStack`, so ROI statistics are in HU.
The retained metadata includes manufacturer, model, series and study IDs,
pixel spacing, slice thickness, reconstruction diameter, kVp, exposure,
kernel, protocol, and study/acquisition descriptions when present.

Localization and coordinates
----------------------------

Localization thresholds the HU image, selects a connected component whose
physical area is compatible with the configurable expected diameter range,
and rejects elongated support/table components using eccentricity, solidity,
and bounding-box aspect ratio.  The result includes center, radius, diameter,
image-relative millimetres, and confidence.

The circular boundary alone cannot determine a clinically meaningful phantom
rotation.  The default rotation is therefore zero with an explicit warning;
provide ``angle_override`` when the GE worksheet or a validated orientation
marker defines the angle.  If automatic localization is unsuitable, pass
``center_override=(x_px, y_px)``.

The automatic module anchors use image-content signatures: the 1.6 mm bar
standard deviation for Section 1, a low-deviation water grid for
noise/uniformity, and compact circular targets plus the 15 x 15 grid for low
contrast.  Pass ``origin_slice`` when the GE procedure identifies a specific
reference slice.  The detected physical z positions are retained in
``module_locations``.

Available measurements
----------------------

The default profile returns measured values immediately.  A configured test
still returns ``passed=None`` when its acceptance rule is not defined.  The
current measurement paths are:

* **CT number:** mean, median, standard deviation, extrema, percentiles, HU
  difference, and optional tolerance for each configured material ROI.
* **Contrast scale:** Plexiglass minus water using the GE reference
  ``120 +/- 12 HU`` and the underlying ROI statistics.
* **Noise:** standard deviation from the 25 mm central box ROI, compared with
  the GE reference ``3.2 +/- 0.3 HU``.  The supplied scan's measured noise is
  reported; it is not replaced with the reference value.
* **Uniformity:** 15 mm center, 12 o'clock, and 3 o'clock ROIs at the detected
  uniform-water slice, with the GE ``0 +/- 3 HU`` center-to-periphery
  reference.
* **High contrast:** Helios-compatible bar ROIs, the GE ``1.6 mm`` standard
  deviation check (``37 +/- 4 HU``), and relative MTF values at 10% through
  90%.  The MTF is explicitly labeled relative/Helios-compatible.
* **Low contrast:** a 15 x 15 grid using 5 mm cells, with mean, standard
  deviation, extrema, and per-target CNR when target ROIs are configured.  The
  GE visual observer score is not fabricated from grid statistics.
* **Slice thickness:** a configured axial profile measured by FWHM, with an
  explicit calibration factor.  At least three slices are required, and the
  DICOM ``SliceThickness`` tag is never reported as a phantom measurement.
* **Positioning:** image-relative x/y phantom offset and localized rotation.
  This is not external laser alignment.

The result also contains ``helios_compatibility``.  It retains the output
shape useful for comparing a GE scan with the existing Helios analyzer:
contrast-scale ROI values, four Helios bar ROI statistics, relative MTF,
three-slice 15 x 15 low-contrast grid statistics, and noise/uniformity ROI
values.  It is explicitly marked as a GE phantom measured with
Helios-compatible algorithms, not as a GE Helios phantom result.

External laser and light-field alignment
-----------------------------------------

A normal CT DICOM series does not contain enough information to measure
external room lasers or a radiation light field.  The ``alignment`` result is
therefore explicitly unavailable and states that a dedicated acquisition is
required.  It is kept separate from the image-based ``positioning`` result.

Results and exports
-------------------

The typed result is :class:`~pylinac.ge_ct_qa.GECTQAResult`.  It contains
metadata, public reference values, localization, detected module locations,
all module result objects, the Helios-compatible comparison block,
availability/reason text, pass/fail values, warning count, and an overall
state.  The overall state is:

* ``False`` when an available configured test fails;
* ``True`` when every available configured test passes;
* ``None`` when no acceptance limits were supplied or a required test is
  unavailable.

Use ``results_data(as_dict=True)`` or ``results_data(as_json=True)`` for
external QA applications and trending.  ``plot_analyzed_image`` and
``plotly_analyzed_images`` show Section 1, noise/uniformity, low contrast,
the series side view, and relative MTF.  ``publish_pdf`` includes the expanded
human-readable summary and module images.

Validation status and required clinical data
---------------------------------------------

Implemented and tested:

* single DICOM, directory, and ZIP loading;
* CT metadata validation, sorting, duplicate/mixed-series rejection, and
  rescaled HU pixels;
* circular localization, center/diameter reporting, module-slice detection,
  and center overrides;
* physical-mm ROI conversion;
* typed results, dict/JSON serialization, plots, and PDF generation;
* GE manual-default CT-number, contrast-scale, noise, uniformity,
  high-contrast/relative-MTF, low-contrast-grid, positioning, and explicit
  acquired-versus-measured slice-thickness reporting;
* Helios-compatible comparison output and expanded Matplotlib/Plotly/PDF
  module figures.

Needs clinical validation before use:

* low-contrast target sizes and observer/CNR rule;
* slice-thickness ramp geometry and calibration factor;
* local action limits and required-test policy;
* passing and failing reference scans.

The supplied CT set and GE manual establish the defaults documented above but
do not establish local clinical acceptance.  A phantom revision check,
validated local measurements, passing and failing reference scans, and a
dedicated laser/light-field acquisition are required for the remaining claims.

API Documentation
-----------------

.. autoclass:: pylinac.ge_ct_qa.GECTQA
    :inherited-members:
    :members:

.. autopydantic_model:: pylinac.ge_ct_qa.GECTQAResult

.. autopydantic_model:: pylinac.ge_ct_qa.GECTQAReference

.. autopydantic_model:: pylinac.ge_ct_qa.GECTQAModuleLocations

.. autopydantic_model:: pylinac.ge_ct_qa.GECTQAConfig

.. autopydantic_model:: pylinac.ge_ct_qa.GECTQAROI

.. autopydantic_model:: pylinac.ge_ct_qa.GECTQAMaterialROI

.. autopydantic_model:: pylinac.ge_ct_qa.GECTQAHighContrastROI

.. autopydantic_model:: pylinac.ge_ct_qa.GECTQALowContrastConfig

.. autopydantic_model:: pylinac.ge_ct_qa.GECTQASliceThicknessConfig
