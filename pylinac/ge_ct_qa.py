"""Analysis of the GE 20 cm CT quality-assurance phantom.

The GE 20 cm phantom geometry is intentionally configuration-driven.  The
repository does not contain the manufacturer's insert drawing, nominal HU
values, or action limits, so this module does not silently substitute values
from a CatPhan or GE Helios phantom.
"""

from __future__ import annotations

import io
import textwrap
import warnings
import webbrowser
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Literal

import matplotlib.pyplot as plt
import numpy as np
import pydicom
from matplotlib.patches import Circle
from plotly import graph_objects as go
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy import ndimage
from skimage import measure, morphology

from .core import pdf
from .core.geometry import Point
from .core.image import DicomImageStack
from .core.io import get_url
from .core.mtf import MTF
from .core.roi import DiskROI, RectangleROI
from .core.utilities import QuaacDatum, QuaacMixin, ResultBase, ResultsDataMixin
from .core.warnings import capture_warnings

GE_QA_REFERENCE_SOURCE = (
    "GE CT Technical Reference Manual 5800010-1ENr2, Chapter 12, Quality Assurance"
)
GE_QA_SECTION_1_LOCATION_MM = 0.0
GE_QA_SECTION_3_LOCATION_MM = 60.0
GE_QA_HIGH_CONTRAST_BAR_SIZES_MM = (1.6, 1.3, 1.0, 0.8, 0.6, 0.5)

GE_HELIOS_CONTRAST_SCALE_ROI_SETTINGS = {
    "Plexiglass": {"width_mm": 10.0, "height_mm": 10.0, "distance_mm": 35.0, "angle_deg": -135.0},
    "Water": {"width_mm": 10.0, "height_mm": 10.0, "distance_mm": 75.0, "angle_deg": -90.0},
}
GE_HELIOS_HIGH_CONTRAST_ROI_SETTINGS = {
    "1.6mm": {"width_mm": 8.0, "distance_mm": 42.0, "angle_deg": -53.0, "bar_size_mm": 1.6},
    "1.3mm": {"width_mm": 7.0, "distance_mm": 21.0, "angle_deg": -62.0, "bar_size_mm": 1.3},
    "1.0mm": {"width_mm": 6.0, "distance_mm": 5.0, "angle_deg": -120.0, "bar_size_mm": 1.0},
    "0.8mm": {"width_mm": 5.0, "distance_mm": 16.0, "angle_deg": 146.0, "bar_size_mm": 0.8},
}
GE_HELIOS_UNIFORMITY_ROI_SETTINGS = {
    "Center": {"width_mm": 15.0, "height_mm": 15.0, "distance_mm": 0.0, "angle_deg": 0.0},
    "12 o'clock": {"width_mm": 15.0, "height_mm": 15.0, "distance_mm": 75.0, "angle_deg": -90.0},
    "3 o'clock": {"width_mm": 15.0, "height_mm": 15.0, "distance_mm": 75.0, "angle_deg": 0.0},
}


def _rectangular_roi(
    settings: dict[str, float],
    *,
    nominal_hu: float | None = None,
    tolerance_hu: float | None = None,
) -> GECTQAMaterialROI:
    """Build a physical-mm rectangular material ROI from a Helios setting."""
    return GECTQAMaterialROI(
        x_mm=np.cos(np.deg2rad(settings["angle_deg"])) * settings["distance_mm"],
        y_mm=np.sin(np.deg2rad(settings["angle_deg"])) * settings["distance_mm"],
        width_mm=settings["width_mm"],
        height_mm=settings["height_mm"],
        nominal_hu=nominal_hu,
        tolerance_hu=tolerance_hu,
    )


def _roi_from_setting(settings: dict[str, float]) -> GECTQAROI:
    """Build a physical-mm rectangular ROI from a Helios setting."""
    return GECTQAROI(
        x_mm=np.cos(np.deg2rad(settings["angle_deg"])) * settings["distance_mm"],
        y_mm=np.sin(np.deg2rad(settings["angle_deg"])) * settings["distance_mm"],
        width_mm=settings["width_mm"],
        height_mm=settings.get("height_mm", settings["width_mm"]),
    )


class GECTQAROI(BaseModel):
    """A circular or rectangular ROI in phantom-relative millimetres.

    Coordinates use the image convention: positive x points right and
    positive y points down.  The phantom rotation is applied around the
    localized center before conversion to pixels.
    """

    model_config = ConfigDict(extra="forbid")

    x_mm: float
    y_mm: float
    radius_mm: float | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    rotation_deg: float = 0

    @model_validator(mode="after")
    def validate_geometry(self) -> GECTQAROI:
        has_radius = self.radius_mm is not None
        has_rectangle = self.width_mm is not None or self.height_mm is not None
        if has_radius == has_rectangle:
            raise ValueError(
                "An ROI must define either radius_mm or both width_mm and height_mm"
            )
        if self.radius_mm is not None and self.radius_mm <= 0:
            raise ValueError("radius_mm must be positive")
        if self.width_mm is not None and self.width_mm <= 0:
            raise ValueError("width_mm must be positive")
        if self.height_mm is not None and self.height_mm <= 0:
            raise ValueError("height_mm must be positive")
        return self


class GECTQAMaterialROI(GECTQAROI):
    """An ROI used for CT-number accuracy measurements."""

    nominal_hu: float | None = None
    tolerance_hu: float | None = None


class GECTQAHighContrastROI(GECTQAROI):
    """A configured high-contrast line-pair sample region."""

    spatial_frequency_lp_mm: float
    visibility_threshold_hu: float | None = None
    reference_std_hu: float | None = None
    tolerance_hu: float | None = None


class GECTQALowContrastTarget(GECTQAROI):
    """A configured low-contrast target region."""

    target_size_mm: float | None = None


class GECTQAContrastScaleConfig(BaseModel):
    """Configuration for a contrast-scale value derived from CT-number ROIs."""

    first_roi: str
    second_roi: str
    nominal_difference_hu: float | None = None
    tolerance_hu: float | None = None
    units: str = "HU difference"


class GECTQALowContrastConfig(BaseModel):
    """Configuration for target/background CNR measurements."""

    background: GECTQAROI
    targets: dict[str, GECTQALowContrastTarget]
    cnr_threshold: float | None = None
    minimum_visible_targets: int | None = None


class GECTQASliceThicknessConfig(BaseModel):
    """Configuration for a calibrated axial slice-thickness profile."""

    roi: GECTQAROI
    offset_mm: float = 0
    sample_half_range_mm: float | None = None
    polarity: Literal["bright", "dark"] = "bright"
    nominal_mm: float | None = None
    tolerance_mm: float | None = None
    correction_factor: float = 1.0
    method: str = "profile_fwhm"

    @model_validator(mode="after")
    def validate_correction(self) -> GECTQASliceThicknessConfig:
        if self.correction_factor <= 0:
            raise ValueError("correction_factor must be positive")
        if self.sample_half_range_mm is not None and self.sample_half_range_mm <= 0:
            raise ValueError("sample_half_range_mm must be positive")
        return self


class GECTQAConfig(BaseModel):
    """Definition of the GE phantom geometry and local acceptance criteria.

    The defaults intentionally contain no insert geometry.  Populate the
    fields from the GE phantom manual or a locally validated QA worksheet.
    ``expected_diameter_range_mm`` is only a localization search range, not a
    manufacturing or acceptance specification.
    """

    model_config = ConfigDict(extra="forbid")

    phantom_model: str = "GE 20 cm QA Phantom"
    reference_source: str | None = None
    expected_diameter_range_mm: tuple[float, float] = (200.0, 215.0)
    section1_location_mm: float = GE_QA_SECTION_1_LOCATION_MM
    section3_location_mm: float = GE_QA_SECTION_3_LOCATION_MM
    automatic_module_detection: bool = False
    use_helios_compatibility: bool = True
    ct_number_offset_mm: float = 0
    ct_number_rois: dict[str, GECTQAMaterialROI] = Field(default_factory=dict)
    contrast_scale: GECTQAContrastScaleConfig | None = None
    noise_offset_mm: float = 0
    noise_roi: GECTQAROI | None = None
    noise_reference_hu: float | None = None
    noise_tolerance_hu: float | None = None
    uniformity_offset_mm: float = 0
    uniformity_rois: dict[str, GECTQAROI] = Field(default_factory=dict)
    uniformity_center_name: str = "center"
    uniformity_reference_hu: float | None = None
    uniformity_tolerance_hu: float | None = None
    high_contrast_offset_mm: float = 0
    high_contrast_rois: dict[str, GECTQAHighContrastROI] = Field(default_factory=dict)
    minimum_resolution_lp_mm: float | None = None
    low_contrast_offset_mm: float = 0
    low_contrast: GECTQALowContrastConfig | None = None
    slice_thickness: GECTQASliceThicknessConfig | None = None
    positioning_tolerance_mm: float | None = None

    @model_validator(mode="after")
    def validate_diameter_range(self) -> GECTQAConfig:
        low, high = self.expected_diameter_range_mm
        if low <= 0 or high <= low:
            raise ValueError("expected_diameter_range_mm must be an increasing range")
        return self

    @classmethod
    def from_ge_manual(cls) -> GECTQAConfig:
        """Return defaults from the GE QA manual and Helios-compatible geometry.

        The ROI dimensions and reference values are taken from the supplied
        GE technical reference manual.  Section slices are still detected
        from image content because ``S0`` and ``S60`` are scan-location labels,
        not reliable DICOM z offsets across acquisitions.
        """
        contrast_rois = GE_HELIOS_CONTRAST_SCALE_ROI_SETTINGS
        high_contrast_rois = {
            name: GECTQAHighContrastROI(
                **_roi_from_setting(setting).model_dump(),
                spatial_frequency_lp_mm=1 / (2 * setting["bar_size_mm"]),
                reference_std_hu=37.0 if name == "1.6mm" else None,
                tolerance_hu=4.0 if name == "1.6mm" else None,
            )
            for name, setting in GE_HELIOS_HIGH_CONTRAST_ROI_SETTINGS.items()
        }
        return cls(
            reference_source=GE_QA_REFERENCE_SOURCE,
            automatic_module_detection=True,
            ct_number_rois={
                "Plexiglass": _rectangular_roi(contrast_rois["Plexiglass"]),
                "Water": _rectangular_roi(
                    contrast_rois["Water"], nominal_hu=0.0, tolerance_hu=3.0
                ),
            },
            contrast_scale=GECTQAContrastScaleConfig(
                first_roi="Plexiglass",
                second_roi="Water",
                nominal_difference_hu=120.0,
                tolerance_hu=12.0,
                units="HU difference",
            ),
            noise_roi=GECTQAROI(x_mm=0, y_mm=0, width_mm=25, height_mm=25),
            noise_reference_hu=3.2,
            noise_tolerance_hu=0.3,
            uniformity_rois={
                name: _roi_from_setting(setting)
                for name, setting in GE_HELIOS_UNIFORMITY_ROI_SETTINGS.items()
            },
            uniformity_center_name="Center",
            uniformity_reference_hu=0.0,
            uniformity_tolerance_hu=3.0,
            high_contrast_rois=high_contrast_rois,
            low_contrast=GECTQALowContrastConfig(
                background=GECTQAROI(x_mm=0, y_mm=0, width_mm=5, height_mm=5),
                targets={},
            ),
            positioning_tolerance_mm=2.0,
        )


class GECTQAROIResult(BaseModel):
    """Measured statistics and physical placement of one ROI."""

    name: str
    offset_mm: float
    slice_index: int
    physical_z_mm: float
    center_x_px: float
    center_y_px: float
    center_x_mm: float
    center_y_mm: float
    radius_mm: float | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    mean_hu: float
    median_hu: float
    std_hu: float
    min_hu: float
    max_hu: float
    percentiles: dict[str, float]
    pixel_count: int


