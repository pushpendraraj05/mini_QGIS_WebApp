import json
import tempfile
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
import streamlit as st


# ============================================================
# OPTIONAL MAP SUPPORT
# ============================================================

try:
    import folium
    from streamlit_folium import st_folium

    HAS_MAP = True

except Exception:
    HAS_MAP = False


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="GIS Data Processing Studio",
    page_icon="🗺️",
    layout="wide"
)


# ============================================================
# APPLICATION HEADER
# ============================================================

st.title("🗺️ GIS Data Processing Studio")

st.caption(
    "Multi-layer GIS ETL, validation, geometry repair, "
    "filtering, spatial analysis and export."
)


# ============================================================
# SESSION STATE
# ============================================================

if "layers" not in st.session_state:
    st.session_state.layers = {}

if "results" not in st.session_state:
    st.session_state.results = {}

if "history" not in st.session_state:
    st.session_state.history = []

if "filter_result" not in st.session_state:
    st.session_state.filter_result = None

if "filter_source_layer" not in st.session_state:
    st.session_state.filter_source_layer = None

if "filter_description" not in st.session_state:
    st.session_state.filter_description = None


# ============================================================
# HELPER - ADD HISTORY
# ============================================================

def add_history(message):

    if not st.session_state.history:
        st.session_state.history.append(message)
        return

    if st.session_state.history[-1] != message:
        st.session_state.history.append(message)


# ============================================================
# ESRI JSON TO GEOJSON GEOMETRY
# ============================================================

def esri_geometry_to_geojson(geom):

    if not geom:
        return None

    if "x" in geom and "y" in geom:

        return {
            "type": "Point",
            "coordinates": [
                geom["x"],
                geom["y"]
            ]
        }

    if "points" in geom:

        return {
            "type": "MultiPoint",
            "coordinates": geom["points"]
        }

    if "paths" in geom:

        paths = geom["paths"]

        if len(paths) == 1:

            return {
                "type": "LineString",
                "coordinates": paths[0]
            }

        return {
            "type": "MultiLineString",
            "coordinates": paths
        }

    if "rings" in geom:

        return {
            "type": "Polygon",
            "coordinates": geom["rings"]
        }

    return None


# ============================================================
# READ UPLOADED FILE
# ============================================================

def read_uploaded(uploaded):

    suffix = Path(uploaded.name).suffix.lower()

    # --------------------------------------------------------
    # GEOJSON / JSON
    # --------------------------------------------------------

    if suffix in [".json", ".geojson"]:

        text = uploaded.getvalue().decode("utf-8-sig")

        obj = json.loads(text)

        if not isinstance(obj, dict):
            raise ValueError(
                "JSON root must be an object."
            )

        # STANDARD GEOJSON FEATURE COLLECTION

        if obj.get("type") == "FeatureCollection":

            return gpd.GeoDataFrame.from_features(
                obj.get("features", []),
                crs="EPSG:4326"
            )

        # SINGLE GEOJSON FEATURE

        if obj.get("type") == "Feature":

            return gpd.GeoDataFrame.from_features(
                [obj],
                crs="EPSG:4326"
            )

        # ESRI FEATURE SET

        if "features" in obj:

            features = []

            for feature in obj.get("features", []):

                if not isinstance(feature, dict):
                    continue

                features.append(
                    {
                        "type": "Feature",
                        "properties": (
                            feature.get(
                                "attributes",
                                {}
                            )
                            or {}
                        ),
                        "geometry": esri_geometry_to_geojson(
                            feature.get("geometry")
                        )
                    }
                )

            spatial_reference = (
                obj.get("spatialReference")
                or {}
            )

            wkid = (
                spatial_reference.get("latestWkid")
                or spatial_reference.get("wkid")
            )

            crs = (
                f"EPSG:{wkid}"
                if wkid
                else "EPSG:4326"
            )

            return gpd.GeoDataFrame.from_features(
                features,
                crs=crs
            )

        raise ValueError(
            "Unsupported JSON format. "
            "Upload GeoJSON or ESRI FeatureSet JSON."
        )

    # --------------------------------------------------------
    # GEOPACKAGE
    # --------------------------------------------------------

    if suffix == ".gpkg":

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".gpkg"
        ) as tmp:

            tmp.write(uploaded.getvalue())
            temp_path = tmp.name

        try:

            return gpd.read_file(temp_path)

        finally:

            try:
                Path(temp_path).unlink(
                    missing_ok=True
                )

            except Exception:
                pass

    raise ValueError(
        "Unsupported file type."
    )


# ============================================================
# GEOPACKAGE / FID SAFETY
# ============================================================

def make_unique_column_names(columns, reserved=None):
    """
    Return unique, case-insensitive-safe column names.
    Reserved names are renamed automatically.
    """
    reserved = {
        str(name).strip().lower()
        for name in (reserved or set())
    }

    used = set()
    new_columns = []

    for original in columns:
        name = str(original).strip() or "field"
        base = name
        key = base.lower()

        if key in reserved:
            base = f"source_{base.lower()}"
            key = base.lower()

        counter = 1

        while key in used or key in reserved:
            base = f"{name}_{counter}"
            key = base.lower()
            counter += 1

        used.add(key)
        new_columns.append(base)

    return new_columns


def sanitize_column_names(gdf):
    """
    Ensure all attribute names are unique before GIS operations/export.
    GeoPackage field names are effectively case-insensitive.
    """
    result = gdf.copy()
    geometry_column = result.geometry.name

    rename_map = {}
    used = {str(geometry_column).lower()}

    for column in result.columns:
        if column == geometry_column:
            continue

        original = str(column).strip() or "field"
        candidate = original
        counter = 1

        while candidate.lower() in used:
            candidate = f"{original}_{counter}"
            counter += 1

        used.add(candidate.lower())

        if candidate != column:
            rename_map[column] = candidate

    if rename_map:
        result = result.rename(columns=rename_map)

    return result


def clean_fid_columns(gdf):
    """
    Rename attribute columns that conflict with GeoPackage/OGR feature IDs.

    FID and OGC_FID are reserved by common GIS drivers. They must not be
    written as ordinary user fields. Existing source values are preserved
    under source_fid, source_fid_1, etc.
    """
    result = gdf.copy()
    geometry_column = result.geometry.name

    reserved_names = {"fid", "ogc_fid"}

    existing = {
        str(column).lower()
        for column in result.columns
        if column != geometry_column
    }

    rename_map = {}

    for column in result.columns:
        if column == geometry_column:
            continue

        if str(column).strip().lower() in reserved_names:
            base = "source_fid"
            candidate = base
            counter = 1

            while (
                candidate.lower() in existing
                and candidate != str(column)
            ):
                candidate = f"{base}_{counter}"
                counter += 1

            existing.add(candidate.lower())
            rename_map[column] = candidate

    if rename_map:
        result = result.rename(columns=rename_map)

    return result


