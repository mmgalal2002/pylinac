from __future__ import annotations

import io
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import numpy as np
from matplotlib import pyplot as plt
from plotly import graph_objects as go
from pydantic import BaseModel, ConfigDict, Field
from scipy.stats import linregress

from .core import pdf
from .core.plotly_utils import add_title
from .core.profile import CollapsedCircleProfile
from .core.roi import DiskROI
from .core.scale import wrap360
from .core.utilities import QuaacDatum, ResultBase, ResultsDataMixin
from .core.warnings import capture_warnings
from .ct import CatPhanBase, CatPhanModule, Slice


class TomoCheeseResult(ResultBase):
    """This class should not be called directly. It is returned by the ``results_data()`` method.
    It is a dataclass under the hood and thus comes with all the dunder magic.

    Use the following attributes as normal class attributes."""

    origin_slice: int = Field(
        description="The slice index that was used for the ROI analysis.",
        title="Slice number of the analyzed image",
    )
    num_images: int = Field(
        description="The number of images that were in the passed dataset.",
        title="Number of images in the stack",
    )
    phantom_roll: float = Field(
        description="The roll of the phantom in degrees.",
        title="Phantom roll (\N{DEGREE SIGN})",
    )
    rois: dict[str, dict[str, int | float]] = Field(
        description="A dictionary of measured ROIs.", title="ROI data"
    )
    # having explicit rois here is a stupid idea. Keeping it for backwards compatibility.
    # `rois` is the new way to go as its extensible for N ROIs.
    roi_1: dict = Field(title="ROI 1")
    roi_2: dict = Field(title="ROI 2")
    roi_3: dict = Field(title="ROI 3")
    roi_4: dict = Field(title="ROI 4")
    roi_5: dict = Field(title="ROI 5")
    roi_6: dict = Field(title="ROI 6")
    roi_7: dict = Field(title="ROI 7")
    roi_8: dict = Field(title="ROI 8")
    roi_9: dict = Field(title="ROI 9")
    roi_10: dict = Field(title="ROI 10")
    roi_11: dict = Field(title="ROI 11")
    roi_12: dict = Field(title="ROI 12")
    roi_13: dict = Field(title="ROI 13")
    roi_14: dict = Field(title="ROI 14")
    roi_15: dict = Field(title="ROI 15")
    roi_16: dict = Field(title="ROI 16")
    roi_17: dict = Field(title="ROI 17")
    roi_18: dict = Field(title="ROI 18")
    roi_19: dict = Field(title="ROI 19")
    roi_20: dict = Field(title="ROI 20")


class CheeseResult(ResultBase):
    """This class should not be called directly. It is returned by the ``results_data()`` method.
    It is a dataclass under the hood and thus comes with all the dunder magic.

    Use the following attributes as normal class attributes."""

    origin_slice: int = Field(
        description="The slice index that was used for the ROI analysis.",
        title="Slice number of the analyzed image",
    )
    num_images: int = Field(
        description="The number of images that were in the passed dataset.",
        title="Number of images in the stack",
    )
    phantom_roll: float = Field(
        description="The roll of the phantom in degrees.",
        title="Phantom roll (\N{DEGREE SIGN})",
    )
    rois: dict[str, dict[str, int | float]] = Field(
        description="A dictionary of measured ROIs.", title="ROI data"
    )


class CIRSInsertReference(BaseModel):
    """Optional, user-supplied identity and reference values for one insert.

    Density is not inferred from CT number. A tolerance is an absolute CT number
    difference in HU and requires an expected CT number.
    """

    model_config = ConfigDict(extra="allow", allow_inf_nan=False)

    material: str | None = Field(default=None, title="Supplied insert material")
    density: float | None = Field(default=None, ge=0, title="Supplied density")
    expected_hu: float | None = Field(default=None, title="Reference CT number (HU)")
    tolerance_hu: float | None = Field(
        default=None, ge=0, title="Supplied CT number tolerance (HU)"
    )


class CIRSInsertResult(BaseModel):
    """Additional sampling statistics and optional comparisons for one insert."""

    material: str | None = Field(title="Supplied material")
    density: float | None = Field(title="Supplied density")
    mean: float = Field(title="Mean CT number (HU)")
    minimum: float = Field(title="Minimum CT number (HU)")
    maximum: float = Field(title="Maximum CT number (HU)")
    percentile_5: float = Field(title="5th percentile CT number (HU)")
    percentile_95: float = Field(title="95th percentile CT number (HU)")
    pixel_count: int = Field(title="Sampled pixels")
    sampled_area_mm2: float = Field(title="Sampled area (square mm)")
    diameter_mm: float = Field(title="Sampling diameter (mm)")
    expected_hu: float | None = Field(title="Reference CT number (HU)")
    tolerance_hu: float | None = Field(title="Supplied tolerance (HU)")
    difference_hu: float | None = Field(title="Median minus reference (HU)")
    within_tolerance: bool | None = Field(title="Within supplied tolerance")
    reference_difference_hu: float | None = Field(
        title="Median difference from selected reference insert (HU)"
    )
    cnr: float | None = Field(title="Contrast-to-noise ratio (pooled pixel SD)")
    fitted_hu: float | None = Field(title="Fitted CT number (HU)")
    fit_residual_hu: float | None = Field(title="Measured minus fitted CT number (HU)")


class CIRSDensityFit(BaseModel):
    """Descriptive straight-line fit of supplied density to median CT number."""

    density_type: str = Field(title="Supplied density type")
    density_units: str = Field(title="Density units")
    number_of_points: int = Field(title="Configured inserts")
    distinct_densities: int = Field(title="Distinct supplied densities")
    status: str = Field(title="Fit availability")
    slope: float | None = Field(default=None, title="Slope (HU per density unit)")
    intercept: float | None = Field(default=None, title="Intercept (HU)")
    r_squared: float | None = Field(default=None, title="Coefficient of determination")
    rmse_hu: float | None = Field(default=None, title="Fit root mean square residual (HU)")
    maximum_absolute_residual_hu: float | None = Field(
        default=None, title="Maximum absolute fit residual (HU)"
    )


