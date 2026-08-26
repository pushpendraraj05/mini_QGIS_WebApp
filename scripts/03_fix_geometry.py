import geopandas as gpd
import pandas as pd
import numpy as np
import re
from pathlib import Path


# ============================================================
# PROJECT CONFIGURATION
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parent.parent

INPUT_DIR = PROJECT_DIR / "output" / "geojson"
OUTPUT_DIR = PROJECT_DIR / "working" / "cleaned"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# FIELD TYPE CONFIGURATION
# ============================================================

# Fields that should normally be treated as TEXT
TEXT_FIELD_PATTERNS = [
    "NAME",
    "V_NAME",
    "GP_NAME",
    "VILLAGE",
    "VILL_NAME",
    "PANCHAYAT",
    "PANCHAYAT_NAME",
    "BLOCK",
    "BLOCK_NAME",
    "DISTRICT",
    "DISTRICT_NAME",
    "STATE",
    "STATE_NAME",
    "ADDRESS",
    "REMARK",
    "REMARKS",
    "DESCRIPTION",
    "TYPE",
    "CATEGORY",
    "STATUS"
]


# Fields that should normally be INTEGER
INTEGER_FIELD_PATTERNS = [
    "ID",
    "FID",
    "OBJECTID",
    "OID",
    "CODE",
    "COUNT",
    "POP",
    "POPULATION",
    "HOUSE",
    "HOUSES",
    "HOUSEHOLD",
    "HOUSEHOLDS",
    "MALE",
    "FEMALE",
    "TOTAL",
    "NO",
    "NUMBER"
]


# Fields that should normally be FLOAT
FLOAT_FIELD_PATTERNS = [
    "AREA",
    "LENGTH",
    "DISTANCE",
    "LAT",
    "LON",
    "LONG",
    "X",
    "Y",
    "ELEVATION",
    "DENSITY",
    "PERCENT",
    "PERCENTAGE"
]


# ============================================================
# FIELD NAME NORMALIZATION
# ============================================================

def normalize_field_name(field_name):

    return re.sub(
        r"[^A-Z0-9]",
        "_",
        str(field_name).upper()
    )


# ============================================================
# CHECK IF FIELD IS TEXT FIELD
# ============================================================

def is_text_field(field_name):

    name = normalize_field_name(field_name)

    for pattern in TEXT_FIELD_PATTERNS:

        if pattern in name:
            return True

    return False


# ============================================================
# CHECK IF FIELD IS INTEGER FIELD
# ============================================================

def is_integer_field(field_name):

    name = normalize_field_name(field_name)

    for pattern in INTEGER_FIELD_PATTERNS:

        if pattern == name:
            return True

        if name.endswith("_" + pattern):
            return True

        if name.startswith(pattern + "_"):
            return True

    return False


# ============================================================
# CHECK IF FIELD IS FLOAT FIELD
# ============================================================

def is_float_field(field_name):

    name = normalize_field_name(field_name)

    for pattern in FLOAT_FIELD_PATTERNS:

        if pattern == name:
            return True

        if name.endswith("_" + pattern):
            return True

        if name.startswith(pattern + "_"):
            return True

    return False


# ============================================================
# CHECK LEADING ZERO
# ============================================================

def contains_leading_zero(values):

    for value in values:

        if pd.isna(value):
            continue

        value = str(value).strip()

        # Example:
        # 001
        # 00025
        if re.fullmatch(r"0\d+", value):

            return True

    return False


# ============================================================
# AUTOMATIC FIELD TYPE DETECTION
# ============================================================

