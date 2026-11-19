from __future__ import annotations

import io
import math
import textwrap
import warnings
import webbrowser
from collections.abc import Mapping
from io import BytesIO
from itertools import combinations
from pathlib import Path
from textwrap import wrap

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.patches import Ellipse
from plotly import graph_objects as go
from pydicom.dataset import Dataset
from pydantic import BaseModel, ConfigDict, Field
from scipy import ndimage
from skimage import draw, measure
from skimage.filters import threshold_li, threshold_otsu

from ._acr_467_report import _json_report, _report_figures, _write_report
from .core import pdf
from .core.array_utils import fill_middle_zeros, find_nearest_idx
from .core.contrast import Contrast
from .core.geometry import Line, LineSerialized, Point
from .core.image import DicomImage, DicomImageStack
from .core.mtf import MTF, format_resolution
from .core.plotly_utils import add_title
from .core.profile import FWXMProfile
from .core.roi import DiskROI, HighContrastDiskROI, LowContrastDiskROI, RectangleROI
from .core.utilities import QuaacDatum, ResultBase, ResultsDataMixin
from .core.warnings import capture_warnings
from .ct import (
    CatPhanBase,
    CatPhanModule,
    Slice,
    ThicknessROI,
    get_regions,
    rois_to_results,
)

# CT
CT_UNIFORMITY_MODULE_OFFSET_MM = 70
CT_SPATIAL_RESOLUTION_MODULE_OFFSET_MM = 100
CT_LOW_CONTRAST_MODULE_OFFSET_MM = 30

# MR
MR_SLICE11_MODULE_OFFSET_MM = 100
MR_GEOMETRIC_DISTORTION_MODULE_OFFSET_MM = 40
MR_UNIFORMITY_MODULE_OFFSET_MM = 60
MR_LOW_CONTRAST_MODULE_OFFSETS_MM = {8: 70, 9: 80, 10: 90, 11: 100}


class CTModule(CatPhanModule):
    common_name = "HU Linearity"
    attr_name = "ct_calibration_module"
    roi_dist_mm = 63
    roi_radius_mm = 10
    roi_settings = {
        "Air": {"angle": 45, "distance": roi_dist_mm, "radius": roi_radius_mm},
        "Poly": {"angle": 225, "distance": roi_dist_mm, "radius": roi_radius_mm},
        "Acrylic": {"angle": 135, "distance": roi_dist_mm, "radius": roi_radius_mm},
        "Bone": {"angle": -45, "distance": roi_dist_mm, "radius": roi_radius_mm},
        "Water": {"angle": 180, "distance": roi_dist_mm, "radius": roi_radius_mm},
    }
    window_min = -200
    window_max = 200


class CTModuleOutput(BaseModel):
    """This class should not be called directly. It is returned by the ``results_data()`` method.

    Use the following attributes as normal class attributes."""

    offset: float = Field(
        description="The offset of the module slice in mm from the origin slice (z-direction)."
    )
    roi_distance_from_center_mm: float = Field(
        description="The distance of the ROIs from the center of the phantom in mm in the image plane."
    )
    roi_radius_mm: float = Field(description="The radius of the ROIs in mm.")
    roi_settings: dict = Field(
        description="The ROI settings. The keys are the material names."
    )
    rois: dict[str, float] = Field(
        description="The analyzed ROIs. The key is the name of the material and the value is the mean HU value. E.g. ``'Air': -987.1``."
    )


class UniformityModule(CatPhanModule):
    """Analyze HU uniformity and BB distance on the ACR CT uniformity slice.

    Five fixed ROIs measure HU uniformity. Two additional roll-corrected search
    ROIs locate the nominally 100 mm-separated BBs and measure image scaling.
    """

    attr_name = "uniformity_module"
    common_name = "HU Uniformity"
    roi_dist_mm = 66
    roi_radius_mm = 11
    roi_settings = {
        "Top": {"angle": -90, "distance": roi_dist_mm, "radius": roi_radius_mm},
        "Right": {"angle": 0, "distance": roi_dist_mm, "radius": roi_radius_mm},
        "Bottom": {"angle": 90, "distance": roi_dist_mm, "radius": roi_radius_mm},
        "Left": {"angle": 180, "distance": roi_dist_mm, "radius": roi_radius_mm},
        "Center": {"angle": 0, "distance": 0, "radius": roi_radius_mm},
    }
    bb_roi_settings = {
        "BB 1": {"angle": -45, "distance": 20, "radius": 5},
        "BB 2": {"angle": 135, "distance": 80, "radius": 5},
    }
    bb_nominal_distance_mm = 100
    window_min = -50
    window_max = 50

    def _setup_rois(self) -> None:
        """In addition to the 5 uniformity ROIs,
        we will also find the 2 BB ROIs to determine scaling/distance."""
        super()._setup_rois()
        self.bb_rois: dict[str, DiskROI] = {}
        self.bb_centers: dict[str, Point] = {}

        for name, setting in self.bb_roi_settings.items():
            roi = DiskROI.from_phantom_center(
                self.image,
                setting["angle_corrected"],
                setting["radius_pixels"],
                setting["distance_pixels"],
                self.phan_center,
            )
            self.bb_rois[name] = roi
            self.bb_centers[name] = self._find_bb_centroid(roi=roi)

    def _find_bb_centroid(
        self,
        roi: DiskROI,
    ) -> Point:
        """Find a BB's weighted centroid within its fixed search ROI."""
        array = np.asarray(self.image.array)
        rr, cc = draw.disk(
            center=(roi.center.y, roi.center.x),
            radius=roi.radius,
            shape=array.shape,
        )
        roi_values = array[rr, cc]
        threshold = (float(np.min(roi_values)) + float(np.max(roi_values))) / 2

        thresholded = np.zeros(array.shape, dtype=bool)
        thresholded[rr, cc] = roi_values >= threshold
        labeled = measure.label(thresholded, connectivity=2)
        strongest_pixel = np.unravel_index(
            np.argmax(np.where(thresholded, array, -np.inf)), array.shape
        )
        strongest_label = labeled[strongest_pixel]
        component_y, component_x = np.nonzero(labeled == strongest_label)
        weights = array[component_y, component_x] - threshold
        return Point(
            x=float(np.average(component_x, weights=weights)),
            y=float(np.average(component_y, weights=weights)),
        )

    @property
    def bb_distance_mm(self) -> float:
        """The measured distance between the two BBs in millimeters."""
        bb_1, bb_2 = self.bb_centers.values()
        return bb_1.distance_to(bb_2) * float(self.mm_per_pixel)

    @property
    def scaling_error_percent(self) -> float:
        """The absolute BB distance scaling error in percent."""
        return (
            abs(self.bb_distance_mm - self.bb_nominal_distance_mm)
            / self.bb_nominal_distance_mm
            * 100
        )

    @property
    def measured_pixel_size(self) -> float:
        """The pixel size (mm/pixel) derived from the nominal BB separation."""
        distance_pixels = self.bb_distance_mm / float(self.mm_per_pixel)
        return self.bb_nominal_distance_mm / distance_pixels

    def plot_rois(self, axis: plt.Axes) -> None:
        """Plot uniformity and BB search ROIs to the axis."""
        super().plot_rois(axis)
        for name, roi in self.bb_rois.items():
            point = self.bb_centers[name]
            # BB ROI
            roi.plot2axes(
                axis,
                edgecolor="green",
                label_position="upper center",
            )
            # BB point
            axis.plot(point.x, point.y, marker="+", color="green")

    def plotly_rois(self, fig: go.Figure) -> None:
        """Plot uniformity and BB search ROIs to the Plotly figure."""
        super().plotly_rois(fig)
        for name, roi in self.bb_rois.items():
            point = self.bb_centers[name]
            # BB ROI
            roi.plotly(
                fig,
                line_color="green",
                label_position="upper center",
                name=f"{name} Search ROI",
            )
            # BB itself
            fig.add_scatter(
                x=[point.x],
                y=[point.y],
                mode="markers",
                marker={"color": "green", "symbol": "cross"},
                name=f"{name} Center",
            )


class UniformityModuleOutput(CTModuleOutput):
    """This class should not be called directly. It is returned by the ``results_data()`` method.

    Use the following attributes as normal class attributes."""

    center_roi_stdev: float = Field(
        description="The standard deviation of the center ROI.",
        title="Center ROI Standard Deviation",
    )
    bb_distance_mm: float = Field(
        description="The measured distance between the two uniformity BBs in millimeters.",
        title="BB Distance (mm)",
    )
    scaling_error_percent: float = Field(
        description="The absolute scaling error of the measured BB distance in percent.",
        title="Scaling Error (%)",
    )
    measured_pixel_size: float = Field(
        description="The pixel size derived from the nominal 100 mm BB separation and distance in pixels.",
        title="Measured Pixel Size (mm/pixel)",
    )


class SpatialResolutionModule(CatPhanModule):
    """Class for analysis of the Uniformity slice of the CTP module. Measures 5 ROIs around the slice that
    should all be close to the same value.
    """

    attr_name = "spatial_resolution_module"
    common_name = "Spatial Resolution"
    rois: dict[str, HighContrastDiskROI]
    roi_dist_mm = 70
    roi_radius_mm = 6
    roi_settings = {
        "10oclock": {
            "angle": -135,
            "distance": roi_dist_mm,
            "radius": roi_radius_mm,
            "lp/mm": 0.4,
        },
        "9oclock": {
            "angle": -180,
            "distance": roi_dist_mm,
            "radius": roi_radius_mm,
            "lp/mm": 0.5,
        },
        "7oclock": {
            "angle": 135,
            "distance": roi_dist_mm,
            "radius": roi_radius_mm,
            "lp/mm": 0.6,
        },
        "6oclock": {
            "angle": 90,
            "distance": roi_dist_mm,
            "radius": roi_radius_mm,
            "lp/mm": 0.7,
        },
        "4oclock": {
            "angle": 45,
            "distance": roi_dist_mm,
            "radius": roi_radius_mm,
            "lp/mm": 0.8,
        },
        "3oclock": {
            "angle": 0,
            "distance": roi_dist_mm,
            "radius": roi_radius_mm,
            "lp/mm": 0.9,
        },
        "2oclock": {
            "angle": -45,
            "distance": roi_dist_mm,
            "radius": roi_radius_mm,
            "lp/mm": 1.0,
        },
        "12oclock": {
            "angle": -90,
            "distance": roi_dist_mm,
            "radius": roi_radius_mm,
            "lp/mm": 1.2,
        },
    }

    def _setup_rois(self) -> None:
        for name, setting in self.roi_settings.items():
            self.rois[name] = HighContrastDiskROI.from_phantom_center(
                self.image,
                setting["angle_corrected"],
                setting["radius_pixels"],
                setting["distance_pixels"],
                self.phan_center,
                contrast_threshold=1.0,  # fixed to 1 so everything passes. We aren't evaluating pass/fail here
            )

    @property
    def mtf(self) -> MTF:
        spacings = [roi["lp/mm"] for roi in self.roi_settings.values()]
        return MTF.from_high_contrast_diskset(
            spacings=spacings, diskset=list(self.rois.values())
        )

    def plotly_rois(self, fig: go.Figure) -> None:
        for name, roi in self.rois.items():
            roi.plotly(fig, line_color="green", name=name)

    def plot_rois(self, axis: plt.Axes) -> None:
        """Plot the ROIs to the axis. Override to set the color"""
        for roi, mtf in zip(self.rois.values(), self.mtf.norm_mtfs.values()):
            roi.plot2axes(axis, edgecolor="g")


class SpatialResolutionModuleOutput(CTModuleOutput):
    """This class should not be called directly. It is returned by the ``results_data()`` method.

    Use the following attributes as normal class attributes."""

    lpmm_to_rmtf: dict = Field(
        description="Line pair to relative modulation transfer mapping. The keys are the line pair values and the values are the relative modulation transfer values.",
        title="Line Pair to Relative MTF",
    )


class LowContrastModule(CatPhanModule):
    """Class for analysis of the Uniformity slice of the CTP module. Measures 5 ROIs around the slice that
    should all be close to the same value.
    """

    attr_name = "low_contrast_module"
    common_name = "Low Contrast"
    roi_dist_mm = 60
    roi_radius_mm = 6
    nominal_value = 0
    roi_settings = {
        "ROI": {"angle": -90, "distance": roi_dist_mm, "radius": roi_radius_mm},
    }
    background_roi_settings = {
        "ROI": {"angle": -115, "distance": roi_dist_mm, "radius": roi_radius_mm},
    }
    window_min = 50
    window_max = 150

    def cnr(self) -> float:
        """Given in the guidance doc as |A-B|/SD where A is the contrast ROI, B is the background, and SD is stdev of B"""
        return (
            abs(self.rois["ROI"].pixel_value - self.background_rois["ROI"].pixel_value)
            / self.background_rois["ROI"].std
        )


class LowContrastModuleOutput(CTModuleOutput):
    """This class should not be called directly. It is returned by the ``results_data()`` method.
    It is a dataclass under the hood and thus comes with all the dunder magic.

    Use the following attributes as normal class attributes."""

    cnr: float = Field(
        description="The contrast-to-noise ratio.", title="Contrast to Noise Ratio"
    )


class ACRCTResult(ResultBase):
    """This class should not be called directly. It is returned by the ``results_data()`` method.

    Use the following attributes as normal class attributes."""

    phantom_model: str = Field(description="The model of the phantom used.")
    phantom_roll_deg: float = Field(
        description="The roll of the phantom in degrees.",
        title="Phantom roll (\N{DEGREE SIGN})",
    )
    origin_slice: int = Field(
        description="The slice number of the 'origin' slice; for ACR this is Module 1."
    )
    num_images: int = Field(description="The number of images in the passed dataset.")
    ct_module: CTModuleOutput = Field(
        description="The results of the CT module.", title="CT Module"
    )
    uniformity_module: UniformityModuleOutput = Field(
        description="The results of the Uniformity module.",
        title="HU Uniformity",
    )
    low_contrast_module: LowContrastModuleOutput = Field(
        description="The results of the Low Contrast module.",
        title="Low Contrast Resolution",
    )
    spatial_resolution_module: SpatialResolutionModuleOutput = Field(
        description="The results of the Spatial Resolution module.",
        title="Spatial Resolution",
    )


