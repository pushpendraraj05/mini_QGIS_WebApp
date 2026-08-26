import geopandas as gpd
import pandas as pd
from pathlib import Path
import re


# ============================================================
# PROJECT CONFIGURATION
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parent.parent

INPUT_DIR = PROJECT_DIR / "working" / "cleaned"

OUTPUT_DIR = PROJECT_DIR / "working" / "analysis"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# FIND INPUT FILE
# ============================================================

def find_input_file():

    files = sorted(
        INPUT_DIR.glob("*.geojson")
    )

    if not files:

        print("\nNo GeoJSON files found.")

        print(
            "\nExpected folder:"
        )

        print(
            INPUT_DIR
        )

        return None

    print("\n" + "=" * 70)
    print("AVAILABLE GEOJSON FILES")
    print("=" * 70)

    for i, file in enumerate(files, 1):

        print(
            f"{i:>3}. {file.name}"
        )

    print("=" * 70)

    while True:

        choice = input(
            "\nSelect file NUMBER: "
        ).strip()

        try:

            number = int(choice)

            if 1 <= number <= len(files):

                return files[number - 1]

        except ValueError:

            pass

        print(
            "Invalid selection. Enter a displayed file number."
        )


# ============================================================
# SHOW FIELDS
# ============================================================

def show_fields(gdf):

    print("\n" + "=" * 70)
    print("AVAILABLE FIELDS")
    print("=" * 70)

    for i, field in enumerate(
        gdf.columns,
        1
    ):

        if field == gdf.geometry.name:
            continue

        print(
            f"{i:>3}. "
            f"{field:<30} "
            f"{str(gdf[field].dtype)}"
        )

    print("=" * 70)


# ============================================================
# FIND FIELD
# ============================================================

def find_field(
    gdf,
    field_input
):

    field_input = field_input.strip()

    # --------------------------------------------------------
    # Exact field name
    # --------------------------------------------------------

    if field_input in gdf.columns:

        return field_input

    # --------------------------------------------------------
    # Case-insensitive field search
    # --------------------------------------------------------

    for field in gdf.columns:

        if (
            field.lower()
            == field_input.lower()
        ):

            return field

    # --------------------------------------------------------
    # Field number
    # --------------------------------------------------------

    try:

        number = int(
            field_input
        )

        fields = [
            f
            for f in gdf.columns
            if f != gdf.geometry.name
        ]

        if 1 <= number <= len(fields):

            return fields[number - 1]

    except ValueError:

        pass

    return None


# ============================================================
# PARSE FILTER EXPRESSION
# ============================================================

def parse_expression(expression):

    # --------------------------------------------------------
    # Supported operators
    # --------------------------------------------------------

    operators = [
        ">=",
        "<=",
        "!=",
        "=",
        ">",
        "<"
    ]

    for operator in operators:

        if operator in expression:

            parts = expression.split(
                operator,
                1
            )

            field = parts[0].strip()

            value = parts[1].strip()

            return (
                field,
                operator,
                value
            )

    return (
        None,
        None,
        None
    )


# ============================================================
# CLEAN VALUE
# ============================================================

def clean_value(value):

    value = value.strip()

    # --------------------------------------------------------
    # Remove quotes
    # --------------------------------------------------------

    if (
        len(value) >= 2
        and (
            (
                value.startswith('"')
                and value.endswith('"')
            )
            or
            (
                value.startswith("'")
                and value.endswith("'")
            )
        )
    ):

        value = value[1:-1]

    return value


# ============================================================
# APPLY FILTER
# ============================================================

def apply_filter(
    gdf,
    field,
    operator,
    value
):

    series = gdf[field]

    value = clean_value(
        value
    )

    # ========================================================
    # NUMERIC FIELD
    # ========================================================

    if pd.api.types.is_numeric_dtype(
        series
    ):

        try:

            numeric_value = float(
                value
            )

        except ValueError:

            print(
                f"\nERROR: {value} is not a valid number."
            )

            return None

        if operator == ">":

            mask = series > numeric_value

        elif operator == ">=":

            mask = series >= numeric_value

        elif operator == "<":

            mask = series < numeric_value

        elif operator == "<=":

            mask = series <= numeric_value

        elif operator == "=":

            mask = series == numeric_value

        elif operator == "!=":

            mask = series != numeric_value

        else:

            print(
                "Unsupported operator."
            )

            return None

    # ========================================================
    # TEXT FIELD
    # ========================================================

    else:

        text_series = (
            series
            .astype("string")
            .str.strip()
        )

        # ----------------------------------------------------
        # Exact comparison
        # ----------------------------------------------------

        if operator == "=":

            mask = (
                text_series.str.lower()
                ==
                value.lower()
            )

        elif operator == "!=":

            mask = (
                text_series.str.lower()
                !=
                value.lower()
            )

        # ----------------------------------------------------
        # Text comparison operators
        # ----------------------------------------------------

        elif operator == ">":

            mask = (
                text_series
                > value
            )

        elif operator == ">=":

            mask = (
                text_series
                >= value
            )

        elif operator == "<":

            mask = (
                text_series
                < value
            )

        elif operator == "<=":

            mask = (
                text_series
                <= value
            )

        else:

            print(
                "Unsupported operator."
            )

            return None

    return mask.fillna(
        False
    )


