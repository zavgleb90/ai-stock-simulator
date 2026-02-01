# AI-SIM Trading Platform

A course project that lets students build an **automated investing desk** on top of a **simulated equity market**.

Students will:
- ingest data (e.g., FinancialModelingPrep) via **n8n**
- engineer features + train models (Python)
- publish target weights and “trade” in a simulator with costs + constraints
- monitor risk and generate weekly reports (Slack/Gmail/Sheets)

## Repo layout

- `simulator/` — market generator, execution model, portfolio accounting, risk checks  
- `news_generator/` — synthetic “market news” + event shocks (optional)  
- `n8n_workflows/` — exported n8n JSON workflows and workflow docs  
- `data/` — **not committed** raw data; use `data/sample/` or Sheets for examples  
- `students/` — student/team folders (template provided); logs are committed as deliverables  
- `dashboards/` — leaderboards / reporting (notebooks or Streamlit)  
- `notebooks/` — demos, EDA, strategy experiments  
- `tests/` — unit tests for simulator + utilities  
- `docs/` — project spec, grading rubric, and how-to guides  

## Quickstart

### 1) Create a venv and install deps

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2) Run a minimal simulation

```bash
python -m simulator.cli run --config simulator/configs/dev.yaml
```

Outputs are written to `data/outputs/` (ignored by git) unless you change the config.

### 3) Connect n8n (optional for Week 1–2)

- Import workflows from `n8n_workflows/` into your n8n instance
- Configure credentials for FMP, Google Sheets, Slack, Gmail
- Run the “Data Refresh” workflow to populate Sheets / `data/`

## Contributing (course mode)

- Add work in your team folder under `students/<team_name>/`
- Keep simulator core changes small and well-tested (`tests/`)
- Document assumptions: costs, slippage, constraints, and any data quirks

## License

Choose a license before publishing (MIT or Apache-2.0 are common). See `LICENSE` placeholder.