@capture_warnings
class ACRCT(CatPhanBase, ResultsDataMixin[ACRCTResult]):
    _model = "ACR CT 464"
    catphan_radius_mm = 100
    air_bubble_radius_mm = 14
    min_num_images = 4
    localization_radius = 70
    ct_calibration_module = CTModule
    low_contrast_module = LowContrastModule
    spatial_resolution_module = SpatialResolutionModule
    uniformity_module = UniformityModule
    clear_borders = False

    @classmethod
    def from_demo_image(cls):
        raise NotImplementedError("There is no demo file for this analysis")

    def _detected_modules(self) -> list[CatPhanModule]:
        return [
            self.ct_calibration_module,
            self.low_contrast_module,
            self.spatial_resolution_module,
            self.uniformity_module,
        ]

    def plot_analyzed_subimage(self, *args, **kwargs):
        raise NotImplementedError("Use `plot_images`")

    def save_analyzed_subimage(self, *args, **kwargs):
        raise NotImplementedError("Use `save_images`")

    def analyze(
        self,
        x_adjustment: float = 0,
        y_adjustment: float = 0,
        angle_adjustment: float = 0,
        roi_size_factor: float = 1,
        scaling_factor: float = 1,
        origin_slice: int | None = None,
    ) -> None:
        """Analyze the ACR CT phantom

        Parameters
        ----------
        x_adjustment: float
            A fine-tuning adjustment to the detected x-coordinate of the phantom center. This will move the
            detected phantom position by this amount in the x-direction in mm. Positive values move the phantom to the right.
        y_adjustment: float
            A fine-tuning adjustment to the detected y-coordinate of the phantom center. This will move the
            detected phantom position by this amount in the y-direction in mm. Positive values move the phantom down.
        angle_adjustment: float
            A fine-tuning adjustment to the detected angle of the phantom. This will rotate the phantom by this amount in degrees.
            Positive values rotate the phantom clockwise.
        roi_size_factor: float
            A fine-tuning adjustment to the ROI sizes of the phantom. This will scale the ROIs by this amount.
            Positive values increase the ROI sizes. In contrast to the scaling adjustment, this
            adjustment effectively makes the ROIs bigger or smaller, but does not adjust their position.
        scaling_factor: float
            A fine-tuning adjustment to the detected magnification of the phantom. This will zoom the ROIs and phantom outline (if applicable) by this amount.
            In contrast to the roi size adjustment, the scaling adjustment effectively moves the phantom and ROIs
            closer or further from the phantom center. I.e. this zooms the outline and ROI positions, but not ROI size.
        origin_slice: int, None
            The slice number of the HU linearity module. If None, will be automatically determined. This is a fallback
            method in case the automatic determination fails.
        """
        self.x_adjustment = x_adjustment
        self.y_adjustment = y_adjustment
        self.angle_adjustment = angle_adjustment
        self.roi_size_factor = roi_size_factor
        self.scaling_factor = scaling_factor
        self.localize(origin_slice=origin_slice)
        self.ct_calibration_module = self.ct_calibration_module(
            self, offset=0, clear_borders=self.clear_borders
        )
        self.uniformity_module = self.uniformity_module(
            self,
            offset=CT_UNIFORMITY_MODULE_OFFSET_MM,
            clear_borders=self.clear_borders,
        )
        self.spatial_resolution_module = self.spatial_resolution_module(
            self,
            offset=CT_SPATIAL_RESOLUTION_MODULE_OFFSET_MM,
            clear_borders=self.clear_borders,
        )
        self.low_contrast_module = self.low_contrast_module(
            self,
            offset=CT_LOW_CONTRAST_MODULE_OFFSET_MM,
            clear_borders=self.clear_borders,
        )

    def plotly_analyzed_images(
        self,
        show: bool = True,
        show_colorbar: bool = True,
        show_legend: bool = True,
        **kwargs,
    ) -> dict[str, go.Figure]:
        """Plot the analyzed image using Plotly. Will create multiple figures.

        Parameters
        ----------
        show : bool
            Whether to show the images. Set to False if doing further processing of the figure.
        show_colorbar : bool
            Whether to show the colorbar on the images.
        show_legend : bool
            Whether to show the legend on the images.
        kwargs
            Additional keyword arguments to pass to the figure.
        """
        figs = {}
        for module in (
            self.ct_calibration_module,
            self.uniformity_module,
            self.spatial_resolution_module,
            self.low_contrast_module,
        ):
            figs[module.common_name] = module.plotly(
                show_colorbar=show_colorbar, show_legend=show_legend, **kwargs
            )
        figs["MTF"] = self.spatial_resolution_module.mtf.plotly(
            show_legend=show_legend, **kwargs
        )
        figs["Side View"] = self.plotly_side_view(show_legend=show_legend)

        if show:
            for fig in figs.values():
                fig.show()
        return figs

    def plot_analyzed_image(self, show: bool = True, **plt_kwargs) -> plt.Figure:
        """Plot the analyzed image

        Parameters
        ----------
        show
            Whether to show the image.
        plt_kwargs
            Keywords to pass to matplotlib for figure customization.
        """
        # set up grid and axes
        fig = plt.figure(**plt_kwargs)
        grid_size = (2, 3)
        hu_ax = plt.subplot2grid(grid_size, (0, 0))
        self.ct_calibration_module.plot(hu_ax)
        unif_ax = plt.subplot2grid(grid_size, (0, 1))
        self.uniformity_module.plot(unif_ax)
        sr_ax = plt.subplot2grid(grid_size, (0, 2))
        self.spatial_resolution_module.plot(sr_ax)
        locon_ax = plt.subplot2grid(grid_size, (1, 0))
        self.low_contrast_module.plot(locon_ax)
        spatial_res_graph = plt.subplot2grid(grid_size, (1, 2))
        self.spatial_resolution_module.mtf.plot(spatial_res_graph)
        side_ax = plt.subplot2grid(grid_size, (1, 1))
        self.plot_side_view(side_ax)

        # finish up
        plt.tight_layout()
        if show:
            plt.show()
        return fig

    def save_analyzed_image(self, filename: str | Path | BytesIO, **plt_kwargs) -> None:
        """Save the analyzed image to disk or stream

        Parameters
        ----------
        filename
            Where to save the image to
        plt_kwargs
            Keywords to pass to matplotlib for figure customization.
        """
        fig = self.plot_analyzed_image(show=False, **plt_kwargs)
        fig.savefig(filename)

    def plot_images(self, show: bool = True, **plt_kwargs) -> dict[str, plt.Figure]:
        """Plot all the individual images separately

        Parameters
        ----------
        show
            Whether to show the images.
        plt_kwargs
            Keywords to pass to matplotlib for figure customization.
        """
        figs = {}
        # plot the images
        modules = {
            "hu": self.ct_calibration_module,
            "uniformity": self.uniformity_module,
            "spatial resolution": self.spatial_resolution_module,
            "low contrast": self.low_contrast_module,
        }
        for key, module in modules.items():
            fig, ax = plt.subplots(**plt_kwargs)
            module.plot(ax)
            figs[key] = fig
        # plot the one-off MTF image
        fig, ax = plt.subplots(**plt_kwargs)
        figs["mtf"] = fig
        self.spatial_resolution_module.mtf.plot(ax)
        # plot the side view
        fig, ax = plt.subplots(**plt_kwargs)
        figs["side"] = fig
        self.plot_side_view(ax)

        plt.tight_layout()

        if show:
            plt.show()
        return figs

    def save_images(
        self,
        directory: Path | str | None = None,
        to_stream: bool = False,
        **plt_kwargs,
    ) -> list[Path | BytesIO]:
        """Save separate images to disk or stream.

        Parameters
        ----------
        directory
            The directory to write the images to. If None, will use current working directory
        to_stream
            Whether to write to stream or disk. If True, will return streams. Directory is ignored in that scenario.
        plt_kwargs
            Keywords to pass to matplotlib for figure customization.
        """
        figs = self.plot_images(show=False, **plt_kwargs)
        paths = []
        for name, fig in figs.items():
            if to_stream:
                path = io.BytesIO()
            else:
                destination = Path(directory) if directory is not None else Path.cwd()
                path = (destination / name).with_suffix(".png").absolute()
            fig.savefig(path)
            paths.append(path)
        return paths

    def find_phantom_roll(self, func=lambda roi: roi.bbox_area) -> float:
        """Determine the "roll" of the phantom.

        Only difference of base method is that we sort the ROIs by size,
        not by being in the center since the two we're looking for are both right-sided.
        """
        return super().find_phantom_roll(func)

    def results(self) -> str:
        """Return the results of the analysis as a string. Use with print()."""
        string = (
            f"\n - ACR CT 464 QA Test - \n"
            f"HU ROIs: {self.ct_calibration_module.roi_vals_as_str}\n"
            f"Contrast to Noise Ratio: {self.low_contrast_module.cnr():2.2f}\n"
            f"Uniformity ROIs: {self.uniformity_module.roi_vals_as_str}\n"
            f"Uniformity Center ROI standard deviation: {self.uniformity_module.rois['Center'].std:2.2f}\n"
            f"BB distance (mm): {self.uniformity_module.bb_distance_mm:2.2f}\n"
            f"MTF 50% (lp/mm): {format_resolution(self.spatial_resolution_module.mtf.relative_resolution(50))}\n"
        )
        return string

    def _generate_results_data(self) -> ACRCTResult:
        return ACRCTResult(
            phantom_model="ACR CT 464",
            phantom_roll_deg=self.catphan_roll,
            origin_slice=self.origin_slice,
            num_images=self.num_images,
            ct_module=CTModuleOutput(
                offset=0,
                roi_distance_from_center_mm=self.ct_calibration_module.roi_dist_mm,
                roi_radius_mm=self.ct_calibration_module.roi_radius_mm,
                roi_settings=self.ct_calibration_module.roi_settings,
                rois={
                    name: roi.mean
                    for name, roi in self.ct_calibration_module.rois.items()
                },
            ),
            uniformity_module=UniformityModuleOutput(
                offset=CT_UNIFORMITY_MODULE_OFFSET_MM,
                roi_distance_from_center_mm=self.uniformity_module.roi_dist_mm,
                roi_radius_mm=self.uniformity_module.roi_radius_mm,
                roi_settings=self.uniformity_module.roi_settings,
                rois={
                    name: roi.mean for name, roi in self.uniformity_module.rois.items()
                },
                center_roi_stdev=self.uniformity_module.rois["Center"].std,
                bb_distance_mm=self.uniformity_module.bb_distance_mm,
                scaling_error_percent=self.uniformity_module.scaling_error_percent,
                measured_pixel_size=self.uniformity_module.measured_pixel_size,
            ),
            spatial_resolution_module=SpatialResolutionModuleOutput(
                offset=CT_SPATIAL_RESOLUTION_MODULE_OFFSET_MM,
                roi_distance_from_center_mm=self.spatial_resolution_module.roi_dist_mm,
                roi_radius_mm=self.spatial_resolution_module.roi_radius_mm,
                roi_settings=self.spatial_resolution_module.roi_settings,
                rois={
                    name: roi.pixel_value
                    for name, roi in self.spatial_resolution_module.rois.items()
                },
                lpmm_to_rmtf=self.spatial_resolution_module.mtf.norm_mtfs,
            ),
            low_contrast_module=LowContrastModuleOutput(
                offset=CT_LOW_CONTRAST_MODULE_OFFSET_MM,
                roi_distance_from_center_mm=self.low_contrast_module.roi_dist_mm,
                roi_radius_mm=self.low_contrast_module.roi_radius_mm,
                roi_settings=self.low_contrast_module.roi_settings,
                rois={
                    name: roi.pixel_value
                    for name, roi in self.low_contrast_module.rois.items()
                },
                cnr=self.low_contrast_module.cnr(),
            ),
        )

    def _quaac_datapoints(self) -> dict[str, QuaacDatum]:
        results_data = self.results_data(as_dict=True)
        data = {}
        data["Phantom Roll"] = QuaacDatum(
            value=results_data["phantom_roll_deg"],
            unit="degrees",
            description="The roll of the phantom in the image",
        )
        for name, value in results_data["ct_module"]["rois"].items():
            data[f"{name} HU"] = QuaacDatum(
                value=value,
                unit="HU",
                description=f"The HU value of the {name} ROI",
            )
        for name, value in results_data["uniformity_module"]["rois"].items():
            data[f"{name} Uniformity HU"] = QuaacDatum(
                value=value,
                unit="HU",
                description=f"The HU value of the {name} Uniformity ROI",
            )
        for name, value in results_data["spatial_resolution_module"][
            "lpmm_to_rmtf"
        ].items():
            data[f"{name} lp/mm"] = QuaacDatum(
                value=value,
                unit="rMTF",
            )
        for name, value in results_data["low_contrast_module"]["rois"].items():
            data[f"{name} CNR"] = QuaacDatum(
                value=value,
                unit="CNR",
                description=f"The CNR value of the {name} ROI",
            )
        return data

    def publish_pdf(
        self,
        filename: str | Path,
        notes: str | None = None,
        open_file: bool = False,
        metadata: dict | None = None,
        logo: Path | str | None = None,
    ) -> None:
        """Publish (print) a PDF containing the analysis and quantitative results.

        Parameters
        ----------
        filename : (str, file-like object}
            The file to write the results to.
        notes : str, list of strings
            Text; if str, prints single line.
            If list of strings, each list item is printed on its own line.
        open_file : bool
            Whether to open the file using the default program after creation.
        metadata : dict
            Extra data to be passed and shown in the PDF. The key and value will be shown with a colon.
            E.g. passing {'Author': 'James', 'Unit': 'TrueBeam'} would result in text in the PDF like:
            --------------
            Author: James
            Unit: TrueBeam
            --------------
        logo: Path, str
            A custom logo to use in the PDF report. If nothing is passed, the default pylinac logo is used.
        """
        analysis_title = f"{self._model} Analysis"
        texts = [
            " - ACR CT 464 Results - ",
            f"HU Linearity ROIs: {self.ct_calibration_module.roi_vals_as_str}",
            f"Low contrast visibility: {self.low_contrast_module.cnr():2.2f}",
            f"Uniformity ROIs: {self.uniformity_module.roi_vals_as_str}",
        ]
        texts.append(f"BB distance: {self.uniformity_module.bb_distance_mm:2.2f} mm")
        analysis_images = self.save_images(to_stream=True)

        canvas = pdf.PylinacCanvas(
            filename, page_title=analysis_title, metadata=metadata, logo=logo
        )
        if notes is not None:
            canvas.add_text(text="Notes:", location=(1, 4.5), font_size=14)
            canvas.add_text(text=notes, location=(1, 4))

        for idx, text in enumerate(texts):
            canvas.add_text(text=text, location=(1.5, 23 - idx * 0.5))
        for page, img in enumerate(analysis_images):
            canvas.add_new_page()
            canvas.add_image(img, location=(1, 5), dimensions=(18, 18))
        canvas.finish()

        if open_file:
            webbrowser.open(filename)

    def _module_offsets(self) -> list[float]:
        absolute_origin_position = self.dicom_stack[self.origin_slice].z_position
        relative_offsets_mm = [
            0,
            CT_UNIFORMITY_MODULE_OFFSET_MM,
            CT_LOW_CONTRAST_MODULE_OFFSET_MM,
            CT_SPATIAL_RESOLUTION_MODULE_OFFSET_MM,
        ]
        return [
            absolute_origin_position + offset_mm for offset_mm in relative_offsets_mm
        ]


class ACRCT467Statistics(BaseModel):
    """Descriptive statistics of the rescaled values in a sampled region."""

    pixel_count: int
    mean: float
    median: float
    stdev: float
    variance: float
    minimum: float
    maximum: float
    percentiles: dict[int, float]
    interquartile_range: float
    median_absolute_deviation: float
    skewness: float | None
    excess_kurtosis: float | None


class ACRCT467Histogram(BaseModel):
    """Bin edges and counts of the original samples in a selected region."""

    bin_edges: list[float]
    counts: list[int]


class ACRCT467Boundary(BaseModel):
    """Independent local threshold evidence for the nominal insert location."""

    center_px: tuple[float, float]
    equivalent_diameter_mm: float
    center_offset_mm: float
    local_contrast: float


class ACRCT467PlacementSample(BaseModel):
    """Statistics for a disk shifted from its nominal location in the image plane."""

    offset_mm: tuple[float, float]
    pixel_count: int
    mean: float
    median: float
    stdev: float


class ACRCT467ROI(ACRCT467Statistics):
    """Image-space location and rescaled pixel statistics of one sampling disk."""

    center_px: tuple[float, float]
    angle_deg: float | None
    distance_mm: float
    radius_mm: float
    histogram: ACRCT467Histogram
    sphere: ACRCT467Statistics | None
    boundary: ACRCT467Boundary | None
    placement_sensitivity: list[ACRCT467PlacementSample]
    placement_median_span: float


