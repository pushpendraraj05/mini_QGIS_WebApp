import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_DIR / "input" / "json"


def inspect_json(file_path):

    print("\n" + "=" * 60)
    print("JSON INSPECTION")
    print("=" * 60)

    print("File:")
    print(file_path)

    # Read JSON
    with open(
        file_path,
        "r",
        encoding="utf-8-sig"
    ) as f:

        data = json.load(f)

    print("\nTop-level keys:")
    print(list(data.keys()))

    # Feature information
    features = data.get("features", [])

    print("\nNumber of features:")
    print(len(features))

    if not features:
        print("\nNo features found.")
        return

    # First feature
    first = features[0]

    print("\nFirst feature keys:")
    print(list(first.keys()))

    # Attributes
    attributes = first.get("attributes", {})

    print("\nAttribute fields:")
    for field in attributes:
        print(" -", field)

    # Geometry
    geometry = first.get("geometry")

    print("\nGeometry:")

    if geometry is None:
        print("NO GEOMETRY")

    else:

        print("Geometry keys:")
        print(list(geometry.keys()))

        print("\nGeometry type:")

        if "x" in geometry and "y" in geometry:
            print("Point")

        elif "paths" in geometry:
            print("Polyline")

        elif "rings" in geometry:
            print("Polygon")

        else:
            print("Unknown geometry")

    # Spatial reference
    print("\nSpatial reference:")

    spatial_reference = data.get(
        "spatialReference"
    )

    print(spatial_reference)

    print("\n" + "=" * 60)
    print("INSPECTION COMPLETE")
    print("=" * 60)


def main():

    json_files = list(
        INPUT_DIR.glob("*.json")
    )

    if not json_files:

        print(
            "\nNo JSON files found in:"
        )

        print(INPUT_DIR)

        return

    for file in json_files:

        try:

            inspect_json(file)

        except Exception as e:

            print(
                f"\nERROR: {file.name}"
            )

            print(e)


if __name__ == "__main__":
    main()