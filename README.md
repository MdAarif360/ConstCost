# Construction Cost Tracker

A Streamlit version of the original React construction cost tracker page.

## Included

- Budget summary with total spent, remaining budget, budget usage, and bill count
- Editable Labour, Material, and Misc budgets
- Spend charts by category, project phase, and month
- Expense creation with optional bill or invoice upload
- CSV import with row-level validation
- CSV export and downloadable import template
- SQLite storage for expenses, budgets, and uploaded bill files
- Bill download and image preview for saved attachments

## Storage

The app creates a SQLite database at:

```text
data/construction_cost_tracker.db
```

Expenses, category budgets, and uploaded bills are saved there and are loaded again when the app opens. You can change the database path by setting the `COST_TRACKER_DB_PATH` environment variable.

For Streamlit Community Cloud, SQLite works for simple single-app usage, but the app filesystem can be reset during redeploys or infrastructure restarts. For business-critical permanent cloud storage, use a hosted database such as Supabase, Neon, or managed Postgres.

## Run Locally

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

On macOS or Linux, activate the environment with:

```bash
source .venv/bin/activate
```

## Deploy With GitHub And Streamlit Community Cloud

1. Create a new GitHub repository.
2. Add these files to the repository root.
3. Commit and push:

```bash
git init
git add .
git commit -m "Add Streamlit construction cost tracker"
git branch -M main
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git push -u origin main
```

4. Open Streamlit Community Cloud and create a new app from the GitHub repository.
5. Set the main file path to `app.py`.
6. Deploy.

GitHub Pages cannot host this app directly because Streamlit needs a Python server. Streamlit Community Cloud, Render, Railway, or a VPS are suitable hosting targets.