class ACRCT467Acquisition(BaseModel):
    """Selected acquisition values reported by DICOM, not inferred measurements."""

    image_type: list[str]
    convolution_kernel: list[str]
    tube_voltage_kvp: float | None
    tube_current_ma: float | None
    exposure_mas: float | None
    ctdi_vol_mgy: float | None
    reconstruction_diameter_mm: float | None


class ACRCT467Slice(BaseModel):
    """Slice geometry and fixed-coordinate disk samples, including outside the phantom."""

    index: int
    z_mm: float
    outline_center_px: tuple[float, float] | None
    outline_equivalent_diameter_mm: float | None
    slice_thickness_mm: float | None
    rescale_slope: float
    rescale_intercept: float
    rescale_type: str | None
    acquisition: ACRCT467Acquisition
    rois: dict[str, ACRCT467Statistics]


class ACRCT467Comparison(BaseModel):
    """Signed contrasts (second minus first) and pooled-noise CNR for two disks."""

    first_roi: str
    second_roi: str
    mean_difference: float
    median_difference: float
    pooled_stdev: float
    mean_cnr: float | None
    median_cnr: float | None


class ACRCT467CTNumberReference(BaseModel):
    """Site-approved mean HU reference for an independently confirmed rod position."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    material: str = Field(min_length=1)
    expected_hu: float = Field(allow_inf_nan=False)
    tolerance_hu: float = Field(ge=0, allow_inf_nan=False)
    source: str = Field(min_length=1)


class ACRCT467CTNumberCheck(BaseModel):
    """Comparison to a supplied reference, or an ungraded observation without HU units."""

    reference: ACRCT467CTNumberReference
    difference_hu: float | None
    passed: bool | None


class ACRCT467GuideMeasurements(BaseModel):
    """Model 467 guide sampling and optional site-specific CT-number checks."""

    guide_url: str = "https://cspmedical.com/content/102-1492_tissue_phantom_user_guide.pdf"
    rod_sample_diameter_mm: float = 10.0
    nominal_caliper_spacing_mm: float = 50.0
    rod_statistics: dict[str, ACRCT467Statistics]
    ct_number_checks: dict[str, ACRCT467CTNumberCheck]
    ct_number_passed: bool | None


class ACRCT467Result(ResultBase):
    """Measurements of numbered regions in a Gammex 467 CT series."""

    phantom_model: str = "ACR Gammex 467"
    origin_slice: int
    origin_z_mm: float
    num_images: int
    center_px: tuple[float, float]
    reference_angle_deg: float
    reference_angle_method: str
    image_shape_px: tuple[int, int]
    pixel_spacing_mm: tuple[float, float]
    slice_spacing_mm: float | None
    value_units: str
    rois: dict[str, ACRCT467ROI]
    slices: list[ACRCT467Slice]
    pair_comparisons: list[ACRCT467Comparison]
    sphere_slice_indices: list[int]
    sphere_unavailable_reason: str | None
    limitations: list[str]
    guide_measurements: ACRCT467GuideMeasurements | None = None


class ACRCT467(ResultsDataMixin[ACRCT467Result]):
    """Measure numbered insert regions in the Gammex 467 CT phantom.

    This is distinct from the four-module 464 phantom analyzed by :class:`ACRCT`.
    The 467 uses a center position and two eight-position rings; numbering is
    geometric and does not assign material identities or acceptance limits.
    """

    def __init__(self, path: str | Path | DicomImageStack) -> None:
        """Load a DICOM directory or an already rescaled CT image stack."""
        super().__init__()
        self.dicom_stack = (
            path
            if isinstance(path, DicomImageStack)
            else DicomImageStack(path, min_number=1, check_uid=False)
        )
        self._result: ACRCT467Result | None = None

    @classmethod
    def from_zip(cls, path: str | Path) -> ACRCT467:
        """Load a single CT series from a ZIP archive."""
        return cls(DicomImageStack.from_zip(path, min_number=1, check_uid=False))

    def analyze(
        self,
        origin_slice: int | None = None,
        reference_angle_deg: float | None = None,
        *,
        ct_number_references: Mapping[str, ACRCT467CTNumberReference] | None = None,
    ) -> None:
        """Locate the phantom and measure both 20 mm disks and 10 mm guide samples.

        Parameters
        ----------
        origin_slice : int, optional
            Zero-based index in the sorted CT stack. By default, use the
            middle slice among those with a complete phantom outline.
        reference_angle_deg : float, optional
            Angle of the first inner-ring position, measured clockwise from
            image right. By default, locate the brightest inner-ring insert.
        ct_number_references : Mapping[str, ACRCT467CTNumberReference], optional
            Site-approved mean HU targets and tolerances keyed by ROI name.
            Confirm the rod identity, sampling position, and scanner protocol
            before supplying a reference. CT-number grading requires declared HU.
            No acceptance limits are inferred from the manufacturer's guide.
        """
        self._result = None
        images = self.dicom_stack
        metadata = [image.metadata for image in images]
        series_uids = {item.get("SeriesInstanceUID") for item in metadata}
        if (
            len(series_uids) != 1
            or None in series_uids
            or any(item.get("Modality") != "CT" for item in metadata)
        ):
            raise ValueError("Gammex 467 analysis requires a single CT series.")
        row_spacing, column_spacing = map(float, metadata[0].PixelSpacing)
        spacing = (row_spacing, column_spacing)
        if not all(np.isfinite(spacing)) or min(spacing) <= 0:
            raise ValueError("Gammex 467 analysis requires positive pixel spacing.")
        shape = images[0].array.shape
        if any(
            image.array.ndim != 2
            or image.array.shape != shape
            or not np.allclose(image.metadata.PixelSpacing, spacing)
            for image in images
        ):
            raise ValueError("Gammex 467 analysis requires a consistent pixel grid.")
        if any(not item.get("ImageOrientationPatient") for item in metadata):
            raise ValueError("Gammex 467 analysis requires DICOM slice orientations.")
        positions_mm = np.asarray(
            [item.ImagePositionPatient for item in metadata], dtype=float
        )
        orientations = np.asarray(
            [item.ImageOrientationPatient for item in metadata], dtype=float
        )
        orientation_axes = orientations[0].reshape(2, 3)
        z_mm = positions_mm[:, 2]
        z_steps = np.diff(z_mm)
        if (
            not np.isfinite(positions_mm).all()
            or not np.allclose(
                positions_mm[:, :2], positions_mm[0, :2], atol=0.01, rtol=0
            )
            or not np.allclose(orientations, orientations[0], atol=0.001, rtol=0)
            or not np.allclose(orientations[:, (2, 5)], 0, atol=0.001, rtol=0)
            or not np.allclose(
                orientation_axes @ orientation_axes.T, np.eye(2), atol=0.001
            )
            or np.any(z_steps <= 0)
        ):
            raise ValueError(
                "Gammex 467 analysis requires aligned axial slices at distinct z positions."
            )
        slice_spacing = (
            float(np.median(z_steps))
            if z_steps.size and np.allclose(z_steps, np.median(z_steps), atol=0.05, rtol=0)
            else None
        )
        thicknesses = [self._numeric_tag(item, "SliceThickness") for item in metadata]
        rescale_types = [
            str(item.get("RescaleType") or "").strip().upper() or None
            for item in metadata
        ]
        if len(set(rescale_types) - {None}) > 1:
            raise ValueError("Gammex 467 analysis cannot combine different declared pixel units.")

        outlines = {
            index: outline
            for index, image in enumerate(images)
            if (outline := self._body_outline(image.array, spacing)) is not None
        }
        if not outlines:
            raise ValueError("No complete Gammex 467 phantom outline was found.")
        if origin_slice is None:
            middle_z = np.median(z_mm[list(outlines)])
            origin_slice = min(outlines, key=lambda index: abs(z_mm[index] - middle_z))
        if origin_slice not in outlines:
            raise ValueError("The selected origin slice has no complete phantom outline.")

        center = outlines[origin_slice][0]
        array = images[origin_slice].array
        smoothed = ndimage.gaussian_filter(
            array.astype(float), sigma=(2 / spacing[0], 2 / spacing[1])
        )
        angle_method = "user_supplied"
        if reference_angle_deg is None:
            reference_angle_deg = self._reference_angle(smoothed, center, spacing)
            angle_method = "brightest_inner_component"
        if not math.isfinite(reference_angle_deg):
            raise ValueError("The Gammex 467 reference angle must be finite.")
        reference_angle_deg %= 360
        positions = [(None, 0.0)] + [
            ((reference_angle_deg + offset + step * 45) % 360, distance)
            for offset, distance in ((0, 55.0), (22.5, 105.0))
            for step in range(8)
        ]
        radius = 10.0
        sphere_indices, sphere_reason = self._sphere_coverage(
            z_mm, origin_slice, radius, set(outlines), slice_spacing, thicknesses
        )
        references = {
            name: ACRCT467CTNumberReference.model_validate(reference)
            for name, reference in (ct_number_references or {}).items()
        }
        unknown = references.keys() - {f"ROI {number}" for number in range(1, len(positions) + 1)}
        if unknown:
            raise ValueError(f"Unknown Gammex 467 reference ROI(s): {', '.join(sorted(unknown))}")
        guide_radius = 5.0
        rois = {}
        guide_statistics = {}
        for number, (angle, distance) in enumerate(positions, start=1):
            radians = math.radians(angle or 0)
            location = (
                center[0] + distance * math.cos(radians) / spacing[1],
                center[1] + distance * math.sin(radians) / spacing[0],
            )
            values = self._disk_values(array, location, radius, spacing)
            name = f"ROI {number}"
            guide_statistics[name] = self._statistics(
                self._disk_values(array, location, guide_radius, spacing)
            )
            statistics = self._statistics(values)
            shifts = self._placement_samples(array, location, radius, spacing)
            medians = [sample.median for sample in shifts]
            sphere = None
            if sphere_indices:
                sphere_values = np.concatenate(
                    [
                        self._disk_values(
                            images[index].array,
                            location,
                            math.sqrt(radius**2 - (z_mm[index] - z_mm[origin_slice]) ** 2),
                            spacing,
                        )
                        for index in sphere_indices
                    ]
                )
                sphere = self._statistics(sphere_values)
            rois[name] = ACRCT467ROI(
                **statistics.model_dump(),
                center_px=location,
                angle_deg=angle,
                distance_mm=distance,
                radius_mm=radius,
                histogram=self._histogram(values, statistics),
                sphere=sphere,
                boundary=self._insert_boundary(smoothed, location, spacing),
                placement_sensitivity=shifts,
                placement_median_span=max(medians) - min(medians),
            )
        slices = [
            ACRCT467Slice(
                index=index,
                z_mm=float(z_mm[index]),
                outline_center_px=outlines[index][0] if index in outlines else None,
                outline_equivalent_diameter_mm=(
                    outlines[index][1] if index in outlines else None
                ),
                slice_thickness_mm=thicknesses[index],
                rescale_slope=float(item.get("RescaleSlope", 1)),
                rescale_intercept=float(item.get("RescaleIntercept", 0)),
                rescale_type=rescale_types[index],
                acquisition=self._acquisition(item),
                rois={
                    name: self._statistics(
                        self._disk_values(images[index].array, roi.center_px, radius, spacing)
                    )
                    for name, roi in rois.items()
                },
            )
            for index, item in enumerate(metadata)
        ]
        value_units = "HU" if all(unit == "HU" for unit in rescale_types) else "RESCALED"
        checks = {}
        for name, reference in references.items():
            difference = (
                guide_statistics[name].mean - reference.expected_hu if value_units == "HU" else None
            )
            checks[name] = ACRCT467CTNumberCheck(
                reference=reference,
                difference_hu=difference,
                passed=abs(difference) <= reference.tolerance_hu if difference is not None else None,
            )
        passed = None
        if checks and value_units == "HU":
            passed = all(check.passed is True for check in checks.values())
        limitations = [
            "ROI numbering describes geometry. Rod identities must be confirmed independently.",
            "Disks use nominal layout coordinates; boundary evidence is reported separately when visible.",
            "The Model 467 guide specifies nominal references, not acceptance limits. No 464 module tests are inferred.",
            "Slice profiles sample fixed coordinates even on planes without a complete phantom outline.",
        ]
        if value_units != "HU":
            limitations.append(
                "Pixel values are rescaled; HU is not explicitly declared on every slice."
            )
        self._result = ACRCT467Result(
            origin_slice=origin_slice,
            origin_z_mm=float(z_mm[origin_slice]),
            num_images=len(images),
            center_px=center,
            reference_angle_deg=reference_angle_deg,
            reference_angle_method=angle_method,
            image_shape_px=shape,
            pixel_spacing_mm=spacing,
            slice_spacing_mm=slice_spacing,
            value_units=value_units,
            rois=rois,
            slices=slices,
            pair_comparisons=[
                self._compare_disks(first_name, first, second_name, second)
                for (first_name, first), (second_name, second) in combinations(rois.items(), 2)
            ],
            sphere_slice_indices=sphere_indices,
            sphere_unavailable_reason=sphere_reason,
            limitations=limitations,
            guide_measurements=ACRCT467GuideMeasurements(
                rod_sample_diameter_mm=2 * guide_radius,
                rod_statistics=guide_statistics,
                ct_number_checks=checks,
                ct_number_passed=passed,
            ),
        )

    def results(self) -> str:
        """Return a summary of the geometry and all 17 disk measurements."""
        result = self._generate_results_data()
        origin = result.slices[result.origin_slice]
        row_mm, column_mm = result.pixel_spacing_mm
        sphere_summary = (
            f"Sphere samples use {len(result.sphere_slice_indices)} planes."
            if result.sphere_slice_indices
            else f"Sphere samples unavailable: {result.sphere_unavailable_reason}"
        )
        lines = [
            f"Origin index {origin.index} of {result.num_images} slices; z = {origin.z_mm:g} mm",
            f"Pixel spacing: {row_mm:g} x {column_mm:g} mm (row x column)",
            f"Reference angle: {result.reference_angle_deg:.2f} deg "
            f"({result.reference_angle_method})",
            f"Units: {result.value_units}; nominal sample diameter: 20 mm",
            sphere_summary,
            "",
            f"{'Region':<8}{'Mean':>10}{'Median':>10}{'SD':>10}{'Sample n':>10}{'Boundary':>12}",
        ]
        for name, roi in result.rois.items():
            boundary = "Visible" if roi.boundary is not None else "Layout only"
            lines.append(
                f"{name:<8}{roi.mean:>10.2f}{roi.median:>10.2f}{roi.stdev:>10.2f}"
                f"{roi.pixel_count:>10}{boundary:>12}"
            )
        lines += ["", "Measurement limitations:"]
        lines.extend(line for note in result.limitations for line in wrap(note, width=96))
        return "\n".join(lines)

    def plot_analyzed_image(self, show: bool = True) -> plt.Figure:
        """Plot the analysis slice and its numbered, physically sized sampling disks."""
        result = self._generate_results_data()
        row_mm, column_mm = result.pixel_spacing_mm
        lower, upper = self._overlay_window(result)
        fig, axis = plt.subplots(figsize=(7, 7), layout="constrained")
        axis.imshow(
            self.dicom_stack[result.origin_slice].array,
            cmap="gray",
            aspect=row_mm / column_mm,
            vmin=lower,
            vmax=upper,
        )
        for name, roi in result.rois.items():
            color = self._roi_color(roi)
            self._draw_sampling_disk(axis, roi, result.pixel_spacing_mm)
            axis.annotate(
                name.removeprefix("ROI "),
                roi.center_px,
                color=color,
                ha="center",
                va="center",
                fontsize=9,
                fontweight="bold",
                bbox={"facecolor": "black", "edgecolor": "none", "alpha": 0.65, "pad": 1},
            )
        axis.set_title(
            f"Gammex 467: slice index {result.origin_slice}, z = {result.origin_z_mm:g} mm\n"
            "Blue: visible boundary   |   Yellow: layout only"
        )
        axis.set_axis_off()
        if show:
            plt.show()
        return fig

    def plotly_analyzed_images(self, show: bool = True) -> dict[str, go.Figure]:
        """Return the analysis slice with interactive sampling-disk overlays."""
        result = self._generate_results_data()
        row_mm, column_mm = result.pixel_spacing_mm
        lower, upper = self._overlay_window(result)
        title = f"Gammex 467: slice index {result.origin_slice}"
        figure = self.dicom_stack[result.origin_slice].plotly(
            title=title,
            show=False,
            show_metrics=False,
            zmin=lower,
            zmax=upper,
        )
        figure.update_yaxes(scaleratio=row_mm / column_mm)
        radians = np.linspace(0, 2 * math.pi, 65)
        for name, roi in result.rois.items():
            color = self._roi_color(roi)
            status = "Visible boundary" if roi.boundary is not None else "Layout only"
            x_center, y_center = roi.center_px
            figure.add_scatter(
                x=x_center + roi.radius_mm / column_mm * np.cos(radians),
                y=y_center + roi.radius_mm / row_mm * np.sin(radians),
                mode="lines",
                line_color=color,
                showlegend=False,
                name=name,
                hovertemplate=(
                    f"{name}: {roi.median:.2f} {result.value_units}"
                    f"<br>{status}<extra></extra>"
                ),
            )
            figure.add_annotation(
                x=x_center,
                y=y_center,
                text=name.removeprefix("ROI "),
                showarrow=False,
                font_color=color,
                bgcolor="black",
            )
        if show:
            figure.show()
        return {result.phantom_model: figure}

    def plot_slice_profiles(self, show: bool = True) -> plt.Figure:
        """Plot the disk medians at fixed image coordinates across the CT stack."""
        result = self._generate_results_data()
        fig, axes = plt.subplots(2, 1, figsize=(8, 7), sharex=True, layout="constrained")
        z_mm = [plane.z_mm for plane in result.slices]
        names = list(result.rois)
        groups = (("Center and inner ring", names[:9]), ("Outer ring", names[9:]))
        for axis, (title, group) in zip(axes, groups):
            for name in group:
                medians = [plane.rois[name].median for plane in result.slices]
                axis.plot(z_mm, medians, ".-", label=name)
            axis.axvline(result.origin_z_mm, color="gray", linestyle="--", linewidth=1)
            axis.set(title=title, ylabel=f"Median ({result.value_units})")
            axis.legend(ncols=5, fontsize=8)
        axes[-1].set_xlabel("DICOM slice position z (mm)")
        if show:
            plt.show()
        return fig

    def publish_pdf(
        self,
        filename: str | Path | BytesIO,
        *,
        detailed: bool = True,
        logo: Path | str | None = None,
    ) -> None:
        """Save a detailed report or a QA summary, both with analysis figures.

        Parameters
        ----------
        filename : str, Path, or BytesIO
            Report destination.
        detailed : bool
            Include all measurement tables. Both modes include the analysis figures.
        logo : Path, str, or None
            Optional logo image for the Pro-ART page header. If omitted, the
            report displays the brand name as text in the logo position.
        """
        result = self.results_data()
        assert isinstance(result, ACRCT467Result)
        destination = str(filename) if isinstance(filename, Path) else filename
        _write_report(
            destination, result, _report_figures(self, result), detailed=detailed, logo=logo,
        )

    def publish_json(self, filename: str | Path) -> None:
        """Save the QA checklist and grouped full-precision measurements as JSON.

        Parameters
        ----------
        filename : str or Path
            Report destination. The raw :meth:`results_data` structure is unchanged.
        """
        result = self.results_data()
        assert isinstance(result, ACRCT467Result)
        Path(filename).write_text(_json_report(result), encoding="utf-8", newline="\n")

    def _generate_results_data(self) -> ACRCT467Result:
        if self._result is None:
            raise ValueError("Analyze the Gammex 467 series before requesting results.")
        return self._result

    @staticmethod
    def _roi_color(roi: ACRCT467ROI) -> str:
        return "deepskyblue" if roi.boundary is not None else "gold"

    @classmethod
    def _draw_sampling_disk(
        cls, axis: plt.Axes, roi: ACRCT467ROI, spacing: tuple[float, float]
    ) -> None:
        row_mm, column_mm = spacing
        axis.add_patch(
            Ellipse(
                roi.center_px,
                width=2 * roi.radius_mm / column_mm,
                height=2 * roi.radius_mm / row_mm,
                fill=False,
                edgecolor=cls._roi_color(roi),
                linewidth=1.5,
            )
        )

    @staticmethod
    def _overlay_window(result: ACRCT467Result) -> tuple[float, float]:
        return (
            min(roi.percentiles[5] for roi in result.rois.values()),
            max(roi.percentiles[95] for roi in result.rois.values()),
        )

    @staticmethod
    def _body_outline(
        array: np.ndarray, spacing: tuple[float, float]
    ) -> tuple[tuple[float, float], float] | None:
        reduced = array[::2, ::2]
        labels, _ = ndimage.label(reduced > threshold_otsu(reduced))
        counts = np.bincount(labels.ravel())
        counts[0] = 0
        if not counts.max():
            return None
        body = ndimage.binary_fill_holes(labels == counts.argmax())
        diameter = 2 * math.sqrt(body.sum() * 4 * math.prod(spacing) / math.pi)
        if not 310 <= diameter <= 350 or any(
            edge.any() for edge in (body[0], body[-1], body[:, 0], body[:, -1])
        ):
            return None
        row, column = ndimage.center_of_mass(body)
        return (float(column * 2), float(row * 2)), diameter

    @staticmethod
    def _sphere_coverage(
        z_mm: np.ndarray,
        origin_slice: int,
        radius: float,
        outline_indices: set[int],
        slice_spacing: float | None,
        thicknesses: list[float | None],
    ) -> tuple[list[int], str | None]:
        origin_z = z_mm[origin_slice]
        first = int(np.searchsorted(z_mm, origin_z - radius, side="right")) - 1
        last = int(np.searchsorted(z_mm, origin_z + radius))
        bracket = range(first, last + 1)
        if first < 0 or last >= len(z_mm) or not outline_indices.issuperset(bracket):
            return [], "The complete sphere extent is not bracketed by phantom slices."
        if slice_spacing is None or any(
            thickness is None or not math.isfinite(thickness) or thickness + 0.05 < slice_spacing
            for thickness in thicknesses[first : last + 1]
        ):
            return [], "Uniform, gap-free coverage of the sphere could not be established."
        return [index for index in bracket if abs(z_mm[index] - origin_z) < radius], None

    @staticmethod
    def _statistics(values: np.ndarray) -> ACRCT467Statistics:
        pixels = values.astype(float, copy=False)
        mean = float(pixels.mean())
        stdev = float(pixels.std())
        levels = (5, 25, 50, 75, 95)
        percentiles = dict(zip(levels, map(float, np.percentile(pixels, levels))))
        normalized = (pixels - mean) / stdev if stdev > 0 else None
        return ACRCT467Statistics(
            pixel_count=pixels.size,
            mean=mean,
            median=percentiles[50],
            stdev=stdev,
            variance=stdev**2,
            minimum=float(pixels.min()),
            maximum=float(pixels.max()),
            percentiles=percentiles,
            interquartile_range=percentiles[75] - percentiles[25],
            median_absolute_deviation=float(np.median(np.abs(pixels - percentiles[50]))),
            skewness=float(np.mean(normalized**3)) if normalized is not None else None,
            excess_kurtosis=float(np.mean(normalized**4) - 3) if normalized is not None else None,
        )

    @staticmethod
    def _histogram(values: np.ndarray, statistics: ACRCT467Statistics) -> ACRCT467Histogram:
        width = 2 * statistics.interquartile_range / math.cbrt(statistics.pixel_count)
        sturges_bins = math.ceil(math.log2(statistics.pixel_count) + 1)
        fd_bins = math.ceil((statistics.maximum - statistics.minimum) / width) if width > 0 else 0
        counts, edges = np.histogram(values, bins=min(256, max(sturges_bins, fd_bins)))
        return ACRCT467Histogram(bin_edges=edges.tolist(), counts=counts.tolist())

    @staticmethod
    def _compare_disks(
        first_name: str,
        first: ACRCT467ROI,
        second_name: str,
        second: ACRCT467ROI,
    ) -> ACRCT467Comparison:
        pooled = math.hypot(first.stdev, second.stdev) / math.sqrt(2)
        mean_difference = second.mean - first.mean
        median_difference = second.median - first.median
        return ACRCT467Comparison(
            first_roi=first_name,
            second_roi=second_name,
            mean_difference=mean_difference,
            median_difference=median_difference,
            pooled_stdev=pooled,
            mean_cnr=abs(mean_difference) / pooled if pooled > 0 else None,
            median_cnr=abs(median_difference) / pooled if pooled > 0 else None,
        )

    @staticmethod
    def _reference_angle(
        smoothed: np.ndarray, center: tuple[float, float], spacing: tuple[float, float]
    ) -> float:
        rows, columns = np.ogrid[: smoothed.shape[0], : smoothed.shape[1]]
        radii = np.hypot((rows - center[1]) * spacing[0], (columns - center[0]) * spacing[1])
        ring = (radii >= 49) & (radii <= 61)
        peak = np.unravel_index(np.argmax(np.where(ring, smoothed, -np.inf)), smoothed.shape)
        baseline = np.median(smoothed[ring])
        threshold = (smoothed[peak] + baseline) / 2
        labels, _ = ndimage.label((smoothed > threshold) & (radii > 33) & (radii < 77))
        component = labels == labels[peak]
        diameter = 2 * math.sqrt(component.sum() * math.prod(spacing) / math.pi)
        if not labels[peak] or not 15 <= diameter <= 45:
            raise ValueError(
                "No distinct inner-ring reference insert was found; supply a reference angle."
            )
        row, column = ndimage.center_of_mass(component)
        dx_mm = (column - center[0]) * spacing[1]
        dy_mm = (row - center[1]) * spacing[0]
        return math.degrees(math.atan2(dy_mm, dx_mm)) % 360

    @staticmethod
    def _insert_boundary(
        smoothed: np.ndarray, center: tuple[float, float], spacing: tuple[float, float]
    ) -> ACRCT467Boundary | None:
        row_radius, column_radius = 22 / spacing[0], 22 / spacing[1]
        top, bottom = math.ceil(center[1] - row_radius), math.floor(center[1] + row_radius) + 1
        left, right = math.ceil(center[0] - column_radius), math.floor(center[0] + column_radius) + 1
        if not (0 <= top < bottom <= smoothed.shape[0] and 0 <= left < right <= smoothed.shape[1]):
            return None
        rows, columns = np.ogrid[top:bottom, left:right]
        radii = np.hypot((rows - center[1]) * spacing[0], (columns - center[0]) * spacing[1])
        patch = smoothed[top:bottom, left:right]
        background = patch[(radii >= 19) & (radii <= 22)]
        background_median = float(np.median(background))
        contrast = float(np.median(patch[radii <= 5])) - background_median
        noise = 1.4826 * np.median(np.abs(background - background_median))
        if abs(contrast) <= 5 * noise:
            return None
        threshold = background_median + contrast / 2
        labels, _ = ndimage.label(((patch - threshold) * contrast > 0) & (radii <= 22))
        label = labels[round(center[1]) - top, round(center[0]) - left]
        if not label:
            return None
        component = labels == label
        diameter = 2 * math.sqrt(component.sum() * math.prod(spacing) / math.pi)
        row, column = ndimage.center_of_mass(component)
        location = (float(column + left), float(row + top))
        displacement = math.hypot(
            (location[0] - center[0]) * spacing[1],
            (location[1] - center[1]) * spacing[0],
        )
        if not 22 <= diameter <= 39 or displacement > 5 or np.any(component & (radii > 21)):
            return None
        return ACRCT467Boundary(
            center_px=location,
            equivalent_diameter_mm=diameter,
            center_offset_mm=displacement,
            local_contrast=contrast,
        )

    def _placement_samples(
        self,
        array: np.ndarray,
        center: tuple[float, float],
        radius: float,
        spacing: tuple[float, float],
    ) -> list[ACRCT467PlacementSample]:
        samples = []
        for x_shift in (-1.0, 0.0, 1.0):
            for y_shift in (-1.0, 0.0, 1.0):
                location = (center[0] + x_shift / spacing[1], center[1] + y_shift / spacing[0])
                values = self._disk_values(array, location, radius, spacing)
                samples.append(
                    ACRCT467PlacementSample(
                        offset_mm=(x_shift, y_shift),
                        pixel_count=values.size,
                        mean=float(np.mean(values)),
                        median=float(np.median(values)),
                        stdev=float(np.std(values)),
                    )
                )
        return samples

    @staticmethod
    def _numeric_tag(dataset: Dataset, name: str) -> float | None:
        value = dataset.get(name)
        if value is None or value == "":
            return None
        number = float(value)
        return number if math.isfinite(number) else None

    def _acquisition(self, dataset: Dataset) -> ACRCT467Acquisition:
        kernel = dataset.get("ConvolutionKernel")
        image_type = dataset.get("ImageType")
        return ACRCT467Acquisition(
            image_type=[image_type] if isinstance(image_type, str) else list(image_type or ()),
            convolution_kernel=[kernel] if isinstance(kernel, str) else list(kernel or ()),
            tube_voltage_kvp=self._numeric_tag(dataset, "KVP"),
            tube_current_ma=self._numeric_tag(dataset, "XRayTubeCurrent"),
            exposure_mas=self._numeric_tag(dataset, "Exposure"),
            ctdi_vol_mgy=self._numeric_tag(dataset, "CTDIvol"),
            reconstruction_diameter_mm=self._numeric_tag(dataset, "ReconstructionDiameter"),
        )

    @staticmethod
    def _disk_values(
        array: np.ndarray,
        center: tuple[float, float],
        radius_mm: float,
        spacing: tuple[float, float],
    ) -> np.ndarray:
        row_radius, column_radius = radius_mm / spacing[0], radius_mm / spacing[1]
        top, bottom = math.ceil(center[1] - row_radius), math.floor(center[1] + row_radius) + 1
        left, right = math.ceil(center[0] - column_radius), math.floor(center[0] + column_radius) + 1
        if not (0 <= top <= bottom <= array.shape[0] and 0 <= left <= right <= array.shape[1]):
            raise ValueError("A Gammex 467 sampling disk falls outside the pixel grid.")
        rows, columns = np.ogrid[top:bottom, left:right]
        dy_mm = (rows - center[1]) * spacing[0]
        dx_mm = (columns - center[0]) * spacing[1]
        disk = dx_mm**2 + dy_mm**2 <= radius_mm**2
        return array[top:bottom, left:right][disk]


class MRSlice11PositionModule(CatPhanModule):
    common_name = "Slice Position, Slice 11"
    roi_settings = {
        "Left": {"width": 2, "height": 25, "distance": 65, "angle": 2.5},
        "Right": {"width": 2, "height": 25, "distance": 65, "angle": -2.5},
    }
    rois: dict = {}

    def _setup_rois(self) -> None:
        for name, setting in self.roi_settings.items():
            # angle is +90 because pointing right is 0, and these rois move downward, not rightward
            self.rois[name] = RectangleROI.from_phantom_center(
                self.image,
                setting["width_pixels"],
                setting["height_pixels"],
                self.catphan_roll - 90 + setting["angle"],
                setting["distance_pixels"],
                self.phan_center,
            )

    @property
    def bar_difference_mm(self) -> float:
        """The difference in height between the two angled bars"""
        idxs = []
        for roi in (self.rois["Right"], self.rois["Left"]):
            prof = roi.pixel_array.max(axis=np.argmin(roi.pixel_array.shape))
            mid_height = (prof.max() - prof.min()) / 2 + prof.min()
            idx = find_nearest_idx(prof, mid_height)
            idxs.append(idx)
        return (idxs[0] - idxs[1]) * self.mm_per_pixel

    @property
    def slice_shift_mm(self) -> float:
        """The effective shift in phantom position in the S/I direction. Because bars are at 45 degrees, the shift is half the bar difference"""
        return self.bar_difference_mm / 2

    def plot_rois(self, axis: plt.Axes) -> None:
        """Plot the ROIs to the axis.

        We overload because simple rectangle ROIs don't have a pass/fail color.
        """
        for roi in self.rois.values():
            roi.plot2axes(axis, edgecolor="blue")

    def plotly_rois(self, fig: go.Figure) -> None:
        for name, roi in self.rois.items():
            roi.plotly(fig, line_color="blue", name=name)


class MRMediumSlice11PositionModule(MRSlice11PositionModule):
    roi_settings = {
        "Left": {"width": 2, "height": 25, "distance": 60, "angle": 2.5},
        "Right": {"width": 2, "height": 25, "distance": 60, "angle": -2.5},
    }


class MRSlice11ModuleOutput(BaseModel):
    """This class should not be called directly. It is returned by the ``results_data()`` method.

    Use the following attributes as normal class attributes."""

    offset: int = Field(
        description="The offset of the phantom in mm from the origin slice."
    )
    roi_settings: dict = Field(
        description="The ROI settings. The keys are the ROI names."
    )
    rois: dict = Field(
        description="The results of the left and right bar ROIs. The key is the name of the bar"
    )
    bar_difference_mm: float = Field(
        description="The difference in bar positions in mm.",
        title="Bar Difference (mm)",
    )
    slice_shift_mm: float = Field(
        description="The measure shift in slice position compared to nominal.",
        title="Slice Shift (mm)",
    )


class MRSlice1Module(CatPhanModule):
    common_name = "Slice 1 (Thickness, Offset, Resolution)"
    slice_lines: dict[str, Line]
    thickness_rois: dict[str, ThicknessROI] = {}
    thickness_roi_settings = {
        "Top": {"width": 100, "height": 3, "distance": -3},
        "Bottom": {"width": 100, "height": 3, "distance": 2.5},
    }
    roi_settings = {
        "Row Reference": {"radius": 9, "distance": 58, "angle": 135, "lp/mm": 0},
        "Col Reference": {"radius": 9, "distance": 58, "angle": 135, "lp/mm": 0},
        "Row 1.1": {"radius": 3, "distance": 40, "angle": 116, "lp/mm": 1 / 1.1},
        "Col 1.1": {"radius": 3, "distance": 44, "angle": 104, "lp/mm": 1 / 1.1},
        "Row 1.0": {"radius": 3, "distance": 36, "angle": 81, "lp/mm": 1.0},
        "Col 1.0": {"radius": 3, "distance": 44, "angle": 74, "lp/mm": 1.0},
        "Row 0.9": {"radius": 2, "distance": 46, "angle": 52, "lp/mm": 1 / 0.9},
        "Col 0.9": {"radius": 2, "distance": 55, "angle": 51, "lp/mm": 1 / 0.9},
    }
    position_roi_settings = {
        "Left": {"width": 2, "height": 25, "distance": 65, "angle": 2.5},
        "Right": {"width": 2, "height": 25, "distance": 65, "angle": -2.5},
    }
    position_rois: dict = {}
    rois: dict[str, HighContrastDiskROI]
    spacings = [0, 1 / 1.1, 1, 1 / 0.9]

    def _setup_rois(self) -> None:
        # thickness
        for name, setting in self.thickness_roi_settings.items():
            # angle is +90 because pointing right is 0, and these rois move downward, not rightward
            self.thickness_rois[name] = ThicknessROI.from_phantom_center(
                self.image,
                setting["width_pixels"],
                setting["height_pixels"],
                self.catphan_roll + 90,
                setting["distance_pixels"],
                self.phan_center,
            )
        # spatial res
        for name, setting in self.roi_settings.items():
            self.rois[name] = HighContrastDiskROI.from_phantom_center(
                self.image,
                setting["angle_corrected"],
                setting["radius_pixels"],
                setting["distance_pixels"],
                self.phan_center,
                contrast_threshold=1.0,  # fixed to 1 so everything passes. We aren't evaluating pass/fail here
            )
        # slice position
        for name, setting in self.position_roi_settings.items():
            # angle is +90 because pointing right is 0, and these rois move downward, not rightward
            self.position_rois[name] = ThicknessROI.from_phantom_center(
                self.image,
                setting["width_pixels"],
                setting["height_pixels"],
                self.catphan_roll - 90 + setting["angle"],
                setting["distance_pixels"],
                self.phan_center,
            )

    def plot_rois(self, axis: plt.Axes) -> None:
        for roi in self.position_rois.values():
            roi.plot2axes(axis, edgecolor="blue")
        for roi in self.thickness_rois.values():
            roi.plot2axes(axis, edgecolor="blue")
        for roi, mtf in zip(self.rois.values(), self.rois.values()):
            roi.plot2axes(axis, edgecolor="g")

    def plotly_rois(self, fig: go.Figure) -> None:
        for name, roi in self.position_rois.items():
            roi.plotly(fig, line_color="blue", name=name)
        for name, roi in self.thickness_rois.items():
            roi.plotly(fig, line_color="blue", name=name)
        for name, roi in self.rois.items():
            roi.plotly(fig, line_color="green", name=name)

    @property
    def bar_difference_mm(self) -> float:
        """The difference in height between the two angled bars"""
        left_array = self.position_rois["Left"].long_profile.values
        left_mid_height = (left_array.max() - left_array.min()) / 2 + left_array.min()
        left_idx = find_nearest_idx(left_array, left_mid_height)
        right_array = self.position_rois["Right"].long_profile.values
        right_mid_height = (
            right_array.max() - right_array.min()
        ) / 2 + right_array.min()
        right_idx = find_nearest_idx(right_array, right_mid_height)
        return (right_idx - left_idx) * self.mm_per_pixel

    @property
    def slice_shift_mm(self) -> float:
        """The effective shift in phantom position in the S/I direction. Because bars are at 45 degrees, the shift is half the bar difference"""
        return self.bar_difference_mm / 2

    @property
    def measured_slice_thickness_mm(self) -> float:
        """The slice thickness as determined by the two angled ROIs in the center of Slice 1"""
        top = self.thickness_rois["Top"].wire_fwhm * self.mm_per_pixel
        bottom = self.thickness_rois["Bottom"].wire_fwhm * self.mm_per_pixel
        return 0.2 * (top * bottom) / (top + bottom)

    @property
    def row_mtf(self) -> MTF:
        """The MTF of the spatial resolution module looking at the row-wise ROIs"""
        return MTF.from_high_contrast_diskset(
            spacings=self.spacings,
            diskset=list(roi for name, roi in self.rois.items() if "Row" in name),
        )

    @property
    def col_mtf(self) -> MTF:
        """The MTF of the spatial resolution module looking at the column-wise ROIs"""
        return MTF.from_high_contrast_diskset(
            spacings=self.spacings,
            diskset=list(roi for name, roi in self.rois.items() if "Col" in name),
        )


class MRMediumSlice1Module(MRSlice1Module):
    spacings = [0, 1 / 1.1, 1, 1 / 0.9, 1 / 0.8]
    roi_settings = {
        "Row Reference": {"radius": 9, "distance": 55, "angle": 138.3, "lp/mm": 0},
        "Col Reference": {"radius": 9, "distance": 55, "angle": 138.3, "lp/mm": 0},
        "Row 1.1": {"radius": 3, "distance": 39.0, "angle": 121.0, "lp/mm": 1 / 1.1},
        "Col 1.1": {"radius": 3, "distance": 42.4, "angle": 108.0, "lp/mm": 1 / 1.1},
        "Row 1.0": {"radius": 3, "distance": 33.3, "angle": 89.2, "lp/mm": 1.0},
        "Col 1.0": {"radius": 3, "distance": 41.0, "angle": 78.8, "lp/mm": 1.0},
        "Row 0.9": {"radius": 2, "distance": 40.1, "angle": 58.5, "lp/mm": 1 / 0.9},
        "Col 0.9": {"radius": 2, "distance": 48.3, "angle": 56.1, "lp/mm": 1 / 0.9},
        "Row 0.8": {"radius": 2, "distance": 52, "angle": 40.4, "lp/mm": 1 / 0.8},
        "Col 0.8": {"radius": 2, "distance": 59.6, "angle": 41, "lp/mm": 1 / 0.8},
    }
    position_roi_settings = {
        "Left": {"width": 2, "height": 25, "distance": 58, "angle": 2.5},
        "Right": {"width": 2, "height": 25, "distance": 58, "angle": -2.5},
    }


class MRSlice1ModuleOutput(BaseModel):
    """This class should not be called directly. It is returned by the ``results_data()`` method.

    Use the following attributes as normal class attributes."""

    offset: int = Field(
        description="The offset of the phantom in mm from the origin slice."
    )
    roi_settings: dict = Field(
        description="A dictionary of the ROI settings. The keys are the ROI names."
    )
    rois: dict = Field(
        description=" A dictionary of the analyzed MTF ROIs. The key is the name of the ROI; e.g. ``Row 1.1``."
    )
    bar_difference_mm: float = Field(
        description="The difference in bar positions in mm.",
        title="Bar Difference (mm)",
    )
    slice_shift_mm: float = Field(
        description="The measured shift in slice position compared to nominal.",
        title="Slice Shift (mm)",
    )
    measured_slice_thickness_mm: float = Field(
        description="The measured slice thickness in mm.",
        title="Measured Slice Thickness (mm)",
    )
    row_mtf_50: float | None = Field(
        description="The MTF at 50% for the row-based ROIs, or None when the requested percentage is outside the measured row MTF range.",
        title="Row-wise 50% MTF (lp/mm)",
    )
    col_mtf_50: float | None = Field(
        description="The MTF at 50% for the column-based ROIs, or None when the requested percentage is outside the measured column MTF range.",
        title="Column-wise 50% MTF (lp/mm)",
    )
    row_mtf_lp_mm: dict[int, float | None] = Field(
        description="A key-value pair of the MTF. The key is the relative resolution in % and the value is the lp/mm at that resolution, or None when the requested percentage is outside the measured row MTF range.",
        title="MTF (lp/mm)",
    )
    col_mtf_lp_mm: dict[int, float | None] = Field(
        description="A key-value pair of the MTF. The key is the relative resolution in % and the value is the lp/mm at that resolution, or None when the requested percentage is outside the measured column MTF range.",
        title="MTF (lp/mm)",
    )


class MRUniformityModule(CatPhanModule):
    """Class for analysis of the Uniformity slice of the CTP module. Measures 5 ROIs around the slice that
    should all be close to the same value.
    """

    common_name = "Signal Uniformity"
    roi_settings = {
        "Center": {
            "angle": 90,
            "distance": 5,
            "radius": 80,
        },  # 80 radius ~= 200cm2, per the manual
    }
    ghost_roi_settings = {
        # size of ~900mm2 per the manual
        "Top": {"angle": -90, "distance": 110, "width": 60, "height": 15},
        "Bottom": {"angle": 90, "distance": 110, "width": 60, "height": 15},
        "Left": {"angle": 180, "distance": 110, "width": 15, "height": 60},
        "Right": {"angle": 0, "distance": 110, "width": 15, "height": 60},
    }
    ghost_rois: dict = {}

    def __init__(self, catphan, offset):
        self.tesla = float(catphan.dicom_stack.metadata.MagneticFieldStrength)
        super().__init__(catphan, tolerance=None, offset=offset)

    def _setup_rois(self) -> None:
        super()._setup_rois()
        for name, roi in self.ghost_roi_settings.items():
            self.ghost_rois[name] = RectangleROI.from_phantom_center(
                self.image,
                roi["width_pixels"],
                roi["height_pixels"],
                roi["angle"] + self.catphan_roll,
                roi["distance_pixels"],
                self.phan_center,
            )

    def plot_rois(self, axis: plt.Axes) -> None:
        super().plot_rois(axis)
        for roi in self.ghost_rois.values():
            roi.plot2axes(axis, edgecolor="yellow")

    def plotly_rois(self, fig: go.Figure) -> None:
        super().plotly_rois(fig)
        for name, roi in self.ghost_rois.items():
            roi.plotly(fig, line_color="yellow", name=name)

    @property
    def percent_image_uniformity(self) -> float:
        """PIU value calculated via section 5.3 of the manual"""
        piu_high = np.percentile(self.rois["Center"].pixel_values, 99)
        piu_low = np.percentile(self.rois["Center"].pixel_values, 1)
        return 100 * (1 - ((piu_high - piu_low) / (piu_high + piu_low)))

    @property
    def piu_passed(self) -> bool:
        """Section 5.4"""
        if self.tesla < 3:
            return self.percent_image_uniformity > 85
        else:
            return self.percent_image_uniformity > 80

    @property
    def ghosting_ratio(self) -> float:
        """Ghosting ratio of section 6.3 of the manual"""
        top = self.ghost_rois["Top"].pixel_value
        bottom = self.ghost_rois["Bottom"].pixel_value
        left = self.ghost_rois["Left"].pixel_value
        right = self.ghost_rois["Right"].pixel_value
        return abs(
            ((top + bottom) - (left + right)) / (2 * self.rois["Center"].pixel_value)
        )

    @property
    def psg(self) -> float:
        """Percent Signal Ghosting"""
        return self.ghosting_ratio * 100

    @property
    def psg_passed(self) -> bool:
        """Whether the PSG is within tolerance"""
        return self.psg < 3.0


class MRMediumUniformityModule(MRUniformityModule):
    roi_settings = {
        "Center": {
            "angle": 90,
            "distance": 5,
            "radius": 60,
        }
    }

    @property
    def piu_passed(self) -> bool:
        """Section 5.4; medium has different settings than large"""
        if self.tesla < 3:
            return self.percent_image_uniformity > 90
        else:
            return self.percent_image_uniformity > 85


class MRUniformityModuleOutput(BaseModel):
    """This class should not be called directly. It is returned by the ``results_data()`` method.

    Use the following attributes as normal class attributes."""

    offset: int = Field(
        description="The offset of the phantom in mm from the origin slice."
    )
    roi_settings: dict = Field(
        description="A dictionary of the ROI settings. The keys are the ROI names."
    )
    rois: dict = Field(description="A dictionary of the analyzed ROIs.")
    ghost_roi_settings: dict = Field(
        description="A dictionary of the ghost ROI settings. The keys are the ROI names."
    )
    ghost_rois: dict = Field(description="A dictionary of the ghost ROIs.")
    psg: float = Field(
        description="The percent signal ghosting.", title="Percent Signal Ghosting"
    )
    ghosting_ratio: float = Field(
        description="The ghosting ratio.", title="Ghosting Ratio"
    )
    piu_passed: bool = Field(
        description="Whether the percent integral uniformity passed the test."
    )
    piu: float = Field(
        description="The percent integral uniformity.",
        title="Percent Integral Uniformity",
    )


class MRLowContrastModule(CatPhanModule):
    """Class for analysis of the Low Contrast of a single slice of the ACR MRI Large phantom.

    It counts complete spokes where all 3 disks are visible.
    Each slice has 10 spokes arranged in a circular pattern, with spoke diameters decreasing
    clockwise from 7.0 mm (spoke 1) to 1.5 mm (spoke 10).
    """

    attr_name = "low_contrast_module"

    low_contrast_region_radius = 40  # mm

    _distances = [12.75, 25.50, 38.25]
    _rsf = 0.8 / 2  # roi_size_factor (/2 to convert diameter to radius)
    roi_settings = {
        "spoke_1": {"angle": -90, "radius": 7.0 * _rsf, "distances": _distances},
        "spoke_2": {"angle": -54, "radius": 6.4 * _rsf, "distances": _distances},
        "spoke_3": {"angle": -18, "radius": 5.8 * _rsf, "distances": _distances},
        "spoke_4": {"angle": 18, "radius": 5.2 * _rsf, "distances": _distances},
        "spoke_5": {"angle": 54, "radius": 4.6 * _rsf, "distances": _distances},
        "spoke_6": {"angle": 90, "radius": 3.9 * _rsf, "distances": _distances},
        "spoke_7": {"angle": 126, "radius": 3.3 * _rsf, "distances": _distances},
        "spoke_8": {"angle": 162, "radius": 2.7 * _rsf, "distances": _distances},
        "spoke_9": {"angle": 198, "radius": 2.1 * _rsf, "distances": _distances},
        "spoke_10": {"angle": 234, "radius": 1.5 * _rsf, "distances": _distances},
    }

    _bg_distances = [0, 20, 32]
    _bg_roi_radius = 2.5
    _angle_offset = 0
    background_roi_settings = {
        "spoke_1": {
            "angle": -90 + _angle_offset,
            "radius": _bg_roi_radius,
            "distances": _bg_distances,
        },
        "spoke_2": {
            "angle": -54 + _angle_offset,
            "radius": _bg_roi_radius,
            "distances": _bg_distances,
        },
        "spoke_3": {
            "angle": -18 + _angle_offset,
            "radius": _bg_roi_radius,
            "distances": _bg_distances,
        },
        "spoke_4": {
            "angle": 18 + _angle_offset,
            "radius": _bg_roi_radius,
            "distances": _bg_distances,
        },
        "spoke_5": {
            "angle": 54 + _angle_offset,
            "radius": _bg_roi_radius,
            "distances": _bg_distances,
        },
        "spoke_6": {
            "angle": 90 + _angle_offset,
            "radius": _bg_roi_radius,
            "distances": _bg_distances,
        },
        "spoke_7": {
            "angle": 126 + _angle_offset,
            "radius": _bg_roi_radius,
            "distances": _bg_distances,
        },
        "spoke_8": {
            "angle": 162 + _angle_offset,
            "radius": _bg_roi_radius,
            "distances": _bg_distances,
        },
        "spoke_9": {
            "angle": 198 + _angle_offset,
            "radius": _bg_roi_radius,
            "distances": _bg_distances,
        },
        "spoke_10": {
            "angle": 234 + _angle_offset,
            "radius": _bg_roi_radius,
            "distances": _bg_distances,
        },
    }

    def __init__(
        self,
        catphan,
        contrast_method: str,
        tolerance: float,
        offset: int,
        spoke_start_angle: float,
        visibility_sanity_multiplier: float,
    ):
        self.contrast_method = contrast_method
        self._spoke_start_angle = spoke_start_angle
        self.visibility_sanity_multiplier = visibility_sanity_multiplier
        super().__init__(catphan, tolerance, offset)

    @property
    def window_min(self) -> int:
        return int(self.low_contrast_region.min)

    @property
    def window_max(self) -> int:
        return int(self.low_contrast_region.max)

    def _convert_units_in_settings(self) -> None:
        super()._convert_units_in_settings()
        for roi, settings in self.roi_settings.items():
            settings["distances_pixels"] = [
                d * self.scaling_factor / self.mm_per_pixel
                for d in settings["distances"]
            ]
        for roi, settings in self.background_roi_settings.items():
            settings["distances_pixels"] = [
                d * self.scaling_factor / self.mm_per_pixel
                for d in settings["distances"]
            ]

    def _setup_rois(self) -> None:
        """Set up ROIs for all spokes and disks.

        Creates low contrast and background ROIs for each of the 3 disks in each of the 10 spokes.
        It assumes ``roi_settings`` and ``background_roi_settings`` have the same dictionary structure.
        ROIs are organized as nested structure: rois[spoke_num][disk_num]
        """
        self.common_name = f"Low Contrast - {self.slice_num + 1}"
        self.rois: dict[str, list[LowContrastDiskROI]] = {}
        self.background_rois: dict[str, list[LowContrastDiskROI]] = {}

        ### Detect the low contrast region containing the objects
        rad_pix = self.low_contrast_region_radius / self.mm_per_pixel
        nominal_area = rad_pix * rad_pix * np.pi
        larr, _, _ = get_regions(self)
        larr = measure.label(~larr)
        prop = measure.regionprops(larr)
        lc_region = min(prop, key=lambda x: np.abs(x.area - nominal_area))
        actual_area = lc_region.area
        is_proper_size = abs(actual_area / nominal_area - 1) < 0.3
        if not is_proper_size:
            raise ValueError("Unable to find the Low Contrast region.")
        centroid = lc_region.centroid
        lc_center = Point(centroid[1], centroid[0])
        lc_region_radius = rad_pix
        self.low_contrast_region = DiskROI(self.image, lc_region_radius, lc_center)

        ### Setup objects (it assumes low contrast and background ROIs have the same dictionary structure.)
        if len(self.roi_settings) != len(self.background_roi_settings):
            msg = "There should be the same number of ROIs for low contrast and background."
            raise ValueError(msg)
        if len(self.roi_settings.keys()) != len(self.background_roi_settings.keys()):
            msg = "Low contrast and background dictionaries must have the same keys."
            raise ValueError(msg)
        for spoke_name in self.roi_settings.keys():
            lc_rois: list[LowContrastDiskROI] = []  # low contrast
            bg_rois: list[LowContrastDiskROI] = []  # background
            for idx in range(len(self.roi_settings[spoke_name]["distances_pixels"])):
                bg_setting = self.background_roi_settings[spoke_name]
                bg_roi = LowContrastDiskROI.from_phantom_center(
                    self.image,
                    bg_setting["angle_corrected"] + self._spoke_start_angle,
                    bg_setting["radius_pixels"],
                    bg_setting["distances_pixels"][idx],
                    lc_center,
                )
                bg_rois.append(bg_roi)

                lc_setting = self.roi_settings[spoke_name]
                lc_roi = LowContrastDiskROI.from_phantom_center(
                    self.image,
                    lc_setting["angle_corrected"] + self._spoke_start_angle,
                    max(lc_setting["radius_pixels"], 1),  # ensure 2 pix to avoid std=0#
                    lc_setting["distances_pixels"][idx],
                    lc_center,
                    contrast_reference=bg_roi.mean,
                    contrast_method=self.contrast_method,
                    visibility_threshold=self.tolerance,
                )
                lc_rois.append(lc_roi)
            self.rois[spoke_name] = lc_rois
            self.background_rois[spoke_name] = bg_rois

    @property
    def score(self) -> int:
        """The number of complete spokes for this slice.

        A spoke is complete only if all 3 disks are visible (visibility > threshold).
        Stop counting at the first incomplete spoke.
        """
        spoke1 = self.rois[list(self.roi_settings.keys())[0]]
        max_visibility = max(r.visibility for r in spoke1)
        sanity_visibility = max_visibility * self.visibility_sanity_multiplier
        is_visible = [
            all(self.roi_is_visible(r, sanity_visibility) for r in s)
            for s in self.rois.values()
        ]
        return len(is_visible) if all(is_visible) else np.argmin(is_visible)

    @staticmethod
    def roi_is_visible(roi: LowContrastDiskROI, sanity_visibility: float) -> bool:
        """Helper method to determine if a roi is visible, including sanity check"""
        return roi.passed_visibility and roi.visibility < sanity_visibility

    def as_dict(self) -> dict:
        """Dump important data as a dictionary."""
        return {
            spoke_name: [roi.as_dict() for roi in spoke_rois]
            for spoke_name, spoke_rois in self.rois.items()
        }

    def plot_rois(self, axis: plt.Axes) -> None:
        """Plot the ROIs to the axis."""
        spoke1 = self.rois[list(self.roi_settings.keys())[0]]
        max_visibility = max(r.visibility for r in spoke1)
        sanity_visibility = max_visibility * self.visibility_sanity_multiplier

        # low contrast region
        self.low_contrast_region.plot2axes(axis, edgecolor="blue")

        # low contrast rois
        for spoke in self.rois.values():
            for roi in spoke:
                roi_is_visible = self.roi_is_visible(roi, sanity_visibility)
                color = "green" if roi_is_visible else "red"
                roi.plot2axes(axis, edgecolor=color)

        # background rois
        for spoke in self.background_rois.values():
            for roi in spoke:
                roi.plot2axes(axis, edgecolor="blue")

    def plotly_rois(self, fig: go.Figure) -> None:
        spoke1 = self.rois[list(self.roi_settings.keys())[0]]
        max_visibility = max(r.visibility for r in spoke1)
        sanity_visibility = max_visibility * self.visibility_sanity_multiplier

        # low contrast region
        self.low_contrast_region.plotly(fig, line_color="blue")

        # low contrast rois
        for spoke in self.rois.values():
            for roi in spoke:
                roi_is_visible = self.roi_is_visible(roi, sanity_visibility)
                color = "green" if roi_is_visible else "red"
                roi.plotly(fig, line_color=color)

        # background rois
        for spoke in self.background_rois.values():
            for roi in spoke:
                roi.plotly(fig, line_color="blue")


class MRLowContrastModuleOutput(BaseModel):
    """This class should not be called directly. It is returned by the ``results_data()`` method.

    Use the following attributes as normal class attributes."""

    offset: float = Field(
        description="The offset of the slice in mm from the origin slice."
    )
    slice_num: int = Field(description="The slice number.")
    spoke_settings: dict = Field(description="A dictionary of the spoke settings.")
    background_settings: dict = Field(
        description="A dictionary of the background roi settings."
    )
    score: int = Field(description="The score of the spoke.")
    spokes: dict = Field(description="A dictionary of the spokes.")


class MRLowContrastMultiSliceModule:
    """Class for managing Low Contrast analysis across multiple slices."""

    roi_settings = {
        "slice_8": {
            "offset": MR_LOW_CONTRAST_MODULE_OFFSETS_MM[8],
            "spoke_start_angle": 0,
        },
        "slice_9": {
            "offset": MR_LOW_CONTRAST_MODULE_OFFSETS_MM[9],
            "spoke_start_angle": 9,
        },
        "slice_10": {
            "offset": MR_LOW_CONTRAST_MODULE_OFFSETS_MM[10],
            "spoke_start_angle": 18,
        },
        "slice_11": {
            "offset": MR_LOW_CONTRAST_MODULE_OFFSETS_MM[11],
            "spoke_start_angle": 27,
        },
    }

    def __init__(
        self,
        catphan,
        contrast_method: str,
        visibility_threshold: float,
        visibility_sanity_multiplier: float,
    ):
        """Initialize the multi-slice Low Contrast Detectability module.

        Parameters
        ----------
        catphan : CatPhanBase
            The ACR MRI Large phantom instance.
        contrast_method : str
            The contrast equation to use. See :ref:`low_contrast_topic`.
        visibility_threshold : float
            The visibility threshold for determining if a disk is visible.
        visibility_sanity_multiplier: float
            This applies to the smallest low-contrast ROIs. Due to the low standard deviation in small ROIs,
            the calculated visibility can become significantly larger than is physically reasonable.
            This sanity threshold ensures that a small ROI is considered not visible if its visibility
            exceeds that of the first spoke by this multiplier.
        """

        self.slices: dict[str, MRLowContrastModule] = {}
        for key, value in self.roi_settings.items():
            self.slices[key] = MRLowContrastModule(
                catphan=catphan,
                contrast_method=contrast_method,
                tolerance=visibility_threshold,
                offset=value["offset"],
                spoke_start_angle=value["spoke_start_angle"],
                visibility_sanity_multiplier=visibility_sanity_multiplier,
            )

    @property
    def score(self) -> int:
        """Get the total low contrast detectability score as the sum of the number of complete spokes."""
        return sum(s.score for s in self.slices.values())


class MRLowContrastMultiSliceModuleOutput(BaseModel):
    """This class should not be called directly. It is returned by the ``results_data()`` method.

    Use the following attributes as normal class attributes."""

    score: int = Field(
        description="The total score across all slices (sum of all slice scores).",
        title="Total Score",
    )
    low_contrast_rois: dict = Field(description="Low contrast outputs.")


class GeometricDistortionModule(CatPhanModule):
    """Class for analysis of the Uniformity slice of the CTP module. Measures 5 ROIs around the slice that
    should all be close to the same value.
    """

    common_name = "Geometric Distortion"
    profiles: dict

    def _setup_rois(self) -> None:
        """This is mostly for plotting purposes. This is why we use FWXMProfile
        instead of FWXMProfilePhysical. The lines to plot should be in pixel coordinates, not physical.
        We convert to physical just for the field width calculation."""
        px_to_cut_off = int(round(5 / self.mm_per_pixel))
        self.profiles = {}
        threshold = threshold_otsu(image=self.image.array)
        bin_image = self.image.as_binary(threshold=threshold)
        bin_image = ndimage.binary_fill_holes(bin_image).astype(float)
        # calculate horizontal
        data = bin_image[int(self.phan_center.y), :]
        # cutoff 3mm from the search area
        f_data = fill_middle_zeros(data, cutoff_px=px_to_cut_off)
        prof = FWXMProfile(values=f_data)
        line = Line(
            Point(prof.field_edge_idx(side="left"), self.phan_center.y),
            Point(prof.field_edge_idx(side="right"), self.phan_center.y),
        )

        self.profiles["horizontal"] = {
            "width (mm)": prof.field_width_px * self.mm_per_pixel,
            "line": line,
        }
        # calculate vertical
        data = bin_image[:, int(self.phan_center.x)]
        f_data = fill_middle_zeros(data, cutoff_px=px_to_cut_off)
        prof = FWXMProfile(values=f_data)
        line = Line(
            Point(self.phan_center.x, prof.field_edge_idx(side="left")),
            Point(self.phan_center.x, prof.field_edge_idx(side="right")),
        )
        self.profiles["vertical"] = {
            "width (mm)": prof.field_width_px * self.mm_per_pixel,
            "line": line,
        }
        # calculate negative diagonal
        # calculate slope equation intercept
        # b = y - (+1)x
        b = self.phan_center.y - self.phan_center.x
        xs = np.arange(0, self.image.shape[1])
        ys = xs + b
        coords = ndimage.map_coordinates(bin_image, [ys, xs], order=1, mode="mirror")
        f_data = fill_middle_zeros(coords, cutoff_px=px_to_cut_off)
        prof = FWXMProfile(values=f_data)
        line = Line(
            Point(
                xs[int(round(prof.field_edge_idx(side="left")))],
                ys[int(round(prof.field_edge_idx(side="left")))],
            ),
            Point(
                xs[int(round(prof.field_edge_idx(side="right")))],
                ys[int(round(prof.field_edge_idx(side="right")))],
            ),
        )
        # pixels are now diagonal and thus spacing between pixels is now the hypotenuse
        # We don't have to fix the line above because that's in pixels. The issue is the
        # geometric distance and thus we only have to correct here.
        self.profiles["negative diagonal"] = {
            "width (mm)": prof.field_width_px * self.mm_per_pixel * math.sqrt(2),
            "line": line,
        }
        # calculate positive diagonal
        # calculate slope equation intercept
        # b = y - (-1)x
        b = self.phan_center.y + self.phan_center.x
        ys = -xs + b
        coords = ndimage.map_coordinates(bin_image, [ys, xs], order=1, mode="mirror")
        f_data = fill_middle_zeros(coords, cutoff_px=px_to_cut_off)
        prof = FWXMProfile(values=f_data)
        line = Line(
            Point(
                xs[int(round(prof.field_edge_idx(side="left")))],
                ys[int(round(prof.field_edge_idx(side="left")))],
            ),
            Point(
                xs[int(round(prof.field_edge_idx(side="right")))],
                ys[int(round(prof.field_edge_idx(side="right")))],
            ),
        )
        self.profiles["positive diagonal"] = {
            "width (mm)": prof.field_width_px * self.mm_per_pixel * math.sqrt(2),
            "line": line,
        }

    def plotly_rois(self, fig: go.Figure) -> None:
        for name, profile_data in self.profiles.items():
            profile_data["line"].plotly(fig, line_width=2, color="blue", name=name)

    def plot_rois(self, axis: plt.Axes):
        for name, profile_data in self.profiles.items():
            profile_data["line"].plot2axes(axis, width=2, color="blue")

    def distances(self) -> dict:
        """The measurements of the phantom size for all 4 lines in mm"""
        return {name: f"{p['width (mm)']:2.2f}mm" for name, p in self.profiles.items()}


class MRGeometricDistortionModuleOutput(BaseModel):
    """This class should not be called directly. It is returned by the ``results_data()`` method.

    Use the following attributes as normal class attributes."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    offset: int = Field(
        description="The offset of the phantom in mm from the origin slice."
    )
    profiles: dict[str, dict[str, float | LineSerialized]] = Field(
        description="A dictionary of the profiles used to measure the geometric distortion. The key is the name of the profile.",
        title="Profile widths (mm)",
    )
    distances: dict = Field(
        description="The lines measuring the ROI size. The key is the name of the line direction and the value is a string of the line length.",
        title="Distance measurements (mm)",
    )


