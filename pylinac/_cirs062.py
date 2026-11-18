"""Nominal Model 062 phantom data for JSON and detailed PDF exports."""

from pydantic import BaseModel, Field


class CIRS062Density(BaseModel):
    """Nominal mass density and electron density relative to water."""

    physical_density_g_cm3: float | None = Field(title="Physical density (g/cm³)")
    relative_electron_density: float | None = Field(title="RED (water = 1)")


class CIRS062Part(BaseModel):
    """Nominal specifications for a phantom component, insert or accessory."""

    model_no: str = Field(title="Model number")
    physical_density_g_cm3: float | None = Field(title="Physical density (g/cm³)")
    electron_density_1e23_per_cm3: float | None = Field(
        title="Electron density (×10²³ electrons/cm³)"
    )
    relative_electron_density: float | None = Field(title="RED (water = 1)")


class CIRS062IncludedPart(CIRS062Part):
    """Catalog part supplied with the phantom and its supplied quantity."""

    quantity: int = Field(title="Quantity")


class CIRS062ApproximateHU(BaseModel):
    """Approximate CT number or inclusive endpoints of an estimated HU range."""

    minimum_hu: int = Field(title="Lower estimate (HU)")
    maximum_hu: int = Field(title="Upper estimate (HU)")


class CIRS062NominalReference(BaseModel):
    """Nominal phantom specifications and material reference tables."""

    model: str = Field(title="Phantom model")
    approximate_thickness_cm: int = Field(title="Approximate thickness (cm)")
    material: str = Field(title="Phantom material")
    included_components: dict[str, CIRS062IncludedPart] = Field(
        title="Included phantom components"
    )
    included_inserts: dict[str, CIRS062IncludedPart] = Field(title="Included inserts")
    optional_accessories: dict[str, CIRS062Part] = Field(title="Optional accessories")
    approximate_hu: dict[str, CIRS062ApproximateHU] = Field(
        title="Approximate Hounsfield units (HU)"
    )
    model_062m_mass_density_and_red: dict[str, CIRS062Density] = Field(
        title="Model 062M physical density and RED"
    )
    reference_notes: dict[str, str] = Field(title="Nominal reference notes")


# Description, model number, quantity, mass density, electron density, RED.
_INCLUDED_COMPONENTS = (
    ("Phantom Head (Center Section)", "06202", 1, 1.01, 3.346, 1.002),
    ("Phantom Body (Outer Ring)", "06202", 1, 1.01, 3.346, 1.002),
)
_INCLUDED_INSERTS = (
    ("H2O Syringe", "06203", 1, 1.00, 3.340, 1.000),
    ("Lung (Inhale)", "06204", 2, 0.20, 0.634, 0.190),
    ("Lung (Exhale)", "06205", 2, 0.50, 1.632, 0.489),
    ("Breast (50/50)", "06206", 2, 0.99, 3.261, 0.976),
    ("Dense Bone 800 mg/cc", "06207", 2, 1.53, 4.862, 1.456),
    ("Trabecular Bone 200 mg/cc", "06208", 2, 1.16, 3.730, 1.117),
    ("Liver", "06209", 2, 1.07, 3.516, 1.052),
    ("Muscle", "06210", 2, 1.06, 3.483, 1.043),
    ("Adipose", "06211", 2, 0.96, 3.170, 0.949),
    ("Distance Marker", "06213", 2, 1.01, None, None),
)

# Description, model number, mass density, electron density, RED.
_OPTIONAL_ACCESSORIES = (
    ("Titanium Insert", "06212", 4.51, 12.475, 3.735),
    ("H2O Insert With Chamber Cavity", "06214-CV", 1.01, 3.346, 1.002),
    ("Dense Bone 800 mg/cc", "06215", 1.53, 4.862, 1.456),
    ("H2O Insert", "06216", 1.01, 3.346, 1.002),
    ("Dense Bone 1000 mg/cc", "06217", 1.66, 5.243, 1.570),
    ("Dense Bone 1250 mg/cc", "06218", 1.83, 5.718, 1.712),
    ("Cortical Bone", "06219", 1.93, 5.956, 1.780),
    ("Dense Bone 1500 mg/cc", "06220", 2.00, 6.209, 1.859),
    ("Dense Bone 1750 mg/cc", "06221", 2.17, 6.698, 2.005),
    ("Cranial Bone Ring", "06222", None, None, None),
)

