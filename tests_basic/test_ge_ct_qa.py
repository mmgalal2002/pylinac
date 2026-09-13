import tempfile
import zipfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import numpy as np
import pydicom
from matplotlib import pyplot as plt
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from pylinac import GECTQA
from pylinac.ge_ct_qa import (
    GE_HELIOS_CT,
    GE_LIGHTSPEED16,
    GE_OPTIMA_CT,
    GECTQAROI,
    GECTQAConfig,
    GECTQAMaterialROI,
    GECTQAReferenceParameter,
    GECTQASliceThicknessConfig,
)


def write_ct_image(
    filename: Path,
    instance_number: int,
    series_uid: str,
    include_material: bool = False,
    manufacturer_model_name: str = "Synthetic GE CT",
) -> None:
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = pydicom.uid.CTImageStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset = FileDataset(str(filename), {}, file_meta=file_meta, preamble=b"\0" * 128)
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
    dataset.ManufacturerModelName = manufacturer_model_name
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

    def test_lightspeed16_is_detected_without_claiming_optima_or_helios(self) -> None:
        for path in self.folder.glob("slice_*.dcm"):
            dataset = pydicom.dcmread(path)
            dataset.ManufacturerModelName = "LightSpeed16"
            dataset.save_as(path)

        qa = GECTQA(self.folder)
        self.assertEqual(qa.profile_selection.scanner_id, GE_LIGHTSPEED16)
        self.assertEqual(qa.profile_selection.phantom_id, "GE_20CM_QA_PHANTOM")
        self.assertEqual(qa.profile_selection.scanner_source, "dicom")
        qa.analyze(angle_override=0)
        data = qa.results_data()
        self.assertEqual(data.configuration.scanner_id, GE_LIGHTSPEED16)
        self.assertEqual(data.configuration.scanner_display_name, "GE LightSpeed16")
        self.assertEqual(data.reference.reference_scope, "shared_ge_reference")
        self.assertNotIn("GE Optima", data.configuration.scanner_display_name)
        self.assertNotIn("GE Helios", data.configuration.scanner_display_name)

    def test_unknown_scanner_uses_generic_fallback(self) -> None:
        with self.assertWarnsRegex(UserWarning, "Unknown scanner model"):
            qa = GECTQA(self.folder)
        self.assertEqual(qa.profile_selection.scanner_id, "GENERIC_GE_CT")
        self.assertEqual(qa.profile_selection.scanner_source, "fallback")

    def test_manual_scanner_profiles_are_recorded_as_user_selected(self) -> None:
        optima = GECTQA(self.folder, scanner_profile=GE_OPTIMA_CT)
        helios = GECTQA(self.folder, scanner_profile=GE_HELIOS_CT)
        self.assertEqual(optima.profile_selection.scanner_id, GE_OPTIMA_CT)
        self.assertEqual(optima.profile_selection.scanner_source, "user")
        self.assertEqual(helios.profile_selection.scanner_id, GE_HELIOS_CT)
        self.assertEqual(helios.profile_selection.scanner_source, "user")
        self.assertEqual(
            optima.profile_selection.scanner_model_from_dicom, "Synthetic GE CT"
        )

    def test_missing_plexiglass_reference_is_not_evaluated(self) -> None:
        config = GECTQAConfig(
            ct_number_rois={
                "Plexiglass": GECTQAMaterialROI(x_mm=0, y_mm=0, radius_mm=5),
            }
        )
        qa = GECTQA(self.folder, config=config)
        qa.analyze(angle_override=0)
        data = qa.results_data()
        self.assertEqual(data.ct_number.status, "NOT_EVALUATED")
        self.assertIn("Plexiglass", data.ct_number.reason)
        self.assertIsNone(data.reference.plexiglass_water_difference_hu)

    def test_slice_thickness_requires_geometry_and_calibration(self) -> None:
        config = GECTQAConfig(
            slice_thickness=GECTQASliceThicknessConfig(
                roi=GECTQAROI(x_mm=0, y_mm=0, radius_mm=5),
                nominal_mm=2.5,
                tolerance_mm=0.5,
            )
        )
        qa = GECTQA(self.folder, config=config)
        qa.analyze(angle_override=0)
        result = qa.results_data().slice_thickness
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertIn("insert geometry and calibration", result.reason)

    def test_alignment_is_unavailable_without_dedicated_acquisition(self) -> None:
        qa = GECTQA(self.folder)
        qa.analyze(angle_override=0)
        result = qa.results_data().alignment
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertFalse(result.applicable)
        self.assertEqual(qa.results_data().num_tests, 8)
        self.assertIn("dedicated alignment acquisition", result.reason)

    def test_scalar_override_inherits_profile_geometry(self) -> None:
        qa = GECTQA(self.folder, config=GECTQAConfig(positioning_tolerance_mm=5))
        self.assertTrue(qa.config.high_contrast_rois)
        self.assertEqual(qa.config.positioning_tolerance_mm, 5)

    def test_explicit_null_reference_does_not_fall_back(self) -> None:
        config = GECTQAConfig(
            reference_parameters={
                "noise_nominal_hu": GECTQAReferenceParameter(value=None),
            }
        )
        qa = GECTQA(self.folder, config=config)
        qa.analyze(angle_override=0)
        data = qa.results_data()
        self.assertIsNone(data.noise.reference_hu)
        self.assertEqual(data.noise.status, "NOT_EVALUATED")
        self.assertIsNone(data.reference.noise_nominal_hu)

    def test_mtf_extrapolation_is_classified(self) -> None:
        class FakeMTF:
            norm_mtfs = {0.1: 0.3, 0.2: 0.2, 0.3: 0.1}

            @staticmethod
            def relative_resolution(percentage: int) -> float:
                return 0.4 - percentage / 1000

        with patch(
            "pylinac.ge_ct_qa.MTF.from_high_contrast_diskset",
            return_value=FakeMTF(),
        ):
            qa = GECTQA(self.folder, config=GECTQAConfig(minimum_resolution_lp_mm=0.1))
            qa.analyze(angle_override=0)
        result = qa.results_data().high_contrast_resolution.mtf_results
        self.assertEqual(result["90"].status, "EXTRAPOLATED")
        self.assertFalse(result["90"].measured_directly)
        self.assertTrue(result["90"].extrapolated)
        self.assertIsNone(qa.results_data().high_contrast_resolution.passed)

    def test_positioning_borderline_failure_reports_excess(self) -> None:
        config = GECTQAConfig(positioning_tolerance_mm=2.0)
        qa = GECTQA(self.folder, config=config)
        qa.analyze(center_override=(129.557, 127.5), angle_override=0)
        result = qa.results_data().positioning
        self.assertEqual(result.status, "FAIL")
        self.assertAlmostEqual(result.excess_mm, 0.057, places=3)
        self.assertIsNotNone(result.confidence)

    def test_slice_thickness_empty_sampling_window_is_unavailable(self) -> None:
        config = GECTQAConfig(
            slice_thickness=GECTQASliceThicknessConfig(
                roi=GECTQAROI(x_mm=0, y_mm=0, radius_mm=5),
                nominal_mm=2.5,
                tolerance_mm=0.5,
                sample_half_range_mm=0.1,
                insert_geometry={"validated": True},
                profile_calibration={"validated": True},
            )
        )
        qa = GECTQA(self.folder, config=config)
        qa.analyze(angle_override=0)
        result = qa.results_data().slice_thickness
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertIn("fewer than three", result.reason)

    def test_user_override_wins_and_is_traceable(self) -> None:
        config = GECTQAConfig.from_profile(
            GE_LIGHTSPEED16,
            user_overrides={"noise_reference_hu": 9.0},
        )
        qa = GECTQA(self.folder, config=config)
        qa.analyze(angle_override=0)
        data = qa.results_data()
        self.assertEqual(data.noise.reference_hu, 9.0)
        parameter = data.reference.parameters["noise_nominal_hu"]
        self.assertTrue(parameter.is_user_override)
        self.assertEqual(data.noise.overrides_used["noise_reference_hu"], 9.0)

    def test_single_file_and_zip(self) -> None:
        single = GECTQA(self.folder / "slice_1.dcm")
        single.analyze(angle_override=0)
        self.assertEqual(single.results_data().num_images, 1)
        self.assertIsNone(single.results_data().helios_compatibility.low_contrast)

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
