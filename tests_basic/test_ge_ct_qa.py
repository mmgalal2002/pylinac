import tempfile
import zipfile
from pathlib import Path
from unittest import TestCase

import numpy as np
import pydicom
from matplotlib import pyplot as plt
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from pylinac import GECTQA
from pylinac.ge_ct_qa import (
    GECTQAROI,
    GECTQAConfig,
    GECTQAMaterialROI,
)


def write_ct_image(
    filename: Path,
    instance_number: int,
    series_uid: str,
    include_material: bool = False,
) -> None:
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = pydicom.uid.CTImageStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset = FileDataset(
        str(filename), {}, file_meta=file_meta, preamble=b"\0" * 128
    )
    dataset.is_little_endian = True
    dataset.is_implicit_VR = False
    dataset.Modality = "CT"
    dataset.SeriesInstanceUID = series_uid
    dataset.StudyInstanceUID = "1.2.826.0.1.3680043.8.498.1"
    dataset.SOPClassUID = pydicom.uid.CTImageStorage
    dataset.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    dataset.Rows = 256
    dataset.Columns = 256
    dataset.PixelSpacing = [1.0, 1.0]
    dataset.ImagePositionPatient = [0.0, 0.0, float(instance_number) * 2.5]
    dataset.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    dataset.InstanceNumber = instance_number
    dataset.SliceThickness = 2.5
    dataset.Manufacturer = "GE MEDICAL SYSTEMS"
    dataset.ManufacturerModelName = "Synthetic GE CT"
    dataset.RescaleSlope = 1.0
    dataset.RescaleIntercept = -1000.0
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.SamplesPerPixel = 1
    dataset.BitsStored = 16
    dataset.BitsAllocated = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 1
    image = np.zeros((256, 256), dtype=np.int16)
    rows, columns = np.ogrid[:256, :256]
    phantom_mask = (columns - 128) ** 2 + (rows - 128) ** 2 <= 100**2
    image[phantom_mask] = 1000
    if include_material:
        material_mask = (columns - 128) ** 2 + (rows - 128) ** 2 <= 8**2
        image[material_mask] = 1100
    dataset.PixelData = image.tobytes()
    dataset.save_as(filename)


def measurement_config() -> GECTQAConfig:
    return GECTQAConfig(
        ct_number_rois={
            "material": GECTQAMaterialROI(
                x_mm=0,
                y_mm=0,
                radius_mm=5,
                nominal_hu=100,
                tolerance_hu=1,
            )
        },
        noise_roi=GECTQAROI(x_mm=40, y_mm=0, radius_mm=5),
        noise_tolerance_hu=0.1,
        uniformity_rois={
            "center": GECTQAROI(x_mm=40, y_mm=0, radius_mm=5),
            "top": GECTQAROI(x_mm=0, y_mm=-40, radius_mm=5),
            "bottom": GECTQAROI(x_mm=0, y_mm=40, radius_mm=5),
        },
        uniformity_tolerance_hu=0.1,
        positioning_tolerance_mm=1,
    )


class TestGECTQA(TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp_dir.name)
        series_uid = generate_uid()
        for instance_number in range(3):
            write_ct_image(
                self.folder / f"slice_{instance_number}.dcm",
                instance_number,
                series_uid,
                include_material=instance_number == 1,
            )

    def tearDown(self) -> None:
        plt.close("all")
        self.temp_dir.cleanup()

    def test_folder_and_configured_measurements(self) -> None:
        qa = GECTQA(self.folder, config=measurement_config())
        qa.analyze(angle_override=0)
        data = qa.results_data()

        self.assertEqual(data.num_images, 3)
        self.assertAlmostEqual(data.localization.phantom_diameter_mm, 200, delta=1)
        self.assertAlmostEqual(data.ct_number.rois["material"].mean_hu, 100, delta=1)
        self.assertTrue(data.ct_number.passed)
        self.assertAlmostEqual(data.noise.noise_hu, 0)
        self.assertTrue(data.uniformity.passed)
        self.assertIsNone(data.alignment.passed)
        self.assertIsInstance(qa.results_data(as_dict=True), dict)
        self.assertIsInstance(qa.results_data(as_json=True), str)

    def test_default_profile_includes_ge_references_and_helios_metrics(self) -> None:
        qa = GECTQA(self.folder)
        qa.analyze(angle_override=0)
        data = qa.results_data()

        self.assertIn("GE CT Technical Reference Manual", data.reference.source)
        self.assertEqual(data.reference.plexiglass_water_difference_hu, 120)
        self.assertIn("not explicitly Optima", data.reference.scanner_reference_status)
        self.assertTrue(data.helios_compatibility.available)
        self.assertIsNotNone(data.helios_compatibility.high_contrast)
        self.assertEqual(data.slice_thickness.acquired_slice_thickness_mm, 2.5)

    def test_single_file_and_zip(self) -> None:
        single = GECTQA(self.folder / "slice_1.dcm")
        single.analyze(angle_override=0)
        self.assertEqual(single.results_data().num_images, 1)

        archive = self.folder / "series.zip"
        with zipfile.ZipFile(archive, "w") as zip_file:
            for path in self.folder.glob("slice_*.dcm"):
                zip_file.write(path, arcname=path.name)
        zipped = GECTQA.from_zip(archive)
        zipped.analyze(angle_override=0)
        self.assertEqual(zipped.results_data().num_images, 3)

    def test_center_override_handles_missing_component(self) -> None:
        background = self.folder / "background.dcm"
        write_ct_image(background, 0, generate_uid())
        dataset = pydicom.dcmread(background)
        dataset.PixelData = np.zeros((256, 256), dtype=np.int16).tobytes()
        dataset.save_as(background)

        qa = GECTQA(background)
        with self.assertRaisesRegex(ValueError, "Unable to localize"):
            qa.analyze(angle_override=0)

        qa.analyze(center_override=(128, 128), angle_override=0)
        self.assertEqual(qa.results_data().localization.localization_confidence, 1)

    def test_mixed_series_is_rejected(self) -> None:
        write_ct_image(
            self.folder / "mixed.dcm",
            4,
            generate_uid(),
        )
        with self.assertRaisesRegex(ValueError, "Multiple incompatible CT series"):
            GECTQA(self.folder)

    def test_plot_and_pdf_outputs(self) -> None:
        qa = GECTQA(self.folder, config=measurement_config())
        qa.analyze(angle_override=0)
        figure = qa.plot_analyzed_image(show=False)
        self.assertEqual(len(figure.axes), 6)
        self.assertEqual(len(qa.plotly_analyzed_images(show=False)), 5)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as report:
            report_name = report.name
        try:
            qa.publish_pdf(report_name)
            self.assertGreater(Path(report_name).stat().st_size, 0)
        finally:
            Path(report_name).unlink()
