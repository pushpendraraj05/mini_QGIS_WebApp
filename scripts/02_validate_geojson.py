import geopandas as gpd
from pathlib import Path
import pandas as pd


# ============================================================
# PROJECT CONFIGURATION
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parent.parent

INPUT_DIR = PROJECT_DIR / "output" / "geojson"
REPORT_DIR = PROJECT_DIR / "reports"

REPORT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# EXPECTED FIELDS
# ============================================================

EXPECTED_FIELDS = [
    "FID",
    "DIST_NAME",
    "DIST_CODE",
    "BLK_NAME",
    "BLK_C_2011",
    "V_NAME",
    "V_CODE2011",
    "POP_2011",
    "AREA",
    "GPCODE2011",
    "GPNAME_1",
    "GP_POP",
    "REMARKS",
    "DistrictID",
    "BlockID"
]


# ============================================================
# VALIDATE ONE GEOJSON FILE
# ============================================================

def validate_geojson(file_path):

    print("\n" + "=" * 70)
    print("GEOJSON VALIDATION")
    print("=" * 70)

    print("File:")
    print(file_path)

    # --------------------------------------------------------
    # Read GeoJSON
    # --------------------------------------------------------

    gdf = gpd.read_file(file_path)

    print("\nFile successfully loaded.")

    # --------------------------------------------------------
    # Basic information
    # --------------------------------------------------------

    feature_count = len(gdf)
    column_count = len(gdf.columns)

    print("\n" + "-" * 70)
    print("1. BASIC INFORMATION")
    print("-" * 70)

    print("Features :", feature_count)
    print("Columns  :", column_count)

    # --------------------------------------------------------
    # CRS
    # --------------------------------------------------------

    print("\n" + "-" * 70)
    print("2. CRS CHECK")
    print("-" * 70)

    print("CRS:", gdf.crs)

    if gdf.crs:

        epsg = gdf.crs.to_epsg()

        print("EPSG:", epsg)

        if epsg == 4326:

            print("Status: OK - WGS 84")

        else:

            print(
                f"Status: CRS is EPSG:{epsg}"
            )

    else:

        epsg = None

        print("WARNING: CRS is missing.")

    # --------------------------------------------------------
    # Geometry type
    # --------------------------------------------------------

    print("\n" + "-" * 70)
    print("3. GEOMETRY TYPE")
    print("-" * 70)

    geometry_types = (
        gdf.geometry
        .geom_type
        .value_counts()
    )

    print(geometry_types)

    # --------------------------------------------------------
    # Null geometry
    # --------------------------------------------------------

    null_geometry = (
        gdf.geometry.isna().sum()
    )

    print("\n" + "-" * 70)
    print("4. NULL GEOMETRY")
    print("-" * 70)

    print(
        "Null geometries:",
        null_geometry
    )

    # --------------------------------------------------------
    # Empty geometry
    # --------------------------------------------------------

    empty_geometry = (
        gdf.geometry.is_empty.sum()
    )

    print("\n" + "-" * 70)
    print("5. EMPTY GEOMETRY")
    print("-" * 70)

    print(
        "Empty geometries:",
        empty_geometry
    )

    # --------------------------------------------------------
    # Invalid geometry
    # --------------------------------------------------------

    invalid_mask = (
        ~gdf.geometry.is_valid
        & gdf.geometry.notna()
    )

    invalid_geometry = (
        invalid_mask.sum()
    )

    print("\n" + "-" * 70)
    print("6. INVALID GEOMETRY")
    print("-" * 70)

    print(
        "Invalid geometries:",
        invalid_geometry
    )

    # --------------------------------------------------------
    # Geometry validity reasons
    # --------------------------------------------------------

    invalid_details = []

    if invalid_geometry > 0:

        for index in gdf.index[invalid_mask]:

            try:

                reason = (
                    gdf.loc[index, "geometry"]
                    .is_valid
                )

                invalid_details.append({
                    "Feature_Index": index,
                    "V_NAME": (
                        gdf.loc[index, "V_NAME"]
                        if "V_NAME" in gdf.columns
                        else ""
                    ),
                    "Validity": reason
                })

            except Exception:

                pass

    # --------------------------------------------------------
    # Expected fields
    # --------------------------------------------------------

    print("\n" + "-" * 70)
    print("7. ATTRIBUTE FIELD CHECK")
    print("-" * 70)

    missing_fields = []

    for field in EXPECTED_FIELDS:

        if field in gdf.columns:

            print(f"[OK]      {field}")

        else:

            print(f"[MISSING] {field}")

            missing_fields.append(field)

    # --------------------------------------------------------
    # Missing values
    # --------------------------------------------------------

    print("\n" + "-" * 70)
    print("8. MISSING ATTRIBUTE VALUES")
    print("-" * 70)

    missing_values = []

    for field in gdf.columns:

        count = gdf[field].isna().sum()

        if count > 0:

            missing_values.append({
                "Field": field,
                "Missing_Count": count
            })

            print(
                f"{field}: {count}"
            )

    if not missing_values:

        print("No missing attribute values.")

    # --------------------------------------------------------
    # Duplicate FID
    # --------------------------------------------------------

    print("\n" + "-" * 70)
    print("9. DUPLICATE ID CHECK")
    print("-" * 70)

    duplicate_results = []

    id_fields = [
        "FID",
        "V_CODE2011",
        "GPCODE2011"
    ]

    for field in id_fields:

        if field not in gdf.columns:

            continue

        duplicate_mask = (
            gdf[field]
            .duplicated(keep=False)
        )

        duplicate_count = (
            duplicate_mask.sum()
        )

        unique_duplicate_values = (
            gdf.loc[
                duplicate_mask,
                field
            ]
            .nunique()
        )

        duplicate_results.append({
            "Field": field,
            "Duplicate_Rows": duplicate_count,
            "Duplicate_Values": unique_duplicate_values
        })

        print(
            f"{field}: "
            f"{duplicate_count} duplicate rows, "
            f"{unique_duplicate_values} duplicate values"
        )

    # --------------------------------------------------------
    # Required field statistics
    # --------------------------------------------------------

    print("\n" + "-" * 70)
    print("10. IMPORTANT FIELD STATISTICS")
    print("-" * 70)

    important_fields = [
        "V_NAME",
        "GPNAME_1",
        "GP_POP",
        "POP_2011",
        "AREA"
    ]

    for field in important_fields:

        if field not in gdf.columns:

            continue

        print(
            f"\n{field}"
        )

        print(
            "  Records:",
            gdf[field].notna().sum()
        )

        print(
            "  Missing:",
            gdf[field].isna().sum()
        )

        if pd.api.types.is_numeric_dtype(
            gdf[field]
        ):

            print(
                "  Minimum:",
                gdf[field].min()
            )

            print(
                "  Maximum:",
                gdf[field].max()
            )

    # --------------------------------------------------------
    # Create QC summary
    # --------------------------------------------------------

    summary = {

        "File": file_path.name,

        "Feature_Count": feature_count,

        "Column_Count": column_count,

        "CRS": str(gdf.crs),

        "EPSG": epsg,

        "Null_Geometry": null_geometry,

        "Empty_Geometry": empty_geometry,

        "Invalid_Geometry": invalid_geometry,

        "Missing_Fields": len(missing_fields),

        "Missing_Values": sum(
            item["Missing_Count"]
            for item in missing_values
        ),

        "Status":
            "PASS"
            if (
                invalid_geometry == 0
                and null_geometry == 0
                and empty_geometry == 0
                and len(missing_fields) == 0
            )
            else "CHECK REQUIRED"
    }

    # --------------------------------------------------------
    # Save summary report
    # --------------------------------------------------------

    summary_file = (
        REPORT_DIR /
        "01_validation_summary.csv"
    )

    pd.DataFrame(
        [summary]
    ).to_csv(
        summary_file,
        index=False
    )

    # --------------------------------------------------------
    # Save missing values report
    # --------------------------------------------------------

    missing_file = (
        REPORT_DIR /
        "01_missing_values.csv"
    )

    pd.DataFrame(
        missing_values
    ).to_csv(
        missing_file,
        index=False
    )

    # --------------------------------------------------------
    # Save duplicate report
    # --------------------------------------------------------

    duplicate_file = (
        REPORT_DIR /
        "01_duplicate_ids.csv"
    )

    pd.DataFrame(
        duplicate_results
    ).to_csv(
        duplicate_file,
        index=False
    )

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("VALIDATION RESULT")
    print("=" * 70)

    print(
        "Overall status:",
        summary["Status"]
    )

    print(
        "\nReports saved to:"
    )

    print(REPORT_DIR)

    return gdf


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

        print(INPUT_DIR)

        return

    print(
        f"\nFound {len(geojson_files)} GeoJSON file(s)."
    )

    for file_path in geojson_files:

        try:

            validate_geojson(
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
                error
            )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()