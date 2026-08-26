import geopandas as gpd
from pathlib import Path

# ============================================================
# PROJECT CONFIGURATION
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parent.parent

INPUT_DIR = PROJECT_DIR / "working" / "cleaned"
OUTPUT_DIR = PROJECT_DIR / "working" / "cleaned"

TARGET_EPSG = 32645

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# REPROJECT
# ============================================================

def reproject_file(input_file):

    print("\n" + "=" * 70)
    print("CRS REPROJECTION")
    print("=" * 70)

    print("Input:")
    print(input_file)

    # --------------------------------------------------------
    # Read cleaned GeoJSON
    # --------------------------------------------------------

    gdf = gpd.read_file(input_file)

    print("\nFeatures:", len(gdf))
    print("Current CRS:", gdf.crs)

    # --------------------------------------------------------
    # Check CRS
    # --------------------------------------------------------

    if gdf.crs is None:

        raise ValueError(
            "Input layer has no CRS."
        )

    source_epsg = gdf.crs.to_epsg()

    print(
        "Source EPSG:",
        source_epsg
    )

    # --------------------------------------------------------
    # Reproject
    # --------------------------------------------------------

    print(
        f"\nReprojecting to EPSG:{TARGET_EPSG}..."
    )

    projected = gdf.to_crs(
        epsg=TARGET_EPSG
    )

    # --------------------------------------------------------
    # Output filename
    # --------------------------------------------------------

    output_file = (
        OUTPUT_DIR /
        f"{input_file.stem}_EPSG{TARGET_EPSG}.geojson"
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    projected.to_file(
        output_file,
        driver="GeoJSON"
    )

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("REPROJECTION COMPLETE")
    print("=" * 70)

    print(
        "Features:",
        len(projected)
    )

    print(
        "Original CRS:",
        gdf.crs
    )

    print(
        "New CRS:",
        projected.crs
    )

    print(
        "New EPSG:",
        projected.crs.to_epsg()
    )

    print("\nSaved:")

    print(output_file)


# ============================================================
# MAIN
# ============================================================

def main():

    files = list(
        INPUT_DIR.glob("*_FIXED.geojson")
    )

    if not files:

        print(
            "\nNo cleaned GeoJSON found."
        )

        print(
            "Expected:"
        )

        print(
            INPUT_DIR
        )

        return

    for file_path in files:

        try:

            reproject_file(
                file_path
            )

        except Exception as error:

            print(
                "\nERROR:"
            )

            print(file_path.name)

            print(error)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()