class SagittalLocalizationModule:
    """Class for analysis of the Sagittal slice of the ACR Phantom."""

    """This class shares some similarities with CatphanModule but also has key differences.
    The options considered were: inherit to override, refactor into a common abstraction,
    or duplicate plot code for a standalone implementation.
    By design choice, the latter was taken."""

    common_name = "Sagittal Distortion"
    roi_settings: dict[str, dict[str, float]] = {
        "ROI1": {"offset": -60},
        "ROI2": {"offset": -25},
        "ROI3": {"offset": 25},
        "ROI4": {"offset": 75},
    }  # offsets in mm left/right from phantom centroid
    rois: dict[str, Line] = {}
    profiles: dict = {}
    image: DicomImage
    window_min: int | None = None  # plt visualization
    window_max: int | None = None  # plt visualization

    def __init__(self, image: DicomImage | None):
        if image is None:
            return

        self.image = image

        # The processing is consistent with the geometric distortion module
        threshold = round(threshold_li(image.array))
        bin_image = image.as_binary(threshold=threshold)
        bin_image = ndimage.binary_fill_holes(bin_image).astype(float)

        centroid = np.argwhere(bin_image).mean(axis=0)
        pixel_size = 1 / image.dpmm
        for key, val in self.roi_settings.items():
            offset_px = val["offset"] * pixel_size
            col = round(centroid[1] + offset_px)
            data = bin_image[:, col]
            prof = FWXMProfile(values=data)
            line = Line(
                Point(col, prof.field_edge_idx(side="left")),
                Point(col, prof.field_edge_idx(side="right")),
            )
            self.profiles[key] = {
                "width (mm)": prof.field_width_px * pixel_size,
                "line": line,
            }
            self.rois[key] = line

    def distances(self) -> dict:
        """The measurements of the phantom size in mm"""
        return {name: f"{p['width (mm)']:2.2f}mm" for name, p in self.profiles.items()}

    def plot(self, axis: plt.Axes):
        """Plot the image along with ROIs to an axis"""
        self.image.plot(ax=axis, show=False, vmin=self.window_min, vmax=self.window_max)
        self.plot_rois(axis)
        axis.autoscale(tight=True)
        axis.set_title(f"{self.common_name}")
        axis.axis("off")

    def plotly(self, **kwargs) -> go.Figure:
        """Plot the image along with the ROIs to a plotly figure."""
        fig = go.Figure()
        self.image.plotly(
            fig, show=False, zmin=self.window_min, zmax=self.window_max, **kwargs
        )
        self.plotly_rois(fig)
        add_title(fig, f"{self.common_name}")
        return fig

    def plotly_rois(self, fig: go.Figure) -> None:
        for name, profile_data in self.profiles.items():
            profile_data["line"].plotly(fig, line_width=2, color="blue", name=name)

    def plot_rois(self, axis: plt.Axes):
        for name, profile_data in self.profiles.items():
            profile_data["line"].plot2axes(axis, width=2, color="blue")


