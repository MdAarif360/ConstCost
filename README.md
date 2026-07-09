# Construction Cost Tracker

A Streamlit version of the original React construction cost tracker page.

## Included

- Budget summary with total spent, remaining budget, budget usage, and bill count
- Editable Labour, Material, and Misc budgets
- Spend charts by category, project phase, and month
- Expense creation with optional bill or invoice upload
- Expense editing from the Manage Expenses tab
- CSV import with row-level validation
- CSV export and downloadable import template
- PostgreSQL storage for expenses, budgets, and uploaded bill files
- Bill download and image preview for saved attachments

## Storage

For permanent storage on Streamlit Community Cloud, use a hosted PostgreSQL database
such as Supabase, Neon, Railway Postgres, Render Postgres, or managed Postgres.
Set the database connection string as a Streamlit secret:

```toml
DATABASE_URL = "postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require"
```

The app also accepts the same value as an environment variable named
`DATABASE_URL`, or as a Streamlit connection-style secret named
`connections.postgres.url`, `connections.postgresql.url`, `connections.sql.url`,
`connections.cost_tracker.url`, or `connections.construction_cost.url`.

When `DATABASE_URL` is not set, the app falls back to a local SQLite database at:

```text
data/construction_cost_tracker.db
```

SQLite is useful for local testing, but Streamlit Community Cloud can reset app
files during redeploys or infrastructure restarts. Use PostgreSQL for data that
must remain permanently available.

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
6. In app secrets, add your PostgreSQL `DATABASE_URL`.
7. Deploy.

GitHub Pages cannot host this app directly because Streamlit needs a Python server. Streamlit Community Cloud, Render, Railway, or a VPS are suitable hosting targets.
