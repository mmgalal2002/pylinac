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

    This is a research and development implementation.  The repository does
    not contain the GE phantom manual or a validated QA worksheet defining the
    insert map, nominal material values, scoring methods, or action limits.
    The analyzer therefore requires those values through
    :class:`~pylinac.ge_ct_qa.GECTQAConfig` and does not substitute CatPhan or
    Helios geometry.

The supplied ``CT.TPSQA2017`` series was used to validate the DICOM loading
and localization path.  It contains 104 CT slices with 0.976562 mm pixels and
2.5 mm slice thickness.  The automatic circular-body estimate is approximately
214 mm in diameter.  Those observations are validation facts for that scan,
not acceptance criteria for the phantom.

Typical Use
-----------

The normal production input is a complete DICOM series.  A single DICOM image
is accepted for measurements that can legitimately use one slice, and a ZIP
archive follows the same convention as other pylinac CT analyzers.

.. code-block:: python

    from pylinac import GECTQA

    qa = GECTQA(r"C:/CT/GE_Set_1")
    qa.analyze(angle_override=0)

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

The default configuration contains no GE insert locations or clinical
tolerances.  Define the geometry from the manufacturer documentation or a
locally validated worksheet.  ROI coordinates are phantom-relative physical
millimetres, not hard-coded pixels.

.. code-block:: python

    from pylinac import GECTQA
    from pylinac.ge_ct_qa import GECTQAConfig, GECTQAMaterialROI, GECTQAROI

    config = GECTQAConfig(
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

The coordinates and values in this example are API examples only.  They are
not a GE phantom definition and must not be used for clinical testing without
validation.

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

The automatic module anchor is the midpoint of the slices in which the
phantom body was detected.  It is only a coordinate reference.  Pass
``origin_slice`` when the GE procedure identifies a specific reference slice.

Available measurements
----------------------

Configured tests return measured values even when no acceptance limit is
configured.  In that case ``passed`` is ``None`` rather than an invented
pass.  The current measurement paths are:

* **CT number:** mean, median, standard deviation, extrema, percentiles, HU
  difference, and optional tolerance for each configured material ROI.
* **Contrast scale:** a configured difference between two CT-number ROIs,
  retaining both underlying values and the optional nominal difference.
* **Noise:** standard deviation from a configured uniform ROI.
* **Uniformity:** per-ROI statistics, maximum deviation from the configured
  center ROI, and maximum pairwise difference.  No undocumented HU uniformity
  index is synthesized.
* **High contrast:** configured line-pair sample regions and their standard
  deviation as a visibility score.  A resolved frequency is reported only
  when a visibility threshold and validated spatial frequency are configured.
  MTF is not claimed automatically and remains ``None``.
* **Low contrast:** configured target/background mean, standard deviation,
  contrast, CNR, visibility, and visible-target count.  This is a quantitative
  CNR estimate and is not represented as equivalent to a visual-observer
  score.
* **Slice thickness:** a configured axial profile measured by FWHM, with an
  explicit calibration factor.  At least three slices are required, and the
  DICOM ``SliceThickness`` tag is never reported as a phantom measurement.
* **Positioning:** image-relative x/y phantom offset and localized rotation.
  This is not external laser alignment.

External laser and light-field alignment
-----------------------------------------

A normal CT DICOM series does not contain enough information to measure
external room lasers or a radiation light field.  The ``alignment`` result is
therefore explicitly unavailable and states that a dedicated acquisition is
required.  It is kept separate from the image-based ``positioning`` result.

Results and exports
-------------------

The typed result is :class:`~pylinac.ge_ct_qa.GECTQAResult`.  It contains
metadata, localization, all module result objects, availability/reason text,
pass/fail values, warning count, and an overall state.  The overall state is:

* ``False`` when an available configured test fails;
* ``True`` when every available configured test passes;
* ``None`` when no acceptance limits were supplied or a required test is
  unavailable.

Use ``results_data(as_dict=True)`` or ``results_data(as_json=True)`` for
external QA applications and trending.  ``plot_analyzed_image`` and
``plotly_analyzed_images`` show the localized body, center, configured ROIs,
and series side view.  ``publish_pdf`` includes the human-readable summary
and analysis images.

Validation status and required clinical data
---------------------------------------------

Implemented and tested:

* single DICOM, directory, and ZIP loading;
* CT metadata validation, sorting, duplicate/mixed-series rejection, and
  rescaled HU pixels;
* circular localization, center/diameter reporting, and center overrides;
* physical-mm ROI conversion;
* typed results, dict/JSON serialization, plots, and PDF generation;
* configured CT-number, noise, uniformity, high-contrast ROI, low-contrast
  CNR, positioning, and profile FWHM code paths.

Needs clinical validation before use:

* the exact GE insert/module layout and z offsets;
* material names and nominal HU values;
* the official contrast-scale equation;
* high-contrast pattern frequencies and scoring method;
* low-contrast target sizes and observer/CNR rule;
* slice-thickness ramp geometry and calibration factor;
* action limits and required-test policy;
* passing and failing reference scans.

The supplied CT set is not sufficient by itself to establish those clinical
definitions.  The GE phantom manual or QA worksheet, phantom revision,
validated local measurements, and a dedicated laser/light-field acquisition
are required for the remaining claims.

API Documentation
-----------------

.. autoclass:: pylinac.ge_ct_qa.GECTQA
    :inherited-members:
    :members:

.. autopydantic_model:: pylinac.ge_ct_qa.GECTQAResult

.. autopydantic_model:: pylinac.ge_ct_qa.GECTQAConfig

.. autopydantic_model:: pylinac.ge_ct_qa.GECTQAROI

.. autopydantic_model:: pylinac.ge_ct_qa.GECTQAMaterialROI

.. autopydantic_model:: pylinac.ge_ct_qa.GECTQAHighContrastROI

.. autopydantic_model:: pylinac.ge_ct_qa.GECTQALowContrastConfig

.. autopydantic_model:: pylinac.ge_ct_qa.GECTQASliceThicknessConfig
