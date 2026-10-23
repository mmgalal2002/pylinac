from matplotlib import pyplot as plt
from matplotlib.figure import Figure
from pydantic import Field

from .. import StandardImagingFC2
from ..core.geometry import Point
from ..metrics.image import SizedDiskLocator
from ..planar_imaging import LightRadResult


class QuasarLightRadScalingResult(LightRadResult):
    """Structured Quasar light/rad and scaling-center results."""

    scaling_centers_detected: int = Field(
        title="Scaling centers detected",
        description="Number of Quasar scaling disks detected in the image.",
    )
    scaling_centers_expected: int = Field(
        title="Scaling centers expected",
        description="Number of scaling disks expected for a complete Quasar analysis.",
    )
    scaling_center_positions_px: list[tuple[float, float]] = Field(
        title="Scaling center positions (image pixels)",
        description="Detected scaling disk centers in zero-based image pixels (X, Y).",
    )
    passed: bool = Field(
        title="Overall test result",
        description="Passes when all expected scaling disks are detected.",
    )


class QuasarLightRadScaling(StandardImagingFC2):
    """A light/rad and also scaling analysis for the Quasar phantom. The user
    also uses custom edge blocks with offset BBs to detect the light corners.
    It's a mix of scaling validation and light/rad."""

    common_name = "Quasar Light/Rad Scaling"
    bb_sampling_box_size_mm = 10
    bb_size_mm = 5
    field_strip_width_mm = 20
    light_rad_bb_offset_mm = 11
    expected_scaling_centers: int = 5
    scaling_centers: list[Point]

    def analyze(
        self, invert: bool = False, fwxm: int = 50, bb_edge_threshold_mm: float = 10
    ) -> None:
        """Analyze the image for the light/rad and scaling"""
        super().analyze(
            invert=invert, fwxm=fwxm, bb_edge_threshold_mm=bb_edge_threshold_mm
        )
        self.scaling_centers = self._detect_scaling_centers()

    @property
    def passed(self) -> bool:
        """Whether the expected number of Quasar scaling centers was detected."""
        return len(self.scaling_centers) == self.expected_scaling_centers

    def results(self, as_list: bool = False) -> str | list[str]:
        """Return the light/rad measurements and scaling-center QA status."""
        results = super().results(as_list=True)
        assert isinstance(results, list)
        results.extend(
            [
                f"Scaling disks detected: {len(self.scaling_centers)}/{self.expected_scaling_centers}",
                f"Scaling disk detection: {'PASS' if self.passed else 'FAIL'}",
            ]
        )
        return results if as_list else "\n".join(results)

    def _generate_results_data(self) -> QuasarLightRadScalingResult:
        """Return the light/rad measurements and scaling-center QA status."""
        light_rad_results = super()._generate_results_data()
        return QuasarLightRadScalingResult(
            **light_rad_results.model_dump(),
            scaling_centers_detected=len(self.scaling_centers),
            scaling_centers_expected=self.expected_scaling_centers,
            scaling_center_positions_px=[
                (center.x, center.y) for center in self.scaling_centers
            ],
            passed=self.passed,
        )

    def plot_analyzed_image(
        self, show: bool = True, **kwargs
    ) -> tuple[list[Figure], list[str]]:
        """Plot the analysis image with the scaling-center count and QA status."""
        figures, names = super().plot_analyzed_image(show=False, **kwargs)
        status = "PASS" if self.passed else "FAIL"
        figures[0].axes[0].set_title(
            f"{self.common_name} Phantom Analysis\n"
            f"Scaling disks: {len(self.scaling_centers)}/"
            f"{self.expected_scaling_centers} ({status})"
        )
        if show:
            plt.show()
        return figures, names

    def _determine_bb_set(self, fwxm: int) -> dict:
        """We determine the BB set to use for the CAX (the light/rad part is separate).
        We do this by first finding the field edges and then offsetting inward by 10 mm.
        """
        fs_y = self.field_width_y / 2
        fs_x = self.field_width_x / 2
        positions_offsets = {
            "TL": (
                -fs_x + self.light_rad_bb_offset_mm,
                -fs_y + self.light_rad_bb_offset_mm,
            ),
            "BL": (
                -fs_x + self.light_rad_bb_offset_mm,
                fs_y - self.light_rad_bb_offset_mm,
            ),
            "TR": (
                fs_x - self.light_rad_bb_offset_mm,
                fs_y - self.light_rad_bb_offset_mm,
            ),
            "BR": (
                fs_x - self.light_rad_bb_offset_mm,
                -fs_y + self.light_rad_bb_offset_mm,
            ),
        }
        return positions_offsets

    def _detect_scaling_centers(self) -> list[Point]:
        """Sample a 10x10mm square about each BB to detect it. Adjustable using self.bb_sampling_box_size_mm"""
        scaling_centers = self.image.compute(
            SizedDiskLocator.from_center_physical(
                name="Quasar scaling disks",
                expected_position_mm=Point(0, 0),
                search_window_mm=(35, 35),
                radius_mm=self.bb_size_mm / 2,
                radius_tolerance_mm=self.bb_size_mm / 2,
                min_number=0,
                max_number=int(self.image.array.size),
                min_separation_mm=4,
            )
        )
        return scaling_centers