def detect_field_type(field_name, series):

    # --------------------------------------------------------
    # Existing boolean
    # --------------------------------------------------------

    if pd.api.types.is_bool_dtype(series):

        return "bool"


    # --------------------------------------------------------
    # Existing datetime
    # --------------------------------------------------------

    if pd.api.types.is_datetime64_any_dtype(series):

        return "datetime"


    # --------------------------------------------------------
    # Explicit text fields
    # --------------------------------------------------------

    if is_text_field(field_name):

        return "string"


    # --------------------------------------------------------
    # Explicit integer fields
    # --------------------------------------------------------

    if is_integer_field(field_name):

        # Never destroy leading zeros
        if contains_leading_zero(series):

            return "string"

        numeric = pd.to_numeric(
            series,
            errors="coerce"
        )

        valid_values = series.notna().sum()

        numeric_values = numeric.notna().sum()

        if valid_values == 0:

            return "Int64"

        if numeric_values == valid_values:

            # Check whether values are actually integers

            if (
                numeric.dropna() % 1 == 0
            ).all():

                return "Int64"

        return "string"


    # --------------------------------------------------------
    # Explicit float fields
    # --------------------------------------------------------

    if is_float_field(field_name):

        numeric = pd.to_numeric(
            series,
            errors="coerce"
        )

        valid_values = series.notna().sum()

        numeric_values = numeric.notna().sum()

        if (
            valid_values > 0
            and numeric_values == valid_values
        ):

            return "float64"

        return "string"


    # --------------------------------------------------------
    # Automatic numeric detection
    # --------------------------------------------------------

    if (
        pd.api.types.is_numeric_dtype(series)
    ):

        if pd.api.types.is_integer_dtype(series):

            return "Int64"

        return "float64"


    # --------------------------------------------------------
    # Convert object/string to numeric if safe
    # --------------------------------------------------------

    non_null = series.dropna()

    if len(non_null) > 0:

        numeric = pd.to_numeric(
            non_null,
            errors="coerce"
        )

        numeric_ratio = (
            numeric.notna().sum()
            / len(non_null)
        )

        # Only convert when 100% of values are numeric
        if numeric_ratio == 1.0:

            if (
                numeric % 1 == 0
            ).all():

                # Do not convert values such as 001
                if not contains_leading_zero(non_null):

                    return "Int64"

                return "string"

            return "float64"


    # --------------------------------------------------------
    # Automatic boolean detection
    # --------------------------------------------------------

    unique_values = set(
        str(v).strip().lower()
        for v in non_null
    )

    boolean_values = {
        "true",
        "false",
        "yes",
        "no",
        "y",
        "n"
    }

    if (
        len(unique_values) > 0
        and unique_values.issubset(boolean_values)
    ):

        return "bool"


    # --------------------------------------------------------
    # Default
    # --------------------------------------------------------

    return "string"


# ============================================================
# CONVERT FIELD
# ============================================================

def convert_field(series, detected_type):

    try:

        # ----------------------------------------------------
        # STRING
        # ----------------------------------------------------

        if detected_type == "string":

            return (
                series
                .astype("string")
                .replace(
                    {
                        "nan": pd.NA,
                        "None": pd.NA,
                        "": pd.NA
                    }
                )
            )


        # ----------------------------------------------------
        # INTEGER
        # ----------------------------------------------------

        if detected_type == "Int64":

            numeric = pd.to_numeric(
                series,
                errors="coerce"
            )

            return numeric.round().astype("Int64")


        # ----------------------------------------------------
        # FLOAT
        # ----------------------------------------------------

        if detected_type == "float64":

            return pd.to_numeric(
                series,
                errors="coerce"
            ).astype("float64")


        # ----------------------------------------------------
        # BOOLEAN
        # ----------------------------------------------------

        if detected_type == "bool":

            mapping = {
                "true": True,
                "false": False,
                "yes": True,
                "no": False,
                "y": True,
                "n": False
            }

            return (
                series
                .astype("string")
                .str.strip()
                .str.lower()
                .map(mapping)
                .astype("boolean")
            )


        # ----------------------------------------------------
        # DATETIME
        # ----------------------------------------------------

        if detected_type == "datetime":

            return pd.to_datetime(
                series,
                errors="coerce"
            )


    except Exception:

        # If conversion fails, preserve original data
        return series.astype("string")


    return series