class MRSagittalLocalizationModuleOutput(BaseModel):
    """This class should not be called directly. It is returned by the ``results_data()`` method.

    Use the following attributes as normal class attributes."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    profiles: dict[str, dict[str, float | LineSerialized]] = Field(
        description="A dictionary of the profiles used to measure the geometric distortion. The key is the name of the profile.",
        title="Profile widths (mm)",
    )
    distances: dict = Field(
        description="The lines measuring the ROI size. The key is the name of the line direction and the value is a string of the line length.",
        title="Distance measurements (mm)",
    )


class ACRMRIResult(ResultBase):
    """This class should not be called directly. It is returned by the ``results_data()`` method.

    Use the following attributes as normal class attributes."""

    phantom_model: str = Field(description="The model of the phantom used.")
    phantom_roll_deg: float = Field(description="The roll of the phantom in degrees.")
    origin_slice: int = Field(
        description="The slice number of the 'origin' slice; for ACR this is Slice 1."
    )
    num_images: int = Field(description="The number of images in the passed dataset.")
    slice1: MRSlice1ModuleOutput = Field(
        description="The results for the 'Slice 1' module", title="Slice 1 Module"
    )
    slice11: MRSlice11ModuleOutput = Field(
        description="The results for the 'Slice 11' module", title="Slice 11 Module"
    )
    uniformity_module: MRUniformityModuleOutput = Field(
        description="Results from the uniformity module", title="Uniformity Module"
    )
    geometric_distortion_module: MRGeometricDistortionModuleOutput = Field(
        description="Results from the geometric distortion module",
        title="Geometric Distortion Module",
    )
    sagittal_localizer_module: MRSagittalLocalizationModuleOutput = Field(
        description="Results from the sagittal localizer module",
        title="Sagittal Localization Module",
    )
    low_contrast_multi_slice_module: MRLowContrastMultiSliceModuleOutput = Field(
        description="Results from the low contrast modules",
        title="Low Contrast Multi Slice",
    )


@capture_warnings
class ACRMRILarge(CatPhanBase, ResultsDataMixin[ACRMRIResult]):
    _model = "ACR MRI Large"
    catphan_radius_mm = 100
    min_num_images = 4
    air_bubble_radius_mm = 20
    slice1 = MRSlice1Module
    geometric_distortion = GeometricDistortionModule
    uniformity_module = MRUniformityModule
    slice11 = MRSlice11PositionModule
    sagittal_localization = SagittalLocalizationModule
    low_contrast_multi_slice = MRLowContrastMultiSliceModule
    has_sagittal_module: bool = False
    clip_in_localization = False
    low_contrast_visibility_sanity_multiplier: float

    @classmethod
    def from_demo_image(cls):
        raise NotImplementedError("There is no demo file for this analysis")

    def plot_analyzed_subimage(self, *args, **kwargs):
        raise NotImplementedError("Use `plot_images`")

    def save_analyzed_subimage(self, *args, **kwargs):
        raise NotImplementedError("Use `save_images`")

    def localize(self) -> None:
        self._phantom_center_func = self.find_phantom_axis()
        self.catphan_roll = self.find_phantom_roll() + self.angle_adjustment
        # now that we have the origin slice, ensure we have scanned all linked modules
        if not self._ensure_physical_scan_extent():
            raise ValueError(
                "The physical scan extent does not cover the extent of module configuration. "
                "This means not all modules were included in the scan. Rescan the phantom to include all "
                "relevant modules, or change the offset values."
            )

    def _module_offsets(self) -> list[float]:
        absolute_origin_position = self.dicom_stack[self.origin_slice].z_position
        relative_offsets_mm = [
            0,
            MR_GEOMETRIC_DISTORTION_MODULE_OFFSET_MM,
            MR_UNIFORMITY_MODULE_OFFSET_MM,
            MR_SLICE11_MODULE_OFFSET_MM,
        ]
        relative_offsets_mm.extend(MR_LOW_CONTRAST_MODULE_OFFSETS_MM.values())
        return [
            absolute_origin_position + offset_mm for offset_mm in relative_offsets_mm
        ]

    def find_phantom_roll(self) -> float:
        """Determine the "roll" of the phantom. This algorithm uses the circular left-upper hole on slice 1 as the reference

        Returns
        -------
        float : the angle of the phantom in **degrees**.
        """
        # get edges and make ROIs from it
        slice = Slice(self, self.origin_slice)
        larr, regions, _ = get_regions(slice)
        try:
            # find appropriate ROIs and grab the two most centrally positioned ones
            circle_bubbles = [
                r
                for r in regions
                if (self._is_right_area(r) and self._is_right_eccentricity(r))
            ]
            exact_size = np.pi * ((self.air_bubble_radius_mm / self.mm_per_pixel) ** 2)
            most_similar_bubble = sorted(
                circle_bubbles, key=lambda r: abs(r.filled_area - exact_size)
            )[0]
            y_dist = most_similar_bubble.centroid[0] - slice.phan_center.y
            x_dist = most_similar_bubble.centroid[1] - slice.phan_center.x
            phan_roll = np.arctan2(y_dist, x_dist)
            corrected_roll = (
                np.rad2deg(phan_roll) + 135
            )  # bubble is at top-left. perfect placement is -135
            return corrected_roll
        except Exception:
            raise RuntimeError(
                "Could not determine the roll of the phantom. Ensure the 20mm top-left circle is visible on Slice 1"
            )

    def analyze(
        self,
        echo_number: int | None = None,
        x_adjustment: float = 0,
        y_adjustment: float = 0,
        angle_adjustment: float = 0,
        roi_size_factor: float = 1,
        scaling_factor: float = 1,
        low_contrast_method: str = Contrast.WEBER,
        low_contrast_visibility_threshold: float = 0.001,
        low_contrast_visibility_sanity_multiplier: float = 3,
    ) -> None:
        """Analyze the ACR CT phantom

        Parameters
        ----------
        echo_number:
            The echo to analyze. If not passed, uses the minimum echo number found.
        x_adjustment: float
            A fine-tuning adjustment to the detected x-coordinate of the phantom center. This will move the
            detected phantom position by this amount in the x-direction in mm. Positive values move the phantom to the right.
        y_adjustment: float
            A fine-tuning adjustment to the detected y-coordinate of the phantom center. This will move the
            detected phantom position by this amount in the y-direction in mm. Positive values move the phantom down.
        angle_adjustment: float
            A fine-tuning adjustment to the detected angle of the phantom. This will rotate the phantom by this amount in degrees.
            Positive values rotate the phantom clockwise.
        roi_size_factor: float
            A fine-tuning adjustment to the ROI sizes of the phantom. This will scale the ROIs by this amount.
            Positive values increase the ROI sizes. In contrast to the scaling adjustment, this
            adjustment effectively makes the ROIs bigger or smaller, but does not adjust their position.
        scaling_factor: float
            A fine-tuning adjustment to the detected magnification of the phantom. This will zoom the ROIs and phantom outline (if applicable) by this amount.
            In contrast to the roi size adjustment, the scaling adjustment effectively moves the phantom and ROIs
            closer or further from the phantom center. I.e. this zooms the outline and ROI positions, but not ROI size.
        low_contrast_method: str
            The contrast equation to use in the low contrast modules. See
            :ref:`low_contrast_topic`.
        low_contrast_visibility_threshold: float
            The visibility threshold for determining if an object is visible in the low contrast modules.
        low_contrast_visibility_sanity_multiplier: float
            This applies to the smallest low-contrast ROIs. Due to the low standard deviation in small ROIs,
            the calculated visibility can become significantly larger than is physically reasonable.
            This sanity threshold ensures that a small ROI is considered not visible if its visibility
            exceeds that of the first spoke by this multiplier.
        """
        self.x_adjustment = x_adjustment
        self.y_adjustment = y_adjustment
        self.angle_adjustment = angle_adjustment
        self.roi_size_factor = roi_size_factor
        self.scaling_factor = scaling_factor
        self.low_contrast_visibility_sanity_multiplier = (
            low_contrast_visibility_sanity_multiplier
        )
        self._select_echo_images(echo_number)
        sagittal_image = self._select_sagittal_image()
        self.has_sagittal_module = sagittal_image is not None
        self.localize()
        self.slice1 = self.slice1(self, offset=0)
        self.geometric_distortion = self.geometric_distortion(
            self, offset=MR_GEOMETRIC_DISTORTION_MODULE_OFFSET_MM
        )
        self.uniformity_module = self.uniformity_module(
            self, offset=MR_UNIFORMITY_MODULE_OFFSET_MM
        )
        self.slice11 = self.slice11(self, offset=MR_SLICE11_MODULE_OFFSET_MM)
        self.sagittal_localization = self.sagittal_localization(sagittal_image)
        self.low_contrast_multi_slice = self.low_contrast_multi_slice(
            self,
            contrast_method=low_contrast_method,
            visibility_threshold=low_contrast_visibility_threshold,
            visibility_sanity_multiplier=low_contrast_visibility_sanity_multiplier,
        )

    def _select_echo_images(self, echo_number: int | None) -> None:
        """Select out the images that match the given echo number"""
        # we check for multiple echos. We only pick the first echo found.
        # this is probably not the best logic but we somehow have to pick
        # Echo Numbers is an int; https://dicom.innolitics.com/ciods/mr-image/mr-image/00180086

        # in case EchoNumbers isn't there, use all
        try:
            all_echos = {int(i.metadata.EchoNumbers) for i in self.dicom_stack}
        except AttributeError:
            # no manipulation; use all images
            return
        if echo_number is None:
            echo_number = min(all_echos)
            if len(all_echos) > 1:
                warnings.warn(
                    f"Multiple echoes found ({all_echos}) and no echo number was passed. Using echo # {echo_number}"
                )
        if echo_number not in all_echos:
            raise ValueError(
                f"Echo number {echo_number} was passed but not found in the dataset. Found echo numbers: {all_echos}. Remove the echo_number parameter or pick a valid echo number."
            )
        # drop images that don't have the same echo number
        to_pop = []
        for idx, img in enumerate([i for i in self.dicom_stack].copy()):
            if int(img.metadata.EchoNumbers) != echo_number:
                to_pop.append(idx)
        for idx in sorted(to_pop, reverse=True):
            del self.dicom_stack[idx]
            del self.dicom_stack.metadatas[idx]

    def _select_sagittal_image(self, max_dist: float = 0.01) -> DicomImage | None:
        """This function return the sagittal image from the dicom stack.

        Parameters
        ----------
        max_dist: float
            Max vectorial distance from the nominal to the actual image orientation.
        """
        # It uses the table in this article to find the sagittal image
        # https://www.kaggle.com/code/rickandjoe/mri-orientation-axial-sagittal-or-coronal

        nominal_sagittal_image_orientation = np.array([0, 1, 0, 0, 0, -1])
        metadatas = self.dicom_stack.metadatas
        image_orientation = [m.ImageOrientationPatient for m in metadatas]
        diff = np.array(image_orientation) - nominal_sagittal_image_orientation
        dist = np.linalg.norm(diff, axis=1)
        if np.sum(dist < max_dist) > 1:
            raise ValueError("There are too many sagittal images in the dataset.")
        min_value = dist.min()
        min_index = dist.argmin()
        if min_value >= max_dist:
            return None

        image = self.dicom_stack[min_index]
        # Remove from the stack since localize() assumes only axial slices are present
        del self.dicom_stack[min_index]
        del self.dicom_stack.metadatas[min_index]
        return image

    def plotly_analyzed_images(
        self,
        show: bool = True,
        show_colorbar: bool = True,
        show_legend: bool = True,
        **kwargs,
    ) -> dict[str, go.Figure]:
        """Plot the analyzed set of images to Plotly figures.

        Parameters
        ----------
        show : bool
            Whether to show the plot.
        show_colorbar : bool
            Whether to show the colorbar on the plot.
        show_legend : bool
            Whether to show the legend on the plot.
        kwargs
            Additional keyword arguments to pass to the plot.

        Returns
        -------
        dict
            A dictionary of the Plotly figures where the key is the name of the
            image and the value is the figure.
        """
        figs = {}
        # plot the images
        modules: list = [
            self.slice1,
            self.geometric_distortion,
            self.uniformity_module,
            self.slice11,
        ]
        modules.extend(list(self.low_contrast_multi_slice.slices.values()))
        if self.has_sagittal_module:
            modules.append(self.sagittal_localization)
        for module in modules:
            figs[module.common_name] = module.plotly(
                show_colorbar=show_colorbar, show_legend=show_legend, **kwargs
            )
        # side view
        figs["Side View"] = self.plotly_side_view(show_legend=show_legend)
        # mtf
        fig = go.Figure()
        self.slice1.row_mtf.plotly(fig=fig, name="Row-wise rMTF")
        figs["MTF"] = self.slice1.col_mtf.plotly(
            show_legend=show_legend,
            fig=fig,
            name="Column-wise rMTF",
            marker_color="orange",
        )

        if show:
            for fig in figs.values():
                fig.show()
        return figs

    def plot_analyzed_image(self, show: bool = True, **plt_kwargs) -> plt.Figure:
        """Plot the analyzed image

        Parameters
        ----------
        show
            Whether to show the image.
        plt_kwargs
            Keywords to pass to matplotlib for figure customization.
        """
        modules: list = [
            self.slice1,
            self.geometric_distortion,
            self.uniformity_module,
            self.slice11,
        ]
        modules.extend(list(self.low_contrast_multi_slice.slices.values()))
        if self.has_sagittal_module:
            modules.append(self.sagittal_localization)

        # set up grid and axes
        fig, axs = plt.subplots(3, 4, **plt_kwargs)
        axes = axs.ravel()
        ax_idx = -1
        for module in modules:
            ax_idx += 1
            module.plot(axes[ax_idx])

        ax_idx += 1
        self.plot_side_view(axes[ax_idx])
        ax_idx += 1
        self.slice1.row_mtf.plot(axes[ax_idx], label="Row-wise rMTF")
        self.slice1.col_mtf.plot(axes[ax_idx], label="Column-wise rMTF")
        axes[ax_idx].legend()

        for i in range(ax_idx + 1, len(axes)):
            axes[i].set_visible(False)

        # finish up
        plt.tight_layout()
        if show:
            plt.show()
        return fig

    def plot_images(self, show: bool = True, **plt_kwargs) -> dict[str, plt.Figure]:
        """Plot all the individual images separately

        Parameters
        ----------
        show
            Whether to show the images.
        plt_kwargs
            Keywords to pass to matplotlib for figure customization.
        """
        figs = {}
        # plot the images
        modules: dict = {
            "geometric": self.geometric_distortion,
            "slice 1": self.slice1,
            "signal uniformity": self.uniformity_module,
            "slice 11": self.slice11,
        }
        modules |= self.low_contrast_multi_slice.slices
        if self.has_sagittal_module:
            modules["sagittal"] = self.sagittal_localization
        for key, module in modules.items():
            fig, ax = plt.subplots(**plt_kwargs)
            module.plot(ax)
            figs[key] = fig
        # plot rMTF
        fig, ax = plt.subplots(**plt_kwargs)
        self.slice1.row_mtf.plot(ax, label="Row-wise rMTF")
        self.slice1.col_mtf.plot(ax, label="Column-wise rMTF")
        ax.legend()
        figs["rMTF"] = fig
        # plot the side view
        fig, ax = plt.subplots(**plt_kwargs)
        figs["side"] = fig
        self.plot_side_view(ax)

        if show:
            plt.show()
        return figs

    def _detected_modules(self) -> list[CatPhanModule]:
        return [
            self.slice1,
            self.slice11,
            self.uniformity_module,
            self.geometric_distortion,
        ]

    def save_images(
        self,
        directory: Path | str | None = None,
        to_stream: bool = False,
        **plt_kwargs,
    ) -> list[Path | BytesIO]:
        """Save separate images to disk or stream.

        Parameters
        ----------
        directory
            The directory to write the images to. If None, will use current working directory
        to_stream
            Whether to write to stream or disk. If True, will return streams. Directory is ignored in that scenario.
        plt_kwargs
            Keywords to pass to matplotlib for figure customization.
        """
        figs = self.plot_images(show=False, **plt_kwargs)
        paths = []
        for name, fig in figs.items():
            if to_stream:
                path = io.BytesIO()
            else:
                destination = Path(directory) if directory is not None else Path.cwd()
                path = (destination / name).with_suffix(".png").absolute()
            fig.savefig(path)
            paths.append(path)
        return paths

    def _quaac_datapoints(self) -> dict[str, QuaacDatum]:
        results_data = self.results_data(as_dict=True)
        data = {}

        data["Phantom Roll"] = QuaacDatum(
            value=results_data["phantom_roll_deg"],
            unit="degrees",
            description="The roll of the phantom in the image",
        )
        slice1_keys = (
            ("bar_difference_mm", "Bar Difference", "mm"),
            ("slice_shift_mm", "Slice Shift", "mm"),
            ("measured_slice_thickness_mm", "Measured Slice Thickness", "mm"),
            ("row_mtf_50", "Row-wise MTF 50%", "lp/mm"),
            ("col_mtf_50", "Column-wise MTF 50%", "lp/mm"),
        )
        for key, name, unit in slice1_keys:
            data[name] = QuaacDatum(
                value="N/A"
                if results_data["slice1"][key] is None
                else results_data["slice1"][key],
                unit=unit,
            )
        for name, roi in results_data["slice11"]["rois"].items():
            data[f"Slice 11 {name} ROI"] = QuaacDatum(
                value=roi["value"],
                unit="HU",
            )
        data["Slice 11 Bar Difference"] = QuaacDatum(
            value=results_data["slice11"]["bar_difference_mm"],
            unit="mm",
        )
        data["Slice 11 Slice Shift"] = QuaacDatum(
            value=results_data["slice11"]["slice_shift_mm"],
            unit="mm",
        )
        for name, roi in results_data["uniformity_module"]["rois"].items():
            data[f"Uniformity {name} ROI"] = QuaacDatum(
                value=roi["value"],
                unit="HU",
            )
        for name, roi in results_data["uniformity_module"]["ghost_rois"].items():
            data[f"Uniformity {name} Ghost ROI"] = QuaacDatum(
                value=roi["value"],
                unit="HU",
            )
        data["Percent Signal Ghosting"] = QuaacDatum(
            value=results_data["uniformity_module"]["psg"],
            unit="%",
        )
        data["Ghosting Ratio"] = QuaacDatum(
            value=results_data["uniformity_module"]["ghosting_ratio"],
            unit="",
        )
        data["Percent Integral Uniformity"] = QuaacDatum(
            value=results_data["uniformity_module"]["piu"],
            unit="%",
        )
        for name, line in results_data["geometric_distortion_module"][
            "profiles"
        ].items():
            data[f"Geometric Distortion {name} line length"] = QuaacDatum(
                value=line["width (mm)"],
                unit="mm",
            )
        for name, line in results_data["sagittal_localizer_module"]["profiles"].items():
            data[f"Localizer Distortion {name} line length"] = QuaacDatum(
                value=line["width (mm)"],
                unit="mm",
            )
        return data

    def publish_pdf(
        self,
        filename: str | Path,
        notes: str | None = None,
        open_file: bool = False,
        metadata: dict | None = None,
        logo: Path | str | None = None,
    ) -> None:
        """Publish (print) a PDF containing the analysis and quantitative results.

        Parameters
        ----------
        filename : (str, file-like object}
            The file to write the results to.
        notes : str, list of strings
            Text; if str, prints single line.
            If list of strings, each list item is printed on its own line.
        open_file : bool
            Whether to open the file using the default program after creation.
        metadata : dict
            Extra data to be passed and shown in the PDF. The key and value will be shown with a colon.
            E.g. passing {'Author': 'James', 'Unit': 'TrueBeam'} would result in text in the PDF like:
            --------------
            Author: James
            Unit: TrueBeam
            --------------
        logo: Path, str
            A custom logo to use in the PDF report. If nothing is passed, the default pylinac logo is used.
        """
        analysis_title = f"{self._model} Analysis"
        analysis_images = self.save_images(to_stream=True)

        canvas = pdf.PylinacCanvas(
            filename, page_title=analysis_title, metadata=metadata
        )
        if notes is not None:
            canvas.add_text(text="Notes:", location=(1, 4.5), font_size=14)
            canvas.add_text(text=notes, location=(1, 4))

        shortened_texts = [
            textwrap.wrap(r, width=110) for r in self.results(as_str=False)
        ]
        idx = 0
        for items in enumerate(shortened_texts):
            for text in items:
                canvas.add_text(text=text, location=(1.5, 25 - idx * 0.5))
                idx += 1
        for page, img in enumerate(analysis_images):
            canvas.add_new_page()
            canvas.add_image(img, location=(1, 5), dimensions=(18, 18))
        canvas.finish()

        if open_file:
            webbrowser.open(filename)

    def results(self, as_str: bool = True) -> str | tuple:
        """Return the results of the analysis as a string. Use with print()."""
        string = (
            f" - {self._model} Results - ",
            f"Geometric Distortions: {self.geometric_distortion.distances()}",
            f"Slice Thickness: {self.slice1.measured_slice_thickness_mm:2.2f}mm",
            f"Slice 1 S/I Position shift: {self.slice1.slice_shift_mm:2.2f}mm",
            f"Slice 11 S/I Position shift: {self.slice11.slice_shift_mm:2.2f}mm",
            f"Uniformity PIU: {self.uniformity_module.percent_image_uniformity:2.2f}",
            f"Percent-signal ghosting: {self.uniformity_module.psg:2.2f}%",
            f"Uniformity Center ROI standard deviation: {self.uniformity_module.rois['Center'].std:2.2f}",
            f"Row-wise MTF 50% (lp/mm): {format_resolution(self.slice1.row_mtf.relative_resolution(50))}",
            f"Column-wise MTF 50% (lp/mm): {format_resolution(self.slice1.col_mtf.relative_resolution(50))}",
            f"Sagittal Distortions: {self.sagittal_localization.distances()}",
            f"Low Contrast Score: {self.low_contrast_multi_slice.score}",
        )
        if as_str:
            return "\n".join(string)
        else:
            return string

    def _generate_results_data(self) -> ACRMRIResult:
        resolutions = range(10, 91, 10)  # 10-90% in 10% increments
        row_mtfs = {
            resolution: self.slice1.row_mtf.relative_resolution(resolution)
            for resolution in resolutions
        }
        col_mtfs = {
            resolution: self.slice1.col_mtf.relative_resolution(resolution)
            for resolution in resolutions
        }
        low_contrast_rois = {}
        for k, v in self.low_contrast_multi_slice.slices.items():
            low_contrast_rois[k] = MRLowContrastModuleOutput(
                offset=MR_LOW_CONTRAST_MODULE_OFFSETS_MM[v.slice_num + 1],
                slice_num=v.slice_num + 1,
                spoke_settings=v.roi_settings,
                background_settings=v.background_roi_settings,
                score=v.score,
                spokes=v.as_dict(),
            )

        return ACRMRIResult(
            phantom_model=self._model,
            phantom_roll_deg=self.catphan_roll,
            origin_slice=self.origin_slice,
            num_images=self.num_images,
            slice1=MRSlice1ModuleOutput(
                offset=0,
                roi_settings=self.slice1.roi_settings,
                rois=rois_to_results(self.slice1.rois),
                bar_difference_mm=self.slice1.bar_difference_mm,
                slice_shift_mm=self.slice1.slice_shift_mm,
                measured_slice_thickness_mm=self.slice1.measured_slice_thickness_mm,
                row_mtf_50=self.slice1.row_mtf.relative_resolution(50),
                col_mtf_50=self.slice1.col_mtf.relative_resolution(50),
                row_mtf_lp_mm=row_mtfs,
                col_mtf_lp_mm=col_mtfs,
            ),
            slice11=MRSlice11ModuleOutput(
                offset=MR_SLICE11_MODULE_OFFSET_MM,
                bar_difference_mm=self.slice11.bar_difference_mm,
                slice_shift_mm=self.slice11.slice_shift_mm,
                rois=rois_to_results(self.slice11.rois),
                roi_settings=self.slice11.roi_settings,
            ),
            geometric_distortion_module=MRGeometricDistortionModuleOutput(
                offset=MR_GEOMETRIC_DISTORTION_MODULE_OFFSET_MM,
                profiles=self.geometric_distortion.profiles,
                distances=self.geometric_distortion.distances(),
            ),
            uniformity_module=MRUniformityModuleOutput(
                offset=0,
                roi_settings=self.uniformity_module.roi_settings,
                rois=rois_to_results(self.uniformity_module.rois),
                ghost_roi_settings=self.uniformity_module.ghost_roi_settings,
                ghost_rois=rois_to_results(self.uniformity_module.ghost_rois),
                psg=self.uniformity_module.psg,
                ghosting_ratio=self.uniformity_module.ghosting_ratio,
                piu=self.uniformity_module.percent_image_uniformity,
                piu_passed=self.uniformity_module.piu_passed,
            ),
            sagittal_localizer_module=MRSagittalLocalizationModuleOutput(
                profiles=self.sagittal_localization.profiles,
                distances=self.sagittal_localization.distances(),
            ),
            low_contrast_multi_slice_module=MRLowContrastMultiSliceModuleOutput(
                score=self.low_contrast_multi_slice.score,
                low_contrast_rois=low_contrast_rois,
            ),
        )


class ACRMRIMedium(ACRMRILarge):
    _model = "ACR MRI Medium"
    catphan_radius_mm = 82.5
    slice1 = MRMediumSlice1Module
    slice11 = MRMediumSlice11PositionModule
    uniformity_module = MRMediumUniformityModule