class CIRS062MResult(CheeseResult):
    """CIRS insert measurements, supplied references and acquisition provenance.

    The inherited ``rois`` measurements retain their original keys and units.
    Additional statistics do not identify materials or establish acceptance limits.
    """

    insert_measurements: dict[str, CIRSInsertResult] = Field(
        title="Additional insert measurements and supplied references"
    )
    density_fit: CIRSDensityFit | None = Field(title="Density and CT number relationship")
    reference_roi: str | None = Field(title="Selected reference insert")
    acquisition: dict[str, str | int | float | None] = Field(title="Scan acquisition")
    analysis_settings: dict[str, str | int | float | None] = Field(
        title="Analysis and sampling settings"
    )
    measurement_notes: list[str] = Field(title="Measurement scope and interpretation")


class CheeseModule(CatPhanModule):
    """A base class for cheese-like phantom modules. Each phantom should have only one module. Inherit from this class
    and populate all attributes"""

    common_name: str
    rois: dict[str, DiskROI]
    roi_settings: dict[str, dict[str, float]]

    def _setup_rois(self) -> None:
        # unlike its super, we use simple disk ROIs as we're not doing complicated things.
        for name, setting in self.roi_settings.items():
            self.rois[name] = DiskROI.from_phantom_center(
                self.image,
                setting["angle_corrected"],
                setting["radius_pixels"],
                setting["distance_pixels"],
                self.phan_center,
            )

    def plot_rois(self, axis: plt.Axes) -> None:
        """Plot the ROIs to the axis. We add the ROI # to help the user differentiate"""
        for name, roi in self.rois.items():
            roi.plot2axes(axis, edgecolor="blue", text=name)

    def plotly_rois(self, fig: go.Figure) -> None:
        """Plot the ROIs to the figure. We add the ROI # to help the user differentiate"""
        for name, roi in self.rois.items():
            roi.plotly(
                fig,
                name=name,
                line_color="blue",
            )


