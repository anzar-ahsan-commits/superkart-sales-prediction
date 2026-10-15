# SuperKart Sales Prediction

Product/store sales prediction using a Random Forest pipeline, a Flask API,
and a Streamlit interface deployed as separate Docker containers.

## Model performance

Reserved test set: 1,753 records.

| Metric | Result |
|---|---:|
| RMSE | 271.145 |
| MAE | 99.355 |
| R² | 0.934 |

The model was trained on 7,010 records. Hyperparameters were selected using
five-fold cross-validation on the training data.

The dataset represents four stores and has no sales dates or defined reporting
period. Results do not establish next-quarter forecasting performance or
generalization to new stores. Currency is unspecified.

## Project files

- `backend_files/`: Flask API, fitted pipeline, metadata, dependencies, Dockerfile.
- `frontend_files/`: Streamlit interface, metadata, dependencies, Dockerfile.
- `compose.yaml`: starts both services on a shared Docker network.
- `Batch_Data_SuperKart.csv`: example inference inputs without actual sales.
- `scripts/fix-codespaces-network.sh`: environment-specific network workaround.

## Start the application

From the repository root:

```bash
docker compose up --build -d
docker compose ps
```

Open forwarded port 8501 in the Codespaces Ports panel.

The frontend connects internally to `http://backend:7860`.
Keep ports private unless external access is needed. For the demonstrated
Colab inference workflow, port 7860 must be public while requests are made.
The API does not implement authentication.

## API routes

- `GET /health`: service health.
- `POST /v1/predict`: one JSON input object.
- `POST /v1/predictbatch`: CSV upload using multipart field `file`.

Prediction responses contain `predictions`, `count`, and `warnings`.
Batch predictions preserve input row order. Required feature names and
training ranges are recorded in `backend_files/model_metadata.json`.

Store age uses the fixed 2025 reference year inferred from the assignment
example. The product grouping is an explicit project convention recorded
in metadata. Inputs outside training coverage generate warnings.

## Verify connectivity

```bash
curl --max-time 10 http://localhost:7860/health
docker compose exec frontend python -c 'import requests; r = requests.get("http://backend:7860/health", timeout=5); print(r.status_code, r.text)'
```

Both checks should return HTTP 200 or the corresponding health response.

## Codespaces network workaround

During deployment, legacy iptables rules had a FORWARD DROP policy and
did not allow the project's bridge. This blocked frontend-to-backend
communication despite both containers being healthy.

If this same conflict recurs, run:

```bash
bash scripts/fix-codespaces-network.sh
```

The script adds rules limited to API traffic on port 7860 and its established
replies within the project's bridge. It preserves the global firewall policy.
It assumes the Compose network is named `superkart-sales-prediction_default`.

The rules may need reapplying after network recreation or environment restart.
This is an environment-specific workaround, not a routine requirement for
every Docker host.

## Verification completed

- Model predictions matched after serialization and reloading.
- API validation rejected malformed and incomplete requests.
- Both Docker containers reported healthy status.
- Streamlit single and batch predictions succeeded.
- Live API batch predictions matched the Colab pipeline numerically.

## Stop the application

```bash
docker compose stop
```

The hosted application is unavailable while its Codespace is stopped.