# ============================================================
# AUTOMATIC DATA TYPE CLEANING
# ============================================================

def fix_data_types(gdf):

    print("\n" + "=" * 70)
    print("ATTRIBUTE DATA TYPE NORMALIZATION")
    print("=" * 70)

    type_report = []

    # --------------------------------------------------------
    # Process every non-geometry field
    # --------------------------------------------------------

    for field in gdf.columns:

        if field == gdf.geometry.name:

            continue

        original_dtype = str(
            gdf[field].dtype
        )

        detected_type = detect_field_type(
            field,
            gdf[field]
        )

        # ----------------------------------------------------
        # Convert
        # ----------------------------------------------------

        gdf[field] = convert_field(
            gdf[field],
            detected_type
        )

        final_dtype = str(
            gdf[field].dtype
        )

        # ----------------------------------------------------
        # Report
        # ----------------------------------------------------

        type_report.append(
            {
                "Field_Name": field,
                "Original_Type": original_dtype,
                "Detected_Type": detected_type,
                "Final_Type": final_dtype
            }
        )

        print(
            f"{field:<30} "
            f"{original_dtype:<15} -> "
            f"{final_dtype}"
        )

    return (
        gdf,
        pd.DataFrame(type_report)
    )


# ============================================================
# FIX GEOMETRY
# ============================================================

