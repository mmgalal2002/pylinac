from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from matplotlib import pyplot as plt

from pylinac import StandardImagingFC2
from pylinac.contrib.quasar import QuasarLightRadScaling
from pylinac.core.geometry import Point
from pylinac.core.warnings import WarningCollectorMixin
from tests_basic.utils import get_folder_from_cloud_repo


class TestQuasar(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dir = Path(get_folder_from_cloud_repo(["planar_imaging", "Quasar"]))

    def test_analyze(self):
        for file in self.dir.iterdir():
            if file.is_file():
                q = QuasarLightRadScaling(file)
                q.analyze()
                q.plot_analyzed_image()
                result = q.results_data(as_dict=True)
                self.assertEqual(
                    result["scaling_centers_detected"], len(q.scaling_centers)
                )
                self.assertEqual(result["passed"], q.passed)

    def test_publish_detailed_pdf(self):
        file = next(path for path in self.dir.iterdir() if path.is_file())
        analysis = QuasarLightRadScaling(file)
        analysis.analyze()

        with TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "quasar_report.pdf"
            analysis.publish_pdf(str(pdf_path), detailed=True)
            self.assertGreater(pdf_path.stat().st_size, 0)


class TestQuasarScalingMismatch(TestCase):
    def _analysis(self):
        analysis = object.__new__(QuasarLightRadScaling)
        WarningCollectorMixin.__init__(analysis)
        analysis.image = Mock()
        analysis.image.array.size = 10000
        analysis.image.dpmm = 1
        analysis.field_width_x = 100
        analysis.field_width_y = 100
        analysis.field_center = Point(10, 10)
        analysis.epid_center = Point(10, 10)
        analysis.bb_center = Point(10, 10)
        analysis.bb_detection_method = "automatic"
        analysis.scaling_centers = [Point(100, 100), Point(200, 200)]
        return analysis

    def test_partial_detection_is_a_failure_not_an_exception(self):
        analysis = self._analysis()
        partial_centers = analysis.scaling_centers

        with patch.object(StandardImagingFC2, "analyze"):
            with patch.object(
                analysis, "_detect_scaling_centers", return_value=partial_centers
            ):
                analysis.analyze()

        result = analysis._generate_results_data()
        self.assertEqual(result.scaling_centers_detected, 2)
        self.assertEqual(result.scaling_centers_expected, 5)
        self.assertFalse(result.passed)
        self.assertIn("2/5", analysis.results())

    def test_scaling_detector_accepts_partial_results(self):
        analysis = self._analysis()
        partial_centers = [Point(100, 100), Point(200, 200)]
        analysis.image.compute.return_value = partial_centers

        self.assertEqual(analysis._detect_scaling_centers(), partial_centers)

        locator = analysis.image.compute.call_args.args[0]
        self.assertEqual(locator.min_number, 0)
        self.assertGreater(locator.max_number, analysis.expected_scaling_centers)

    def test_plot_shows_partial_count_and_failure(self):
        analysis = self._analysis()
        figure, _ = plt.subplots()

        try:
            with patch.object(
                StandardImagingFC2,
                "plot_analyzed_image",
                return_value=([figure], ["image"]),
            ):
                figures, _ = analysis.plot_analyzed_image(show=False)
            self.assertIn("2/5 (FAIL)", figures[0].axes[0].get_title())
        finally:
            plt.close(figure)
