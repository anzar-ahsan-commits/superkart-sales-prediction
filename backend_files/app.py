from pathlib import Path
import json

import joblib
import numpy as np
import pandas as pd
from flask import Flask, jsonify, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

BASE_DIR = Path(__file__).resolve().parent

model = joblib.load(BASE_DIR / "superkart_model.joblib")
with (BASE_DIR / "model_metadata.json").open(encoding="utf-8") as file:
    metadata = json.load(file)

FEATURES = metadata["feature_columns"]
NUMERIC = metadata["numeric_features"]
CATEGORICAL = metadata["categorical_features"]

superkart_api = Flask(__name__)
superkart_api.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


def prepare_inputs(frame):
    """Validate inputs and flag departures from the training data."""
    if frame.empty:
        raise ValueError("At least one input record is required.")

    missing = sorted(set(FEATURES) - set(frame.columns))
    extra = sorted(set(frame.columns) - set(FEATURES))

    if missing or extra:
        raise ValueError(
            f"Input columns do not match. Missing: {missing}. Extra: {extra}."
        )

    frame = frame[FEATURES].copy()
    warnings = []

    for column in CATEGORICAL:
        if not frame[column].map(lambda value: isinstance(value, str)).all():
            raise ValueError(f"{column} must contain text values.")

        frame[column] = frame[column].str.strip()
        if frame[column].eq("").any():
            raise ValueError(f"{column} cannot contain blank values.")

    frame["Product_Sugar_Content"] = (
        frame["Product_Sugar_Content"].replace({"reg": "Regular"})
    )

    for column in NUMERIC:
        if frame[column].map(
            lambda value: isinstance(value, (bool, np.bool_))
        ).any():
            raise ValueError(f"{column} cannot contain boolean values.")

        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if not np.isfinite(frame[column].to_numpy(dtype=float)).all():
            raise ValueError(f"{column} must contain finite numeric values.")

    if (frame["Product_Weight"] <= 0).any():
        raise ValueError("Product_Weight must be positive.")
    if (frame["Product_MRP"] <= 0).any():
        raise ValueError("Product_MRP must be positive.")
    if not frame["Product_Allocated_Area"].between(0, 1).all():
        raise ValueError("Product_Allocated_Area must be between 0 and 1.")

    ages = frame["Store_Age_Years"]
    if ((ages < 0) | (ages % 1 != 0)).any():
        raise ValueError("Store_Age_Years must be a nonnegative whole number.")

    for column in CATEGORICAL:
        unseen = sorted(
            set(frame[column]) - set(metadata["training_categories"][column])
        )
        if unseen:
            warnings.append(
                f"{column}: unseen categories {unseen}; "
                "prediction reliability is not established."
            )

    for column in NUMERIC:
        bounds = metadata["training_numeric_ranges"][column]
        outside = ~frame[column].between(bounds["min"], bounds["max"])
        if outside.any():
            warnings.append(
                f"{column}: {int(outside.sum())} record(s) outside "
                f"the training range [{bounds['min']}, {bounds['max']}]."
            )

    store_columns = [
        "Store_Size", "Store_Location_City_Type",
        "Store_Type", "Store_Age_Years",
    ]
    known = {
        tuple(record[column] for column in store_columns)
        for record in metadata["known_store_combinations"]
    }
    unfamiliar = sum(
        tuple(row) not in known
        for row in frame[store_columns].itertuples(index=False, name=None)
    )
    if unfamiliar:
        warnings.append(
            f"{unfamiliar} record(s) have store combinations absent "
            "from training; predictions require caution."
        )

    return frame, warnings


def prediction_response(frame):
    frame, warnings = prepare_inputs(frame)
    predictions = model.predict(frame)

    if not np.isfinite(predictions).all():
        raise RuntimeError("Model returned non-finite predictions.")

    return jsonify({
        "predictions": predictions.tolist(),
        "count": len(predictions),
        "warnings": warnings,
    })


@superkart_api.get("/health")
def health():
    return jsonify({"status": "ok", "model": metadata["model_name"]})


@superkart_api.post("/v1/predict")
def predict():
    if not request.is_json:
        return jsonify({"error": "Send a JSON object."}), 400

    payload = request.get_json()
    if not isinstance(payload, dict):
        return jsonify({"error": "Expected one JSON object."}), 400

    return prediction_response(pd.DataFrame([payload]))


@superkart_api.post("/v1/predictbatch")
def predict_batch():
    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify({"error": "Upload a CSV using the field 'file'."}), 400

    try:
        frame = pd.read_csv(uploaded)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError):
        return jsonify({"error": "Upload a valid, nonempty UTF-8 CSV."}), 400

    return prediction_response(frame)


@superkart_api.errorhandler(ValueError)
def invalid_input(error):
    return jsonify({"error": str(error)}), 400


@superkart_api.errorhandler(BadRequest)
def invalid_request(error):
    return jsonify({"error": "Malformed request or JSON."}), 400


@superkart_api.errorhandler(RequestEntityTooLarge)
def oversized_upload(error):
    return jsonify({"error": "Request exceeds the 5 MB limit."}), 413


if __name__ == "__main__":
    superkart_api.run(host="0.0.0.0", port=7860, debug=False)