def sanitize_gpkg_values(gdf):
    """
    Convert problematic pandas extension/object values into GeoPackage-safe
    scalar types without changing geometry.
    """
    result = gdf.copy()
    geometry_column = result.geometry.name

    for column in result.columns:
        if column == geometry_column:
            continue

        series = result[column]

        # Nullable boolean -> object with None for missing values.
        if pd.api.types.is_bool_dtype(series):
            result[column] = series.astype("object").where(
                series.notna(),
                None
            )

        # Pandas nullable integer/float can cause driver compatibility issues.
        elif pd.api.types.is_integer_dtype(series):
            result[column] = series.astype("object").where(
                series.notna(),
                None
            )

        elif pd.api.types.is_float_dtype(series):
            result[column] = series.astype("float64")

        elif pd.api.types.is_datetime64_any_dtype(series):
            result[column] = series.dt.strftime(
                "%Y-%m-%dT%H:%M:%S"
            ).where(series.notna(), None)

        elif pd.api.types.is_object_dtype(series):
            result[column] = series.map(
                lambda value: (
                    None
                    if pd.isna(value)
                    else str(value)
                    if isinstance(value, (list, tuple, dict, set))
                    else value
                )
            )

    return result


def prepare_for_export(gdf):
    """
    Centralized cleanup used before GeoJSON/GPKG export.

    - Removes duplicate dataframe index values.
    - Renames reserved FID/OGC_FID fields.
    - Makes attribute names unique case-insensitively.
    - Removes null/empty geometry.
    - Converts attributes to driver-safe scalar values.
    """
    if gdf is None:
        raise ValueError("No GeoDataFrame supplied for export.")

    if not isinstance(gdf, gpd.GeoDataFrame):
        raise TypeError("Expected a GeoDataFrame.")

    result = gdf.copy()

    if result.geometry.name not in result.columns:
        raise ValueError("No active geometry column found.")

    result = result.reset_index(drop=True)
    result = sanitize_column_names(result)
    result = clean_fid_columns(result)

    result = result.loc[
        result.geometry.notna()
    ].copy()

    if not result.empty:
        result = result.loc[
            ~result.geometry.is_empty
        ].copy()

    result = result.reset_index(drop=True)
    result = sanitize_gpkg_values(result)

    return gpd.GeoDataFrame(
        result,
        geometry=result.geometry.name,
        crs=gdf.crs
    )


# ============================================================
# NORMALIZE ATTRIBUTE TYPES
# ============================================================

TEXT_FIELD_PATTERNS = [
    "NAME",
    "V_NAME",
    "VILLAGE",
    "GP_NAME",
    "GPNAME",
    "PANCHAYAT",
    "BLOCK",
    "DISTRICT",
    "STATE",
    "REMARK",
    "DESCRIPTION",
    "CATEGORY",
    "STATUS",
    "CLASS",
    "ADDRESS"
]

INTEGER_FIELD_PATTERNS = [
    "OBJECTID",
    "OID",
    "ID",
    "POP",
    "POPULATION",
    "COUNT",
    "HOUSE",
    "HOUSEHOLD",
    "MALE",
    "FEMALE",
    "TOTAL",
    "NUMBER",
    "YEAR"
]

FLOAT_FIELD_PATTERNS = [
    "AREA",
    "LENGTH",
    "PERIM",
    "DISTANCE",
    "ELEVATION",
    "DENSITY",
    "PERCENT",
    "RATIO",
    "LATITUDE",
    "LONGITUDE"
]

BOOLEAN_MAP = {
    "true": True,
    "false": False,
    "yes": True,
    "no": False,
    "y": True,
    "n": False
}


def _field_tokens(name):

    return set(
        re.sub(
            r"[^A-Z0-9]+",
            "_",
            str(name).upper()
        )
        .strip("_")
        .split("_")
    )


def _matches(field_name, patterns):

    normalized = (
        re.sub(
            r"[^A-Z0-9]+",
            "_",
            str(field_name).upper()
        )
        .strip("_")
    )

    tokens = _field_tokens(field_name)

    for pattern in patterns:

        p = (
            re.sub(
                r"[^A-Z0-9]+",
                "_",
                pattern.upper()
            )
            .strip("_")
        )

        if normalized == p or p in tokens:
            return True

        if (
            normalized.startswith(p + "_")
            or normalized.endswith("_" + p)
        ):
            return True

    return False


def _clean_scalar(value):

    if pd.isna(value):
        return pd.NA

    value = str(value).strip()

    if value.lower() in {
        "",
        "nan",
        "none",
        "null",
        "<na>"
    }:
        return pd.NA

    return value


def _numeric_series(series):

    cleaned = series.map(_clean_scalar)

    return pd.to_numeric(
        cleaned,
        errors="coerce"
    )


def _has_leading_zero(series):

    for value in series.dropna():

        value = str(value).strip()

        if re.fullmatch(
            r"[+-]?0\d+",
            value
        ):
            return True

    return False


def detect_field_type(field_name, series):

    if pd.api.types.is_bool_dtype(series):
        return "boolean"

    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"

    if _matches(
        field_name,
        TEXT_FIELD_PATTERNS
    ):
        return "string"

    values = series.dropna()

    if len(values) == 0:

        if _matches(
            field_name,
            INTEGER_FIELD_PATTERNS
        ):
            return "Int64"

        if _matches(
            field_name,
            FLOAT_FIELD_PATTERNS
        ):
            return "Float64"

        return "string"

    if _has_leading_zero(values):
        return "string"

    numeric = _numeric_series(series)

    numeric_ratio = (
        numeric.notna().sum()
        /
        max(len(values), 1)
    )

    all_numeric = numeric_ratio == 1.0

    if _matches(
        field_name,
        INTEGER_FIELD_PATTERNS
    ):

        if all_numeric:

            non_null = numeric.dropna()

            if (
                len(non_null) == 0
                or ((non_null % 1) == 0).all()
            ):
                return "Int64"

        return "string"

    if _matches(
        field_name,
        FLOAT_FIELD_PATTERNS
    ):

        return (
            "Float64"
            if all_numeric
            else "string"
        )

    if pd.api.types.is_numeric_dtype(series):

        non_null = numeric.dropna()

        if (
            len(non_null) == 0
            or ((non_null % 1) == 0).all()
        ):
            return "Int64"

        return "Float64"

    normalized = {
        str(v).strip().lower()
        for v in values
    }

    if (
        normalized
        and normalized.issubset(
            BOOLEAN_MAP.keys()
        )
    ):
        return "boolean"

    if all_numeric:

        non_null = numeric.dropna()

        if (
            len(non_null) == 0
            or ((non_null % 1) == 0).all()
        ):
            return "Int64"

        return "Float64"

    return "string"


