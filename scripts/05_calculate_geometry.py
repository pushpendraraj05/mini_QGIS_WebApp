import geopandas as gpd
from pathlib import Path


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parent.parent

INPUT_DIR = PROJECT_DIR / "working" / "cleaned"
OUTPUT_DIR = PROJECT_DIR / "working" / "cleaned"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# CALCULATE GEOMETRY METRICS
# ============================================================

def calculate_metrics(input_file):

    print("\n" + "=" * 70)
    print("GEOMETRY METRICS")
    print("=" * 70)

    print("Input:")
    print(input_file)

    # --------------------------------------------------------
    # Read layer
    # --------------------------------------------------------

    gdf = gpd.read_file(input_file)

    print("\nFeatures:", len(gdf))
    print("CRS:", gdf.crs)

    # --------------------------------------------------------
    # Check projected CRS
    # --------------------------------------------------------

    if gdf.crs is None:

        raise ValueError(
            "Layer has no CRS."
        )

    if not gdf.crs.is_projected:

        raise ValueError(
            "Layer is not projected. "
            "Use a metre-based CRS first."
        )

    # --------------------------------------------------------
    # Calculate area
    # --------------------------------------------------------

    gdf["AREA_M2"] = (
        gdf.geometry.area
    )

    gdf["AREA_HA"] = (
        gdf["AREA_M2"] / 10_000
    )

    gdf["AREA_KM2"] = (
        gdf["AREA_M2"] / 1_000_000
    )

    # --------------------------------------------------------
    # Calculate perimeter
    # --------------------------------------------------------

    gdf["PERIM_M"] = (
        gdf.geometry.length
    )

    # --------------------------------------------------------
    # Geometry status
    # --------------------------------------------------------

    gdf["GEOM_VALID"] = (
        gdf.geometry.is_valid
    )

    gdf["GEOM_TYPE"] = (
        gdf.geometry.geom_type
    )

    # --------------------------------------------------------
    # Create processing ID
    # --------------------------------------------------------

    gdf["GIS_ID"] = range(
        1,
        len(gdf) + 1
    )

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    output_file = (
        OUTPUT_DIR /
        f"{input_file.stem}_METRICS.geojson"
    )

    gdf.to_file(
        output_file,
        driver="GeoJSON"
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("METRICS CALCULATED")
    print("=" * 70)

    print(
        "Total area (m²):",
        round(
            gdf["AREA_M2"].sum(),
            2
        )
    )

    print(
        "Total area (ha):",
        round(
            gdf["AREA_HA"].sum(),
            2
        )
    )

    print(
        "Total area (km²):",
        round(
            gdf["AREA_KM2"].sum(),
            4
        )
    )

    print(
        "Total perimeter (m):",
        round(
            gdf["PERIM_M"].sum(),
            2
        )
    )

    print(
        "Invalid geometries:",
        (~gdf["GEOM_VALID"]).sum()
    )

    print(
        "\nSaved:"
    )

    print(output_file)


# ============================================================
# MAIN
# ============================================================

def main():

    files = list(
        INPUT_DIR.glob(
            "*_FIXED_EPSG32645.geojson"
        )
    )

    if not files:

        print(
            "\nNo EPSG:32645 layer found."
        )

        print(
            "Expected folder:"
        )

        print(INPUT_DIR)

        return

    for file_path in files:

        try:

            calculate_metrics(
                file_path
            )

        except Exception as error:

            print("\nERROR:")
            print(file_path.name)
            print(error)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