# Material, lower HU estimate, upper HU estimate.
_APPROXIMATE_HU = (
    ("Lung (Inhale)", -800, -800),
    ("Lung (Exhale)", -500, -500),
    ("Adipose", -100, -100),
    ("Breast", -30, -30),
    ("Water", 0, 0),
    ("Muscle", 40, 40),
    ("Liver", 60, 60),
    ("Trabecular Bone 200", 200, 350),
    ("Dense Bone 800", 800, 1200),
    ("Dense Bone 1250", 1300, 1800),
)

# Material, mass density, RED, as listed in the supplied density/RED table.
_MASS_DENSITY_AND_RED = (
    ("Lung (Inhale)", 0.205, 0.200),
    ("Lung (Exhale)", 0.507, 0.496),
    ("Adipose", 0.960, 0.949),
    ("Breast (50/50)", 0.990, 0.976),
    ("Water", 1.000, 1.000),
    ("Water-equivalent Background", 1.029, 0.998),
    ("Muscle", 1.060, 1.043),
    ("Liver", 1.070, 1.052),
    ("Trabecular Bone (200 mg/cm³ HA)", 1.160, 1.117),
    ("Dense Bone (800 mg/cm³ HA)", 1.530, 1.456),
    ("Dense Bone (1000 mg/cm³ HA)", 1.660, 1.570),
    ("Dense Bone (1250 mg/cm³ HA)", 1.820, 1.695),
    ("Cortical Bone (ICRU)", 1.910, 1.771),
    ("Dense Bone (1500 mg/cm³ HA)", 1.990, 1.837),
    ("Dense Bone (1750 mg/cm³ HA)", 2.150, 1.976),
)


def _included_parts(
    rows: tuple[tuple[str, str, int, float, float | None, float | None], ...],
) -> dict[str, CIRS062IncludedPart]:
    return {
        description: CIRS062IncludedPart(
            model_no=model_no,
            quantity=quantity,
            physical_density_g_cm3=mass_density,
            electron_density_1e23_per_cm3=electron_density,
            relative_electron_density=red,
        )
        for description, model_no, quantity, mass_density, electron_density, red in rows
    }


def build_nominal_reference() -> CIRS062NominalReference:
    """Build an independent snapshot of the supplied Model 062 reference data."""
    return CIRS062NominalReference(
        model="CIRS Model 062 Electron Density Phantom",
        approximate_thickness_cm=5,
        material="Proprietary epoxy resin",
        included_components=_included_parts(_INCLUDED_COMPONENTS),
        included_inserts=_included_parts(_INCLUDED_INSERTS),
        optional_accessories={
            description: CIRS062Part(
                model_no=model_no,
                physical_density_g_cm3=mass_density,
                electron_density_1e23_per_cm3=electron_density,
                relative_electron_density=red,
            )
            for description, model_no, mass_density, electron_density, red in _OPTIONAL_ACCESSORIES
        },
        approximate_hu={
            material: CIRS062ApproximateHU(minimum_hu=minimum, maximum_hu=maximum)
            for material, minimum, maximum in _APPROXIMATE_HU
        },
        model_062m_mass_density_and_red={
            material: CIRS062Density(
                physical_density_g_cm3=mass_density, relative_electron_density=red
            )
            for material, mass_density, red in _MASS_DENSITY_AND_RED
        },
        reference_notes={
            "physical_density": "Physical density represents mass density in g/cm³.",
            "electron_density": "Electron density is expressed in ×10²³ electrons/cm³.",
            "relative_electron_density": "RED represents relative electron density with respect to water.",
            "bone_reference_diameter": "All bone references are 10 mm in diameter in an H2O insert.",
            "bone_reference_composition": "Bone references contain hydroxyapatite (mg/cc) in an H2O background.",
            "special_order_plugs": "Plugs to accommodate chambers, TLDs, and film are available upon special request.",
        },
    )