def convert_field(series, target_type):

    if target_type == "string":

        return (
            series
            .map(_clean_scalar)
            .astype("string")
        )

    if target_type == "Int64":

        numeric = _numeric_series(series)

        non_null = numeric.dropna()

        if (
            len(non_null)
            and not ((non_null % 1) == 0).all()
        ):

            return (
                series
                .map(_clean_scalar)
                .astype("string")
            )

        return numeric.astype("Int64")

    if target_type == "Float64":

        return (
            _numeric_series(series)
            .astype("Float64")
        )

    if target_type == "boolean":

        def convert_bool(value):

            if pd.isna(value):
                return pd.NA

            return BOOLEAN_MAP.get(
                str(value)
                .strip()
                .lower(),
                pd.NA
            )

        return (
            series
            .map(convert_bool)
            .astype("boolean")
        )

    if target_type == "datetime":

        return pd.to_datetime(
            series,
            errors="coerce"
        )

    return series


def normalize_types(gdf):

    result = gdf.copy()

    geometry_column = result.geometry.name

    rows = []

    changed_count = 0

    for field in list(result.columns):

        if field == geometry_column:
            continue

        original_dtype = str(
            result[field].dtype
        )

        if str(field).strip().lower() in {"fid", "ogc_fid"}:
            result = clean_fid_columns(result)
            field = next(
                (
                    column
                    for column in result.columns
                    if column != geometry_column
                    and str(column).lower().startswith("source_fid")
                ),
                field
            )

        target_type = detect_field_type(
            field,
            result[field]
        )

        try:

            result[field] = convert_field(
                result[field],
                target_type
            )

            final_dtype = str(
                result[field].dtype
            )

            changed = (
                original_dtype
                != final_dtype
            )

        except Exception as error:

            final_dtype = original_dtype

            changed = False

            target_type = (
                f"ERROR: {error}"
            )

        if changed:
            changed_count += 1

        rows.append(
            {
                "Field": field,
                "Original Type": original_dtype,
                "Detected Type": target_type,
                "Final Type": final_dtype,
                "Changed": changed,
                "Null Values": int(
                    result[field]
                    .isna()
                    .sum()
                )
            }
        )

    return (
        result,
        pd.DataFrame(rows),
        changed_count
    )


# ============================================================
# GEOMETRY REPORT
# ============================================================

def report(gdf):

    if gdf is None:
        return {
            "Features": 0,
            "Null geometries": 0,
            "Empty geometries": 0,
            "Invalid geometries": 0,
            "CRS": "Not defined",
            "Geometry types": "None"
        }

    if gdf.empty:
        return {
            "Features": 0,
            "Null geometries": 0,
            "Empty geometries": 0,
            "Invalid geometries": 0,
            "CRS": (
                str(gdf.crs)
                if gdf.crs
                else "Not defined"
            ),
            "Geometry types": "None"
        }

    geom = gdf.geometry

    null_mask = geom.isna()

    valid_geom = geom.loc[
        ~null_mask
    ]

    empty_count = int(
        valid_geom.is_empty.sum()
    )

    non_empty = valid_geom.loc[
        ~valid_geom.is_empty
    ]

    invalid_count = int(
        (~non_empty.is_valid).sum()
    )

    geometry_types = (
        ", ".join(
            map(
                str,
                non_empty.geom_type
                .dropna()
                .unique()
            )
        )
        if len(non_empty)
        else "None"
    )

    return {
        "Features": int(len(gdf)),
        "Null geometries": int(
            null_mask.sum()
        ),
        "Empty geometries": empty_count,
        "Invalid geometries": invalid_count,
        "CRS": (
            str(gdf.crs)
            if gdf.crs
            else "Not defined"
        ),
        "Geometry types": geometry_types
    }


# ============================================================
# REPAIR GEOMETRY
# ============================================================

def _repair_one_geometry(geometry):

    if geometry is None:
        return geometry, "null"

    try:

        if geometry.is_empty:
            return geometry, "empty"

        if geometry.is_valid:
            return geometry, "already_valid"

    except Exception:
        return geometry, "unreadable"

    try:

        import shapely

        if hasattr(
            shapely,
            "make_valid"
        ):

            repaired = shapely.make_valid(
                geometry
            )

            if (
                repaired is not None
                and not repaired.is_empty
            ):

                return repaired, "make_valid"

    except Exception:
        pass

    try:

        repaired = geometry.buffer(0)

        if (
            repaired is not None
            and not repaired.is_empty
        ):

            return repaired, "buffer(0)"

    except Exception:
        pass

    return geometry, "failed"


def repair_geometry(gdf):

    result = gdf.copy()

    before = report(result)

    null_removed = int(
        result.geometry.isna().sum()
    )

    result = result.loc[
        result.geometry.notna()
    ].copy()

    empty_removed_before = int(
        result.geometry.is_empty.sum()
    )

    result = result.loc[
        ~result.geometry.is_empty
    ].copy()

    invalid_mask = (
        ~result.geometry.is_valid
    )

    invalid_indices = (
        result.index[
            invalid_mask
        ]
        .tolist()
    )

    repaired_count = 0

    failed_count = 0

    methods = {}

    geometry_column = result.geometry.name

    for idx in invalid_indices:

        repaired, method = (
            _repair_one_geometry(
                result.at[
                    idx,
                    geometry_column
                ]
            )
        )

        methods[method] = (
            methods.get(method, 0)
            + 1
        )

        if repaired is not None:

            try:

                if (
                    not repaired.is_empty
                    and repaired.is_valid
                ):

                    result.at[
                        idx,
                        geometry_column
                    ] = repaired

                    repaired_count += 1

                else:
                    failed_count += 1

            except Exception:
                failed_count += 1

        else:
            failed_count += 1

    result = result.loc[
        result.geometry.notna()
    ].copy()

    result = result.loc[
        ~result.geometry.is_empty
    ].copy()

    result = result.reset_index(
        drop=True
    )

    after = report(result)

    summary = {
        "Features before": before["Features"],
        "Features after": after["Features"],
        "Null removed": null_removed,
        "Empty removed": empty_removed_before,
        "Invalid before": before["Invalid geometries"],
        "Invalid after": after["Invalid geometries"],
        "Geometries repaired": repaired_count,
        "Failed repairs": failed_count,
        "Repair methods": methods,
        "Status": (
            "PASS"
            if (
                after["Null geometries"] == 0
                and after["Empty geometries"] == 0
                and after["Invalid geometries"] == 0
            )
            else "CHECK REQUIRED"
        )
    }

    return result, summary


# ============================================================
# MATCH CRS
# ============================================================

def match_crs(
    primary_gdf,
    reference_gdf
):

    if primary_gdf.crs is None:

        raise ValueError(
            "Primary layer has no CRS."
        )

    if reference_gdf.crs is None:

        raise ValueError(
            "Reference layer has no CRS."
        )

    if (
        primary_gdf.crs
        != reference_gdf.crs
    ):

        reference_gdf = (
            reference_gdf.to_crs(
                primary_gdf.crs
            )
        )

    return reference_gdf


