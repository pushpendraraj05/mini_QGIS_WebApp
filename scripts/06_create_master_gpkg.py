import geopandas as gpd
from pathlib import Path


# ============================================================
# GIS PYTHON PROJECT
# STEP 06 - CREATE MASTER GEOPACKAGE
# ============================================================


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parent.parent

INPUT_DIR = PROJECT_DIR / "working" / "cleaned"

OUTPUT_DIR = (
    PROJECT_DIR /
    "output" /
    "geopackage"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# CONFIGURATION
# ============================================================

GPKG_NAME = "PURVI_CHAMPARAN_GIS.gpkg"

LAYER_NAME = "villages"

TARGET_EPSG = 32645

GPKG_PATH = (
    OUTPUT_DIR /
    GPKG_NAME
)


# ============================================================
# FIND INPUT FILE
# ============================================================

def find_input_file():

    files = list(
        INPUT_DIR.glob(
            "*_METRICS.geojson"
        )
    )

    if not files:

        raise FileNotFoundError(
            "\nNo *_METRICS.geojson file found in:\n"
            f"{INPUT_DIR}"
        )

    if len(files) > 1:

        print(
            "\nMultiple metrics files found:"
        )

        for file in files:
            print(
                " -",
                file.name
            )

        print(
            "\nUsing the first file."
        )

    return files[0]


# ============================================================
# RENAME RESERVED FIELDS
# ============================================================

def fix_field_names(gdf):

    print("\n" + "-" * 70)
    print("FIELD NAME CHECK")
    print("-" * 70)

    # GeoPackage/SQLite-related reserved names
    reserved_mapping = {

        "FID": "SOURCE_FID",

    }

    for old_name, new_name in reserved_mapping.items():

        if old_name in gdf.columns:

            print(
                f"Renaming field: "
                f"{old_name} -> {new_name}"
            )

            # Avoid collision if SOURCE_FID already exists
            if new_name in gdf.columns:

                print(
                    f"WARNING: {new_name} already exists."
                )

                gdf = gdf.rename(
                    columns={
                        old_name:
                        "SOURCE_FID_ORIGINAL"
                    }
                )

            else:

                gdf = gdf.rename(
                    columns={
                        old_name:
                        new_name
                    }
                )

    return gdf


# ============================================================
# CHECK AND REPAIR GEOMETRY
# ============================================================

def validate_geometry(gdf):

    print("\n" + "-" * 70)
    print("GEOMETRY CHECK")
    print("-" * 70)

    null_count = (
        gdf.geometry.isna().sum()
    )

    empty_count = (
        gdf.geometry.is_empty.sum()
    )

    invalid_count = (
        (
            ~gdf.geometry.is_valid
        )
        & gdf.geometry.notna()
    ).sum()

    print(
        "Null geometries   :",
        null_count
    )

    print(
        "Empty geometries  :",
        empty_count
    )

    print(
        "Invalid geometries:",
        invalid_count
    )

    # --------------------------------------------------------
    # Repair invalid geometry
    # --------------------------------------------------------

    if invalid_count > 0:

        print(
            "\nRepairing invalid geometries..."
        )

        gdf["geometry"] = (
            gdf.geometry.make_valid()
        )

    # --------------------------------------------------------
    # Remove null geometries
    # --------------------------------------------------------

    if null_count > 0:

        print(
            "\nRemoving null geometries..."
        )

        gdf = gdf[
            gdf.geometry.notna()
        ].copy()

    # --------------------------------------------------------
    # Remove empty geometries
    # --------------------------------------------------------

    if empty_count > 0:

        print(
            "\nRemoving empty geometries..."
        )

        gdf = gdf[
            ~gdf.geometry.is_empty
        ].copy()

    # --------------------------------------------------------
    # Final geometry check
    # --------------------------------------------------------

    final_invalid = (
        (
            ~gdf.geometry.is_valid
        )
        & gdf.geometry.notna()
    ).sum()

    print(
        "\nInvalid geometries after repair:",
        final_invalid
    )

    if final_invalid > 0:

        raise ValueError(
            "Some geometries remain invalid "
            "after repair."
        )

    return gdf


# ============================================================
# CHECK CRS
# ============================================================

def validate_crs(gdf):

    print("\n" + "-" * 70)
    print("CRS CHECK")
    print("-" * 70)

    if gdf.crs is None:

        raise ValueError(
            "Input layer has no CRS."
        )

    print(
        "Input CRS:",
        gdf.crs
    )

    source_epsg = (
        gdf.crs.to_epsg()
    )

    print(
        "Input EPSG:",
        source_epsg
    )

    # --------------------------------------------------------
    # Reproject if necessary
    # --------------------------------------------------------

    if source_epsg != TARGET_EPSG:

        print(
            f"\nReprojecting "
            f"EPSG:{source_epsg} "
            f"to EPSG:{TARGET_EPSG}"
        )

        gdf = gdf.to_crs(
            epsg=TARGET_EPSG
        )

    else:

        print(
            f"CRS already EPSG:{TARGET_EPSG}"
        )

    print(
        "Final CRS:",
        gdf.crs
    )

    return gdf


# ============================================================
# ADD MASTER GIS ID
# ============================================================

def create_gis_id(gdf):

    print("\n" + "-" * 70)
    print("GIS ID")
    print("-" * 70)

    # Remove existing GIS_ID if present
    # so reruns do not create conflicts.

    if "GIS_ID" in gdf.columns:

        print(
            "Existing GIS_ID found."
        )

        print(
            "Recreating GIS_ID."
        )

        gdf = gdf.drop(
            columns=["GIS_ID"]
        )

    gdf.insert(
        0,
        "GIS_ID",
        range(
            1,
            len(gdf) + 1
        )
    )

    print(
        "GIS_ID created."
    )

    print(
        "Range:",
        gdf["GIS_ID"].min(),
        "to",
        gdf["GIS_ID"].max()
    )

    return gdf


# ============================================================
# WRITE GEOPACKAGE
# ============================================================

def write_geopackage(gdf):

    print("\n" + "-" * 70)
    print("GEOPACKAGE CREATION")
    print("-" * 70)

    # --------------------------------------------------------
    # Delete old GeoPackage
    # --------------------------------------------------------

    if GPKG_PATH.exists():

        print(
            "Existing GeoPackage found."
        )

        print(
            "Removing old file:"
        )

        print(
            GPKG_PATH
        )

        GPKG_PATH.unlink()

    # --------------------------------------------------------
    # Write layer
    # --------------------------------------------------------

    print(
        "\nCreating GeoPackage..."
    )

    gdf.to_file(
        GPKG_PATH,
        layer=LAYER_NAME,
        driver="GPKG"
    )

    print(
        "\nGeoPackage written successfully."
    )


# ============================================================
# VERIFY GEOPACKAGE
# ============================================================

def verify_geopackage():

    print("\n" + "-" * 70)
    print("GEOPACKAGE VERIFICATION")
    print("-" * 70)

    if not GPKG_PATH.exists():

        raise FileNotFoundError(
            "GeoPackage was not created."
        )

    check = gpd.read_file(
        GPKG_PATH,
        layer=LAYER_NAME
    )

    print(
        "File:",
        GPKG_PATH
    )

    print(
        "Layer:",
        LAYER_NAME
    )

    print(
        "Features:",
        len(check)
    )

    print(
        "CRS:",
        check.crs
    )

    print(
        "EPSG:",
        check.crs.to_epsg()
    )

    print(
        "\nGeometry types:"
    )

    print(
        check.geometry
        .geom_type
        .value_counts()
    )

    print(
        "\nFields:"
    )

    for field in check.columns:

        print(
            " -",
            field
        )

    # --------------------------------------------------------
    # Final geometry check
    # --------------------------------------------------------

    invalid = (
        ~check.geometry.is_valid
    ).sum()

    null = (
        check.geometry.isna()
    ).sum()

    empty = (
        check.geometry.is_empty
    ).sum()

    print(
        "\nFinal geometry quality:"
    )

    print(
        "Invalid:",
        invalid
    )

    print(
        "Null:",
        null
    )

    print(
        "Empty:",
        empty
    )

    # --------------------------------------------------------
    # Final status
    # --------------------------------------------------------

    if (
        invalid == 0
        and null == 0
        and empty == 0
    ):

        print(
            "\nSTATUS: PASS"
        )

        print(
            "Master GeoPackage is ready."
        )

    else:

        print(
            "\nSTATUS: CHECK REQUIRED"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n")
    print("=" * 70)
    print("PURVI CHAMPARAN GIS PROJECT")
    print("STEP 06 - MASTER GEOPACKAGE")
    print("=" * 70)

    try:

        # ----------------------------------------------------
        # 1. Find input
        # ----------------------------------------------------

        input_file = find_input_file()

        print("\nInput file:")
        print(input_file)

        # ----------------------------------------------------
        # 2. Read input
        # ----------------------------------------------------

        print("\nReading GeoJSON...")

        gdf = gpd.read_file(
            input_file
        )

        print(
            "Features loaded:",
            len(gdf)
        )

        # ----------------------------------------------------
        # 3. CRS
        # ----------------------------------------------------

        gdf = validate_crs(
            gdf
        )

        # ----------------------------------------------------
        # 4. Geometry
        # ----------------------------------------------------

        gdf = validate_geometry(
            gdf
        )

        # ----------------------------------------------------
        # 5. Reserved fields
        # ----------------------------------------------------

        gdf = fix_field_names(
            gdf
        )

        # ----------------------------------------------------
        # 6. Create GIS ID
        # ----------------------------------------------------

        gdf = create_gis_id(
            gdf
        )

        # ----------------------------------------------------
        # 7. Write GeoPackage
        # ----------------------------------------------------

        write_geopackage(
            gdf
        )

        # ----------------------------------------------------
        # 8. Verify
        # ----------------------------------------------------

        verify_geopackage()

        # ----------------------------------------------------
        # FINAL
        # ----------------------------------------------------

        print("\n")
        print("=" * 70)
        print("MASTER GEOPACKAGE COMPLETE")
        print("=" * 70)

        print(
            "\nLocation:"
        )

        print(
            GPKG_PATH
        )

        print(
            "\nLayer:"
        )

        print(
            LAYER_NAME
        )

        print(
            "\nReady for GIS processing."
        )

    except Exception as error:

        print("\n")
        print("=" * 70)
        print("MASTER GEOPACKAGE FAILED")
        print("=" * 70)

        print(
            "\nError:"
        )

        print(
            error
        )

        raise


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()