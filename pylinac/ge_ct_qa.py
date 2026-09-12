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
from .core.roi import DiskROI, RectangleROI
from .core.utilities import QuaacDatum, QuaacMixin, ResultBase, ResultsDataMixin
from .core.warnings import capture_warnings


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
    expected_diameter_range_mm: tuple[float, float] = (200.0, 215.0)
    ct_number_offset_mm: float = 0
    ct_number_rois: dict[str, GECTQAMaterialROI] = Field(default_factory=dict)
    contrast_scale: GECTQAContrastScaleConfig | None = None
    noise_offset_mm: float = 0
    noise_roi: GECTQAROI | None = None
    noise_tolerance_hu: float | None = None
    uniformity_offset_mm: float = 0
    uniformity_rois: dict[str, GECTQAROI] = Field(default_factory=dict)
    uniformity_center_name: str = "center"
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


class GECTQAUniformityResult(GECTQATestResult):
    """Results for configured uniformity ROIs."""

    rois: dict[str, GECTQAROIResult] = Field(default_factory=dict)
    center_roi_name: str | None = None
    max_deviation_from_center_hu: float | None = None
    max_pairwise_difference_hu: float | None = None
    uniformity_index: float | None = None
    integral_uniformity: float | None = None


class GECTQAHighContrastROIResult(GECTQAROIResult):
    """Measured statistics for one configured high-contrast region."""

    spatial_frequency_lp_mm: float
    visibility_score_hu: float
    visibility_threshold_hu: float | None
    resolved: bool | None