# ============================================================
# SAVE FILTERED RESULT
# ============================================================

def save_result(
    gdf,
    input_file,
    field,
    operator,
    value
):

    # --------------------------------------------------------
    # Safe filename
    # --------------------------------------------------------

    safe_field = re.sub(
        r"[^A-Za-z0-9_]+",
        "_",
        field
    )

    safe_value = re.sub(
        r"[^A-Za-z0-9_]+",
        "_",
        value
    )

    output_file = (
        OUTPUT_DIR
        /
        f"{input_file.stem}_FILTER_{safe_field}_{safe_value}.geojson"
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    gdf.to_file(
        output_file,
        driver="GeoJSON"
    )

    return output_file


# ============================================================
# MAIN FILTER PROCESS
# ============================================================

def main():

    print("\n")
    print("=" * 70)
    print("GIS FEATURE FILTER")
    print("=" * 70)

    # --------------------------------------------------------
    # Select input
    # --------------------------------------------------------

    input_file = find_input_file()

    if input_file is None:

        return

    print(
        "\nSelected:"
    )

    print(
        input_file
    )

    # --------------------------------------------------------
    # Read
    # --------------------------------------------------------

    print(
        "\nReading layer..."
    )

    gdf = gpd.read_file(
        input_file
    )

    print(
        "Features:",
        len(gdf)
    )

    print(
        "CRS:",
        gdf.crs
    )

    # --------------------------------------------------------
    # Fields
    # --------------------------------------------------------

    show_fields(
        gdf
    )

    # ========================================================
    # FILTER LOOP
    # ========================================================

    while True:

        print("\n" + "=" * 70)

        print(
            "FILTER EXAMPLES"
        )

        print(
            "  GP_POP > 8000"
        )

        print(
            "  GP_POP >= 8000"
        )

        print(
            "  POP_2011 < 5000"
        )

        print(
            "  AREA > 100"
        )

        print(
            '  V_NAME = "Harpur"'
        )

        print(
            '  DIST_NAME = "PURVI CHAMPARAN"'
        )

        print(
            "  Enter Q to quit"
        )

        print("=" * 70)

        expression = input(
            "\nEnter filter expression: "
        ).strip()

        if expression.lower() == "q":

            print(
                "\nFilter cancelled."
            )

            return

        if not expression:

            print(
                "Please enter a filter."
            )

            continue

        # ----------------------------------------------------
        # Parse
        # ----------------------------------------------------

        (
            field_input,
            operator,
            value
        ) = parse_expression(
            expression
        )

        if field_input is None:

            print(
                "\nInvalid filter expression."
            )

            print(
                "Example:"
            )

            print(
                "GP_POP > 8000"
            )

            continue

        # ----------------------------------------------------
        # Find field
        # ----------------------------------------------------

        field = find_field(
            gdf,
            field_input
        )

        if field is None:

            print(
                "\nField not found:"
            )

            print(
                field_input
            )

            print(
                "\nUse one of the displayed field names."
            )

            continue

        # ----------------------------------------------------
        # Apply
        # ----------------------------------------------------

        print(
            "\nApplying:"
        )

        print(
            f"{field} {operator} {value}"
        )

        mask = apply_filter(
            gdf,
            field,
            operator,
            value
        )

        if mask is None:

            continue

        filtered = (
            gdf.loc[
                mask
            ]
            .copy()
        )

        # ----------------------------------------------------
        # Result
        # ----------------------------------------------------

        print("\n" + "=" * 70)
        print("FILTER RESULT")
        print("=" * 70)

        print(
            "Original features:",
            len(gdf)
        )

        print(
            "Selected features:",
            len(filtered)
        )

        print(
            "Excluded features:",
            len(gdf) - len(filtered)
        )

        print("=" * 70)

        if len(filtered) == 0:

            print(
                "\nNo features matched the filter."
            )

            continue

        # ----------------------------------------------------
        # Preview
        # ----------------------------------------------------

        print(
            "\nSELECTED FEATURES PREVIEW:"
        )

        preview_columns = [
            field
        ]

        # Add useful name fields
        for candidate in [
            "V_NAME",
            "GPNAME_1",
            "GP_NAME",
            "BLK_NAME",
            "DIST_NAME",
            "GP_POP",
            "POP_2011",
            "AREA"
        ]:

            if (
                candidate in gdf.columns
                and
                candidate not in preview_columns
            ):

                preview_columns.append(
                    candidate
                )

        print(
            filtered[
                preview_columns
            ]
            .head(20)
            .to_string(
                index=False
            )
        )

        # ----------------------------------------------------
        # Save?
        # ----------------------------------------------------

        save_choice = input(
            "\nSave filtered layer? [Y/N]: "
        ).strip().lower()

        if save_choice == "y":

            output_file = save_result(
                filtered,
                input_file,
                field,
                operator,
                value
            )

            print(
                "\nFILTERED FILE CREATED:"
            )

            print(
                output_file
            )

        # ----------------------------------------------------
        # Continue?
        # ----------------------------------------------------

        another = input(
            "\nApply another filter? [Y/N]: "
        ).strip().lower()

        if another != "y":

            break

    print(
        "\nFilter process complete."
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()