class TomoCheeseModule(CheeseModule):
    """The pluggable module with user-accessible holes.

    The ROIs of the inner circle are ~45 degrees apart. The ROIs of the outer circle are ~30 degrees apart.

    """

    common_name = "Tomo Cheese"
    inner_roi_dist_mm = 65
    outer_roi_dist_mm = 110
    roi_radius_mm = 12
    roi_settings = {
        "1": {
            "angle": -75,
            "distance": outer_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "2": {
            "angle": -67.5,
            "distance": inner_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "3": {
            "angle": -45,
            "distance": outer_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "4": {
            "angle": -22.5,
            "distance": inner_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "5": {
            "angle": -15,
            "distance": outer_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "6": {
            "angle": 15,
            "distance": outer_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "7": {
            "angle": 22.5,
            "distance": inner_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "8": {
            "angle": 45,
            "distance": outer_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "9": {
            "angle": 67.5,
            "distance": inner_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "10": {
            "angle": 75,
            "distance": outer_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "11": {
            "angle": 105,
            "distance": outer_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "12": {
            "angle": 112.5,
            "distance": inner_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "13": {
            "angle": 135,
            "distance": outer_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "14": {
            "angle": 157.5,
            "distance": inner_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "15": {
            "angle": 165,
            "distance": outer_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "16": {
            "angle": -165,
            "distance": outer_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "17": {
            "angle": -157.5,
            "distance": inner_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "18": {
            "angle": -135,
            "distance": outer_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "19": {
            "angle": -112.5,
            "distance": inner_roi_dist_mm,
            "radius": roi_radius_mm,
        },
        "20": {
            "angle": -105,
            "distance": outer_roi_dist_mm,
            "radius": roi_radius_mm,
        },
    }


class CheesePhantomBase(CatPhanBase, ResultsDataMixin[CheeseResult]):
    """A base class for doing cheese-like phantom analysis. A subset of catphan analysis where only one module is assumed."""

    model: str
    _demo_url: str
    air_bubble_radius_mm: int | float
    localization_radius: int | float
    min_num_images: int
    catphan_radius_mm: float
    roi_config: dict
    module_class: type[CheeseModule]
    module: CheeseModule
    clip_in_localization = True

    def analyze(
        self,
        roi_config: dict | None = None,
        x_adjustment: float = 0,
        y_adjustment: float = 0,
        angle_adjustment: float = 0,
        roi_size_factor: float = 1,
        scaling_factor: float = 1,
        origin_slice: int | None = None,
    ) -> None:
        """Analyze the Tomo Cheese phantom.

        Parameters
        ----------
        roi_config : dict
            The configuration of the ROIs, specifically the known densities.
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
        origin_slice : int, None
            The slice number to analyze. If None, the slice will be automatically determined. This is a fallback
            method in case the automatic slice detection fails.
        """
        self.x_adjustment = x_adjustment
        self.y_adjustment = y_adjustment
        self.angle_adjustment = angle_adjustment
        self.roi_size_factor = roi_size_factor
        self.scaling_factor = scaling_factor
        self.localize(origin_slice=origin_slice)
        self.module = self.module_class(self, clear_borders=self.clear_borders)
        self.roi_config = roi_config

    def _roi_angles(self) -> list[float]:
        return [wrap360(s["angle"]) for s in self.module_class.roi_settings.values()]

    def _density_roi_config(self) -> dict[str, dict]:
        return {
            name: values
            for name, values in (self.roi_config or {}).items()
            if values.get("density") is not None
        }

    def _ensure_physical_scan_extent(self) -> bool:
        """The cheese phantom only has one module."""
        return True

    def find_phantom_roll(self, func: Callable | None = None) -> float:
        """Examine the phantom for the maximum HU delta insert position. Roll the phantom by the
        measured angle to the nearest nominal angle if nearby. If not nearby, default to 0
        """
        # get edges and make ROIs from it
        slice = Slice(self, self.origin_slice, clear_borders=self.clear_borders)
        circle = CollapsedCircleProfile(
            slice.phan_center,
            self.localization_radius / self.mm_per_pixel,
            slice.image.array,
            ccw=False,
            width_ratio=0.05,
            num_profiles=5,
        )
        # we only want peaks. air pockets can cause bad range shifts so set min to 0
        circle.values = np.where(circle.values < 0, 0, circle.values)
        peak_idxs, _ = circle.find_fwxm_peaks(max_number=1)
        if peak_idxs:
            angle = peak_idxs[0] / len(circle) * 360
            # see if angle is near an ROI node
            shifts = [angle - a for a in self._roi_angles()]
            min_shift = shifts[np.argmin([abs(shift) for shift in shifts])]
            if -5 < min_shift < 5:
                return min_shift
            else:
                print(
                    f"Detected shift of {min_shift} was >5 degrees; automatic roll compensation aborted. Setting roll to 0."
                )
                return 0
        else:
            print(
                "No low-HU regions found in the outer ROI circle; automatic roll compensation aborted. Setting roll to 0."
            )
            return 0

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
        figs = {
            self.module.common_name: self.module.plotly(
                show_colorbar=show_colorbar, show_legend=show_legend, **kwargs
            )
        }

        # density curve (if densities passed)
        if self._density_roi_config():
            xs = []
            ys = []
            for roi_num, roi_data in self._density_roi_config().items():
                xs.append(roi_data["density"])
                ys.append(self.module.rois[roi_num].pixel_value)
            # sort by HU so it looks like a normal curve; ROI densities can be out of order
            sorted_args = np.argsort(xs)
            xs = np.array(xs)[sorted_args]
            ys = np.array(ys)[sorted_args]
            # plot
            density_fig = go.Figure()
            density_fig.add_scatter(
                x=xs,
                y=ys,
                mode="lines+markers",
                line_dash="dash",
                marker_symbol="diamond",
            )
            density_fig.update_layout(
                yaxis_title="HU",
                xaxis_title="Density",
            )
            add_title(density_fig, "Density vs HU curve")
            figs["Density vs HU curve"] = density_fig

        if show:
            for fig in figs.values():
                fig.show()
        return figs

    def plot_analyzed_image(self, show: bool = True, **plt_kwargs: dict) -> None:
        """Plot the images used in the calculation and summary data.

        Parameters
        ----------
        show : bool
            Whether to plot the image or not.
        plt_kwargs : dict
            Keyword args passed to the plt.figure() method. Allows one to set things like figure size.
        """
        fig, ax = plt.subplots(**plt_kwargs)
        self.module.plot(ax)
        plt.tight_layout()
        if show:
            plt.show()

    def plot_roi_values(
        self, show: bool = True, *, color: str | None = None, **plt_kwargs: dict
    ) -> None:
        """Plot the CT number and pixel variation of every measured insert.

        Parameters
        ----------
        show : bool
            Whether to display the figure.
        color : str, optional
            Colour of the CT number and pixel-variation series.
        plt_kwargs : dict
            Keyword arguments passed to :func:`matplotlib.pyplot.subplots`.
        """
        figure, axes = plt.subplots(2, 1, sharex=True, **plt_kwargs)
        names = list(self.module.rois)
        positions = np.arange(len(names))
        medians = [roi.pixel_value for roi in self.module.rois.values()]
        means = [roi.mean for roi in self.module.rois.values()]
        deviations = [roi.std for roi in self.module.rois.values()]
        axes[0].errorbar(
            positions, means, yerr=deviations, fmt="o", capsize=3,
            label="Mean and pixel standard deviation", color=color,
        )
        axes[0].scatter(positions, medians, marker="x", label="Median", color="black")
        axes[0].set_ylabel("CT number (HU)")
        axes[0].set_title("CT number by insert")
        axes[0].legend(fontsize="small")
        axes[1].bar(positions, deviations, color=color)
        axes[1].set_ylabel("Pixel standard deviation (HU)")
        axes[1].set_xlabel("Insert number")
        axes[1].set_xticks(positions, names)
        for axis in axes:
            axis.grid(axis="y", alpha=0.3)
        figure.tight_layout()
        if show:
            plt.show()

    def plot_roi_images(
        self, show: bool = True, **plt_kwargs: dict
    ) -> dict[str, plt.Figure]:
        """Plot numbered close-ups of every insert with its sampling boundary.

        Parameters
        ----------
        show : bool
            Whether to display the figures.
        plt_kwargs : dict
            Keyword arguments passed to :func:`matplotlib.pyplot.subplots`.

        Returns
        -------
        dict
            Named figures with up to six insert views each. All views use the
            same CT number window and retain image-coordinate pixel positions.
        """
        figures = {}
        inserts = list(self.module.rois.items())
        values = np.concatenate([roi.pixel_values for _, roi in inserts])
        window = (float(np.min(values)), float(np.max(values)))
        options = {"figsize": (8, 10), **plt_kwargs}
        for start in range(0, len(inserts), 6):
            figure, axes = plt.subplots(3, 2, **options)
            selection = inserts[start : start + 6]
            for axis, (name, roi) in zip(axes.flat, selection):
                axis.imshow(
                    self.module.image.array, cmap="gray", vmin=window[0], vmax=window[1]
                )
                roi.plot2axes(axis, edgecolor="blue")
                margin = roi.radius * 1.8
                axis.set_xlim(roi.center.x - margin, roi.center.x + margin)
                axis.set_ylim(roi.center.y + margin, roi.center.y - margin)
                axis.set_title(
                    f"Insert {name}\nMedian {roi.pixel_value:.1f} HU; SD {roi.std:.1f} HU",
                    fontsize=10,
                )
                axis.set_xlabel("Image horizontal coordinate (pixels)", fontsize=8)
                axis.set_ylabel("Image vertical coordinate (pixels)", fontsize=8)
                axis.tick_params(labelsize=8)
            for axis in list(axes.flat)[len(selection) :]:
                axis.set_visible(False)
            figure.tight_layout()
            title = f"Insert sampling close-ups: {selection[0][0]} to {selection[-1][0]}"
            figures[title] = figure
        if show:
            plt.show()
        return figures

    def results(self, as_list: bool = False) -> str | list[str]:
        """Return the results of the analysis as a string. Use with print().

        Parameters
        ----------
        as_list : bool
            Whether to return as a list of strings vs single string. Pretty much for internal usage.
        """
        results = [
            f" - {self.model} Phantom Analysis - ",
            " - HU Module - ",
        ]
        results += [
            f"ROI {name} median: {roi.pixel_value:.1f}, stdev: {roi.std:.1f}"
            for name, roi in self.module.rois.items()
        ]
        if as_list:
            return results
        else:
            return "\n".join(results)

    def plot_density_curve(
        self, show: bool = True, *, color: str | None = None, **plt_kwargs: dict
    ) -> None:
        """Plot the densities of the ROIs vs the measured HU. This will sort the ROIs by measured HU before plotting.

        Parameters
        ----------
        show : bool
            Whether to plot the image or not.
        color : str, optional
            Colour of the measured density series.
        plt_kwargs : dict
            Keyword args passed to the plt.figure() method. Allows one to set things like figure size.
        """
        density_config = self._density_roi_config()
        if not density_config:
            raise ValueError(
                "No ROI density configuration was passed to the analyze method. Re-analyze with densities first."
            )
        xs = []
        ys = []
        for roi_num, roi_data in density_config.items():
            xs.append(roi_data["density"])
            ys.append(self.module.rois[roi_num].pixel_value)
        # sort by HU so it looks like a normal curve; ROI densities can be out of order
        sorted_args = np.argsort(xs)
        xs = np.array(xs)[sorted_args]
        ys = np.array(ys)[sorted_args]
        # plot
        fig, ax = plt.subplots(**plt_kwargs)
        ax.plot(xs, ys, linestyle="-.", marker="D", color=color)
        ax.set_title("Density vs HU curve")
        ax.set_ylabel("HU")
        ax.set_xlabel("Density")
        ax.grid("on")
        plt.tight_layout()
        if show:
            plt.show()

    def _quaac_datapoints(self) -> dict[str, QuaacDatum]:
        results_data = self.results_data(as_dict=True)
        data = {}
        data["Phantom roll"] = QuaacDatum(
            value=results_data["phantom_roll"],
            unit="degrees",
        )
        for roi_num, roi_data in results_data["rois"].items():
            data[f"ROI {roi_num}"] = QuaacDatum(
                value=roi_data["median"],
                unit="HU",
            )
        return data

    def publish_pdf(
        self,
        filename: str | Path,
        notes: str | None = None,
        open_file: bool = False,
        metadata: dict | None = None,
        logo: Path | str | None = None,
        *,
        detailed: bool = False,
        branding: dict[str, object] | None = None,
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
        detailed : bool
            Include every region result, the analysed image and available density curve.
        branding : mapping, optional
            Full report identity, used only for detailed reports.
        """
        if detailed:
            from .core.reporting import (
                ReportBranding,
                ReportField,
                ReportTableLabels,
                publish_analysis_report,
            )

            report_branding = (
                branding if isinstance(branding, ReportBranding)
                else ReportBranding.model_validate(branding or {})
            )
            chart_color = report_branding.chart_color or report_branding.primary_color
            plots = {
                "Analysed phantom image": lambda: self.plot_analyzed_image(show=False),
                "CT numbers and pixel variation": lambda: self.plot_roi_values(show=False, color=chart_color),
                "Insert sampling close-ups": lambda: self.plot_roi_images(show=False),
            }
            if self._density_roi_config():
                plots["Density and CT number curve"] = lambda: self.plot_density_curve(show=False, color=chart_color)
            if isinstance(self, CIRS062M):
                plots["Insert CT number distributions"] = lambda: self.plot_roi_distributions(show=False, color=chart_color)
            fields = {
                ("origin_slice",): ReportField("Reference scan image number", numbered=True),
                ("phantom_roll",): ReportField("Phantom rotation (degrees)", decimal_places=2),
                ("rois",): ReportField("Insert CT number measurements"),
                ("rois", "*", "center_x"): ReportField("Image horizontal coordinate (pixels)"),
                ("rois", "*", "center_y"): ReportField("Image vertical coordinate (pixels)"),
                ("rois", "*", "diameter"): ReportField("Sampling diameter (pixels)"),
                ("rois", "*", "median"): ReportField("Median CT number (HU)"),
                ("rois", "*", "std"): ReportField("Pixel standard deviation (HU)"),
                ("insert_measurements", "*", "within_tolerance"): ReportField(
                    "Within supplied tolerance", missing_label="Not evaluated"
                ),
            }
            if isinstance(self, CIRS062M):
                fields.update({
                    ("acquisition", name): ReportField(label)
                    for name, label in {
                        "tube_voltage_kv": "Tube voltage (kV)",
                        "slice_thickness_mm": "Nominal slice thickness (mm)",
                        "slice_spacing_mm": "Scan image spacing (mm)",
                        "rescale_units": "DICOM rescale units",
                    }.items()
                })
            publish_analysis_report(
                self.results_data(), filename, title=f"{self.model} Phantom Analysis",
                context={"Phantom model": self.model, "Number of scan images": self.num_images},
                scan_images=[Path(img.path).name for img in self.dicom_stack],
                notes=notes, metadata=metadata, logo=logo, branding=branding,
                fields=fields,
                table_labels={
                    "rois": ReportTableLabels(
                        row_heading="Insert", series_heading="Insert",
                        row_labels={name: f"Insert {name}" for name in self.module.rois},
                        column_labels={
                            "center_x": "Image horizontal coordinate (pixels)",
                            "center_y": "Image vertical coordinate (pixels)",
                            "diameter": "Sampling diameter (pixels)",
                            "median": "Median CT number (HU)",
                            "std": "Pixel standard deviation (HU)",
                        },
                    ),
                    "insert_measurements": ReportTableLabels(
                        row_heading="Insert", series_heading="Insert",
                        row_labels={name: f"Insert {name}" for name in self.module.rois},
                        column_labels={
                            name: definition.title or name
                            for name, definition in CIRSInsertResult.model_fields.items()
                        },
                    ),
                },
                plots=plots, open_file=open_file,
            )
            return
        canvas = pdf.PylinacCanvas(
            filename,
            page_title=f"{self.model} Phantom",
            metadata=metadata,
            logo=logo,
        )
        if notes is not None:
            canvas.add_text(text="Notes:", location=(1, 4.5), font_size=14)
            canvas.add_text(text=notes, location=(1, 4))

        canvas.add_text(text=self.results(as_list=True), location=(3, 23), font_size=16)
        data = io.BytesIO()
        self.save_analyzed_image(data)
        canvas.add_new_page()
        canvas.add_image(data, location=(0, 4), dimensions=(22, 22))
        canvas.finish()
        if open_file:
            webbrowser.open(filename)

    def save_analyzed_subimage(self) -> None:
        raise NotImplementedError("There are no sub-images for cheese-like phantoms")

    def plot_analyzed_subimage(self) -> None:
        raise NotImplementedError("There are no sub-images for cheese-like phantoms")

    def _generate_results_data(self) -> CheeseResult:
        return CheeseResult(
            origin_slice=self.origin_slice,
            num_images=self.num_images,
            phantom_roll=self.catphan_roll,
            rois={name: roi.as_dict() for name, roi in self.module.rois.items()},
        )


@capture_warnings
class TomoCheese(CheesePhantomBase, ResultsDataMixin[TomoCheeseResult]):
    """A class for analyzing the TomoTherapy 'Cheese' Phantom containing insert holes and plugs for HU analysis."""

    model = "Tomotherapy Cheese"
    _demo_url = "TomoCheese.zip"
    air_bubble_radius_mm = 14
    localization_radius = 110
    min_num_images = 10
    catphan_radius_mm = 150
    module_class = TomoCheeseModule
    module: TomoCheeseModule

    @staticmethod
    def run_demo(show: bool = True):
        """Run the Tomotherapy Cheese demo"""
        cheese = TomoCheese.from_demo_images()
        cheese.analyze()
        print(cheese.results())
        cheese.plot_analyzed_image(show)

    def _generate_results_data(self):
        """Return the results of the analysis as a structure dataclass"""
        return TomoCheeseResult(
            origin_slice=self.origin_slice,
            num_images=self.num_images,
            phantom_roll=self.catphan_roll,
            rois={name: roi.as_dict() for name, roi in self.module.rois.items()},
            roi_1=self.module.rois["1"].as_dict(),
            roi_2=self.module.rois["2"].as_dict(),
            roi_3=self.module.rois["3"].as_dict(),
            roi_4=self.module.rois["4"].as_dict(),
            roi_5=self.module.rois["5"].as_dict(),
            roi_6=self.module.rois["6"].as_dict(),
            roi_7=self.module.rois["7"].as_dict(),
            roi_8=self.module.rois["8"].as_dict(),
            roi_9=self.module.rois["9"].as_dict(),
            roi_10=self.module.rois["10"].as_dict(),
            roi_11=self.module.rois["11"].as_dict(),
            roi_12=self.module.rois["12"].as_dict(),
            roi_13=self.module.rois["13"].as_dict(),
            roi_14=self.module.rois["14"].as_dict(),
            roi_15=self.module.rois["15"].as_dict(),
            roi_16=self.module.rois["16"].as_dict(),
            roi_17=self.module.rois["17"].as_dict(),
            roi_18=self.module.rois["18"].as_dict(),
            roi_19=self.module.rois["19"].as_dict(),
            roi_20=self.module.rois["20"].as_dict(),
        )


class CIRSHUModule(CheeseModule):
    """The pluggable module with user-accessible holes.

    The ROIs of each circle are ~45 degrees apart.
    """

    common_name = "CIRS electron density"
    outer_radius_mm = 115
    inner_radius_mm = 60
    roi_radius_mm = 10
    roi_settings = {
        "1": {
            "angle": 0,
            "distance": 0,
            "radius": roi_radius_mm,
        },
        "2": {
            "angle": -90,
            "distance": inner_radius_mm,
            "radius": roi_radius_mm,
        },
        "3": {
            "angle": -90,
            "distance": outer_radius_mm,
            "radius": roi_radius_mm,
        },
        "4": {
            "angle": -45,
            "distance": inner_radius_mm,
            "radius": roi_radius_mm,
        },
        "5": {
            "angle": -45,
            "distance": outer_radius_mm,
            "radius": roi_radius_mm,
        },
        "6": {
            "angle": 0,
            "distance": inner_radius_mm,
            "radius": roi_radius_mm,
        },
        "7": {
            "angle": 0,
            "distance": outer_radius_mm,
            "radius": roi_radius_mm,
        },
        "8": {
            "angle": 45,
            "distance": inner_radius_mm,
            "radius": roi_radius_mm,
        },
        "9": {
            "angle": 45,
            "distance": outer_radius_mm,
            "radius": roi_radius_mm,
        },
        "10": {
            "angle": 90,
            "distance": inner_radius_mm,
            "radius": roi_radius_mm,
        },
        # this one is closer to the ring; presumably because the bottom of the phantom is flatter than the top
        "11": {
            "angle": 90,
            "distance": outer_radius_mm - 5,
            "radius": roi_radius_mm,
        },
        "12": {
            "angle": 135,
            "distance": inner_radius_mm,
            "radius": roi_radius_mm,
        },
        "13": {
            "angle": 135,
            "distance": outer_radius_mm,
            "radius": roi_radius_mm,
        },
        "14": {
            "angle": 180,
            "distance": inner_radius_mm,
            "radius": roi_radius_mm,
        },
        "15": {
            "angle": 180,
            "distance": outer_radius_mm,
            "radius": roi_radius_mm,
        },
        "16": {
            "angle": -135,
            "distance": inner_radius_mm,
            "radius": roi_radius_mm,
        },
        "17": {
            "angle": -135,
            "distance": outer_radius_mm,
            "radius": roi_radius_mm,
        },
    }


@capture_warnings
class CIRS062M(CheesePhantomBase):
    """A class for analyzing the CIRS Electron Density Phantom containing insert holes and plugs for HU analysis.

    See Also
    --------
    https://www.cirsinc.com/products/all/24/electron-density-phantom/
    """

    model = "CIRS Electron Density (062M)"
    air_bubble_radius_mm = 30
    clear_borders = False
    hu_origin_slice_variance = 150
    localization_radius = 115
    catphan_radius_mm = 155
    min_num_images = 10
    roi_config: dict
    module_class = CIRSHUModule
    module: CIRSHUModule
    _insert_references: dict[str, CIRSInsertReference]
    _density_type: str
    _reference_roi: str | None

    def analyze(
        self,
        roi_config: dict | None = None,
        x_adjustment: float = 0,
        y_adjustment: float = 0,
        angle_adjustment: float = 0,
        roi_size_factor: float = 1,
        scaling_factor: float = 1,
        origin_slice: int | None = None,
        *,
        density_type: Literal["unspecified", "mass", "relative_electron"] = "unspecified",
        reference_roi: str | None = None,
    ) -> None:
        """Analyze all 17 inserts, with optional supplied reference measurements.

        Parameters
        ----------
        roi_config : dict, optional
            Insert numbers as string keys. Each value may contain ``material``,
            ``density``, ``expected_hu`` and ``tolerance_hu``. Interchangeable plug
            identities and densities must match the scanned arrangement.
            CT number comparisons use the measured median and an inclusive
            absolute tolerance; a tolerance requires ``expected_hu``.
        x_adjustment, y_adjustment : float
            Image-coordinate phantom-center adjustments in mm, as described in
            :meth:`CheesePhantomBase.analyze`.
        angle_adjustment : float
            Clockwise phantom rotation adjustment in degrees.
        roi_size_factor, scaling_factor : float
            Positive sampling-size and insert-position scale factors.
        origin_slice : int, optional
            Zero-based scan image index, otherwise detected automatically.
        density_type : {"unspecified", "mass", "relative_electron"}
            Meaning of the supplied density values. Mass densities must be in
            g/cm3; relative electron densities use water = 1. The default does
            not infer density type or units from the values.
        reference_roi : str, optional
            Explicitly selected insert for CT number differences and CNR. CNR
            uses the absolute median difference divided by the root mean square
            of the two pixel standard deviations. Zero denominator gives no CNR.
            Selecting an insert does not identify it as water or uniform material.
        """
        if density_type not in {"unspecified", "mass", "relative_electron"}:
            raise ValueError("Density type must be unspecified, mass or relative_electron.")
        if reference_roi is not None and reference_roi not in self.module_class.roi_settings:
            raise ValueError("The reference insert must be a string from '1' to '17'.")
        references = {}
        for name, values in (roi_config or {}).items():
            if name not in self.module_class.roi_settings:
                raise ValueError(f"Unknown CIRS insert {name!r}; use strings '1' to '17'.")
            reference = CIRSInsertReference.model_validate(values)
            if reference.tolerance_hu is not None and reference.expected_hu is None:
                raise ValueError(f"Insert {name}: a tolerance requires a reference CT number.")
            references[name] = reference
        for label, value in (
            ("x_adjustment", x_adjustment), ("y_adjustment", y_adjustment),
            ("angle_adjustment", angle_adjustment),
            ("roi_size_factor", roi_size_factor), ("scaling_factor", scaling_factor),
        ):
            if not np.isfinite(value):
                raise ValueError(f"{label} must be finite.")
        if roi_size_factor <= 0 or scaling_factor <= 0:
            raise ValueError("ROI size and position scale factors must be positive.")
        if origin_slice is not None and (
            isinstance(origin_slice, bool)
            or not isinstance(origin_slice, (int, np.integer))
            or not 0 <= origin_slice < self.num_images
        ):
            raise ValueError("The origin slice must be a zero-based index within the scan.")
        spacing = self.dicom_stack.metadata.PixelSpacing
        if any(not np.isfinite(float(value)) or float(value) <= 0 for value in spacing):
            raise ValueError("Pixel spacing must contain finite positive values.")
        if not np.isclose(float(spacing[0]), float(spacing[1]), rtol=1e-5, atol=1e-8):
            raise ValueError("CIRS circular insert sampling requires equal row and column pixel spacing.")
        self._insert_references = references
        self._density_type = density_type
        self._reference_roi = reference_roi
        super().analyze(
            roi_config={
                name: values.model_dump(exclude_none=True)
                for name, values in references.items()
            } if roi_config is not None else None,
            x_adjustment=x_adjustment, y_adjustment=y_adjustment,
            angle_adjustment=angle_adjustment, roi_size_factor=roi_size_factor,
            scaling_factor=scaling_factor, origin_slice=origin_slice,
        )
        height, width = self.module.image.array.shape
        for name, roi in self.module.rois.items():
            if (
                roi.center.x - roi.radius < 0 or roi.center.x + roi.radius >= width
                or roi.center.y - roi.radius < 0 or roi.center.y + roi.radius >= height
            ):
                raise ValueError(f"Insert {name} extends outside the image; check localization and sampling size.")
            if roi.pixel_values.size == 0:
                raise ValueError(f"Insert {name} contains no sampled pixels; increase the ROI size.")

    def plot_density_curve(
        self, show: bool = True, *, color: str | None = None, **plt_kwargs: dict
    ) -> None:
        """Plot supplied densities, measured median CT numbers and fit residuals.

        Parameters
        ----------
        show : bool
            Whether to display the figure.
        color : str, optional
            Colour of the measured data and residuals.
        plt_kwargs : dict
            Keyword arguments passed to :func:`matplotlib.pyplot.subplots`.
        """
        fit = self._density_fit()
        if fit is None:
            raise ValueError("No insert densities were supplied to analyze().")
        configuration = self._density_roi_config()
        names = list(configuration)
        densities = np.array([values["density"] for values in configuration.values()])
        measured = np.array([self.module.rois[name].pixel_value for name in names])
        figure, axes = plt.subplots(2, 1, **plt_kwargs)
        axes[0].scatter(densities, measured, color=color, label="Measured median")
        for name, density, value in zip(names, densities, measured):
            axes[0].annotate(name, (density, value), xytext=(4, 4), textcoords="offset points", fontsize=8)
        if fit.slope is not None and fit.intercept is not None:
            ordered = np.argsort(densities)
            fitted = fit.slope * densities + fit.intercept
            axes[0].plot(densities[ordered], fitted[ordered], color="black", linestyle="--", label="Descriptive linear fit")
            axes[1].bar(names, measured - fitted, color=color)
            axes[1].axhline(0, color="black", linewidth=0.8)
        else:
            axes[1].text(0.5, 0.5, fit.status, ha="center", va="center", wrap=True, transform=axes[1].transAxes)
        axes[0].set_title("Density and CT number relationship")
        axes[0].set_xlabel(f"{fit.density_type.capitalize()} density ({fit.density_units})")
        axes[0].set_ylabel("Median CT number (HU)")
        axes[0].legend(fontsize="small")
        axes[1].set_xlabel("Insert number")
        axes[1].set_ylabel("Measured minus fitted (HU)")
        for axis in axes:
            axis.grid(axis="y", alpha=0.3)
        figure.tight_layout()
        if show:
            plt.show()

    def plot_roi_distributions(
        self, show: bool = True, *, color: str | None = None, **plt_kwargs: dict
    ) -> dict[str, plt.Figure]:
        """Plot sampled pixel distributions without assuming insert homogeneity.

        Parameters
        ----------
        show : bool
            Whether to display the figures.
        color : str, optional
            Histogram colour.
        plt_kwargs : dict
            Keyword arguments passed to :func:`matplotlib.pyplot.subplots`.

        Returns
        -------
        dict
            Named figures with up to six insert histograms each.
        """
        figures = {}
        inserts = list(self.module.rois.items())
        options = {"figsize": (8, 10), **plt_kwargs}
        for start in range(0, len(inserts), 6):
            figure, axes = plt.subplots(3, 2, **options)
            selection = inserts[start : start + 6]
            for axis, (name, roi) in zip(axes.flat, selection):
                axis.hist(roi.pixel_values, bins="auto", color=color)
                axis.axvline(roi.pixel_value, color="black", linestyle="--", label="Median")
                axis.set_title(f"Insert {name}", fontsize=10)
                axis.set_xlabel("CT number (HU)", fontsize=8)
                axis.set_ylabel("Sampled pixels", fontsize=8)
                axis.tick_params(labelsize=8)
                axis.legend(fontsize=7)
            for axis in list(axes.flat)[len(selection) :]:
                axis.set_visible(False)
            figure.tight_layout()
            figures[f"Insert CT number distributions: {selection[0][0]} to {selection[-1][0]}"] = figure
        if show:
            plt.show()
        return figures

    def _density_fit(self) -> CIRSDensityFit | None:
        configuration = self._density_roi_config()
        if not configuration:
            return None
        densities = np.array([values["density"] for values in configuration.values()], dtype=float)
        ct_numbers = np.array([self.module.rois[name].pixel_value for name in configuration])
        units = {
            "unspecified": "Not specified",
            "mass": "g/cm3",
            "relative_electron": "Relative to water = 1",
        }
        result = CIRSDensityFit(
            density_type=self._density_type.replace("_", " "),
            density_units=units[self._density_type],
            number_of_points=len(densities), distinct_densities=len(np.unique(densities)),
            status="Not fitted: at least two distinct supplied densities are required.",
        )
        if result.distinct_densities < 2:
            return result
        fit = linregress(densities, ct_numbers)
        residuals = ct_numbers - (fit.slope * densities + fit.intercept)
        result.slope = float(fit.slope)
        result.intercept = float(fit.intercept)
        result.r_squared = float(fit.rvalue**2) if np.ptp(ct_numbers) > 0 else None
        result.rmse_hu = float(np.sqrt(np.mean(residuals**2)))
        result.maximum_absolute_residual_hu = float(np.max(np.abs(residuals)))
        result.status = "Descriptive least-squares fit of median CT number against supplied density."
        if len(densities) == 2:
            result.status += " Two points determine a line; fit quality is not independently assessed."
        return result

    def _generate_results_data(self) -> CIRS062MResult:
        base = super()._generate_results_data()
        fit = self._density_fit()
        reference_roi = self.module.rois.get(self._reference_roi)
        measurements = {}
        for name, roi in self.module.rois.items():
            reference = self._insert_references.get(name, CIRSInsertReference())
            percentiles = np.percentile(roi.pixel_values, [5, 95])
            difference = roi.pixel_value - reference.expected_hu if reference.expected_hu is not None else None
            reference_difference = roi.pixel_value - reference_roi.pixel_value if reference_roi is not None else None
            pooled_noise = float(np.hypot(roi.std, reference_roi.std) / np.sqrt(2)) if reference_roi is not None else 0
            fitted_hu = (
                fit.slope * reference.density + fit.intercept
                if fit is not None and fit.slope is not None
                and fit.intercept is not None and reference.density is not None
                else None
            )
            measurements[name] = CIRSInsertResult(
                material=reference.material, density=reference.density,
                mean=roi.mean, minimum=roi.min, maximum=roi.max,
                percentile_5=float(percentiles[0]), percentile_95=float(percentiles[1]),
                pixel_count=int(roi.pixel_values.size),
                sampled_area_mm2=float(roi.pixel_values.size * self.mm_per_pixel**2),
                diameter_mm=float(2 * roi.radius * self.mm_per_pixel),
                expected_hu=reference.expected_hu, tolerance_hu=reference.tolerance_hu,
                difference_hu=difference,
                within_tolerance=abs(difference) <= reference.tolerance_hu
                if difference is not None and reference.tolerance_hu is not None else None,
                reference_difference_hu=reference_difference,
                cnr=abs(reference_difference) / pooled_noise
                if reference_difference is not None and pooled_noise > 0 else None,
                fitted_hu=fitted_hu,
                fit_residual_hu=roi.pixel_value - fitted_hu if fitted_hu is not None else None,
            )
        metadata = self.dicom_stack[self.origin_slice].metadata
        acquisition = {
            "manufacturer": getattr(metadata, "Manufacturer", None),
            "scanner_model": getattr(metadata, "ManufacturerModelName", None),
            "modality": getattr(metadata, "Modality", None),
            "tube_voltage_kv": float(metadata.KVP) if getattr(metadata, "KVP", None) not in (None, "") else None,
            "image_rows": int(metadata.Rows), "image_columns": int(metadata.Columns),
            "row_spacing_mm": float(metadata.PixelSpacing[0]),
            "column_spacing_mm": float(metadata.PixelSpacing[1]),
            "slice_thickness_mm": float(metadata.SliceThickness),
            "slice_spacing_mm": float(self.dicom_stack.slice_spacing),
            "rescale_slope": float(getattr(metadata, "RescaleSlope", 1)),
            "rescale_intercept": float(getattr(metadata, "RescaleIntercept", 0)),
            "rescale_units": getattr(metadata, "RescaleType", None),
            "reconstruction_kernel": str(metadata.ConvolutionKernel) if "ConvolutionKernel" in metadata else None,
        }
        return CIRS062MResult(
            **base.model_dump(), insert_measurements=measurements, density_fit=fit,
            reference_roi=self._reference_roi, acquisition=acquisition,
            analysis_settings={
                "x_adjustment_mm": float(self.x_adjustment),
                "y_adjustment_mm": float(self.y_adjustment),
                "angle_adjustment_degrees": float(self.angle_adjustment),
                "roi_size_factor": float(self.roi_size_factor),
                "position_scaling_factor": float(self.scaling_factor),
                "phantom_center_x_pixels": float(self.module.phan_center.x),
                "phantom_center_y_pixels": float(self.module.phan_center.y),
                "density_type": self._density_type.replace("_", " "),
                "comparison_statistic": "Median CT number",
            },
            measurement_notes=[
                "Insert identities and densities are supplied, not inferred from CT number.",
                "Pixel standard deviation includes noise, material structure, partial volume and artifacts; it is not a standalone scanner-noise or uniformity measurement.",
                "An insert is evaluated only when both its reference CT number and tolerance are supplied.",
                "The density fit describes the supplied points; it is not an automatically commissioned density conversion.",
                "Spatial resolution, slice-thickness accuracy and dose are not measured by this insert analysis.",
                "Stored DICOM rescaling is retained without water or air correction. Missing rescale units are not independently verified.",
            ],
        )

    @classmethod
    def from_demo_images(cls):
        raise NotImplementedError("No demo images available for this phantom")

    def find_origin_slice(self) -> int:
        """We override to lower the minimum variation required. This is ripe for refactor, but I'd like to
        add a few more phantoms first to get the full picture required."""
        hu_slices = []
        for image_number in range(0, self.num_images, 2):
            slice = Slice(
                self, image_number, combine=False, clear_borders=self.clear_borders
            )
            if slice.is_phantom_in_view():
                circle_prof = CollapsedCircleProfile(
                    slice.phan_center,
                    radius=self.localization_radius / self.mm_per_pixel,
                    image_array=slice.image,
                    width_ratio=0.05,
                    num_profiles=5,
                )
                prof = circle_prof.values
                # determine if the profile contains both low and high values and that most values are the same
                low_end, high_end = np.percentile(prof, [2, 98])
                median = np.median(prof)
                ##################################
                # the difference from the original
                ##################################
                middle_variation = np.percentile(prof, 60) - np.percentile(prof, 40)
                variation_limit = max(
                    100, self.dicom_stack.metadata.SliceThickness * -100 + 300
                )
                if (
                    (low_end < median - self.hu_origin_slice_variance)
                    or (high_end > median + self.hu_origin_slice_variance)
                    and (middle_variation < variation_limit)
                ):
                    hu_slices.append(image_number)

        if not hu_slices:
            raise ValueError(
                "No slices were found that resembled the HU linearity module"
            )
        hu_slices = np.array(hu_slices)
        c = int(round(float(np.median(hu_slices))))
        ln = len(hu_slices)
        # drop slices that are way far from median
        hu_slices = hu_slices[((c + ln / 2) >= hu_slices) & (hu_slices >= (c - ln / 2))]
        center_hu_slice = int(round(float(np.median(hu_slices))))
        if self._is_within_image_extent(center_hu_slice):
            return center_hu_slice