def fix_geometry(file_path):

    print("\n" + "=" * 70)
    print("PROCESSING FILE")
    print("=" * 70)

    print("Input:")
    print(file_path)

    # --------------------------------------------------------
    # Read GeoJSON
    # --------------------------------------------------------

    gdf = gpd.read_file(
        file_path
    )

    original_count = len(gdf)

    print(
        "\nTotal features:",
        original_count
    )

    # --------------------------------------------------------
    # CRS
    # --------------------------------------------------------

    print(
        "CRS:",
        gdf.crs
    )

    # --------------------------------------------------------
    # Geometry statistics BEFORE repair
    # --------------------------------------------------------

    null_before = (
        gdf.geometry.isna().sum()
    )

    empty_before = (
        gdf.geometry.is_empty.sum()
    )

    invalid_before = (
        (
            ~gdf.geometry.is_valid
        )
        & gdf.geometry.notna()
    ).sum()

    print("\nBEFORE REPAIR")
    print("-" * 70)

    print(
        "Null geometries   :",
        null_before
    )

    print(
        "Empty geometries  :",
        empty_before
    )

    print(
        "Invalid geometries:",
        invalid_before
    )

    # --------------------------------------------------------
    # Repair invalid geometries
    # --------------------------------------------------------

    print("\nRepairing geometries...")

    repair_mask = (
        gdf.geometry.notna()
        & (
            ~gdf.geometry.is_valid
        )
    )

    repaired_count = int(
        repair_mask.sum()
    )

    if repaired_count > 0:

        gdf.loc[
            repair_mask,
            "geometry"
        ] = (
            gdf.loc[
                repair_mask,
                "geometry"
            ].make_valid()
        )

    print(
        "Geometries repaired:",
        repaired_count
    )

    # --------------------------------------------------------
    # Remove empty geometries
    # --------------------------------------------------------

    empty_mask = (
        gdf.geometry.notna()
        & gdf.geometry.is_empty
    )

    empty_count = int(
        empty_mask.sum()
    )

    if empty_count > 0:

        print(
            "Empty geometries found:",
            empty_count
        )

        gdf = gdf.loc[
            ~empty_mask
        ].copy()

    # --------------------------------------------------------
    # Remove NULL geometries
    # --------------------------------------------------------

    null_mask = (
        gdf.geometry.isna()
    )

    null_removed = int(
        null_mask.sum()
    )

    if null_removed > 0:

        print(
            "NULL geometries found:",
            null_removed
        )

        gdf = gdf.loc[
            ~null_mask
        ].copy()

    # ========================================================
    # ATTRIBUTE DATA TYPE FIX
    # ========================================================

    gdf, type_report = fix_data_types(
        gdf
    )

    # --------------------------------------------------------
    # Check geometry AFTER repair
    # --------------------------------------------------------

    invalid_after = (
        (
            ~gdf.geometry.is_valid
        )
        & gdf.geometry.notna()
    ).sum()

    null_after = (
        gdf.geometry.isna().sum()
    )

    empty_after = (
        gdf.geometry.is_empty.sum()
    )

    # --------------------------------------------------------
    # Geometry types
    # --------------------------------------------------------

    geometry_types = (
        gdf.geometry
        .geom_type
        .value_counts()
    )

    # ========================================================
    # OUTPUT FILE
    # ========================================================

    output_file = (
        OUTPUT_DIR /
        f"{file_path.stem}_FIXED.geojson"
    )

    # --------------------------------------------------------
    # Save cleaned GeoJSON
    # --------------------------------------------------------

    gdf.to_file(
        output_file,
        driver="GeoJSON"
    )

    # ========================================================
    # GEOMETRY REPORT
    # ========================================================

    geometry_report_file = (
        OUTPUT_DIR /
        f"{file_path.stem}_GEOMETRY_REPORT.csv"
    )

    geometry_report = pd.DataFrame([
        {
            "Input_File": file_path.name,
            "Original_Features": original_count,
            "Repaired_Geometries": repaired_count,
            "Removed_Empty_Geometries": empty_count,
            "Removed_Null_Geometries": null_removed,
            "Null_Geometries_After": null_after,
            "Empty_Geometries_After": empty_after,
            "Invalid_Geometries_After": invalid_after,
            "Final_Features": len(gdf),
            "CRS": str(gdf.crs),
            "Status":
                "PASS"
                if (
                    invalid_after == 0
                    and null_after == 0
                    and empty_after == 0
                )
                else "CHECK REQUIRED"
        }
    ])

    geometry_report.to_csv(
        geometry_report_file,
        index=False
    )

    # ========================================================
    # DATA TYPE REPORT
    # ========================================================

    type_report_file = (
        OUTPUT_DIR /
        f"{file_path.stem}_FIELD_TYPES_REPORT.csv"
    )

    type_report.to_csv(
        type_report_file,
        index=False
    )

    # ========================================================
    # FINAL RESULT
    # ========================================================

    print("\n" + "=" * 70)
    print("AFTER CLEANING")
    print("=" * 70)

    print(
        "Null geometries   :",
        null_after
    )

    print(
        "Empty geometries  :",
        empty_after
    )

    print(
        "Invalid geometries:",
        invalid_after
    )

    print(
        "Final features    :",
        len(gdf)
    )

    print("\nGeometry types:")

    print(
        geometry_types
    )

    # --------------------------------------------------------
    # Final status
    # --------------------------------------------------------

    print("\nStatus:")

    if (
        invalid_after == 0
        and null_after == 0
        and empty_after == 0
    ):

        print(
            "PASS - geometry and attributes are clean"
        )

    else:

        print(
            "CHECK REQUIRED - "
            "some geometry problems remain"
        )

    # --------------------------------------------------------
    # Output paths
    # --------------------------------------------------------

    print("\nCleaned GeoJSON:")
    print(output_file)

    print("\nGeometry Report:")
    print(geometry_report_file)

    print("\nField Type Report:")
    print(type_report_file)


# ============================================================
# MAIN
# ============================================================

def main():

    geojson_files = list(
        INPUT_DIR.glob("*.geojson")
    )

    if not geojson_files:

        print(
            "\nNo GeoJSON files found."
        )

        print(
            "Expected folder:"
        )

        print(
            INPUT_DIR
        )

        return

    print(
        f"\nFound {len(geojson_files)} GeoJSON file(s)."
    )

    for file_path in geojson_files:

        try:

            fix_geometry(
                file_path
            )

        except Exception as error:

            print(
                "\nERROR:"
            )

            print(
                file_path.name
            )

            print(
                repr(error)
            )
# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()