# ============================================================
# PREPARE METRIC CRS
# ============================================================

def prepare_metric_crs(
    gdf,
    metric_crs="EPSG:32645"
):

    if gdf.crs is None:

        raise ValueError(
            "Layer CRS is not defined."
        )

    original_crs = gdf.crs

    if original_crs.is_geographic:

        working_gdf = gdf.to_crs(
            metric_crs
        )

    else:
        working_gdf = gdf.copy()

    return (
        working_gdf,
        original_crs
    )


# ============================================================
# CALCULATE METRICS
# ============================================================

def calculate_metrics(
    gdf,
    metric_crs="EPSG:32645"
):

    working, original_crs = (
        prepare_metric_crs(
            gdf,
            metric_crs
        )
    )

    result = working.copy()

    result["AREA_M2"] = (
        working.geometry.area
    )

    result["AREA_HA"] = (
        result["AREA_M2"]
        / 10000
    )

    result["AREA_KM2"] = (
        result["AREA_M2"]
        / 1000000
    )

    result["PERIM_M"] = (
        working.geometry.length
    )

    result["GEOM_VALID"] = (
        working.geometry.is_valid
    )

    result["GEOM_TYPE"] = (
        working.geometry.geom_type
        .astype("string")
    )

    return result.to_crs(
        original_crs
    )


# ============================================================
# ATTRIBUTE FILTER
# ============================================================

def apply_condition(
    gdf,
    field,
    operator,
    value
):

    series = gdf[field]

    if pd.api.types.is_numeric_dtype(
        series
    ):

        numeric_value = (
            pd.to_numeric(
                pd.Series([value]),
                errors="coerce"
            )
            .iloc[0]
        )

        if pd.isna(
            numeric_value
        ):

            raise ValueError(
                "Please enter a valid numeric value."
            )

        value = numeric_value

    else:

        value = (
            str(value)
            .strip()
            .strip("\"'")
        )

    if operator == "contains":

        return (
            series.astype("string")
            .str.contains(
                str(value),
                case=False,
                na=False,
                regex=False
            )
        )

    if operator == "starts with":

        return (
            series.astype("string")
            .str.startswith(
                str(value),
                na=False
            )
        )

    if operator == "ends with":

        return (
            series.astype("string")
            .str.endswith(
                str(value),
                na=False
            )
        )

    if operator == "=":

        if pd.api.types.is_numeric_dtype(
            series
        ):

            return series == value

        return (
            series.astype("string")
            .str.strip()
            .str.lower()
            ==
            str(value).lower()
        )

    if operator == "!=":

        if pd.api.types.is_numeric_dtype(
            series
        ):

            return series != value

        return (
            series.astype("string")
            .str.strip()
            .str.lower()
            !=
            str(value).lower()
        )

    if operator == ">":
        return series > value

    if operator == ">=":
        return series >= value

    if operator == "<":
        return series < value

    if operator == "<=":
        return series <= value

    raise ValueError(
        "Unsupported operator."
    )


# ============================================================
# BUFFER OPERATION
# ============================================================

def buffer_layer(
    gdf,
    distance,
    metric_crs="EPSG:32645"
):

    working, original_crs = (
        prepare_metric_crs(
            gdf,
            metric_crs
        )
    )

    result = working.copy()

    result["geometry"] = (
        working.geometry.buffer(
            distance
        )
    )

    result = result.loc[
        result.geometry.notna()
    ].copy()

    result = result.loc[
        ~result.geometry.is_empty
    ].copy()

    result[
        "BUFFER_DISTANCE_M"
    ] = distance

    return result.to_crs(
        original_crs
    )


# ============================================================
# CLIP OPERATION
# ============================================================

def clip_layers(
    primary,
    masks
):

    if not masks:
        raise ValueError(
            "At least one mask layer is required."
        )

    all_masks = []

    for mask in masks:

        mask = match_crs(
            primary,
            mask
        )

        all_masks.append(mask)

    combined = gpd.GeoDataFrame(
        pd.concat(
            all_masks,
            ignore_index=True
        ),
        geometry="geometry",
        crs=primary.crs
    )

    union_geometry = (
        combined.geometry.union_all()
    )

    mask_gdf = gpd.GeoDataFrame(
        geometry=[
            union_geometry
        ],
        crs=primary.crs
    )

    return gpd.clip(
        primary,
        mask_gdf
    )


# ============================================================
# INTERSECTION OPERATION
# ============================================================

def intersection_layers(
    primary,
    references
):

    result = primary.copy()

    for reference in references:

        reference = match_crs(
            result,
            reference
        )

        result = gpd.overlay(
            result,
            reference,
            how="intersection",
            keep_geom_type=False
        )

        if result.empty:
            break

    return result


# ============================================================
# DISSOLVE OPERATION
# ============================================================

def dissolve_layer(
    gdf,
    field
):

    if field not in gdf.columns:

        raise ValueError(
            f"Field not found: {field}"
        )

    return gdf.dissolve(
        by=field,
        as_index=False
    )


# ============================================================
# MERGE LAYERS
# ============================================================

def merge_layers(layer_dict):

    if not layer_dict:

        raise ValueError(
            "No layers selected."
        )

    names = list(
        layer_dict.keys()
    )

    first = layer_dict[names[0]]

    target_crs = first.crs

    merged = []

    for name, gdf in (
        layer_dict.items()
    ):

        layer = prepare_for_export(gdf)

        if (
            target_crs is not None
            and layer.crs is not None
            and layer.crs != target_crs
        ):

            layer = layer.to_crs(
                target_crs
            )

        layer["SOURCE_LAYER"] = name

        layer["GEOMETRY_TYPE"] = (
            layer.geometry.geom_type
        )

        merged.append(layer)

    result = pd.concat(
        merged,
        ignore_index=True,
        sort=False
    )

    result = gpd.GeoDataFrame(
        result,
        geometry="geometry",
        crs=target_crs
    )

    return prepare_for_export(result)


# ============================================================
# SPATIAL JOIN
# ============================================================

def spatial_join_layers(
    primary,
    references,
    predicate
):

    result = primary.copy()

    for reference in references:

        reference = match_crs(
            result,
            reference
        )

        result = gpd.sjoin(
            result,
            reference,
            how="left",
            predicate=predicate,
            rsuffix="REF"
        )

        result = result.drop(
            columns=[
                col
                for col in result.columns
                if col.startswith(
                    "index_"
                )
            ],
            errors="ignore"
        )

    return result


# ============================================================
# EXTRACT BY LOCATION
# ============================================================

