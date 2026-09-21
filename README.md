# WalletTracker

A REST API for tracking personal finances, built with Flask and deployed on a self-hosted infrastructure stack.

The API handles authentication (JWT with RSA keys), expense categories, and expense tracking. It is designed for self-hosting and exposes endpoints through a Cloudflare tunnel. The Android client [WalletTracker](https://github.com/noelnovo/WalletTracker) consumes this API.

---

## Architecture

```
GitHub ──► GitHub Actions ──► Jenkins ──► Proxmox (Docker containers)
                                               │
                              Cloudflare Tunnel ◄─── Flask API (port 5000) ──► SonarQube Scanner
                                                         │
                                                    MariaDB (port 3306)

Terraform manages: Proxmox VMs/containers, Cloudflare DNS, Vault secrets
HashiCorp Vault: stores all secrets (Jenkins credentials, DB passwords, API tokens)
```

### Components

| Component | Role |
|---|---|
| **Flask (Python)** | REST API backend — auth, expenses, categories |
| **MariaDB** | Relational database via SQLAlchemy ORM |
| **Docker / Docker Compose** | Containerization with profile-based service selection |
| **Terraform** | Provisions Proxmox LXC containers, Cloudflare DNS records, and Vault secrets |
| **HashiCorp Vault** | Centralized secrets management — no secrets in CI/CD or environment files |
| **GitHub Actions** | CI on pull requests, CD trigger on merge to `main` |
| **Jenkins** | Executes the actual deployment pipeline on the self-hosted server |
| **SonarQube** | Analyses the codebase and checks for vulnerabilities and code quality |
| **Proxmox** | Hypervisor hosting the LXC containers for the API and database |
| **Cloudflare** | Tunnel and DNS routing — exposes the API publicly without open ports |
| **Bruno** | API collection for manual endpoint testing during development |
| **[WalletTracker](https://github.com/noelnovo/WalletTracker)** | Android client app — consumes this API |

### CI/CD Flow

- **CI** — runs on every pull request to `main`: spins up the `app` container via Docker Compose and runs `pytest` against an in-memory SQLite DB (no real DB needed)
- **CD** — runs on merge to `main`: fetches secrets from Vault and triggers a Jenkins webhook to deploy
- **Post CD** — Jenkins builds the Docker image, scans it with Trivy, generates a CycloneDX SBOM, and uploads it to OWASP Dependency-Track for continuous vulnerability monitoring before pushing
- **Post CD** - Jenkins calls SonarQube to run the scanner.
- To skip CD on a specific merge, add the **`skip cd`** label to the PR before merging

---

## Dev Environment Setup

### Requirements

- Python 3.x
- Docker and Docker Compose
- MariaDB client libraries (for `mysqlclient`)

On Arch Linux:
```bash
yay -S mariadb-libs
```

On Debian/Ubuntu:
```bash
sudo apt install libmariadb-dev
```

### 1. Clone

```bash
git clone https://github.com/noelnovo/WalletTrackerAPI.git && cd WalletTrackerAPI/
```

### 2. Python virtual environment

```bash
python3 -m venv .venv
```

Activate — Linux:
```bash
source .venv/bin/activate
```

Activate — Windows:
```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:
```bash
uv sync
```

### 3. Environment variables

Create a `.env` file in the project root:

```env
DATABASE_NAME=wallet_tracker
DATABASE_ROOT_PASSWORD=adminadmin
WALLET_TRACKER_SECRET=your_secret_here
WALLET_TRACKER_DB_USER=root
WALLET_TRACKER_DB_HOST=db
ENABLE_REGISTER=true

# Controls which Docker Compose services start (see below)
COMPOSE_PROFILES=db,app
```

#### `COMPOSE_PROFILES`

Docker Compose uses profiles to selectively start services:

| Value | Services started | Use case |
|---|---|---|
| `db` | MariaDB only | Run the app locally against a containerized DB |
| `app` | Flask app only | Use an external DB |
| `db,app` | Both | Full local stack / CI |

Example — start only the database (run the app directly with Python):
```bash
COMPOSE_PROFILES=db docker compose up -d --build
```

### 4. Run with Docker Compose

Start both services:
```bash
docker compose up -d --build
```

The API will be available at `http://localhost:5000`.

### 5. Run the app directly (without Docker)

Make sure the database is running (either via Docker or externally), then:
```bash
python app/main.py
```

### 6. Run tests

With the virtual environment activated:
```bash
pytest -v
```

Or via Docker Compose (mirrors CI):
```bash
docker compose exec app pytest -v
```

---

## Database Migrations

Schema is split across two migration directories:

| Directory | Covers | Managed by |
|---|---|---|
| `migrations_main/` | `User`, `RefreshToken` (main DB) | Flask-Migrate |
| `migrations_tenant/` | `Expense`, `ExpenseCategory`, `Season`, `Importe` (per-user DBs) | Flask-Migrate |

### First-time setup (clean database)

Start the database, set env vars, then apply migrations:

```bash
COMPOSE_PROFILES=db docker compose up -d

export FLASK_APP=main.py
export DATABASE_ROOT_PASSWORD=adminadmin
export DATABASE_NAME=wallet_tracker
export WALLET_TRACKER_DB_USER=root
export WALLET_TRACKER_DB_HOST=127.0.0.1

cd app/
flask db upgrade --directory migrations_main
```

Tenant migrations run automatically when the first user registers (`initialise_tenant_db` calls `create_all`). After that, `migrate_all.py` keeps them in sync.

### Applying all migrations (after schema changes)

```bash
cd app/
export DATABASE_ROOT_PASSWORD=... DATABASE_NAME=... WALLET_TRACKER_DB_USER=... WALLET_TRACKER_DB_HOST=...
python migrate_all.py
```

This runs `migrations_main` against the main DB, then `migrations_tenant` against every `wallet_tracker_u*` DB.

### Creating a new migration

After changing a model, generate the migration file for the relevant directory:

```bash
# Main DB models (User, RefreshToken)
flask db migrate --directory migrations_main -m "describe your change"

# Tenant models (Expense, ExpenseCategory, Season, Importe)
flask db migrate --directory migrations_tenant -m "describe your change"
```

Review the generated file in `versions/` before committing. Then apply with `migrate_all.py`.

### Removing a table

Removing a model from the code does **not** automatically drop the table — you must generate and commit a migration first:

1. Delete the model class from the codebase
2. Generate the migration for the relevant directory:

```bash
# Main DB
flask db migrate --directory migrations_main -m "remove <table>"

# Tenant DB
flask db migrate --directory migrations_tenant -m "remove <table>"
```

3. Review the generated file in `versions/` — confirm it contains `op.drop_table(...)`
4. Commit and push the migration file
5. The next pipeline run will apply it and drop the table in prod

If you skip step 2–4 and only remove the model, the pipeline will find no new migration and leave the table untouched.

### On deploy

`migrate_all.py` runs automatically on every deploy via Terraform (`backend.tf`), before the service restarts.

---

## API Endpoints

Use the [Bruno](https://www.usebruno.com/) collection in the `bruno/` directory to explore and test the available endpoints.

Available request groups:
- Auth (`/login`, `/register`)
- Expense Categories
- Expenses
