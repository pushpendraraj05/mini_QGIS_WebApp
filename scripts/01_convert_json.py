import json
from pathlib import Path


# ============================================================
# PROJECT CONFIGURATION
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parent.parent

INPUT_DIR = PROJECT_DIR / "input" / "json"
OUTPUT_DIR = PROJECT_DIR / "output" / "geojson"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# ESRI JSON GEOMETRY → GEOJSON GEOMETRY
# ============================================================

def convert_geometry(esri_geometry):

    if not esri_geometry:
        return None

    # --------------------------------------------------------
    # Point
    # --------------------------------------------------------

    if "x" in esri_geometry and "y" in esri_geometry:

        return {
            "type": "Point",
            "coordinates": [
                esri_geometry["x"],
                esri_geometry["y"]
            ]
        }

    # --------------------------------------------------------
    # Polyline
    # --------------------------------------------------------

    if "paths" in esri_geometry:

        paths = esri_geometry["paths"]

        if len(paths) == 1:

            return {
                "type": "LineString",
                "coordinates": paths[0]
            }

        return {
            "type": "MultiLineString",
            "coordinates": paths
        }

    # --------------------------------------------------------
    # Polygon
    # --------------------------------------------------------

    if "rings" in esri_geometry:

        rings = esri_geometry["rings"]

        return {
            "type": "Polygon",
            "coordinates": rings
        }

    return None


# ============================================================
# CONVERT ONE FILE
# ============================================================

def convert_file(input_file):

    output_file = (
        OUTPUT_DIR /
        f"{input_file.stem}.geojson"
    )

    print("\n" + "=" * 60)
    print("CONVERTING")
    print("=" * 60)

    print("Input :", input_file)
    print("Output:", output_file)

    # --------------------------------------------------------
    # Read ESRI JSON
    # utf-8-sig handles BOM automatically
    # --------------------------------------------------------

    with open(
        input_file,
        "r",
        encoding="utf-8-sig"
    ) as f:

        data = json.load(f)

    # --------------------------------------------------------
    # Validate ESRI structure
    # --------------------------------------------------------

    if "features" not in data:

        raise ValueError(
            "Invalid ESRI JSON: 'features' not found."
        )

    features = data["features"]

    print("Input features:", len(features))

    # --------------------------------------------------------
    # Read CRS
    # --------------------------------------------------------

    spatial_reference = data.get(
        "spatialReference",
        {}
    )

    wkid = spatial_reference.get("latestWkid")

    if wkid is None:
        wkid = spatial_reference.get("wkid")

    print("Source WKID:", wkid)

    # --------------------------------------------------------
    # Convert features
    # --------------------------------------------------------

    geojson_features = []

    skipped_geometry = 0

    for index, feature in enumerate(
        features,
        start=1
    ):

        attributes = feature.get(
            "attributes",
            {}
        )

        esri_geometry = feature.get(
            "geometry"
        )

        geometry = convert_geometry(
            esri_geometry
        )

        if geometry is None:

            skipped_geometry += 1

            print(
                f"WARNING: Feature {index} "
                f"has no supported geometry."
            )

            continue

        geojson_features.append({

            "type": "Feature",

            "properties": attributes,

            "geometry": geometry
        })

    # --------------------------------------------------------
    # Build GeoJSON
    # --------------------------------------------------------

    geojson = {

        "type": "FeatureCollection",

        "name": input_file.stem,

        "crs": {

            "type": "name",

            "properties": {

                "name": f"urn:ogc:def:crs:EPSG::{wkid}"

            }
        },

        "features": geojson_features
    }

    # --------------------------------------------------------
    # Write GeoJSON
    # --------------------------------------------------------

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            geojson,
            f,
            ensure_ascii=False,
            indent=2
        )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print("\nConversion complete.")

    print(
        "Output features:",
        len(geojson_features)
    )

    print(
        "Skipped features:",
        skipped_geometry
    )

    print(
        "CRS:",
        f"EPSG:{wkid}"
    )

    print(
        "Saved:",
        output_file
    )


# ============================================================
# MAIN
# ============================================================

def main():

    json_files = list(
        INPUT_DIR.glob("*.json")
    )

    if not json_files:

        print(
            "\nNo ESRI JSON files found in:"
        )

        print(INPUT_DIR)

        return

    print(
        f"\nFound {len(json_files)} JSON file(s)."
    )

    for input_file in json_files:

        try:

            convert_file(input_file)

        except Exception as error:

            print(
                f"\nERROR: {input_file.name}"
            )

            print(error)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()