def extract_by_location(
    primary,
    references,
    predicate,
    logic
):

    if not references:

        raise ValueError(
            "At least one reference layer is required."
        )

    if logic == "ANY":

        selected_indexes = set()

        for reference in references:

            reference = match_crs(
                primary,
                reference
            )

            joined = gpd.sjoin(
                primary,
                reference,
                how="inner",
                predicate=predicate
            )

            selected_indexes.update(
                joined.index.tolist()
            )

        return primary.loc[
            list(selected_indexes)
        ].copy()

    selected_indexes = set(
        primary.index
    )

    for reference in references:

        reference = match_crs(
            primary,
            reference
        )

        joined = gpd.sjoin(
            primary,
            reference,
            how="inner",
            predicate=predicate
        )

        matched = set(
            joined.index.tolist()
        )

        selected_indexes = (
            selected_indexes.intersection(
                matched
            )
        )

    return primary.loc[
        list(selected_indexes)
    ].copy()


# ============================================================
# EXPORT FUNCTIONS
# ============================================================

def geojson_bytes(gdf):
    export_gdf = prepare_for_export(gdf)

    return (
        export_gdf.to_json(
            drop_id=True
        )
        .encode("utf-8")
    )


def safe_layer_name(name):
    """
    Create a conservative GeoPackage layer name.
    """
    name = re.sub(
        r"[^A-Za-z0-9_]+",
        "_",
        str(name).strip()
    )

    name = name.strip("_") or "layer"

    if name[0].isdigit():
        name = f"layer_{name}"

    return name[:60]


def gpkg_bytes(
    gdf,
    layer_name
):
    """
    Export through one centralized safe path.

    index=False is essential: pandas indexes must not be written as a
    competing feature ID column.
    """
    export_gdf = prepare_for_export(gdf)
    layer_name = safe_layer_name(layer_name)

    with tempfile.TemporaryDirectory() as directory:

        path = (
            Path(directory)
            / "GIS_OUTPUT.gpkg"
        )

        export_gdf.to_file(
            path,
            layer=layer_name,
            driver="GPKG",
            index=False
        )

        return path.read_bytes()


# ============================================================
# MAP PREVIEW
# ============================================================

def show_map(
    gdf,
    key="map"
):

    if not HAS_MAP:

        st.info(
            "Map preview unavailable. "
            "Install folium and streamlit-folium."
        )

        return


    if gdf is None or gdf.empty:

        st.warning(
            "No features available to display."
        )

        return


    try:

        # ====================================================
        # CRS VALIDATION
        # ====================================================

        if gdf.crs is None:

            st.warning(
                "Map preview requires a CRS."
            )

            return


        # ====================================================
        # CONVERT TO WGS84 FOR WEB MAP
        # ====================================================

        map_gdf = gdf.to_crs(
            "EPSG:4326"
        )


        # ====================================================
        # REMOVE INVALID / EMPTY GEOMETRIES
        # ====================================================

        valid_geometry = map_gdf.loc[
            map_gdf.geometry.notna()
        ].copy()


        valid_geometry = valid_geometry.loc[
            ~valid_geometry.geometry.is_empty
        ].copy()


        if valid_geometry.empty:

            st.warning(
                "No valid geometry available for map preview."
            )

            return


        # ====================================================
        # CALCULATE BOUNDS
        # ====================================================

        bounds = valid_geometry.total_bounds

        minx = bounds[0]
        miny = bounds[1]
        maxx = bounds[2]
        maxy = bounds[3]


        # ====================================================
        # CALCULATE CENTER
        # ====================================================

        center = [
            (miny + maxy) / 2,
            (minx + maxx) / 2
        ]


        # ====================================================
        # CREATE MAP
        # ====================================================

        m = folium.Map(
            location=center,
            zoom_start=10,
            control_scale=True
        )


        # ====================================================
        # ADD GEOJSON LAYER
        # ====================================================

        folium.GeoJson(
            json.loads(
                valid_geometry.to_json()
            ),
            name="Features",
            style_function=lambda feature: {
                "weight": 2,
                "fillOpacity": 0.3
            }
        ).add_to(m)


        # ====================================================
        # AUTO FIT MAP TO DATA BOUNDS
        # ====================================================

        m.fit_bounds([
            [miny, minx],
            [maxy, maxx]
        ])


        # ====================================================
        # LAYER CONTROL
        # ====================================================

        folium.LayerControl().add_to(m)


        # ====================================================
        # FULL WIDTH STREAMLIT MAP
        # ====================================================

        st_folium(
            m,
            height=600,
            use_container_width=True,
            key=key
        )


    except Exception as error:

        st.warning(
            f"Map preview unavailable: {error}"
        )

# ============================================================
# SIDEBAR NAVIGATION
# ============================================================

with st.sidebar:

    st.header(
        "🗺️ GIS Modules"
    )

    page = st.radio(
        "Select Module",
        [
            "📂 Layer Manager",
            "📊 Layer Explorer",
            "🧹 Clean & Validate",
            "📐 CRS & Metrics",
            "🔎 Feature Filter",
            "⚙️ Spatial Operations",
            "📁 Results & Export"
        ],
        key="main_navigation"
    )

    st.divider()

    st.caption(
        f"Layers: "
        f"{len(st.session_state.layers)}"
    )

    st.caption(
        f"Results: "
        f"{len(st.session_state.results)}"
    )


# ============================================================
# LAYER MANAGER
# ============================================================

if page == "📂 Layer Manager":

    st.header(
        "📂 Layer Manager"
    )

    uploaded_files = st.file_uploader(
        "Upload GIS datasets",
        type=[
            "json",
            "geojson",
            "gpkg"
        ],
        accept_multiple_files=True,
        key="layer_upload"
    )

    source_crs = st.text_input(
        "Source CRS if missing",
        "EPSG:4326",
        key="source_crs_input"
    )

    if uploaded_files:

        for uploaded in uploaded_files:

            layer_name = (
                Path(uploaded.name)
                .stem
            )

            if (
                layer_name
                in st.session_state.layers
            ):
                continue

            try:

                with st.spinner(
                    f"Loading {uploaded.name}..."
                ):

                    gdf = read_uploaded(
                        uploaded
                    )

                if gdf.crs is None:

                    gdf = gdf.set_crs(
                        source_crs,
                        allow_override=True
                    )

                gdf = prepare_for_export(gdf)

                st.session_state.layers[
                    layer_name
                ] = gdf

                add_history(
                    f"Loaded layer: "
                    f"{layer_name} "
                    f"({len(gdf)} features)"
                )

                st.success(
                    f"Loaded: {layer_name}"
                )

            except Exception as error:

                st.error(
                    f"{uploaded.name}: {error}"
                )

    if st.session_state.layers:

        rows = []

        for name, gdf in (
            st.session_state.layers.items()
        ):

            info = report(gdf)

            rows.append(
                {
                    "Layer": name,
                    "Features": info["Features"],
                    "CRS": info["CRS"],
                    "Geometry": (
                        info["Geometry types"]
                    )
                }
            )

        st.subheader(
            "Loaded Layers"
        )

        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True
        )


# ============================================================
# LAYER EXPLORER
# ============================================================