class GECTQAMaterialResult(GECTQAROIResult):
    """Measured CT-number accuracy for one material ROI."""

    nominal_hu: float | None
    difference_hu: float | None
    percent_error: float | None
    tolerance_hu: float | None
    passed: bool | None


class GECTQATestResult(BaseModel):
    """Common availability and pass/fail state for a GE QA test."""

    available: bool
    passed: bool | None
    reason: str | None = None


class GECTQACTNumberResult(GECTQATestResult):
    """Results for configured CT-number/material ROIs."""

    rois: dict[str, GECTQAMaterialResult] = Field(default_factory=dict)


class GECTQAContrastScaleResult(GECTQATestResult):
    """Results for the configured contrast-scale calculation."""

    first_roi: str | None = None
    second_roi: str | None = None
    reference_values_hu: dict[str, float] = Field(default_factory=dict)
    contrast_scale: float | None = None
    contrast_scale_units: str | None = None
    nominal_difference_hu: float | None = None
    deviation_hu: float | None = None
    tolerance_hu: float | None = None


class GECTQANoiseResult(GECTQATestResult):
    """Results for the configured noise ROI."""

    roi: GECTQAROIResult | None = None
    noise_hu: float | None = None
    reference_hu: float | None = None
    difference_hu: float | None = None
    tolerance_hu: float | None = None
    method: str = "ROI standard deviation"


class GECTQAUniformityResult(GECTQATestResult):
    """Results for configured uniformity ROIs."""

    rois: dict[str, GECTQAROIResult] = Field(default_factory=dict)
    center_roi_name: str | None = None
    max_deviation_from_center_hu: float | None = None
    max_pairwise_difference_hu: float | None = None
    uniformity_index: float | None = None
    integral_uniformity: float | None = None
    reference_difference_hu: float | None = None
    tolerance_hu: float | None = None
    method: str = "center-to-periphery mean difference"


class GECTQAHighContrastROIResult(GECTQAROIResult):
    """Measured statistics for one configured high-contrast region."""

    spatial_frequency_lp_mm: float
    visibility_score_hu: float
    visibility_threshold_hu: float | None
    resolved: bool | None
    reference_std_hu: float | None = None
    difference_hu: float | None = None
    tolerance_hu: float | None = None
    passed: bool | None = None


class GECTQAHighContrastResult(GECTQATestResult):
    """Results for configured high-contrast line-pair samples."""

    rois: dict[str, GECTQAHighContrastROIResult] = Field(default_factory=dict)
    resolved_group: str | None = None
    resolution_lp_mm: float | None = None
    resolution_lp_cm: float | None = None
    mtf: dict[str, float] | None = None
    method: str = "Helios-compatible ROI standard deviation and relative MTF"


class GECTQALowContrastROIResult(GECTQAROIResult):
    """Measured statistics for one configured low-contrast target."""

    target_size_mm: float | None
    target_mean_hu: float
    target_std_hu: float
    background_mean_hu: float
    background_std_hu: float
    contrast_hu: float
    cnr: float | None
    visibility_score: float | None
    passed: bool | None


class GECTQALowContrastResult(GECTQATestResult):
    """Results for configured low-contrast targets."""

    background: GECTQAROIResult | None = None
    rois: dict[str, GECTQALowContrastROIResult] = Field(default_factory=dict)
    cnr_threshold: float | None = None
    num_rois_detected: int = 0
    num_rois_visible: int = 0
    minimum_visible_contrast_hu: float | None = None
    best_cnr: float | None = None
    worst_cnr: float | None = None
    method: str = "GE 15 x 15 cell grid statistics"
    grid_cell_size_mm: float | None = None
    grid_num_cells: int | None = None
    grid_mean_hu: float | None = None
    grid_std_hu: float | None = None
    grid_min_hu: float | None = None
    grid_max_hu: float | None = None


class GECTQASliceThicknessResult(GECTQATestResult):
    """Results for a configured and calibrated slice-thickness profile."""

    nominal_slice_thickness_mm: float | None = None
    measured_slice_thickness_mm: float | None = None
    difference_mm: float | None = None
    percent_difference: float | None = None
    tolerance_mm: float | None = None
    method: str | None = None
    slice_index: int | None = None
    physical_z_mm: float | None = None
    profile_z_mm: list[float] = Field(default_factory=list)
    profile_values_hu: list[float] = Field(default_factory=list)
    acquired_slice_thickness_mm: float | None = None


class GECTQAPositioningResult(GECTQATestResult):
    """Image-based phantom-to-image-center positioning results."""

    offset_x_mm: float | None = None
    offset_y_mm: float | None = None
    rotation_deg: float | None = None
    tolerance_mm: float | None = None


class GECTQAAlignmentResult(GECTQATestResult):
    """Explicit result for external laser/light-field alignment."""

    mode: str = "external_acquisition_required"


class GECTQALocalizationResult(BaseModel):
    """Localized phantom geometry in pixels and image-relative millimetres."""

    phantom_center_x_px: float
    phantom_center_y_px: float
    phantom_center_x_mm: float
    phantom_center_y_mm: float
    phantom_radius_mm: float
    phantom_diameter_mm: float
    phantom_rotation_deg: float
    localization_confidence: float


class GECTQAModuleLocations(BaseModel):
    """Detected GE test-module slices and their image-content scores."""

    section1_scan_location_mm: float
    section3_scan_location_mm: float
    section1_slice_index: int
    section1_physical_z_mm: float
    section1_score: float
    uniformity_slice_index: int
    uniformity_physical_z_mm: float
    uniformity_score: float
    low_contrast_slice_index: int
    low_contrast_physical_z_mm: float
    low_contrast_score: float
    detection_method: str


class GECTQAReference(BaseModel):
    """Public reference values used by the automatic GE default profile."""

    source: str
    section1_scan_location_mm: float
    section3_scan_location_mm: float
    water_nominal_hu: float
    water_tolerance_hu: float
    plexiglass_water_difference_hu: float
    plexiglass_water_tolerance_hu: float
    noise_nominal_hu: float
    noise_tolerance_hu: float
    uniformity_difference_nominal_hu: float
    uniformity_difference_tolerance_hu: float
    high_contrast_1_6mm_std_hu: float
    high_contrast_1_6mm_tolerance_hu: float
    high_contrast_bar_sizes_mm: tuple[float, ...]
    positioning_tolerance_mm: float
    scanner_reference_status: str
    clinical_status: str = "public reference; local clinical validation required"


class GECTQAHeliosContrastScaleResult(BaseModel):
    """Helios-compatible contrast-scale values measured on GE Section 1."""

    slice_index: int
    physical_z_mm: float
    roi_settings: dict[str, GECTQAROIResult]
    mean_hu_water: float
    mean_hu_plastic: float
    hu_difference: float
    std_dev_water: float


class GECTQAHeliosHighContrastResult(BaseModel):
    """Helios-compatible high-contrast ROI and relative-MTF values."""

    slice_index: int
    physical_z_mm: float
    rois: dict[str, GECTQAROIResult]
    roi_std_hu: dict[str, float]
    mtf_lp_mm: dict[str, float] | None
    mtf_50_lp_mm: float | None


class GECTQAHeliosLowContrastSliceResult(BaseModel):
    """One Helios-compatible 15 x 15 low-contrast grid slice."""

    slice_index: int
    physical_z_mm: float
    offset_from_center_slice_mm: float
    mean: float
    std: float
    min_hu: float
    max_hu: float


class GECTQAHeliosLowContrastResult(BaseModel):
    """Helios-compatible low-contrast grid summary across three slices."""

    slices: dict[str, GECTQAHeliosLowContrastSliceResult]
    mean: float
    std: float
    cell_size_mm: float
    num_cells: int


class GECTQAHeliosNoiseUniformityResult(BaseModel):
    """Helios-compatible noise and uniformity values on GE Section 3."""

    slice_index: int
    physical_z_mm: float
    rois: dict[str, GECTQAROIResult]
    noise_roi: GECTQAROIResult
    noise_center_std: float
    mean_outer: float
    uniformity_difference: float


class GECTQAHeliosCompatibilityResult(BaseModel):
    """Helios-shaped values retained without claiming Helios phantom identity."""

    available: bool
    reference_source: str
    validity: str
    contrast_scale: GECTQAHeliosContrastScaleResult | None = None
    high_contrast: GECTQAHeliosHighContrastResult | None = None
    low_contrast: GECTQAHeliosLowContrastResult | None = None
    noise_uniformity: GECTQAHeliosNoiseUniformityResult | None = None


class GECTQAMetadata(BaseModel):
    """DICOM acquisition metadata retained for machine-readable output."""

    modality: str | None = None
    manufacturer: str | None = None
    manufacturer_model_name: str | None = None
    series_instance_uid: str | None = None
    study_instance_uid: str | None = None
    rows: int | None = None
    columns: int | None = None
    pixel_spacing_mm: tuple[float, float] | None = None
    slice_thickness_mm: float | None = None
    spacing_between_slices_mm: float | None = None
    reconstruction_diameter_mm: float | None = None
    kvp: float | None = None
    convolution_kernel: str | None = None
    exposure: float | None = None
    exposure_time_ms: float | None = None
    tube_current_ma: float | None = None
    protocol_name: str | None = None
    series_description: str | None = None
    study_description: str | None = None
    acquisition_date: str | None = None
    acquisition_time: str | None = None


class GECTQAResult(ResultBase):
    """Structured results for the GE 20 cm CT QA phantom."""

    phantom_model: str
    reference: GECTQAReference
    metadata: GECTQAMetadata
    scanner_model: str | None
    num_images: int
    origin_slice: int
    module_locations: GECTQAModuleLocations
    localization: GECTQALocalizationResult
    ct_number: GECTQACTNumberResult
    contrast_scale: GECTQAContrastScaleResult
    noise: GECTQANoiseResult
    uniformity: GECTQAUniformityResult
    high_contrast_resolution: GECTQAHighContrastResult
    low_contrast: GECTQALowContrastResult
    slice_thickness: GECTQASliceThicknessResult
    positioning: GECTQAPositioningResult
    alignment: GECTQAAlignmentResult
    helios_compatibility: GECTQAHeliosCompatibilityResult | None
    overall_passed: bool | None
    num_tests: int
    num_passed: int
    num_failed: int
    num_warnings: int


