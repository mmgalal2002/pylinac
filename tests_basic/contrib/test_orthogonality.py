from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pylinac.contrib.orthogonality import JawOrthogonality
from tests_basic.utils import get_folder_from_cloud_repo


class TestOrthogonality(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dir = Path(get_folder_from_cloud_repo(["planar_imaging", "Orthogonality"]))

    def test_analyze(self):
        for file in self.dir.iterdir():
            if file.is_file():
                q = JawOrthogonality(file)
                q.analyze()
                q.plot_analyzed_image()

    def test_publish_pdf(self):
        file = next(path for path in self.dir.iterdir() if path.is_file())
        analysis = JawOrthogonality(file)
        analysis.analyze()

        with TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "jaw_orthogonality.pdf"
            analysis.publish_pdf(pdf_path)
            self.assertGreater(pdf_path.stat().st_size, 0)