elif page == "📊 Layer Explorer":

    st.header(
        "📊 Layer Explorer"
    )

    all_layers = {
        **st.session_state.layers,
        **st.session_state.results
    }

    if not all_layers:

        st.info(
            "Upload or create a GIS layer first."
        )

    else:

        selected_name = st.selectbox(
            "Select Layer",
            list(all_layers.keys()),
            key="explorer_layer"
        )

        gdf = all_layers[selected_name]

        info = report(gdf)

        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Features",
            info["Features"]
        )

        c2.metric(
            "Invalid",
            info["Invalid geometries"]
        )

        c3.metric(
            "CRS",
            info["CRS"]
        )

        c4.metric(
            "Geometry",
            info["Geometry types"]
        )

        st.subheader("Schema")

        schema = pd.DataFrame(
            {
                "Field": gdf.columns,
                "Data Type": [
                    str(gdf[c].dtype)
                    for c in gdf.columns
                ]
            }
        )

        st.dataframe(
            schema,
            use_container_width=True,
            hide_index=True
        )

        st.subheader(
            "Attribute Preview"
        )

        st.dataframe(
            gdf.drop(
                columns="geometry",
                errors="ignore"
            ).head(100),
            use_container_width=True,
            hide_index=True
        )

        st.subheader(
            "Map Preview"
        )

        show_map(
            gdf,
            key=f"explorer_map_{selected_name}"
        )


# ============================================================
# CLEAN & VALIDATE
# ============================================================

elif page == "🧹 Clean & Validate":

    st.header(
        "🧹 Clean & Validate"
    )

    if not st.session_state.layers:

        st.info(
            "Upload a layer first."
        )

    else:

        layer_name = st.selectbox(
            "Select Layer",
            list(
                st.session_state.layers.keys()
            ),
            key="clean_validate_layer"
        )

        gdf = st.session_state.layers[
            layer_name
        ]

        info = report(gdf)

        st.subheader(
            "Current Geometry Status"
        )

        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Features",
            info["Features"]
        )

        c2.metric(
            "Null",
            info["Null geometries"]
        )

        c3.metric(
            "Empty",
            info["Empty geometries"]
        )

        c4.metric(
            "Invalid",
            info["Invalid geometries"]
        )

        with st.expander(
            "View Full Geometry Report"
        ):
            st.json(info)

        st.divider()

        st.subheader(
            "🔧 Repair Geometry"
        )

        if st.button(
            "🔧 Repair Geometry",
            type="primary",
            key="repair_geometry_button"
        ):

            try:

                with st.spinner(
                    "Checking and repairing geometry..."
                ):

                    repaired_gdf, summary = (
                        repair_geometry(gdf)
                    )

                st.session_state.layers[
                    layer_name
                ] = repaired_gdf

                result_name = (
                    f"{layer_name}_cleaned"
                )

                st.session_state.results[
                    result_name
                ] = repaired_gdf

                add_history(
                    f"{layer_name}: "
                    f"geometry repair completed | "
                    f"repaired="
                    f"{summary['Geometries repaired']}"
                )

                st.success(
                    "Geometry processing completed."
                )

                st.rerun()

            except Exception as error:

                st.error(
                    f"Geometry repair failed: {error}"
                )

        st.divider()

        st.subheader(
            "🔄 Normalize Data Types"
        )

        if st.button(
            "🔄 Normalize Data Types",
            key="normalize_data_button"
        ):

            try:

                with st.spinner(
                    "Analyzing data types..."
                ):

                    normalized_gdf, type_report, changed_count = (
                        normalize_types(gdf)
                    )

                st.session_state.layers[
                    layer_name
                ] = normalized_gdf

                result_name = (
                    f"{layer_name}_normalized"
                )

                st.session_state.results[
                    result_name
                ] = normalized_gdf

                add_history(
                    f"{layer_name}: "
                    f"data type normalization | "
                    f"fields changed={changed_count}"
                )

                st.success(
                    f"Normalization completed. "
                    f"{changed_count} field(s) changed."
                )

                st.rerun()

            except Exception as error:

                st.error(
                    f"Data type normalization failed: {error}"
                )


# ============================================================
# CRS & METRICS
# ============================================================

elif page == "📐 CRS & Metrics":

    st.header(
        "📐 CRS & Geometry Metrics"
    )

    if not st.session_state.layers:

        st.info(
            "Upload a layer first."
        )

    else:

        layer_name = st.selectbox(
            "Select Layer",
            list(
                st.session_state.layers.keys()
            ),
            key="crs_metrics_layer"
        )

        gdf = st.session_state.layers[
            layer_name
        ]

        current_crs = (
            str(gdf.crs)
            if gdf.crs
            else "EPSG:4326"
        )

        target_crs = st.text_input(
            "Target CRS",
            current_crs,
            key="target_crs"
        )

        if st.button(
            "🌐 Reproject Layer",
            key="reproject_layer_button"
        ):

            try:

                if gdf.crs is None:
                    raise ValueError(
                        "Layer CRS is not defined."
                    )

                result = gdf.to_crs(
                    target_crs
                )

                st.session_state.layers[
                    layer_name
                ] = result

                add_history(
                    f"{layer_name}: "
                    f"reprojected to {target_crs}"
                )

                st.success(
                    f"Reprojected to {target_crs}"
                )

                st.rerun()

            except Exception as error:

                st.error(
                    f"Reprojection failed: {error}"
                )

        st.divider()

        metric_crs = st.text_input(
            "Metric CRS",
            "EPSG:32645",
            key="metric_crs"
        )

        if st.button(
            "📐 Calculate Metrics",
            type="primary",
            key="calculate_metrics_button"
        ):

            try:

                result = calculate_metrics(
                    gdf,
                    metric_crs
                )

                result_name = (
                    f"{layer_name}_metrics"
                )

                st.session_state.results[
                    result_name
                ] = result

                add_history(
                    f"{layer_name}: "
                    f"geometry metrics calculated"
                )

                st.success(
                    f"Created {result_name}"
                )

            except Exception as error:

                st.error(
                    f"Metric calculation failed: {error}"
                )


# ============================================================
# FEATURE FILTER
# ============================================================

