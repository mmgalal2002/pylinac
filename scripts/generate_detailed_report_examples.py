"""Generate local detailed-report review examples without downloading data."""

from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

FAMILIES = {
    "picketfence": ("PicketFence",),
    "winston_lutz": ("WinstonLutz2D", "WinstonLutz", "WinstonLutzMultiTargetMultiField"),
    "starshot": ("Starshot",),
    "vmat": ("DRGS", "DRCS", "DRMLC"),
    "field_analysis": ("FieldAnalysis",),
    "field_profile_analysis": ("FieldProfileAnalysis",),
    "planar_imaging": (
        "StandardImagingFC2", "IMTLRad", "DoselabRLf", "IsoAlign", "SNCFSQA",
        "LasVegas", "ElektaLasVegas", "PTWEPIDQC", "IBAPrimusA", "StandardImagingQC3",
        "StandardImagingQCkV", "SNCkV", "SNCMV", "SNCMV12510", "LeedsTOR", "LeedsTORBlue",
        "DoselabMC2kV", "DoselabMC2MV", "ACRDigitalMammography", "SmallACRMammography",
    ),
    "ct": ("CatPhan503", "CatPhan504", "CatPhan600", "CatPhan604", "CatPhan700"),
    "acr": ("ACRCT", "ACRMRILarge", "ACRMRIMedium"),
    "cheese": ("TomoCheese", "CIRS062M"),
    "quart": ("QuartDVT", "HypersightQuartDVT"),
    "ge_ct_qa": ("GECTQA",),
    "helios": ("GEHeliosCTDaily",),
    "dlg": ("DLG",),
    "contrib.quasar": ("QuasarLightRadScaling",),
    "contrib.orthogonality": ("JawOrthogonality",),
}

OUT_OF_SCOPE = (
    "DeviceFieldAnalysis", "MaxCountRate", "PlanarUniformity", "CenterOfRotation",
    "TomographicResolution", "SimpleSensitivity", "FourBarResolution", "QuadrantResolution",
    "TomographicUniformity", "TomographicContrast", "Dynalog", "TrajectoryLog", "MachineLogs",
    "TG51Photon", "TG51ElectronLegacy", "TG51ElectronModern", "TRS398Photon", "TRS398Electron",
)


def _local_spec(name: str, model: type, source: Path) -> dict[str, object] | None:
    files = {
        "PicketFence": ("AS1200.dcm",),
        "WinstonLutz": ("winston_lutz.zip",),
        "WinstonLutz2D": ("winston_lutz.zip",),
        "WinstonLutzMultiTargetMultiField": ("SNC_MTWL_demo.zip",),
        "Starshot": ("starshot.tif",),
        "DRGS": ("DRGS_open.dcm", "DRGS_dmlc.dcm"),
        "DRCS": ("VMAT_vmat_mod-rad-open.dcm", "VMAT_vmat_mod-rad-dyn.dcm"),
        "DRMLC": ("DRMLC_open.dcm", "DRMLC_dmlc.dcm"),
        "FieldAnalysis": ("Field Analysis/fa.dcm",),
        "FieldProfileAnalysis": ("Field Analysis/10x10 field analysis.dcm",),
        "ACRCT": ("acr1.zip",),
        "ACRMRILarge": ("ACRMRILarge.zip",),
        "GECTQA": ("GE Set 1.zip",),
        "GEHeliosCTDaily": ("GE Set 1.zip",),
        "JawOrthogonality": ("10x10.dcm",),
        "LasVegas": ("LasVegas2.dcm",),
        "SmallACRMammography": ("Planar Mammo.dcm",),
    }
    if name in {"ACRMRIMedium", "HypersightQuartDVT", "LeedsTORBlue", "QuasarLightRadScaling", "Starshot"}:
        return None
    if name in files:
        inputs = [str(source / item) for item in files[name]]
    else:
        filename = getattr(model, "_demo_filename", None) or getattr(model, "_demo_url", None)
        if not filename:
            return None
        matches = sorted(path for path in source.rglob("*") if path.is_file() and path.name.casefold() == str(filename).casefold())
        if not matches and name == "CatPhan604":
            matches = sorted(source.rglob("CBCTCatPhan604.zip"))
        if not matches:
            return None
        inputs = [str(matches[0])]
    if any(not Path(item).exists() for item in inputs):
        return None
    method = "from_zip" if len(inputs) == 1 and inputs[0].lower().endswith(".zip") else "constructor"
    if name == "WinstonLutz2D":
        method = "first_winston_lutz_image"
    return {"inputs": inputs, "method": method, "init": {}, "analyze": {}}