class GECTQAHighContrastResult(GECTQATestResult):
    """Results for configured high-contrast line-pair samples."""

    rois: dict[str, GECTQAHighContrastROIResult] = Field(default_factory=dict)
    resolved_group: str | None = None
    resolution_lp_mm: float | None = None
    resolution_lp_cm: float | None = None
    mtf: dict[str, float] | None = None


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
    metadata: GECTQAMetadata
    scanner_model: str | None
    num_images: int
    origin_slice: int
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
        self.config = GECTQAConfig.model_validate(config or {})
        self.dicom_stack = self._load_stack(folderpath, is_zip=is_zip)
        self._validate_stack()
        self._metadata = self._build_metadata()
        self._analysis_complete = False
        self._plot_entries: list[tuple[int, object, str]] = []

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

    def _find_origin_slice(self, requested: int | None) -> int:
        if requested is not None:
            if not 0 <= requested < self.num_images:
                raise ValueError("origin_slice is outside the loaded CT series.")
            return int(requested)
        if self.num_images == 1:
            return 0
        return self._localization_slice_indices[len(self._localization_slice_indices) // 2]

    def _module_slice(self, offset_mm: float) -> int | None:
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
    def _unavailable(result_type, reason: str):
        return result_type(available=False, passed=None, reason=reason)

    def _analyze_ct_number(self) -> GECTQACTNumberResult:
        if not self.config.ct_number_rois:
            return self._unavailable(
                GECTQACTNumberResult,
                "Required GE CT-number ROI geometry and nominal values were not supplied.",
            )
        slice_index = self._module_slice(self.config.ct_number_offset_mm)
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
        slice_index = self._module_slice(self.config.noise_offset_mm)
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
        passed = (
            roi_result.std_hu <= self.config.noise_tolerance_hu
            if self.config.noise_tolerance_hu is not None
            else None
        )
        return GECTQANoiseResult(
            available=True,
            passed=passed,
            roi=roi_result,
            noise_hu=roi_result.std_hu,
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
        slice_index = self._module_slice(self.config.uniformity_offset_mm)
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
        passed = (
            max_deviation <= self.config.uniformity_tolerance_hu
            if self.config.uniformity_tolerance_hu is not None
            else None
        )
        return GECTQAUniformityResult(
            available=True,
            passed=passed,
            rois=roi_results,
            center_roi_name=self.config.uniformity_center_name,
            max_deviation_from_center_hu=max_deviation,
            max_pairwise_difference_hu=max_pairwise,
        )

    def _analyze_high_contrast(self) -> GECTQAHighContrastResult:
        if not self.config.high_contrast_rois:
            return self._unavailable(
                GECTQAHighContrastResult,
                "Required GE high-contrast ROI geometry and line-pair definition were not supplied.",
            )
        slice_index = self._module_slice(self.config.high_contrast_offset_mm)
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
                roi_results[name] = GECTQAHighContrastROIResult(
                    **base_result.model_dump(),
                    spatial_frequency_lp_mm=definition.spatial_frequency_lp_mm,
                    visibility_score_hu=base_result.std_hu,
                    visibility_threshold_hu=threshold,
                    resolved=resolved,
                )
        except ValueError as exc:
            return self._unavailable(GECTQAHighContrastResult, str(exc))
        resolved_rois = [result for result in roi_results.values() if result.resolved]
        best = max(resolved_rois, key=lambda result: result.spatial_frequency_lp_mm, default=None)
        resolution = best.spatial_frequency_lp_mm if best is not None else None
        passed = None
        if self.config.minimum_resolution_lp_mm is not None:
            if resolution is not None:
                passed = resolution >= self.config.minimum_resolution_lp_mm
        return GECTQAHighContrastResult(
            available=True,
            passed=passed,
            rois=roi_results,
            resolved_group=best.name if best is not None else None,
            resolution_lp_mm=resolution,
            resolution_lp_cm=resolution * 10 if resolution is not None else None,
            mtf=None,
        )

    def _analyze_low_contrast(self) -> GECTQALowContrastResult:
        definition = self.config.low_contrast
        if definition is None or not definition.targets:
            return self._unavailable(
                GECTQALowContrastResult,
                "Required GE low-contrast target geometry and scoring rule were not supplied.",
            )
        slice_index = self._module_slice(self.config.low_contrast_offset_mm)
        try:
            background, _ = self._roi_result(
                "background",
                definition.background,
                slice_index,
                self.config.low_contrast_offset_mm,
                "Low contrast",
            )
            roi_results: dict[str, GECTQALowContrastROIResult] = {}
            for name, target_definition in definition.targets.items():
                target, _ = self._roi_result(
                    name,
                    target_definition,
                    slice_index,
                    self.config.low_contrast_offset_mm,
                    "Low contrast",
                )
                contrast = abs(target.mean_hu - background.mean_hu)
                denominator = np.sqrt((target.std_hu**2 + background.std_hu**2) / 2)
                cnr = float(contrast / denominator) if denominator > 0 else None
                visible = cnr >= definition.cnr_threshold if cnr is not None and definition.cnr_threshold is not None else None
                roi_results[name] = GECTQALowContrastROIResult(
                    **target.model_dump(),
                    target_size_mm=target_definition.target_size_mm,
                    target_mean_hu=target.mean_hu,
                    target_std_hu=target.std_hu,
                    background_mean_hu=background.mean_hu,
                    background_std_hu=background.std_hu,
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
            background=background,
            rois=roi_results,
            cnr_threshold=definition.cnr_threshold,
            num_rois_detected=len(roi_results),
            num_rois_visible=visible_count,
            minimum_visible_contrast_hu=min(contrasts) if contrasts else None,
            best_cnr=max(cnrs) if cnrs else None,
            worst_cnr=min(cnrs) if cnrs else None,
        )

    def _analyze_slice_thickness(self) -> GECTQASliceThicknessResult:
        definition = self.config.slice_thickness
        if definition is None:
            return self._unavailable(
                GECTQASliceThicknessResult,
                "Required GE slice-thickness insert geometry and calibration were not supplied.",
            )
        if self.num_images < 3 or self.slice_spacing_mm is None:
            return self._unavailable(
                GECTQASliceThicknessResult,
                "At least three CT slices with usable z spacing are required for slice-thickness analysis.",
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
            return self._unavailable(GECTQASliceThicknessResult, str(exc))
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
        self.origin_slice = self._find_origin_slice(origin_slice)
        ct_number = self._analyze_ct_number()
        contrast_scale = self._analyze_contrast_scale(ct_number)
        noise = self._analyze_noise()
        uniformity = self._analyze_uniformity()
        high_contrast = self._analyze_high_contrast()
        low_contrast = self._analyze_low_contrast()
        slice_thickness = self._analyze_slice_thickness()
        positioning = self._analyze_positioning()
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
            metadata=self._metadata,
            scanner_model=self._metadata.manufacturer_model_name,
            num_images=self.num_images,
            origin_slice=self.origin_slice,
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
            overall_passed=overall_passed,
            num_tests=len(available_tests),
            num_passed=len(passed_tests),
            num_failed=len(failed_tests),
            num_warnings=len(self.get_captured_warnings()),
        )

    def results(self) -> str:
        """Return a concise human-readable report."""
        data = self.results_data()
        status = "PASS" if data.overall_passed is True else "FAIL" if data.overall_passed is False else "NOT ASSESSED"
        lines = [
            "GE CT QA Phantom Analysis",
            "-------------------------",
            f"Phantom: {data.phantom_model}",
            f"Images: {data.num_images}",
            f"Phantom diameter: {data.localization.phantom_diameter_mm:.1f} mm",
            f"Phantom rotation: {data.localization.phantom_rotation_deg:.2f} deg",
            f"Positioning: ({data.positioning.offset_x_mm:.2f}, {data.positioning.offset_y_mm:.2f}) mm; passed={data.positioning.passed}",
            f"CT number: {data.ct_number.passed if data.ct_number.available else 'unavailable'}",
            f"Contrast scale: {data.contrast_scale.contrast_scale if data.contrast_scale.available else 'unavailable'}",
            f"Noise: {data.noise.noise_hu if data.noise.available else 'unavailable'} HU",
            f"Uniformity: {data.uniformity.max_deviation_from_center_hu if data.uniformity.available else 'unavailable'} HU max deviation",
            f"High contrast: {data.high_contrast_resolution.resolution_lp_mm if data.high_contrast_resolution.available else 'unavailable'} lp/mm",
            f"Low contrast: {data.low_contrast.num_rois_visible}/{data.low_contrast.num_rois_detected} visible" if data.low_contrast.available else "Low contrast: unavailable",
            f"Slice thickness: {data.slice_thickness.measured_slice_thickness_mm if data.slice_thickness.available else 'unavailable'} mm",
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

    def plot_analyzed_image(self, show: bool = True, **plt_kwargs) -> plt.Figure:
        """Plot the localized phantom and configured ROIs."""
        if not self._analysis_complete:
            raise ValueError("The GE CT QA phantom has not been analyzed yet.")
        figure, axes = plt.subplots(1, 2, **plt_kwargs)
        self._plot_axial(axes[0], self.origin_slice)
        self._plot_side(axes[1])
        figure.tight_layout()
        if show:
            plt.show()
        return figure

    def plot_images(self, show: bool = True, **plt_kwargs) -> dict[str, plt.Figure]:
        """Return individual axial and side-view figures."""
        if not self._analysis_complete:
            raise ValueError("The GE CT QA phantom has not been analyzed yet.")
        axial, axial_axis = plt.subplots(**plt_kwargs)
        self._plot_axial(axial_axis, self.origin_slice)
        side, side_axis = plt.subplots(**plt_kwargs)
        self._plot_side(side_axis)
        figures = {"localization": axial, "side": side}
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
        """Return Plotly axial and side-view figures."""
        if not self._analysis_complete:
            raise ValueError("The GE CT QA phantom has not been analyzed yet.")
        image_array = np.asarray(self.dicom_stack[self.origin_slice].array)
        axial = go.Figure(
            go.Heatmap(
                z=image_array,
                colorscale="gray",
                zmin=-1000,
                zmax=1000,
                showscale=show_colorbar,
            )
        )
        axial.add_trace(
            go.Scatter(
                x=[self._current_localization.phantom_center_x_px],
                y=[self._current_localization.phantom_center_y_px],
                mode="markers",
                name="Phantom center",
                marker={"color": "red", "symbol": "cross"},
            )
        )
        side = go.Figure(
            go.Heatmap(
                z=self.dicom_stack.side_view(axis=1),
                colorscale="gray",
                showscale=show_colorbar,
                **kwargs,
            )
        )
        axial.update_layout(showlegend=show_legend, title="GE CT QA localization")
        side.update_layout(showlegend=show_legend, title="GE CT QA side view")
        figures = {"Localization": axial, "Side View": side}
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
            filename,
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