elif page == "🔎 Feature Filter":

    st.header(
        "🔎 Feature Filtering"
    )

    if not st.session_state.layers:

        st.info(
            "Upload a layer first."
        )

    else:

        layer_name = st.selectbox(
            "Select Layer",
            list(
                st.session_state.layers.keys()
            ),
            key="filter_layer_selector"
        )

        gdf = st.session_state.layers[
            layer_name
        ]

        if (
            st.session_state.filter_source_layer
            is not None
            and st.session_state.filter_source_layer
            != layer_name
        ):

            st.session_state.filter_result = None

            st.session_state.filter_source_layer = None

            st.session_state.filter_description = None

        fields = [
            column
            for column in gdf.columns
            if column != gdf.geometry.name
        ]

        if not fields:

            st.warning(
                "No attribute fields available."
            )

        else:

            with st.form(
                "feature_filter_form",
                clear_on_submit=False
            ):

                field = st.selectbox(
                    "Field",
                    fields,
                    key="filter_field"
                )

                numeric = (
                    pd.api.types.is_numeric_dtype(
                        gdf[field]
                    )
                )

                if numeric:

                    operators = [
                        ">",
                        ">=",
                        "<",
                        "<=",
                        "=",
                        "!="
                    ]

                else:

                    operators = [
                        "=",
                        "!=",
                        "contains",
                        "starts with",
                        "ends with"
                    ]

                operator = st.selectbox(
                    "Operator",
                    operators,
                    key="filter_operator"
                )

                value = st.text_input(
                    "Value",
                    key="filter_value"
                )

                c1, c2 = st.columns(2)

                with c1:

                    apply_filter = (
                        st.form_submit_button(
                            "🔎 Apply Filter",
                            type="primary"
                        )
                    )

                with c2:

                    reset_filter = (
                        st.form_submit_button(
                            "♻ Reset Filter"
                        )
                    )

            if reset_filter:

                st.session_state.filter_result = None

                st.session_state.filter_source_layer = None

                st.session_state.filter_description = None

                st.rerun()

            if apply_filter:

                try:

                    if not str(value).strip():

                        raise ValueError(
                            "Please enter a filter value."
                        )

                    mask = apply_condition(
                        gdf,
                        field,
                        operator,
                        value
                    )

                    result = (
                        gdf.loc[mask]
                        .copy()
                    )

                    st.session_state.filter_result = result

                    st.session_state.filter_source_layer = (
                        layer_name
                    )

                    st.session_state.filter_description = (
                        f"{field} {operator} {value}"
                    )

                    result_name = (
                        f"{layer_name}_filtered"
                    )

                    st.session_state.results[
                        result_name
                    ] = result

                    add_history(
                        f"{layer_name}: filter applied | "
                        f"{field} {operator} {value}"
                    )

                except Exception as error:

                    st.error(
                        f"Filter failed: {error}"
                    )

            if (
                st.session_state.filter_result
                is not None
                and st.session_state.filter_source_layer
                == layer_name
            ):

                result = (
                    st.session_state.filter_result
                )

                st.divider()

                st.subheader(
                    "📌 Active Filter Result"
                )

                st.info(
                    f"Active Filter: "
                    f"`{st.session_state.filter_description}`"
                )

                c1, c2, c3 = st.columns(3)

                c1.metric(
                    "Original Features",
                    len(gdf)
                )

                c2.metric(
                    "Selected Features",
                    len(result)
                )

                c3.metric(
                    "Filtered Out",
                    len(gdf) - len(result)
                )

                if result.empty:

                    st.warning(
                        "No features matched the filter."
                    )

                else:

                    st.dataframe(
                        result.drop(
                            columns="geometry",
                            errors="ignore"
                        ),
                        use_container_width=True,
                        hide_index=True
                    )

                    show_map(
                        result,
                        key=f"filter_map_{layer_name}"
                    )


# ============================================================
# SPATIAL OPERATIONS
# ============================================================