@capture_warnings
class GECTQA(ResultsDataMixin[GECTQAResult], QuaacMixin):
    """Analyze a GE 20 cm CT QA phantom using an explicit local definition.

    Parameters
    ----------
    folderpath : str, Path, sequence, or file-like object
        A DICOM directory, a single DICOM image, or a sequence of DICOM paths
        or streams.
    config : GECTQAConfig, dict, or None
        GE phantom geometry and local acceptance criteria.  No insert geometry
        is assumed when omitted.
    check_uid : bool
        Retained for consistency with pylinac CT analyzers.  Mixed series are
        always rejected because combining them would make measurements unsafe.
    is_zip : bool
        Internal flag used by :meth:`from_zip`.
    """

    _model = "GE 20 cm CT QA Phantom"
    _phantom_threshold_hu = -250

    def __init__(
        self,
        folderpath: str | Path | Sequence[str | Path] | BinaryIO,
        config: GECTQAConfig | dict | None = None,
        check_uid: bool = True,
        is_zip: bool = False,
    ) -> None:
        super().__init__()
        self.config = (
            GECTQAConfig.from_ge_manual()
            if config is None
            else GECTQAConfig.model_validate(config)
        )
        self.dicom_stack = self._load_stack(folderpath, is_zip=is_zip)
        self._validate_stack()
        self._metadata = self._build_metadata()
        self._analysis_complete = False
        self._plot_entries: list[tuple[int, object, str]] = []
        self._module_locations: GECTQAModuleLocations | None = None

    @classmethod
    def from_zip(
        cls,
        zip_file: str | Path | BinaryIO,
        config: GECTQAConfig | dict | None = None,
        check_uid: bool = True,
    ) -> GECTQA:
        """Construct an analyzer from a ZIP archive of DICOM images."""
        return cls(zip_file, config=config, check_uid=check_uid, is_zip=True)

    @classmethod
    def from_url(
        cls,
        url: str,
        config: GECTQAConfig | dict | None = None,
        check_uid: bool = True,
    ) -> GECTQA:
        """Construct an analyzer from a URL pointing to a DICOM ZIP archive."""
        return cls.from_zip(get_url(url), config=config, check_uid=check_uid)

    @classmethod
    def from_demo_image(cls):
        """GE phantom demo data are not distributed with pylinac."""
        raise NotImplementedError("There is no GE CT QA demo file for this analysis")

    def _load_stack(
        self,
        source: str | Path | Sequence[str | Path] | BinaryIO,
        is_zip: bool,
    ) -> DicomImageStack:
        try:
            if is_zip:
                return DicomImageStack.from_zip(
                    source, min_number=1, check_uid=False
                )
            if isinstance(source, str | Path) and Path(source).is_file():
                source = [source]
            elif hasattr(source, "read"):
                source = [source]
            return DicomImageStack(source, min_number=1, check_uid=False)
        except (AttributeError, FileNotFoundError, IndexError, TypeError) as exc:
            raise ValueError(
                "No valid CT DICOM images were found in the supplied input."
            ) from exc

    def _validate_stack(self) -> None:
        if len(self.dicom_stack) == 0:
            raise ValueError("No CT DICOM images found.")
        metadatas = self.dicom_stack.metadatas
        modalities = {str(getattr(metadata, "Modality", "")).upper() for metadata in metadatas}
        if modalities != {"CT"}:
            raise ValueError(
                f"The GE CT QA analyzer requires CT DICOM images; found {sorted(modalities)}."
            )
        series_uids = {
            str(getattr(metadata, "SeriesInstanceUID", ""))
            for metadata in metadatas
        }
        if len(series_uids) > 1:
            raise ValueError("Multiple incompatible CT series detected.")
        study_uids = {
            str(getattr(metadata, "StudyInstanceUID", ""))
            for metadata in metadatas
            if getattr(metadata, "StudyInstanceUID", None) is not None
        }
        if len(study_uids) > 1:
            raise ValueError("Multiple incompatible CT studies detected.")

        reference_shape = (int(metadatas[0].Rows), int(metadatas[0].Columns))
        reference_spacing = self._pixel_spacing(metadatas[0])
        z_positions: list[float] = []
        for slice_index, metadata in enumerate(metadatas):
            if not hasattr(metadata, "PixelData"):
                try:
                    image = self.dicom_stack[slice_index]
                    if image.array.size == 0:
                        raise ValueError("A DICOM image contains no pixel data.")
                except (AttributeError, KeyError, ValueError, IndexError) as exc:
                    raise ValueError("A CT DICOM image does not contain pixel data.") from exc
            shape = (int(metadata.Rows), int(metadata.Columns))
            if shape != reference_shape:
                raise ValueError("CT DICOM images have inconsistent matrix dimensions.")
            spacing = self._pixel_spacing(metadata)
            if not np.allclose(spacing, reference_spacing, rtol=0, atol=1e-5):
                raise ValueError("CT DICOM images have inconsistent pixel spacing.")
            if not hasattr(metadata, "ImagePositionPatient"):
                raise ValueError("ImagePositionPatient is required for CT series sorting.")
            if len(metadata.ImagePositionPatient) < 3:
                raise ValueError("ImagePositionPatient must contain three coordinates.")
            z_positions.append(float(metadata.ImagePositionPatient[2]))

        if len(set(np.round(z_positions, 6))) != len(z_positions):
            raise ValueError("Duplicate CT slices were detected.")
        if len(z_positions) > 2:
            spacing_values = np.abs(np.diff(z_positions))
            median_spacing = float(np.median(spacing_values))
            self._slice_spacing_consistent = bool(
                np.allclose(spacing_values, median_spacing, rtol=0.05, atol=0.01)
            )
            if not self._slice_spacing_consistent:
                warnings.warn(
                    "Slice spacing is inconsistent; slice-dependent GE QA tests require review.",
                    UserWarning,
                )
        else:
            self._slice_spacing_consistent = True
        manufacturer = getattr(metadatas[0], "Manufacturer", None)
        if not manufacturer:
            warnings.warn("Manufacturer is missing from the CT DICOM metadata.", UserWarning)
        elif "GE" not in str(manufacturer).upper():
            warnings.warn(
                "Manufacturer is not GE; analysis continued because the phantom was loaded.",
                UserWarning,
            )
        if not getattr(metadatas[0], "ManufacturerModelName", None):
            warnings.warn("ManufacturerModelName is missing from the CT DICOM metadata.", UserWarning)

    @staticmethod
    def _pixel_spacing(metadata: pydicom.Dataset) -> tuple[float, float]:
        try:
            spacing = tuple(float(value) for value in metadata.PixelSpacing)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("Pixel spacing is missing or invalid.") from exc
        if len(spacing) != 2 or min(spacing) <= 0:
            raise ValueError("Pixel spacing is missing or invalid.")
        return spacing

    @property
    def num_images(self) -> int:
        """Return the number of loaded CT images."""
        return len(self.dicom_stack)

    @property
    def module_locations(self) -> GECTQAModuleLocations:
        """Return detected GE module locations after analysis."""
        if self._module_locations is None:
            raise ValueError("The GE CT QA phantom has not been analyzed yet.")
        return self._module_locations

    @property
    def pixel_spacing(self) -> tuple[float, float]:
        """Return DICOM row and column spacing in millimetres."""
        return self._pixel_spacing(self.dicom_stack.metadatas[0])

    @property
    def z_positions(self) -> np.ndarray:
        """Return sorted slice positions in millimetres."""
        return np.asarray(
            [float(metadata.ImagePositionPatient[2]) for metadata in self.dicom_stack.metadatas]
        )

    @property
    def slice_spacing_mm(self) -> float | None:
        """Return the measured median inter-slice spacing, if available."""
        if self.num_images > 1:
            return float(np.median(np.abs(np.diff(self.z_positions))))
        metadata = self.dicom_stack.metadatas[0]
        for name in ("SpacingBetweenSlices", "SliceThickness"):
            value = getattr(metadata, name, None)
            if value is not None:
                try:
                    return abs(float(value))
                except (TypeError, ValueError):
                    pass
        return None

    def _build_metadata(self) -> GECTQAMetadata:
        metadata = self.dicom_stack.metadatas[0]

        def text(name: str) -> str | None:
            value = getattr(metadata, name, None)
            return str(value) if value is not None else None

        def number(name: str) -> float | None:
            value = getattr(metadata, name, None)
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        return GECTQAMetadata(
            modality=text("Modality"),
            manufacturer=text("Manufacturer"),
            manufacturer_model_name=text("ManufacturerModelName"),
            series_instance_uid=text("SeriesInstanceUID"),
            study_instance_uid=text("StudyInstanceUID"),
            rows=int(getattr(metadata, "Rows", 0)),
            columns=int(getattr(metadata, "Columns", 0)),
            pixel_spacing_mm=self.pixel_spacing,
            slice_thickness_mm=number("SliceThickness"),
            spacing_between_slices_mm=number("SpacingBetweenSlices"),
            reconstruction_diameter_mm=number("ReconstructionDiameter"),
            kvp=number("KVP"),
            convolution_kernel=text("ConvolutionKernel"),
            exposure=number("Exposure"),
            exposure_time_ms=number("ExposureTime"),
            tube_current_ma=number("XRayTubeCurrent"),
            protocol_name=text("ProtocolName"),
            series_description=text("SeriesDescription"),
            study_description=text("StudyDescription"),
            acquisition_date=text("AcquisitionDate"),
            acquisition_time=text("AcquisitionTime"),
        )

    def _phantom_component(self, array: np.ndarray) -> tuple[float, float, float] | None:
        row_spacing, column_spacing = self.pixel_spacing
        closing_radius = max(1, int(round(2.0 / min(row_spacing, column_spacing))))
        mask = np.isfinite(array) & (array > self._phantom_threshold_hu)
        mask = ndimage.binary_closing(mask, structure=morphology.disk(closing_radius))
        mask = morphology.remove_small_objects(mask, max_size=max(25, closing_radius**2))
        regions = sorted(measure.regionprops(measure.label(mask)), key=lambda region: region.area, reverse=True)
        lower_diameter, upper_diameter = self.config.expected_diameter_range_mm
        candidates: list[tuple[measure._regionprops.RegionProperties, float]] = []
        for region in regions:
            area_mm2 = region.area * row_spacing * column_spacing
            diameter_mm = float(np.sqrt(4 * area_mm2 / np.pi))
            box_height = region.bbox[2] - region.bbox[0]
            box_width = region.bbox[3] - region.bbox[1]
            aspect_ratio = box_height / box_width if box_width else 0
            if (
                lower_diameter * 0.7 <= diameter_mm <= upper_diameter * 1.3
                and region.eccentricity < 0.75
                and region.solidity > 0.7
                and 0.65 <= aspect_ratio <= 1.5
            ):
                candidates.append((region, diameter_mm))
        if not candidates:
            return None
        region, diameter_mm = candidates[0]
        return float(region.centroid[1]), float(region.centroid[0]), diameter_mm

    def _localize(
        self,
        center_override: tuple[float, float] | None,
        angle_override: float | None,
    ) -> GECTQALocalizationResult:
        observations: list[tuple[float, float, float]] = []
        self._localization_slice_indices: list[int] = []
        for slice_index, image in enumerate(self.dicom_stack):
            component = self._phantom_component(np.asarray(image.array, dtype=float))
            if component is not None:
                observations.append(component)
                self._localization_slice_indices.append(slice_index)
        if center_override is None and not observations:
            raise ValueError(
                "Unable to localize GE QA phantom. Supply center_override=(x, y) "
                "or verify that the phantom is visible in the CT image."
            )
        if center_override is not None:
            center_x_px, center_y_px = (float(center_override[0]), float(center_override[1]))
            if not (0 <= center_x_px < self._metadata.columns and 0 <= center_y_px < self._metadata.rows):
                raise ValueError("center_override must be inside the image matrix.")
            if not self._localization_slice_indices:
                self._localization_slice_indices = list(range(self.num_images))
            diameter_mm = float(np.median([item[2] for item in observations])) if observations else float(np.mean(self.config.expected_diameter_range_mm))
            confidence = 1.0
        else:
            center_x_px = float(np.median([item[0] for item in observations]))
            center_y_px = float(np.median([item[1] for item in observations]))
            diameter_mm = float(np.median([item[2] for item in observations]))
            confidence = min(1.0, len(observations) / max(3, self.num_images))
        if angle_override is None:
            warnings.warn(
                "Phantom rotation was not determined from the circular boundary; using 0 degrees. "
                "Supply angle_override or a validated orientation definition when needed.",
                UserWarning,
            )
            angle = 0.0
        else:
            angle = float(angle_override)
        image_center_x = (self._metadata.columns - 1) / 2
        image_center_y = (self._metadata.rows - 1) / 2
        row_spacing, column_spacing = self.pixel_spacing
        return GECTQALocalizationResult(
            phantom_center_x_px=center_x_px,
            phantom_center_y_px=center_y_px,
            phantom_center_x_mm=(center_x_px - image_center_x) * column_spacing,
            phantom_center_y_mm=(center_y_px - image_center_y) * row_spacing,
            phantom_radius_mm=diameter_mm / 2,
            phantom_diameter_mm=diameter_mm,
            phantom_rotation_deg=angle,
            localization_confidence=confidence,
        )

    def _image_array(self, slice_index: int) -> np.ndarray:
        """Return one stack image as a floating-point HU array."""
        return np.asarray(self.dicom_stack[slice_index].array, dtype=float)

    def _default_high_contrast_rois(self) -> dict[str, GECTQAHighContrastROI]:
        """Return the four Helios-compatible bar ROIs used for detection."""
        return {
            name: GECTQAHighContrastROI(
                **_roi_from_setting(setting).model_dump(),
                spatial_frequency_lp_mm=1 / (2 * setting["bar_size_mm"]),
            )
            for name, setting in GE_HELIOS_HIGH_CONTRAST_ROI_SETTINGS.items()
        }

    def _grid_statistics(
        self,
        slice_index: int,
        cell_size_mm: float = 5.0,
        num_cells: int = 15,
    ) -> dict[str, float | list[float]]:
        """Measure a centered physical-mm grid used by GE and Helios QA."""
        array = self._image_array(slice_index)
        cell_width_px = cell_size_mm / self.pixel_spacing[1]
        cell_height_px = cell_size_mm / self.pixel_spacing[0]
        total_width_px = num_cells * cell_width_px
        total_height_px = num_cells * cell_height_px
        first_x = (
            self._current_localization.phantom_center_x_px
            - total_width_px / 2
            + cell_width_px / 2
        )
        first_y = (
            self._current_localization.phantom_center_y_px
            - total_height_px / 2
            + cell_height_px / 2
        )
        means: list[float] = []
        for row in range(num_cells):
            for column in range(num_cells):
                roi = RectangleROI(
                    array=array,
                    width=cell_width_px,
                    height=cell_height_px,
                    center=Point(
                        first_x + column * cell_width_px,
                        first_y + row * cell_height_px,
                    ),
                )
                means.append(roi.mean)
        values = np.asarray(means, dtype=float)
        return {
            "means": means,
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
            "min": float(np.min(values)),
            "max": float(np.max(values)),
            "high_cell_count": float(
                np.sum(values > np.median(values) + 15)
            ),
        }

    def _low_contrast_target_definitions(
        self, slice_index: int
    ) -> list[tuple[str, GECTQALowContrastTarget]]:
        """Find compact circular contrast candidates in the selected slice."""
        array = self._image_array(slice_index)
        enhanced = ndimage.gaussian_filter(array, 1) - ndimage.gaussian_filter(
            array, 6
        )
        row_spacing, column_spacing = self.pixel_spacing
        yy, xx = np.indices(array.shape)
        central_mask = (
            (xx - self._current_localization.phantom_center_x_px) ** 2
            + (yy - self._current_localization.phantom_center_y_px) ** 2
            < (70 / np.mean(self.pixel_spacing)) ** 2
        )
        threshold = max(5.0, float(np.percentile(enhanced[central_mask], 95)))
        regions = measure.regionprops(
            measure.label((enhanced > threshold) & central_mask)
        )
        target_regions = [
            region
            for region in regions
            if 80 <= region.area <= 350 and region.eccentricity < 0.85
        ]
        target_regions.sort(key=lambda region: (region.centroid[0], region.centroid[1]))
        definitions = []
        for number, region in enumerate(target_regions, start=1):
            center_x, center_y = region.centroid[1], region.centroid[0]
            radius_px = np.sqrt(region.area / np.pi)
            definitions.append(
                (
                    f"candidate_{number}",
                    GECTQALowContrastTarget(
                        x_mm=(center_x - self._current_localization.phantom_center_x_px)
                        * column_spacing,
                        y_mm=(center_y - self._current_localization.phantom_center_y_px)
                        * row_spacing,
                        radius_mm=float(radius_px * np.mean(self.pixel_spacing)),
                        target_size_mm=float(2 * radius_px * np.mean(self.pixel_spacing)),
                    ),
                )
            )
        return definitions

    def _target_background_statistics(
        self, array: np.ndarray, target_roi: DiskROI | RectangleROI
    ) -> tuple[float, float]:
        """Estimate local background statistics from an annulus around a target."""
        yy, xx = np.indices(array.shape)
        distance = np.sqrt(
            (xx - target_roi.center.x) ** 2 + (yy - target_roi.center.y) ** 2
        )
        if isinstance(target_roi, DiskROI):
            inner_radius = target_roi.radius * 1.5
            outer_radius = target_roi.radius * 3.0
        else:
            inner_radius = max(target_roi.width, target_roi.height) * 0.75
            outer_radius = max(target_roi.width, target_roi.height) * 1.5
        values = array[(distance >= inner_radius) & (distance <= outer_radius)]
        values = values[np.isfinite(values)]
        if values.size == 0:
            return float(np.mean(array)), float(np.std(array))
        return float(np.mean(values)), float(np.std(values))

    def _detect_module_locations(self) -> GECTQAModuleLocations:
        """Detect the image slices that best represent the GE QA modules."""
        candidate_indices = self._localization_slice_indices or list(
            range(self.num_images)
        )
        high_definitions = self.config.high_contrast_rois or self._default_high_contrast_rois()
        first_definition = high_definitions.get("1.6mm") or next(
            iter(high_definitions.values())
        )
        section1_scores: dict[int, float] = {}
        low_scores: dict[int, float] = {}
        uniformity_scores: dict[int, float] = {}
        for slice_index in candidate_indices:
            try:
                array = self._image_array(slice_index)
                first_roi = self._create_roi(array, first_definition)
                section1_scores[slice_index] = float(np.std(self._roi_pixels(first_roi)))
                grid = self._grid_statistics(slice_index)
                water_reference = (
                    self.config.uniformity_reference_hu
                    if self.config.uniformity_reference_hu is not None
                    else 0.0
                )
                uniformity_scores[slice_index] = float(
                    abs(float(grid["mean"]) - water_reference)
                    + float(grid["std"])
                )
                enhanced = ndimage.gaussian_filter(array, 1) - ndimage.gaussian_filter(
                    array, 6
                )
                central_mask = (
                    (np.indices(array.shape)[1] - self._current_localization.phantom_center_x_px) ** 2
                    + (np.indices(array.shape)[0] - self._current_localization.phantom_center_y_px) ** 2
                    < (70 / np.mean(self.pixel_spacing)) ** 2
                )
                threshold = max(
                    5.0,
                    float(np.percentile(enhanced[central_mask], 95)),
                )
                regions = measure.regionprops(
                    measure.label((enhanced > threshold) & central_mask)
                )
                circular_target_count = sum(
                    80 <= region.area <= 350 and region.eccentricity < 0.85
                    for region in regions
                )
                if -20 <= float(grid["mean"]) <= 180:
                    low_scores[slice_index] = float(
                        circular_target_count * 100 + float(grid["high_cell_count"])
                    )
                else:
                    low_scores[slice_index] = -1.0
            except (IndexError, ValueError):
                section1_scores[slice_index] = -np.inf
                uniformity_scores[slice_index] = np.inf
                low_scores[slice_index] = -np.inf

        section1_slice = max(section1_scores, key=section1_scores.get)
        uniformity_candidates = [
            index
            for index in candidate_indices
            if abs(index - section1_slice) > 5
        ] or candidate_indices
        uniformity_slice = min(
            uniformity_candidates,
            key=lambda index: uniformity_scores.get(index, np.inf),
        )
        low_contrast_candidates = [
            index
            for index in candidate_indices
            if index != section1_slice and abs(index - section1_slice) > 3
        ] or candidate_indices
        low_contrast_slice = max(
            low_contrast_candidates,
            key=lambda index: low_scores.get(index, -np.inf),
        )
        return GECTQAModuleLocations(
            section1_scan_location_mm=self.config.section1_location_mm,
            section3_scan_location_mm=self.config.section3_location_mm,
            section1_slice_index=int(section1_slice),
            section1_physical_z_mm=float(self.z_positions[section1_slice]),
            section1_score=float(section1_scores[section1_slice]),
            uniformity_slice_index=int(uniformity_slice),
            uniformity_physical_z_mm=float(self.z_positions[uniformity_slice]),
            uniformity_score=float(uniformity_scores[uniformity_slice]),
            low_contrast_slice_index=int(low_contrast_slice),
            low_contrast_physical_z_mm=float(self.z_positions[low_contrast_slice]),
            low_contrast_score=float(low_scores[low_contrast_slice]),
            detection_method=(
                "content signatures: 1.6 mm bar-pattern standard deviation, "
                "uniform-water center ROI, and low-contrast grid high-cell count"
            ),
        )

    def _find_origin_slice(self, requested: int | None) -> int:
        if requested is not None:
            if not 0 <= requested < self.num_images:
                raise ValueError("origin_slice is outside the loaded CT series.")
            return int(requested)
        if self.config.automatic_module_detection and self._module_locations is not None:
            return self._module_locations.section1_slice_index
        if self.num_images == 1:
            return 0
        return self._localization_slice_indices[len(self._localization_slice_indices) // 2]

    def _module_slice(self, offset_mm: float, module_name: str | None = None) -> int | None:
        if (
            self.config.automatic_module_detection
            and self._module_locations is not None
            and abs(offset_mm) < 1e-6
            and module_name is not None
        ):
            return int(getattr(self._module_locations, f"{module_name}_slice_index"))
        target_z = self.z_positions[self.origin_slice] + offset_mm
        index = int(np.argmin(np.abs(self.z_positions - target_z)))
        distance = abs(float(self.z_positions[index] - target_z))
        spacing = self.slice_spacing_mm
        if spacing is not None and distance > max(spacing / 2, 1.0):
            warnings.warn(
                f"Configured module offset {offset_mm:g} mm is not represented by a nearby CT slice.",
                UserWarning,
            )
        return index

    def _create_roi(self, array: np.ndarray, definition: GECTQAROI):
        row_spacing, column_spacing = self.pixel_spacing
        angle = np.deg2rad(self._current_localization.phantom_rotation_deg)
        rotated_x = definition.x_mm * np.cos(angle) - definition.y_mm * np.sin(angle)
        rotated_y = definition.x_mm * np.sin(angle) + definition.y_mm * np.cos(angle)
        center = Point(
            self._current_localization.phantom_center_x_px + rotated_x / column_spacing,
            self._current_localization.phantom_center_y_px + rotated_y / row_spacing,
        )
        if definition.radius_mm is not None:
            radius_px = definition.radius_mm / np.mean(self.pixel_spacing)
            return DiskROI(array=array, radius=radius_px, center=center)
        return RectangleROI(
            array=array,
            width=definition.width_mm / column_spacing,
            height=definition.height_mm / row_spacing,
            center=center,
            rotation=definition.rotation_deg + self._current_localization.phantom_rotation_deg,
        )

    @staticmethod
    def _roi_pixels(roi: DiskROI | RectangleROI) -> np.ndarray:
        if isinstance(roi, DiskROI):
            values = roi.circle_mask()
        else:
            values = roi.pixels_flat
        values = np.asarray(values, dtype=float).ravel()
        values = values[np.isfinite(values)]
        if values.size == 0:
            raise ValueError("The configured ROI contains no image pixels.")
        return values

    def _roi_result(
        self,
        name: str,
        definition: GECTQAROI,
        slice_index: int,
        offset_mm: float,
        module_name: str,
    ) -> tuple[GECTQAROIResult, DiskROI | RectangleROI]:
        image_array = np.asarray(self.dicom_stack[slice_index].array)
        roi = self._create_roi(image_array, definition)
        values = self._roi_pixels(roi)
        percentiles = {
            "p01": float(np.percentile(values, 1)),
            "p05": float(np.percentile(values, 5)),
            "p50": float(np.percentile(values, 50)),
            "p95": float(np.percentile(values, 95)),
            "p99": float(np.percentile(values, 99)),
        }
        result = GECTQAROIResult(
            name=name,
            offset_mm=offset_mm,
            slice_index=slice_index,
            physical_z_mm=float(self.z_positions[slice_index]),
            center_x_px=float(roi.center.x),
            center_y_px=float(roi.center.y),
            center_x_mm=definition.x_mm,
            center_y_mm=definition.y_mm,
            radius_mm=definition.radius_mm,
            width_mm=definition.width_mm,
            height_mm=definition.height_mm,
            mean_hu=float(np.mean(values)),
            median_hu=float(np.median(values)),
            std_hu=float(np.std(values)),
            min_hu=float(np.min(values)),
            max_hu=float(np.max(values)),
            percentiles=percentiles,
            pixel_count=int(values.size),
        )
        self._plot_entries.append((slice_index, roi, f"{module_name}: {name}"))
        return result, roi

    @staticmethod
    def _combine_passes(passes: Sequence[bool | None]) -> bool | None:
        values = list(passes)
        if not values or any(value is None for value in values):
            return None if not any(value is False for value in values) else False
        return all(values)

    @staticmethod
    def _combine_known_passes(passes: Sequence[bool | None]) -> bool | None:
        """Combine configured checks while ignoring metrics with no limit."""
        known_values = [value for value in passes if value is not None]
        return all(known_values) if known_values else None

    def _unavailable(self, result_type, reason: str, **values):
        return result_type(available=False, passed=None, reason=reason, **values)

    def _analyze_ct_number(self) -> GECTQACTNumberResult:
        if not self.config.ct_number_rois:
            return self._unavailable(
                GECTQACTNumberResult,
                "Required GE CT-number ROI geometry and nominal values were not supplied.",
            )
        slice_index = self._module_slice(
            self.config.ct_number_offset_mm, module_name="section1"
        )
        roi_results: dict[str, GECTQAMaterialResult] = {}
        for name, definition in self.config.ct_number_rois.items():
            try:
                base_result, _ = self._roi_result(
                    name,
                    definition,
                    slice_index,
                    self.config.ct_number_offset_mm,
                    "CT number",
                )
            except ValueError as exc:
                return self._unavailable(GECTQACTNumberResult, str(exc))
            difference = (
                base_result.mean_hu - definition.nominal_hu
                if definition.nominal_hu is not None
                else None
            )
            percent_error = None
            if difference is not None and definition.nominal_hu not in (None, 0):
                percent_error = abs(difference / definition.nominal_hu) * 100
            passed = (
                abs(difference) <= definition.tolerance_hu
                if difference is not None and definition.tolerance_hu is not None
                else None
            )
            roi_results[name] = GECTQAMaterialResult(
                **base_result.model_dump(),
                nominal_hu=definition.nominal_hu,
                difference_hu=difference,
                percent_error=percent_error,
                tolerance_hu=definition.tolerance_hu,
                passed=passed,
            )
        return GECTQACTNumberResult(
            available=True,
            passed=self._combine_passes([result.passed for result in roi_results.values()]),
            rois=roi_results,
        )

    def _analyze_contrast_scale(
        self, ct_number: GECTQACTNumberResult
    ) -> GECTQAContrastScaleResult:
        definition = self.config.contrast_scale
        if definition is None:
            return self._unavailable(
                GECTQAContrastScaleResult,
                "The GE contrast-scale formula and reference ROIs were not supplied.",
            )
        if not ct_number.available:
            return self._unavailable(
                GECTQAContrastScaleResult,
                "Contrast scale requires configured CT-number reference ROIs.",
            )
        try:
            first_value = ct_number.rois[definition.first_roi].mean_hu
            second_value = ct_number.rois[definition.second_roi].mean_hu
        except KeyError as exc:
            return self._unavailable(
                GECTQAContrastScaleResult,
                f"Contrast-scale reference ROI is missing: {exc.args[0]}.",
            )
        contrast_scale = first_value - second_value
        deviation = (
            contrast_scale - definition.nominal_difference_hu
            if definition.nominal_difference_hu is not None
            else None
        )
        passed = (
            abs(deviation) <= definition.tolerance_hu
            if deviation is not None and definition.tolerance_hu is not None
            else None
        )
        return GECTQAContrastScaleResult(
            available=True,
            passed=passed,
            first_roi=definition.first_roi,
            second_roi=definition.second_roi,
            reference_values_hu={
                definition.first_roi: first_value,
                definition.second_roi: second_value,
            },
            contrast_scale=contrast_scale,
            contrast_scale_units=definition.units,
            nominal_difference_hu=definition.nominal_difference_hu,
            deviation_hu=deviation,
            tolerance_hu=definition.tolerance_hu,
        )

    def _analyze_noise(self) -> GECTQANoiseResult:
        if self.config.noise_roi is None:
            return self._unavailable(
                GECTQANoiseResult,
                "Required GE noise ROI geometry was not supplied.",
            )
        slice_index = self._module_slice(
            self.config.noise_offset_mm, module_name="uniformity"
        )
        try:
            roi_result, _ = self._roi_result(
                "noise",
                self.config.noise_roi,
                slice_index,
                self.config.noise_offset_mm,
                "Noise",
            )
        except ValueError as exc:
            return self._unavailable(GECTQANoiseResult, str(exc))
        if self.config.noise_tolerance_hu is None:
            passed = None
        elif self.config.noise_reference_hu is None:
            passed = roi_result.std_hu <= self.config.noise_tolerance_hu
        else:
            passed = (
                abs(roi_result.std_hu - self.config.noise_reference_hu)
                <= self.config.noise_tolerance_hu
            )
        return GECTQANoiseResult(
            available=True,
            passed=passed,
            roi=roi_result,
            noise_hu=roi_result.std_hu,
            reference_hu=self.config.noise_reference_hu,
            difference_hu=(
                roi_result.std_hu - self.config.noise_reference_hu
                if self.config.noise_reference_hu is not None
                else None
            ),
            tolerance_hu=self.config.noise_tolerance_hu,
        )

    def _analyze_uniformity(self) -> GECTQAUniformityResult:
        if not self.config.uniformity_rois:
            return self._unavailable(
                GECTQAUniformityResult,
                "Required GE uniformity ROI geometry was not supplied.",
            )
        if self.config.uniformity_center_name not in self.config.uniformity_rois:
            return self._unavailable(
                GECTQAUniformityResult,
                f"Uniformity center ROI '{self.config.uniformity_center_name}' was not supplied.",
            )
        slice_index = self._module_slice(
            self.config.uniformity_offset_mm, module_name="uniformity"
        )
        roi_results: dict[str, GECTQAROIResult] = {}
        try:
            for name, definition in self.config.uniformity_rois.items():
                roi_results[name], _ = self._roi_result(
                    name,
                    definition,
                    slice_index,
                    self.config.uniformity_offset_mm,
                    "Uniformity",
                )
        except ValueError as exc:
            return self._unavailable(GECTQAUniformityResult, str(exc))
        center_value = roi_results[self.config.uniformity_center_name].mean_hu
        means = [result.mean_hu for result in roi_results.values()]
        peripheral = [
            result.mean_hu
            for name, result in roi_results.items()
            if name != self.config.uniformity_center_name
        ]
        max_deviation = max((abs(value - center_value) for value in peripheral), default=0.0)
        max_pairwise = max(means) - min(means)
        if self.config.uniformity_tolerance_hu is None:
            passed = None
        elif self.config.uniformity_reference_hu is None:
            passed = max_deviation <= self.config.uniformity_tolerance_hu
        else:
            passed = (
                abs(max_deviation - self.config.uniformity_reference_hu)
                <= self.config.uniformity_tolerance_hu
            )
        return GECTQAUniformityResult(
            available=True,
            passed=passed,
            rois=roi_results,
            center_roi_name=self.config.uniformity_center_name,
            max_deviation_from_center_hu=max_deviation,
            max_pairwise_difference_hu=max_pairwise,
            reference_difference_hu=self.config.uniformity_reference_hu,
            tolerance_hu=self.config.uniformity_tolerance_hu,
        )

    def _analyze_high_contrast(self) -> GECTQAHighContrastResult:
        if not self.config.high_contrast_rois:
            return self._unavailable(
                GECTQAHighContrastResult,
                "Required GE high-contrast ROI geometry and line-pair definition were not supplied.",
            )
        slice_index = self._module_slice(
            self.config.high_contrast_offset_mm, module_name="section1"
        )
        roi_results: dict[str, GECTQAHighContrastROIResult] = {}
        try:
            for name, definition in self.config.high_contrast_rois.items():
                base_result, _ = self._roi_result(
                    name,
                    definition,
                    slice_index,
                    self.config.high_contrast_offset_mm,
                    "High contrast",
                )
                threshold = definition.visibility_threshold_hu
                resolved = base_result.std_hu >= threshold if threshold is not None else None
                reference_difference = (
                    base_result.std_hu - definition.reference_std_hu
                    if definition.reference_std_hu is not None
                    else None
                )
                reference_passed = (
                    abs(reference_difference) <= definition.tolerance_hu
                    if reference_difference is not None
                    and definition.tolerance_hu is not None
                    else None
                )
                roi_results[name] = GECTQAHighContrastROIResult(
                    **base_result.model_dump(),
                    spatial_frequency_lp_mm=definition.spatial_frequency_lp_mm,
                    visibility_score_hu=base_result.std_hu,
                    visibility_threshold_hu=threshold,
                    resolved=resolved,
                    reference_std_hu=definition.reference_std_hu,
                    difference_hu=reference_difference,
                    tolerance_hu=definition.tolerance_hu,
                    passed=reference_passed,
                )
        except ValueError as exc:
            return self._unavailable(GECTQAHighContrastResult, str(exc))
        resolved_rois = [result for result in roi_results.values() if result.resolved]
        best = max(resolved_rois, key=lambda result: result.spatial_frequency_lp_mm, default=None)
        resolution = best.spatial_frequency_lp_mm if best is not None else None
        mtf_values: dict[str, float] | None = None
        mtf_50 = None
        try:
            ordered_names = list(self.config.high_contrast_rois)
            ordered_rois = [
                self._create_roi(self._image_array(slice_index), self.config.high_contrast_rois[name])
                for name in ordered_names
            ]
            spacings = [
                self.config.high_contrast_rois[name].spatial_frequency_lp_mm
                for name in ordered_names
            ]
            mtf = MTF.from_high_contrast_diskset(
                spacings=spacings,
                diskset=ordered_rois,
            )
            mtf_values = {
                str(percentage): float(mtf.relative_resolution(percentage))
                for percentage in range(10, 100, 10)
            }
            mtf_50 = mtf_values["50"]
            if resolution is None:
                resolution = mtf_50
        except (IndexError, KeyError, ValueError, TypeError):
            pass
        passed = (
            resolution >= self.config.minimum_resolution_lp_mm
            if resolution is not None and self.config.minimum_resolution_lp_mm is not None
            else self._combine_known_passes(
                [result.passed for result in roi_results.values()]
            )
        )
        return GECTQAHighContrastResult(
            available=True,
            passed=passed,
            rois=roi_results,
            resolved_group=best.name if best is not None else None,
            resolution_lp_mm=resolution,
            resolution_lp_cm=resolution * 10 if resolution is not None else None,
            mtf=mtf_values,
        )

    def _analyze_low_contrast(self) -> GECTQALowContrastResult:
        definition = self.config.low_contrast
        if definition is None:
            return self._unavailable(
                GECTQALowContrastResult,
                "Required GE low-contrast target geometry and scoring rule were not supplied.",
            )
        slice_index = self._module_slice(
            self.config.low_contrast_offset_mm, module_name="low_contrast"
        )
        grid = self._grid_statistics(slice_index)
        auto_target_definitions = []
        if not definition.targets:
            auto_target_definitions = self._low_contrast_target_definitions(slice_index)
            if auto_target_definitions:
                definition = definition.model_copy(
                    update={"targets": dict(auto_target_definitions)}
                )
        if not definition.targets:
            return GECTQALowContrastResult(
                available=True,
                passed=None,
                reason=(
                    "Automated grid statistics are available; the GE procedure's "
                    "visual low-contrast observer score was not inferred."
                ),
                cnr_threshold=definition.cnr_threshold,
                num_rois_detected=0,
                num_rois_visible=0,
                grid_cell_size_mm=5.0,
                grid_num_cells=15,
                grid_mean_hu=float(grid["mean"]),
                grid_std_hu=float(grid["std"]),
                grid_min_hu=float(grid["min"]),
                grid_max_hu=float(grid["max"]),
            )
        try:
            background_result, _ = self._roi_result(
                "background",
                definition.background,
                slice_index,
                self.config.low_contrast_offset_mm,
                "Low contrast",
            )
            roi_results: dict[str, GECTQALowContrastROIResult] = {}
            for name, target_definition in definition.targets.items():
                target, target_roi = self._roi_result(
                    name,
                    target_definition,
                    slice_index,
                    self.config.low_contrast_offset_mm,
                    "Low contrast",
                )
                background_mean, background_std = self._target_background_statistics(
                    self._image_array(slice_index), target_roi
                )
                contrast = abs(target.mean_hu - background_mean)
                denominator = np.sqrt((target.std_hu**2 + background_std**2) / 2)
                cnr = float(contrast / denominator) if denominator > 0 else None
                visible = cnr >= definition.cnr_threshold if cnr is not None and definition.cnr_threshold is not None else None
                roi_results[name] = GECTQALowContrastROIResult(
                    **target.model_dump(),
                    target_size_mm=target_definition.target_size_mm,
                    target_mean_hu=target.mean_hu,
                    target_std_hu=target.std_hu,
                    background_mean_hu=background_mean,
                    background_std_hu=background_std,
                    contrast_hu=contrast,
                    cnr=cnr,
                    visibility_score=cnr,
                    passed=visible,
                )
        except ValueError as exc:
            return self._unavailable(GECTQALowContrastResult, str(exc))
        visible_values = [
            result.cnr
            for result in roi_results.values()
            if result.cnr is not None and definition.cnr_threshold is not None and result.cnr >= definition.cnr_threshold
        ]
        cnrs = [result.cnr for result in roi_results.values() if result.cnr is not None]
        visible_count = len(visible_values)
        passed = None
        if (
            definition.minimum_visible_targets is not None
            and definition.cnr_threshold is not None
        ):
            passed = visible_count >= definition.minimum_visible_targets
        contrasts = [result.contrast_hu for result in roi_results.values()]
        return GECTQALowContrastResult(
            available=True,
            passed=passed,
            background=background_result,
            rois=roi_results,
            cnr_threshold=definition.cnr_threshold,
            num_rois_detected=len(roi_results),
            num_rois_visible=visible_count,
            minimum_visible_contrast_hu=min(contrasts) if contrasts else None,
            best_cnr=max(cnrs) if cnrs else None,
            worst_cnr=min(cnrs) if cnrs else None,
            grid_cell_size_mm=5.0,
            grid_num_cells=15,
            grid_mean_hu=float(grid["mean"]),
            grid_std_hu=float(grid["std"]),
            grid_min_hu=float(grid["min"]),
            grid_max_hu=float(grid["max"]),
            method=(
                "automatic circular target candidates + CNR estimate; visual "
                "observer score not inferred"
                if auto_target_definitions
                else "configured target/background CNR"
            ),
        )

    def _analyze_slice_thickness(self) -> GECTQASliceThicknessResult:
        definition = self.config.slice_thickness
        if definition is None:
            return self._unavailable(
                GECTQASliceThicknessResult,
                "Required GE slice-thickness insert geometry and calibration were not supplied.",
                acquired_slice_thickness_mm=self._metadata.slice_thickness_mm,
            )
        if self.num_images < 3 or self.slice_spacing_mm is None:
            return self._unavailable(
                GECTQASliceThicknessResult,
                "At least three CT slices with usable z spacing are required for slice-thickness analysis.",
                acquired_slice_thickness_mm=self._metadata.slice_thickness_mm,
            )
        values: list[float] = []
        try:
            for slice_index in range(self.num_images):
                roi, _ = self._roi_result(
                    "slice thickness profile",
                    definition.roi,
                    slice_index,
                    definition.offset_mm,
                    "Slice thickness",
                )
                values.append(roi.mean_hu)
        except ValueError as exc:
            return self._unavailable(
                GECTQASliceThicknessResult,
                str(exc),
                acquired_slice_thickness_mm=self._metadata.slice_thickness_mm,
            )
        profile_z = self.z_positions.copy()
        target_z = profile_z[self.origin_slice] + definition.offset_mm
        if definition.sample_half_range_mm is not None:
            keep = np.abs(profile_z - target_z) <= definition.sample_half_range_mm
            profile_z = profile_z[keep]
            values = list(np.asarray(values)[keep])
        profile_values = np.asarray(values, dtype=float)
        if definition.polarity == "dark":
            profile_values = -profile_values
        peak_index = int(np.argmax(profile_values))
        baseline = float(np.percentile(profile_values, 10))
        peak = float(profile_values[peak_index])
        if peak <= baseline:
            return self._unavailable(
                GECTQASliceThicknessResult,
                "The configured slice-thickness profile has no measurable peak.",
                acquired_slice_thickness_mm=self._metadata.slice_thickness_mm,
            )
        half_level = baseline + (peak - baseline) / 2
        above = profile_values >= half_level
        group_start = peak_index
        group_end = peak_index
        while group_start > 0 and above[group_start - 1]:
            group_start -= 1
        while group_end < len(above) - 1 and above[group_end + 1]:
            group_end += 1
        if group_start == 0 or group_end == len(above) - 1:
            return self._unavailable(
                GECTQASliceThicknessResult,
                "The slice-thickness FWHM reaches the acquired series boundary.",
                acquired_slice_thickness_mm=self._metadata.slice_thickness_mm,
            )
        left_position = self._interpolate_crossing(
            profile_z[group_start - 1],
            profile_z[group_start],
            profile_values[group_start - 1],
            profile_values[group_start],
            half_level,
        )
        right_position = self._interpolate_crossing(
            profile_z[group_end],
            profile_z[group_end + 1],
            profile_values[group_end],
            profile_values[group_end + 1],
            half_level,
        )
        measured = abs(right_position - left_position) * definition.correction_factor
        difference = measured - definition.nominal_mm if definition.nominal_mm is not None else None
        percent_difference = abs(difference / definition.nominal_mm) * 100 if difference is not None and definition.nominal_mm not in (None, 0) else None
        passed = abs(difference) <= definition.tolerance_mm if difference is not None and definition.tolerance_mm is not None else None
        selected_peak_z = float(profile_z[peak_index])
        selected_peak_index = int(np.argmin(np.abs(self.z_positions - selected_peak_z)))
        return GECTQASliceThicknessResult(
            available=True,
            passed=passed,
            nominal_slice_thickness_mm=definition.nominal_mm,
            measured_slice_thickness_mm=measured,
            difference_mm=difference,
            percent_difference=percent_difference,
            tolerance_mm=definition.tolerance_mm,
            method=definition.method,
            slice_index=selected_peak_index,
            physical_z_mm=selected_peak_z,
            profile_z_mm=[float(value) for value in profile_z],
            profile_values_hu=[float(value) for value in profile_values],
            acquired_slice_thickness_mm=self._metadata.slice_thickness_mm,
        )

    @staticmethod
    def _interpolate_crossing(
        first_z: float,
        second_z: float,
        first_value: float,
        second_value: float,
        level: float,
    ) -> float:
        if second_value == first_value:
            return (first_z + second_z) / 2
        fraction = (level - first_value) / (second_value - first_value)
        return first_z + fraction * (second_z - first_z)

    def _analyze_positioning(self) -> GECTQAPositioningResult:
        tolerance = self.config.positioning_tolerance_mm
        offset_x = self._current_localization.phantom_center_x_mm
        offset_y = self._current_localization.phantom_center_y_mm
        passed = (
            max(abs(offset_x), abs(offset_y)) <= tolerance
            if tolerance is not None
            else None
        )
        return GECTQAPositioningResult(
            available=True,
            passed=passed,
            offset_x_mm=offset_x,
            offset_y_mm=offset_y,
            rotation_deg=self._current_localization.phantom_rotation_deg,
            tolerance_mm=tolerance,
        )

    def _reference_result(self) -> GECTQAReference:
        """Build the public reference values included in every result."""
        water = self.config.ct_number_rois.get("Water")
        first_high = self.config.high_contrast_rois.get("1.6mm")
        scanner_model = self._metadata.manufacturer_model_name or "unknown model"
        if "OPTIMA" in scanner_model.upper():
            scanner_reference_status = (
                f"DICOM model is {scanner_model}; GE phantom references are applied, "
                "with local Optima protocol validation still required."
            )
        else:
            scanner_reference_status = (
                f"DICOM model is {scanner_model}, not explicitly Optima; GE phantom "
                "references are applied without inventing model-specific calibration."
            )
        return GECTQAReference(
            source=self.config.reference_source or "local configuration",
            section1_scan_location_mm=self.config.section1_location_mm,
            section3_scan_location_mm=self.config.section3_location_mm,
            water_nominal_hu=water.nominal_hu if water and water.nominal_hu is not None else 0.0,
            water_tolerance_hu=water.tolerance_hu if water and water.tolerance_hu is not None else 3.0,
            plexiglass_water_difference_hu=(
                self.config.contrast_scale.nominal_difference_hu
                if self.config.contrast_scale
                and self.config.contrast_scale.nominal_difference_hu is not None
                else 120.0
            ),
            plexiglass_water_tolerance_hu=(
                self.config.contrast_scale.tolerance_hu
                if self.config.contrast_scale
                and self.config.contrast_scale.tolerance_hu is not None
                else 12.0
            ),
            noise_nominal_hu=(
                self.config.noise_reference_hu
                if self.config.noise_reference_hu is not None
                else 3.2
            ),
            noise_tolerance_hu=(
                self.config.noise_tolerance_hu
                if self.config.noise_tolerance_hu is not None
                else 0.3
            ),
            uniformity_difference_nominal_hu=(
                self.config.uniformity_reference_hu
                if self.config.uniformity_reference_hu is not None
                else 0.0
            ),
            uniformity_difference_tolerance_hu=(
                self.config.uniformity_tolerance_hu
                if self.config.uniformity_tolerance_hu is not None
                else 3.0
            ),
            high_contrast_1_6mm_std_hu=(
                first_high.reference_std_hu
                if first_high and first_high.reference_std_hu is not None
                else 37.0
            ),
            high_contrast_1_6mm_tolerance_hu=(
                first_high.tolerance_hu
                if first_high and first_high.tolerance_hu is not None
                else 4.0
            ),
            high_contrast_bar_sizes_mm=GE_QA_HIGH_CONTRAST_BAR_SIZES_MM,
            positioning_tolerance_mm=(
                self.config.positioning_tolerance_mm
                if self.config.positioning_tolerance_mm is not None
                else 2.0
            ),
            scanner_reference_status=scanner_reference_status,
        )

    def _analyze_helios_compatibility(self) -> GECTQAHeliosCompatibilityResult:
        """Generate Helios-shaped metrics without identifying the phantom as Helios."""
        if not self.config.use_helios_compatibility:
            return GECTQAHeliosCompatibilityResult(
                available=False,
                reference_source=GE_QA_REFERENCE_SOURCE,
                validity="disabled by configuration",
            )
        section1 = self._module_locations.section1_slice_index
        uniformity = self._module_locations.uniformity_slice_index
        low_contrast = self._module_locations.low_contrast_slice_index
        try:
            contrast_results = {}
            for name, setting in GE_HELIOS_CONTRAST_SCALE_ROI_SETTINGS.items():
                definition = _roi_from_setting(setting)
                contrast_results[name], _ = self._roi_result(
                    name,
                    definition,
                    section1,
                    self.config.section1_location_mm,
                    "Helios contrast scale",
                )
            plastic = contrast_results["Plexiglass"]
            water = contrast_results["Water"]
            contrast_scale = GECTQAHeliosContrastScaleResult(
                slice_index=section1,
                physical_z_mm=float(self.z_positions[section1]),
                roi_settings=contrast_results,
                mean_hu_water=water.mean_hu,
                mean_hu_plastic=plastic.mean_hu,
                hu_difference=plastic.mean_hu - water.mean_hu,
                std_dev_water=water.std_hu,
            )
        except (IndexError, ValueError, KeyError):
            contrast_scale = None

        high_results = {}
        high_settings = GE_HELIOS_HIGH_CONTRAST_ROI_SETTINGS
        high_definitions = self._default_high_contrast_rois()
        try:
            for name, definition in high_definitions.items():
                high_results[name], _ = self._roi_result(
                    name,
                    definition,
                    section1,
                    self.config.section1_location_mm,
                    "Helios high contrast",
                )
            high_rois = [
                self._create_roi(self._image_array(section1), high_definitions[name])
                for name in high_settings
            ]
            mtf = MTF.from_high_contrast_diskset(
                spacings=[1 / (2 * high_settings[name]["bar_size_mm"]) for name in high_settings],
                diskset=high_rois,
            )
            mtf_values = {
                str(percentage): float(mtf.relative_resolution(percentage))
                for percentage in range(10, 100, 10)
            }
            high_contrast = GECTQAHeliosHighContrastResult(
                slice_index=section1,
                physical_z_mm=float(self.z_positions[section1]),
                rois=high_results,
                roi_std_hu={name: result.std_hu for name, result in high_results.items()},
                mtf_lp_mm=mtf_values,
                mtf_50_lp_mm=mtf_values["50"],
            )
        except (IndexError, ValueError, KeyError, TypeError):
            high_contrast = None

        low_slices = {}
        low_slice_indices = [
            max(0, min(self.num_images - 1, low_contrast + offset))
            for offset in (0, -1, -2)
        ]
        try:
            low_means = []
            low_stds = []
            for number, slice_index in enumerate(low_slice_indices, start=1):
                grid = self._grid_statistics(slice_index)
                low_means.append(float(grid["mean"]))
                low_stds.append(float(grid["std"]))
                low_slices[f"slice_{number}"] = GECTQAHeliosLowContrastSliceResult(
                    slice_index=slice_index,
                    physical_z_mm=float(self.z_positions[slice_index]),
                    offset_from_center_slice_mm=float(
                        self.z_positions[slice_index] - self.z_positions[low_contrast]
                    ),
                    mean=float(grid["mean"]),
                    std=float(grid["std"]),
                    min_hu=float(grid["min"]),
                    max_hu=float(grid["max"]),
                )
            low_contrast_result = GECTQAHeliosLowContrastResult(
                slices=low_slices,
                mean=float(np.mean(low_means)),
                std=float(np.mean(low_stds)),
                cell_size_mm=5.0,
                num_cells=15,
            )
        except (IndexError, ValueError, KeyError):
            low_contrast_result = None

        noise_uniformity = None
        try:
            roi_results = {}
            for name, setting in GE_HELIOS_UNIFORMITY_ROI_SETTINGS.items():
                roi_results[name], _ = self._roi_result(
                    name,
                    _roi_from_setting(setting),
                    uniformity,
                    self.config.section3_location_mm,
                    "Helios noise uniformity",
                )
            noise_definition = GECTQAROI(
                x_mm=0,
                y_mm=0,
                width_mm=25,
                height_mm=25,
            )
            noise_roi, _ = self._roi_result(
                "Center",
                noise_definition,
                uniformity,
                self.config.section3_location_mm,
                "Helios noise",
            )
            outer_mean = float(
                np.mean(
                    [
                        roi_results["12 o'clock"].mean_hu,
                        roi_results["3 o'clock"].mean_hu,
                    ]
                )
            )
            noise_uniformity = GECTQAHeliosNoiseUniformityResult(
                slice_index=uniformity,
                physical_z_mm=float(self.z_positions[uniformity]),
                rois=roi_results,
                noise_roi=noise_roi,
                noise_center_std=noise_roi.std_hu,
                mean_outer=outer_mean,
                uniformity_difference=roi_results["Center"].mean_hu - outer_mean,
            )
        except (IndexError, ValueError, KeyError):
            noise_uniformity = None

        return GECTQAHeliosCompatibilityResult(
            available=any(
                value is not None
                for value in (
                    contrast_scale,
                    high_contrast,
                    low_contrast_result,
                    noise_uniformity,
                )
            ),
            reference_source=GE_QA_REFERENCE_SOURCE,
            validity=(
                "GE QA phantom measured with Helios-compatible ROI algorithms; "
                "not a GE Helios phantom result"
            ),
            contrast_scale=contrast_scale,
            high_contrast=high_contrast,
            low_contrast=low_contrast_result,
            noise_uniformity=noise_uniformity,
        )

    def analyze(
        self,
        center_override: tuple[float, float] | None = None,
        angle_override: float | None = None,
        origin_slice: int | None = None,
    ) -> None:
        """Analyze the localized GE phantom and all configured tests.

        Parameters
        ----------
        center_override : tuple of float, optional
            Explicit phantom center as ``(x_px, y_px)`` when automatic
            localization is not suitable.
        angle_override : float, optional
            Phantom rotation in degrees. Positive values follow the image
            convention used by pylinac, with positive y pointing down.
        origin_slice : int, optional
            Slice used as the zero point for configured module offsets.
        """
        self._plot_entries = []
        self._current_localization = self._localize(center_override, angle_override)
        self._module_locations = self._detect_module_locations()
        self.origin_slice = self._find_origin_slice(origin_slice)
        if origin_slice is not None:
            self._module_locations = self._module_locations.model_copy(
                update={
                    "section1_slice_index": self.origin_slice,
                    "section1_physical_z_mm": float(self.z_positions[self.origin_slice]),
                }
            )
        ct_number = self._analyze_ct_number()
        contrast_scale = self._analyze_contrast_scale(ct_number)
        noise = self._analyze_noise()
        uniformity = self._analyze_uniformity()
        high_contrast = self._analyze_high_contrast()
        low_contrast = self._analyze_low_contrast()
        slice_thickness = self._analyze_slice_thickness()
        positioning = self._analyze_positioning()
        self._helios_compatibility = self._analyze_helios_compatibility()
        self._analysis = {
            "ct_number": ct_number,
            "contrast_scale": contrast_scale,
            "noise": noise,
            "uniformity": uniformity,
            "high_contrast_resolution": high_contrast,
            "low_contrast": low_contrast,
            "slice_thickness": slice_thickness,
            "positioning": positioning,
            "alignment": GECTQAAlignmentResult(
                available=False,
                passed=None,
                reason=(
                    "A routine CT DICOM series does not contain external laser or "
                    "light-field markers. Supply a dedicated alignment acquisition."
                ),
            ),
        }
        self._analysis_complete = True

    def _generate_results_data(self) -> GECTQAResult:
        if not self._analysis_complete:
            raise ValueError("The GE CT QA phantom has not been analyzed yet.")
        tests = list(self._analysis.values())
        available_tests = [test for test in tests if test.available]
        passed_tests = [test for test in available_tests if test.passed is True]
        failed_tests = [test for test in available_tests if test.passed is False]
        if failed_tests:
            overall_passed = False
        elif available_tests and len(passed_tests) == len(available_tests):
            overall_passed = True
        else:
            overall_passed = None
        return GECTQAResult(
            phantom_model=self.config.phantom_model,
            reference=self._reference_result(),
            metadata=self._metadata,
            scanner_model=self._metadata.manufacturer_model_name,
            num_images=self.num_images,
            origin_slice=self.origin_slice,
            module_locations=self._module_locations,
            localization=self._current_localization,
            ct_number=self._analysis["ct_number"],
            contrast_scale=self._analysis["contrast_scale"],
            noise=self._analysis["noise"],
            uniformity=self._analysis["uniformity"],
            high_contrast_resolution=self._analysis["high_contrast_resolution"],
            low_contrast=self._analysis["low_contrast"],
            slice_thickness=self._analysis["slice_thickness"],
            positioning=self._analysis["positioning"],
            alignment=self._analysis["alignment"],
            helios_compatibility=self._helios_compatibility,
            overall_passed=overall_passed,
            num_tests=len(available_tests),
            num_passed=len(passed_tests),
            num_failed=len(failed_tests),
            num_warnings=len(self.get_captured_warnings()),
        )

    def results(self) -> str:
        """Return a concise human-readable report."""
        data = self.results_data()
        status = (
            "PASS"
            if data.overall_passed is True
            else "FAIL"
            if data.overall_passed is False
            else "NOT ASSESSED"
        )
        material_lines = [
            f"  {name}: {result.mean_hu:.2f} HU (nominal={result.nominal_hu}, passed={result.passed})"
            for name, result in data.ct_number.rois.items()
        ]
        high_lines = [
            f"  {name}: SD={result.std_hu:.2f} HU (reference={result.reference_std_hu}, passed={result.passed})"
            for name, result in data.high_contrast_resolution.rois.items()
        ]
        lines = [
            "GE CT QA Phantom Analysis",
            "-------------------------",
            f"Phantom: {data.phantom_model}",
            f"Scanner: {data.scanner_model or 'unknown'}",
            f"Reference applicability: {data.reference.scanner_reference_status}",
            f"Images: {data.num_images}",
            f"Matrix/pixel spacing: {data.metadata.rows} x {data.metadata.columns} / {data.metadata.pixel_spacing_mm} mm",
            f"Acquisition: {data.metadata.kvp} kVp, {data.metadata.tube_current_ma} mA, kernel={data.metadata.convolution_kernel}",
            f"Phantom diameter: {data.localization.phantom_diameter_mm:.1f} mm",
            f"Phantom rotation: {data.localization.phantom_rotation_deg:.2f} deg",
            f"Module slices: Section 1={data.module_locations.section1_slice_index} (z={data.module_locations.section1_physical_z_mm:.1f}), uniformity={data.module_locations.uniformity_slice_index} (z={data.module_locations.uniformity_physical_z_mm:.1f}), low contrast={data.module_locations.low_contrast_slice_index} (z={data.module_locations.low_contrast_physical_z_mm:.1f})",
            "",
            "CT Number Accuracy",
            *material_lines,
            f"  Passed: {data.ct_number.passed}",
            "Contrast Scale",
            f"  Plexiglass - water: {data.contrast_scale.contrast_scale:.2f} HU (reference={data.reference.plexiglass_water_difference_hu:.1f} +/- {data.reference.plexiglass_water_tolerance_hu:.1f}; passed={data.contrast_scale.passed})"
            if data.contrast_scale.contrast_scale is not None
            else "  unavailable",
            "Noise and Uniformity",
            f"  Noise: {data.noise.noise_hu:.2f} HU (reference={data.reference.noise_nominal_hu:.1f} +/- {data.reference.noise_tolerance_hu:.1f}; passed={data.noise.passed})"
            if data.noise.noise_hu is not None
            else "  unavailable",
            f"  Uniformity max deviation: {data.uniformity.max_deviation_from_center_hu:.2f} HU (limit={data.reference.uniformity_difference_tolerance_hu:.1f}; passed={data.uniformity.passed})"
            if data.uniformity.max_deviation_from_center_hu is not None
            else "  unavailable",
            "High Contrast Spatial Resolution",
            *high_lines,
            f"  Relative MTF 50%: {data.high_contrast_resolution.mtf.get('50'):.3f} lp/mm"
            if data.high_contrast_resolution.mtf
            and data.high_contrast_resolution.mtf.get("50") is not None
            else "  Relative MTF: unavailable",
            f"  Reference check passed: {data.high_contrast_resolution.passed}",
            "Low Contrast Detectability",
            f"  15 x 15 grid: mean={data.low_contrast.grid_mean_hu:.2f} HU, SD={data.low_contrast.grid_std_hu:.2f} HU, range={data.low_contrast.grid_min_hu:.2f} to {data.low_contrast.grid_max_hu:.2f} HU"
            if data.low_contrast.grid_mean_hu is not None
            else "  unavailable",
            "  Visual observer score: not automated",
            "Slice Thickness",
            f"  DICOM acquired SliceThickness: {data.slice_thickness.acquired_slice_thickness_mm} mm",
            f"  Phantom measurement: {data.slice_thickness.measured_slice_thickness_mm if data.slice_thickness.available else 'not available'}",
            "Positioning and Alignment",
            f"  Image offset: x={data.positioning.offset_x_mm:.2f} mm, y={data.positioning.offset_y_mm:.2f} mm; passed={data.positioning.passed}",
            f"  External laser/light-field: {data.alignment.reason}",
            "Helios-compatible comparison",
            f"  Relative MTF 50%: {data.helios_compatibility.high_contrast.mtf_50_lp_mm:.3f} lp/mm"
            if data.helios_compatibility
            and data.helios_compatibility.high_contrast
            else "  unavailable",
            f"  Low-contrast grid mean/SD: {data.helios_compatibility.low_contrast.mean:.2f} / {data.helios_compatibility.low_contrast.std:.2f} HU"
            if data.helios_compatibility
            and data.helios_compatibility.low_contrast
            else "  unavailable",
            f"  Validity: {data.helios_compatibility.validity}"
            if data.helios_compatibility
            else "  unavailable",
            "",
            f"Tests: {data.num_passed} passed, {data.num_failed} failed, {data.num_tests} assessed; warnings={data.num_warnings}",
            f"Overall: {status}",
        ]
        return "\n".join(lines)

    def _plot_axial(self, axis: plt.Axes, slice_index: int) -> None:
        image_array = np.asarray(self.dicom_stack[slice_index].array)
        axis.imshow(image_array, cmap="gray", vmin=-1000, vmax=1000)
        axis.set_title(f"Axial slice {slice_index}")
        radius_px = self._current_localization.phantom_radius_mm / np.mean(self.pixel_spacing)
        boundary = Circle(
            (
                self._current_localization.phantom_center_x_px,
                self._current_localization.phantom_center_y_px,
            ),
            radius_px,
            fill=False,
            color="yellow",
            linewidth=1.5,
        )
        axis.add_patch(boundary)
        axis.scatter(
            [self._current_localization.phantom_center_x_px],
            [self._current_localization.phantom_center_y_px],
            color="red",
            marker="+",
        )
        for entry_slice, roi, label in self._plot_entries:
            if entry_slice != slice_index:
                continue
            roi.plot2axes(axis, edgecolor="cyan")
            axis.text(roi.center.x, roi.center.y, label, color="white", fontsize=7)

    def _plot_side(self, axis: plt.Axes) -> None:
        side_array = self.dicom_stack.side_view(axis=1)
        axis.imshow(side_array, aspect="auto", cmap="gray", vmin=-1000, vmax=1000)
        axis.axvline(self.origin_slice, color="red")
        for entry_slice, _, label in self._plot_entries:
            axis.axvline(entry_slice, color="cyan", alpha=0.35)
            axis.text(entry_slice, 0, label, rotation=90, color="white", fontsize=7)
        axis.set_title("Series side view")
        axis.set_yticks([])

    def _plot_mtf(self, axis: plt.Axes) -> None:
        compatibility = self.results_data().helios_compatibility
        if compatibility is None or compatibility.high_contrast is None:
            axis.text(0.5, 0.5, "Relative MTF unavailable", ha="center", va="center")
            axis.set_axis_off()
            return
        mtf_values = compatibility.high_contrast.mtf_lp_mm
        if not mtf_values:
            axis.text(0.5, 0.5, "Relative MTF unavailable", ha="center", va="center")
            axis.set_axis_off()
            return
        percentages = [int(value) for value in mtf_values]
        axis.plot(percentages, [mtf_values[str(value)] for value in percentages], marker="o")
        axis.set_title("Relative MTF")
        axis.set_xlabel("MTF (%)")
        axis.set_ylabel("lp/mm")
        axis.grid(alpha=0.25)

    def plot_analyzed_image(self, show: bool = True, **plt_kwargs) -> plt.Figure:
        """Plot all automatically detected GE modules and configured ROIs."""
        if not self._analysis_complete:
            raise ValueError("The GE CT QA phantom has not been analyzed yet.")
        figure, axes = plt.subplots(2, 3, **plt_kwargs)
        self._plot_axial(axes[0, 0], self.module_locations.section1_slice_index)
        axes[0, 0].set_title("Section 1: contrast / resolution")
        self._plot_axial(axes[0, 1], self.module_locations.uniformity_slice_index)
        axes[0, 1].set_title("Section 3: noise / uniformity")
        self._plot_axial(axes[0, 2], self.module_locations.low_contrast_slice_index)
        axes[0, 2].set_title("Section 3: low contrast")
        self._plot_side(axes[1, 0])
        self._plot_mtf(axes[1, 1])
        axes[1, 2].axis("off")
        figure.tight_layout()
        if show:
            plt.show()
        return figure

    def plot_images(self, show: bool = True, **plt_kwargs) -> dict[str, plt.Figure]:
        """Return individual module, side-view, and MTF figures."""
        if not self._analysis_complete:
            raise ValueError("The GE CT QA phantom has not been analyzed yet.")
        section1, section1_axis = plt.subplots(**plt_kwargs)
        self._plot_axial(section1_axis, self.module_locations.section1_slice_index)
        section1_axis.set_title("Section 1: contrast / resolution")
        uniformity, uniformity_axis = plt.subplots(**plt_kwargs)
        self._plot_axial(uniformity_axis, self.module_locations.uniformity_slice_index)
        uniformity_axis.set_title("Section 3: noise / uniformity")
        low_contrast, low_contrast_axis = plt.subplots(**plt_kwargs)
        self._plot_axial(low_contrast_axis, self.module_locations.low_contrast_slice_index)
        low_contrast_axis.set_title("Section 3: low contrast")
        side, side_axis = plt.subplots(**plt_kwargs)
        self._plot_side(side_axis)
        mtf, mtf_axis = plt.subplots(**plt_kwargs)
        self._plot_mtf(mtf_axis)
        figures = {
            "section1": section1,
            "uniformity": uniformity,
            "low_contrast": low_contrast,
            "side": side,
            "mtf": mtf,
        }
        if show:
            plt.show()
        return figures

    def plotly_analyzed_images(
        self,
        show: bool = True,
        show_colorbar: bool = True,
        show_legend: bool = True,
        **kwargs,
    ) -> dict[str, go.Figure]:
        """Return Plotly module, side-view, and relative-MTF figures."""
        if not self._analysis_complete:
            raise ValueError("The GE CT QA phantom has not been analyzed yet.")

        def axial_figure(slice_index: int, title: str) -> go.Figure:
            figure = go.Figure(
                go.Heatmap(
                    z=np.asarray(self.dicom_stack[slice_index].array),
                    colorscale="gray",
                    zmin=-1000,
                    zmax=1000,
                    showscale=show_colorbar,
                )
            )
            figure.add_trace(
                go.Scatter(
                    x=[self._current_localization.phantom_center_x_px],
                    y=[self._current_localization.phantom_center_y_px],
                    mode="markers",
                    name="Phantom center",
                    marker={"color": "red", "symbol": "cross"},
                )
            )
            figure.update_layout(showlegend=show_legend, title=title)
            return figure

        section1 = axial_figure(
            self.module_locations.section1_slice_index,
            "Section 1: contrast / resolution",
        )
        uniformity = axial_figure(
            self.module_locations.uniformity_slice_index,
            "Section 3: noise / uniformity",
        )
        low_contrast = axial_figure(
            self.module_locations.low_contrast_slice_index,
            "Section 3: low contrast",
        )
        side = go.Figure(
            go.Heatmap(
                z=self.dicom_stack.side_view(axis=1),
                colorscale="gray",
                showscale=show_colorbar,
                **kwargs,
            )
        )
        side.update_layout(showlegend=show_legend, title="GE CT QA side view")
        mtf = go.Figure()
        compatibility = self.results_data().helios_compatibility
        if compatibility and compatibility.high_contrast and compatibility.high_contrast.mtf_lp_mm:
            values = compatibility.high_contrast.mtf_lp_mm
            mtf.add_scatter(
                x=[int(value) for value in values],
                y=[values[value] for value in values],
                mode="lines+markers",
                name="Relative MTF",
            )
        mtf.update_layout(showlegend=show_legend, title="Relative MTF", xaxis_title="MTF (%)", yaxis_title="lp/mm")
        figures = {
            "Section 1": section1,
            "Uniformity": uniformity,
            "Low Contrast": low_contrast,
            "Side View": side,
            "MTF": mtf,
        }
        if show:
            for figure in figures.values():
                figure.show()
        return figures

    def save_images(
        self,
        directory: Path | str | None = None,
        to_stream: bool = False,
        **plt_kwargs,
    ) -> list[Path | BytesIO]:
        """Save the axial and side-view plots to disk or streams."""
        figures = self.plot_images(show=False, **plt_kwargs)
        outputs: list[Path | BytesIO] = []
        for name, figure in figures.items():
            if to_stream:
                output: Path | BytesIO = io.BytesIO()
            else:
                destination = Path(directory) if directory is not None else Path.cwd()
                destination.mkdir(parents=True, exist_ok=True)
                output = (destination / name).with_suffix(".png").absolute()
            figure.savefig(output)
            outputs.append(output)
        return outputs

    def save_analyzed_image(self, filename: str | Path | BinaryIO, **kwargs) -> None:
        """Save the combined analyzed-image figure."""
        figure = self.plot_analyzed_image(show=False)
        figure.savefig(filename, **kwargs)

    def publish_pdf(
        self,
        filename: str | Path,
        notes: str | None = None,
        open_file: bool = False,
        metadata: dict | None = None,
        logo: Path | str | None = None,
    ) -> None:
        """Publish a PDF containing structured results and analysis plots."""
        analysis_images = self.save_images(to_stream=True)
        canvas = pdf.PylinacCanvas(
            str(filename),
            page_title=f"{self._model} Analysis",
            metadata=metadata,
            logo=logo,
        )
        if notes is not None:
            canvas.add_text(text="Notes:", location=(1, 4.5), font_size=14)
            canvas.add_text(text=notes, location=(1, 4))
        for index, line in enumerate(textwrap.wrap(self.results(), width=110)):
            canvas.add_text(text=line, location=(2.5, 24 - index * 0.5))
        for image in analysis_images:
            canvas.add_new_page()
            canvas.add_image(image, location=(1, 5), dimensions=(18, 18))
        canvas.finish()
        if open_file:
            webbrowser.open(str(filename))

    def _quaac_datapoints(self) -> dict[str, QuaacDatum]:
        """Return stable scalar values for QuAAC and external QA systems."""
        data = self.results_data()
        datapoints: dict[str, QuaacDatum] = {
            "Phantom diameter": QuaacDatum(
                value=data.localization.phantom_diameter_mm, unit="mm"
            ),
            "Phantom rotation": QuaacDatum(
                value=data.localization.phantom_rotation_deg, unit="degrees"
            ),
            "Positioning X offset": QuaacDatum(
                value=data.positioning.offset_x_mm, unit="mm"
            ),
            "Positioning Y offset": QuaacDatum(
                value=data.positioning.offset_y_mm, unit="mm"
            ),
        }
        if data.noise.noise_hu is not None:
            datapoints["Noise"] = QuaacDatum(value=data.noise.noise_hu, unit="HU")
        if data.uniformity.max_deviation_from_center_hu is not None:
            datapoints["Uniformity max deviation"] = QuaacDatum(
                value=data.uniformity.max_deviation_from_center_hu, unit="HU"
            )
        if data.high_contrast_resolution.resolution_lp_mm is not None:
            datapoints["High contrast resolution"] = QuaacDatum(
                value=data.high_contrast_resolution.resolution_lp_mm, unit="lp/mm"
            )
        if data.slice_thickness.measured_slice_thickness_mm is not None:
            datapoints["Measured slice thickness"] = QuaacDatum(
                value=data.slice_thickness.measured_slice_thickness_mm, unit="mm"
            )
        return datapoints
