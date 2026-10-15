from pathlib import Path
import json
import os

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="SuperKart Sales Predictor", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
with (BASE_DIR / "model_metadata.json").open(encoding="utf-8") as file:
    metadata = json.load(file)

# "backend" will be the backend container name on the Docker network.
API_URL = os.environ.get("BACKEND_URL", "http://backend:7860").rstrip("/")

STORES = {
    "OUT001": {
        "Store_Size": "High",
        "Store_Location_City_Type": "Tier 2",
        "Store_Type": "Supermarket Type1",
        "Store_Age_Years": 38,
    },
    "OUT002": {
        "Store_Size": "Small",
        "Store_Location_City_Type": "Tier 3",
        "Store_Type": "Food Mart",
        "Store_Age_Years": 27,
    },
    "OUT003": {
        "Store_Size": "Medium",
        "Store_Location_City_Type": "Tier 1",
        "Store_Type": "Departmental Store",
        "Store_Age_Years": 26,
    },
    "OUT004": {
        "Store_Size": "Medium",
        "Store_Location_City_Type": "Tier 2",
        "Store_Type": "Supermarket Type2",
        "Store_Age_Years": 16,
    },
}


def call_api(endpoint, **kwargs):
    """Call the backend and show useful errors."""
    try:
        response = requests.post(
            f"{API_URL}{endpoint}", timeout=120, **kwargs
        )
    except requests.RequestException:
        st.error("Cannot reach the prediction service. Please try again later.")
        return None

    try:
        result = response.json()
    except ValueError:
        st.error("The prediction service returned an unreadable response.")
        return None

    if not response.ok:
        message = result.get("error") if isinstance(result, dict) else None
        st.error(message or f"Prediction failed (HTTP {response.status_code}).")
        return None

    if not isinstance(result, dict) or not isinstance(
        result.get("predictions"), list
    ):
        st.error("The prediction service returned an unexpected response.")
        return None

    return result


def show_warnings(result):
    for warning in result.get("warnings", []):
        st.warning(warning)


st.title("SuperKart Sales Predictor")
st.write("Estimate product sales revenue for the existing store network.")
st.caption(
    "Results use the dataset's sales units; currency and reporting period "
    "are unspecified. Future-quarter performance has not been validated."
)

single_tab, batch_tab = st.tabs(["Single prediction", "Batch prediction"])

with single_tab:
    with st.form("single_prediction"):
        left, right = st.columns(2)

        with left:
            store_id = st.selectbox("Store", list(STORES))
            product_type = st.selectbox(
                "Product category",
                sorted(metadata["product_category_map"]),
            )
            sugar = st.selectbox(
                "Sugar content",
                metadata["training_categories"]["Product_Sugar_Content"],
            )
            weight = st.number_input(
                "Product weight", min_value=0.01, value=12.66, step=0.1
            )

        with right:
            mrp = st.number_input(
                "Maximum retail price", min_value=0.01, value=117.08, step=1.0
            )
            area = st.number_input(
                "Allocated display-area ratio",
                min_value=0.0,
                max_value=1.0,
                value=0.027,
                step=0.001,
                format="%.3f",
            )

        submitted = st.form_submit_button("Predict sales")

    if submitted:
        # Prefix relationships observed in the supplied training dataset.
        if product_type in ["Hard Drinks", "Soft Drinks"]:
            prefix = "DR"
        elif product_type in ["Health and Hygiene", "Household", "Others"]:
            prefix = "NC"
        else:
            prefix = "FD"

        payload = {
            "Product_Weight": weight,
            "Product_Sugar_Content": sugar,
            "Product_Allocated_Area": area,
            "Product_MRP": mrp,
            **STORES[store_id],
            "Product_Id_char": prefix,
            "Product_Type_Category": metadata["product_category_map"][
                product_type
            ],
        }

        with st.spinner("Calculating prediction..."):
            result = call_api("/v1/predict", json=payload)

        if result is not None:
            if len(result["predictions"]) != 1:
                st.error("Expected exactly one prediction.")
            else:
                st.metric(
                    "Predicted sales",
                    f"{result['predictions'][0]:,.2f}",
                )
                show_warnings(result)
                st.caption(
                    "This result corresponds to the inputs submitted "
                    "with the Predict sales button."
                )

with batch_tab:
    st.write(
        "Upload a CSV containing the 10 model input columns. "
        "Store age must use the fixed 2025 reference year."
    )

    template = pd.DataFrame(columns=metadata["feature_columns"])
    st.download_button(
        "Download blank CSV template",
        data=template.to_csv(index=False).encode("utf-8"),
        file_name="superkart_batch_template.csv",
        mime="text/csv",
    )

    uploaded = st.file_uploader("Choose a batch CSV", type=["csv"])

    # Clear saved results when the uploaded content changes.
    current_bytes = uploaded.getvalue() if uploaded is not None else None
    if st.session_state.get("batch_source") != current_bytes:
        st.session_state["batch_source"] = current_bytes
        st.session_state.pop("batch_output", None)
        st.session_state.pop("batch_warnings", None)

    if uploaded is not None and st.button("Predict batch"):
        st.session_state.pop("batch_output", None)
        st.session_state.pop("batch_warnings", None)

        try:
            uploaded.seek(0)
            batch_df = pd.read_csv(uploaded)
        except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError):
            st.error("Please upload a valid, nonempty UTF-8 CSV.")
        else:
            with st.spinner("Calculating batch predictions..."):
                result = call_api(
                    "/v1/predictbatch",
                    files={
                        "file": (uploaded.name, current_bytes, "text/csv")
                    },
                )

            if result is not None:
                if len(result["predictions"]) != len(batch_df):
                    st.error("The number of predictions does not match the CSV.")
                else:
                    output = batch_df.copy()
                    output["Predicted_Sales"] = result["predictions"]
                    st.session_state["batch_output"] = output
                    st.session_state["batch_warnings"] = result.get(
                        "warnings", []
                    )

    if "batch_output" in st.session_state:
        for warning in st.session_state.get("batch_warnings", []):
            st.warning(warning)

        output = st.session_state["batch_output"]
        st.success(f"Generated {len(output)} predictions.")
        st.dataframe(output, use_container_width=True)
        st.download_button(
            "Download predictions",
            data=output.to_csv(index=False).encode("utf-8"),
            file_name="superkart_predictions.csv",
            mime="text/csv",
        )