elif page == "⚙️ Spatial Operations":

    st.header(
        "⚙️ Multi-Layer Spatial Operations"
    )

    if not st.session_state.layers:

        st.info(
            "Upload GIS layers first."
        )

    else:

        selected_names = st.multiselect(
            "Select Input Layers",
            list(
                st.session_state.layers.keys()
            ),
            key="spatial_input_layers"
        )

        if selected_names:

            operation = st.selectbox(
                "Select Operation",
                [
                    "Buffer",
                    "Clip",
                    "Intersection",
                    "Dissolve",
                    "Merge Layers",
                    "Spatial Join",
                    "Extract by Location"
                ],
                key="spatial_operation"
            )

            if operation == "Buffer":

                distance = st.number_input(
                    "Buffer Distance (meters)",
                    min_value=0.1,
                    value=20.0,
                    key="buffer_distance"
                )

                if st.button(
                    "Run Buffer",
                    type="primary",
                    key="run_buffer"
                ):

                    try:

                        for name in selected_names:

                            result = buffer_layer(
                                st.session_state.layers[name],
                                distance
                            )

                            result[
                                "SOURCE_LAYER"
                            ] = name

                            result_name = (
                                f"{name}_buffer_"
                                f"{int(distance)}m"
                            )

                            st.session_state.results[
                                result_name
                            ] = result

                        add_history(
                            f"Buffer completed: "
                            f"{distance} meters"
                        )

                        st.success(
                            "Buffer completed."
                        )

                    except Exception as error:

                        st.error(
                            f"Buffer failed: {error}"
                        )

            elif operation == "Clip":

                if len(selected_names) < 2:

                    st.warning(
                        "Select at least two layers."
                    )

                else:

                    primary_name = st.selectbox(
                        "Primary Layer",
                        selected_names,
                        key="clip_primary"
                    )

                    if st.button(
                        "Run Clip",
                        type="primary",
                        key="run_clip"
                    ):

                        try:

                            primary = (
                                st.session_state.layers[
                                    primary_name
                                ]
                            )

                            masks = [
                                st.session_state.layers[name]
                                for name in selected_names
                                if name != primary_name
                            ]

                            result = clip_layers(
                                primary,
                                masks
                            )

                            result = prepare_for_export(result)

                            st.session_state.results[
                                "clip_result"
                            ] = result

                            add_history(
                                "Clip operation completed"
                            )

                            st.success(
                                f"Clip completed: "
                                f"{len(result)} features."
                            )

                        except Exception as error:

                            st.error(
                                f"Clip failed: {error}"
                            )

            elif operation == "Intersection":

                if len(selected_names) < 2:

                    st.warning(
                        "Select at least two layers."
                    )

                else:

                    primary_name = st.selectbox(
                        "Primary Layer",
                        selected_names,
                        key="intersection_primary"
                    )

                    if st.button(
                        "Run Intersection",
                        type="primary",
                        key="run_intersection"
                    ):

                        try:

                            primary = (
                                st.session_state.layers[
                                    primary_name
                                ]
                            )

                            references = [
                                st.session_state.layers[name]
                                for name in selected_names
                                if name != primary_name
                            ]

                            result = intersection_layers(
                                primary,
                                references
                            )

                            result = prepare_for_export(result)

                            st.session_state.results[
                                "intersection_result"
                            ] = result

                            add_history(
                                "Intersection operation completed"
                            )

                            st.success(
                                f"Intersection completed: "
                                f"{len(result)} features."
                            )

                        except Exception as error:

                            st.error(
                                f"Intersection failed: {error}"
                            )

            elif operation == "Dissolve":

                dissolve_name = st.selectbox(
                    "Layer to Dissolve",
                    selected_names,
                    key="dissolve_layer"
                )

                gdf = st.session_state.layers[
                    dissolve_name
                ]

                fields = [
                    column
                    for column in gdf.columns
                    if column != gdf.geometry.name
                ]

                if not fields:

                    st.warning(
                        "No attribute field available."
                    )

                else:

                    dissolve_field = st.selectbox(
                        "Dissolve Field",
                        fields,
                        key="dissolve_field"
                    )

                    if st.button(
                        "Run Dissolve",
                        type="primary",
                        key="run_dissolve"
                    ):

                        try:

                            result = dissolve_layer(
                                gdf,
                                dissolve_field
                            )

                            result_name = (
                                f"{dissolve_name}_dissolved"
                            )

                            st.session_state.results[
                                result_name
                            ] = result

                            add_history(
                                f"{dissolve_name}: "
                                f"dissolved by "
                                f"{dissolve_field}"
                            )

                            st.success(
                                f"Dissolve completed: "
                                f"{len(result)} features."
                            )

                        except Exception as error:

                            st.error(
                                f"Dissolve failed: {error}"
                            )

            elif operation == "Merge Layers":

                if len(selected_names) < 2:

                    st.warning(
                        "Select at least two layers."
                    )

                elif st.button(
                    "Run Merge",
                    type="primary",
                    key="run_merge"
                ):

                    try:

                        selected = {
                            name: (
                                st.session_state.layers[name]
                            )
                            for name in selected_names
                        }

                        result = merge_layers(
                            selected
                        )

                        st.session_state.results[
                            "merged_result"
                        ] = result

                        add_history(
                            f"Merged "
                            f"{len(selected_names)} layers"
                        )

                        st.success(
                            f"Merged "
                            f"{len(selected_names)} layers "
                            f"into {len(result)} features."
                        )

                    except Exception as error:

                        st.error(
                            f"Merge failed: {error}"
                        )

            elif operation == "Spatial Join":

                if len(selected_names) < 2:

                    st.warning(
                        "Select at least two layers."
                    )

                else:

                    primary_name = st.selectbox(
                        "Primary Layer",
                        selected_names,
                        key="join_primary"
                    )

                    predicate = st.selectbox(
                        "Spatial Relationship",
                        [
                            "intersects",
                            "within",
                            "contains",
                            "touches",
                            "crosses",
                            "overlaps"
                        ],
                        key="join_predicate"
                    )

                    if st.button(
                        "Run Spatial Join",
                        type="primary",
                        key="run_spatial_join"
                    ):

                        try:

                            primary = (
                                st.session_state.layers[
                                    primary_name
                                ]
                            )

                            references = [
                                st.session_state.layers[name]
                                for name in selected_names
                                if name != primary_name
                            ]

                            result = (
                                spatial_join_layers(
                                    primary,
                                    references,
                                    predicate
                                )
                            )

                            result = prepare_for_export(result)

                            st.session_state.results[
                                "spatial_join_result"
                            ] = result

                            add_history(
                                "Spatial join completed"
                            )

                            st.success(
                                "Spatial Join completed."
                            )

                        except Exception as error:

                            st.error(
                                f"Spatial Join failed: "
                                f"{error}"
                            )

            elif operation == "Extract by Location":

                if len(selected_names) < 2:

                    st.warning(
                        "Select at least two layers."
                    )

                else:

                    primary_name = st.selectbox(
                        "Primary Layer",
                        selected_names,
                        key="extract_primary"
                    )

                    predicate = st.selectbox(
                        "Spatial Relationship",
                        [
                            "intersects",
                            "within",
                            "contains",
                            "touches",
                            "crosses",
                            "overlaps"
                        ],
                        key="extract_predicate"
                    )

                    logic = st.radio(
                        "Reference Logic",
                        [
                            "ANY",
                            "ALL"
                        ],
                        horizontal=True,
                        key="extract_logic"
                    )

                    if st.button(
                        "Run Extract by Location",
                        type="primary",
                        key="run_extract"
                    ):

                        try:

                            primary = (
                                st.session_state.layers[
                                    primary_name
                                ]
                            )

                            references = [
                                st.session_state.layers[name]
                                for name in selected_names
                                if name != primary_name
                            ]

                            result = (
                                extract_by_location(
                                    primary,
                                    references,
                                    predicate,
                                    logic
                                )
                            )

                            result = prepare_for_export(result)

                            st.session_state.results[
                                "extract_by_location_result"
                            ] = result

                            add_history(
                                f"Extract by Location | "
                                f"{logic} | "
                                f"{predicate}"
                            )

                            st.success(
                                f"Extracted "
                                f"{len(result)} features."
                            )

                        except Exception as error:

                            st.error(
                                f"Extract failed: {error}"
                            )


# ============================================================
# RESULTS AND EXPORT
# ============================================================

elif page == "📁 Results & Export":

    st.header(
        "📁 Results & Export"
    )

    if not st.session_state.results:

        st.info(
            "No results available yet."
        )

    else:

        result_name = st.selectbox(
            "Select Result",
            list(
                st.session_state.results.keys()
            ),
            key="result_selector"
        )

        result = st.session_state.results[
            result_name
        ]

        c1, c2 = st.columns(2)

        c1.metric(
            "Result Features",
            len(result)
        )

        c2.metric(
            "Result Name",
            result_name
        )

        st.dataframe(
            result.drop(
                columns="geometry",
                errors="ignore"
            ).head(500),
            use_container_width=True,
            hide_index=True
        )

        st.subheader(
            "Map Preview"
        )

        show_map(
            result,
            key=f"result_map_{result_name}"
        )

        st.divider()

        st.subheader(
            "Download"
        )

        st.download_button(
            "⬇ Download GeoJSON",
            geojson_bytes(result),
            f"{result_name}.geojson",
            "application/geo+json",
            key=f"download_geojson_{result_name}"
        )

        try:

            st.download_button(
                "⬇ Download GeoPackage",
                gpkg_bytes(
                    result,
                    result_name
                ),
                f"{result_name}.gpkg",
                "application/geopackage+sqlite3",
                key=f"download_gpkg_{result_name}"
            )

        except Exception as error:

            st.error(
                f"GeoPackage export failed: {error}"
            )

        st.divider()

        st.subheader(
            "Processing History"
        )

        if st.session_state.history:

            for item in reversed(
                st.session_state.history
            ):

                st.write(
                    "•",
                    item
                )

        if st.button(
            "♻ Reset Session",
            key="reset_session"
        ):

            st.session_state.layers = {}
            st.session_state.results = {}
            st.session_state.history = []
            st.session_state.filter_result = None
            st.session_state.filter_source_layer = None
            st.session_state.filter_description = None

            st.rerun()


# ============================================================
# FOOTER
# ============================================================

st.sidebar.divider()

st.sidebar.caption(
    "GIS Python Project | "
    "Streamlit GIS Processing Application"
)