def _construct(model: type, name: str, spec: Mapping[str, object], source: Path) -> object:
    inputs = [str((source / str(item)).resolve()) if not Path(str(item)).is_absolute() else str(item) for item in spec.get("inputs", [])]
    init = dict(spec.get("init", {}))
    method = str(spec.get("method", "constructor"))
    if method not in {"constructor", "from_zip", "from_multiple_images", "first_winston_lutz_image"}:
        raise ValueError("Example generation accepts local constructors and archive/image factories only; downloads are not supported.")
    if method == "first_winston_lutz_image":
        from pylinac.winston_lutz import WinstonLutz

        analysis = WinstonLutz.from_zip(inputs[0], **init)
        analysis.analyze(**dict(spec.get("analyze", {})))
        return analysis.images[0]
    factory = model if method == "constructor" else getattr(model, method)
    if name in {"DRGS", "DRCS", "DRMLC"} and len(inputs) > 1:
        analysis = factory(inputs, **init)
    else:
        analysis = factory(*inputs, **init)
    kwargs = dict(spec.get("analyze", {}))
    if name == "DLG" and isinstance(kwargs.get("mlc"), str):
        from pylinac.picketfence import MLC

        kwargs["mlc"] = MLC[kwargs["mlc"]]
    if name == "WinstonLutzMultiTargetMultiField" and "bb_arrangement" not in kwargs:
        from pylinac.winston_lutz import BBArrangement

        kwargs["bb_arrangement"] = BBArrangement.DEMO
    analysis.analyze(**kwargs)
    return analysis


def _write_progress(output: Path, records: Mapping[str, object]) -> None:
    (output / "generation_status.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    lines = [
        "# Detailed PDF Example Generation", "",
        "Local generation only. No test suite, content checks or human acceptance were performed.", "",
        "| Analysis | Generation | PDFs | Detail |", "| --- | --- | --- | --- |",
    ]
    for name, record in records.items():
        status = record["status"]
        files = ", ".join(record.get("files", [])) or "None"
        detail = str(record.get("detail", "")).replace("|", "/").replace("\n", " ")
        lines.append(f"| {name} | {status} | {files} | {detail} |")
    (output / "generation_status.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    """Generate explicitly identified local review examples and record every outcome."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--only", nargs="+")
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if not source.is_dir():
        parser.error(f"Input directory does not exist: {source}")
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest else {}
    registry = {name: module for module, names in FAMILIES.items() for name in names}
    unknown = set(manifest) - set(registry)
    if unknown:
        parser.error(f"Unsupported analysis names: {', '.join(sorted(unknown))}")
    if args.only and set(args.only) - set(registry):
        parser.error("--only contains an unsupported analysis name.")
    status_path = output / "generation_status.json"
    records = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    for name in registry:
        records.setdefault(name, {"status": "Pending", "files": []})
    for name in OUT_OF_SCOPE:
        records[name] = {"status": "Excluded by user scope", "files": [], "detail": "Scope is X-ray imaging, MRI, CT and mammography only."}
    failures = 0
    for name, module in registry.items():
        if args.only and name not in args.only:
            continue
        print(f"Generating {name}...", flush=True)
        record = {"status": "Pending", "files": [], "updated": datetime.now().isoformat()}
        records[name] = record
        try:
            model = getattr(importlib.import_module(f"pylinac.{module}"), name)
            spec = manifest.get(name) or _local_spec(name, model, source)
            if spec is None:
                detail = "Supplied TIFF has no SID. Provide the measured source-to-image distance in the Starshot manifest's init settings." if name == "Starshot" else "No matching local input or required measurement configuration. Supply this analysis in --manifest."
                record.update(status="Awaiting input", detail=detail)
            else:
                record["source_inputs"] = spec.get("inputs", [])
                record["stage"] = "Loading and analysis"
                analysis = _construct(model, name, spec, source)
                for variant in ("detailed", "branded"):
                    destination = output / f"{name}_{variant}.pdf"
                    options = dict(spec.get("publish", {}))
                    options.update(detailed=True, open_file=False)
                    if variant == "branded":
                        options["branding"] = {
                            "name": "QA Report Review", "report_title": f"{name} Report Review",
                            "primary_color": "#165A70", "chart_color": "#287A63",
                            "header_text": "Local QA review", "footer_text": "Human acceptance pending",
                        }
                    record["stage"] = f"{variant.capitalize()} PDF generation"
                    analysis.publish_pdf(destination, **options)
                    record["files"].append(destination.name)
                record.update(status="Generated", detail="Standard and branded examples generated; human review pending.")
        except Exception as error:
            failures += 1
            record.update(status="Generation failed", detail=f"{type(error).__name__}: {error}")
        _write_progress(output, records)
        print(f"{name}: {record['status']}", flush=True)
    print(f"Reports and per-analysis Markdown progress: {output}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())