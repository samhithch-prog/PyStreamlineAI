# PyStreamlineAI
Resume AI Checker using Streamlit + LangChain + OpenAI.

## Setup
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set your OpenAI key:
   - PowerShell:
     ```powershell
     $env:OPENAI_API_KEY="your_key_here"
     ```
3. Configure PostgreSQL connection (required):
   - Set `DATABASE_URL` environment variable, or set `[database].url` in `.streamlit/secrets.toml`
   - Example:
     ```powershell
     $env:DATABASE_URL="postgresql://pystreamline_app:YOUR_PASSWORD@localhost:5432/pystreamline"
     ```
4. Configure email verification (required for password login):
   - Set SMTP + OTP settings via environment variables or `.streamlit/secrets.toml`
   - PowerShell example:
     ```powershell
     $env:SMTP_HOST="smtp.gmail.com"
     $env:SMTP_PORT="587"
     $env:SMTP_USERNAME="your_smtp_user"
     $env:SMTP_PASSWORD="your_smtp_password"
     $env:SMTP_FROM_EMAIL="no-reply@yourdomain.com"
     $env:SMTP_USE_TLS="true"
     $env:OTP_PEPPER="long_random_secret_value"
     ```
   - `OTP_PEPPER` is optional if `[auth].cookie_secret` is already set; that value is used as fallback.
5. Optional OAuth login (recommended for refresh-persistent login):
   - Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
   - Fill `cookie_secret` and provider credentials (`[auth.google]` and/or `[auth.linkedin]`)
   - Optional promo codes (disabled by default):
     - Set `[promo].enabled = true` and add `valid_codes = ["CODE1", "CODE2"]`
   - For LinkedIn app setup:
     - In LinkedIn Developer portal, enable **Sign In with LinkedIn using OpenID Connect**
     - Add your redirect URL to the app (must match `auth.redirect_uri` exactly)
     - Use metadata URL: `https://www.linkedin.com/oauth/.well-known/openid-configuration`
     - Use scopes: `openid profile email`
   - If LinkedIn rejects `http://localhost:8501/oauth2callback`, use an HTTPS tunnel URL and set `auth.redirect_uri` to that HTTPS callback
6. Run:
   ```bash
   streamlit run app.py
   ```

## PostgreSQL + pgAdmin (Org-Style)
1. Copy environment template and set strong passwords:
   - `.env.postgres.example` -> `.env.postgres`
2. Start PostgreSQL and pgAdmin:
   ```bash
   docker compose --env-file .env.postgres -f docker-compose.postgres.yml up -d
   ```
3. Configure app DB URL (use either option):
   - PowerShell:
     ```powershell
     $env:DATABASE_URL="postgresql://pystreamline_app:YOUR_PASSWORD@localhost:5432/pystreamline"
     ```
   - or `.streamlit/secrets.toml`:
     ```toml
     [database]
     url = "postgresql://pystreamline_app:YOUR_PASSWORD@localhost:5432/pystreamline"
     ```
4. Pre-create schema with SQL:
   ```bash
   psql "$DATABASE_URL" -f infra/postgres/schema.sql
   ```
5. (Optional) migrate existing local SQLite data:
   ```bash
   python scripts/migrate_sqlite_to_postgres.py --sqlite-path users.db --truncate
   ```
6. Open pgAdmin:
   - URL: `http://localhost:5050`
   - Login from `.env.postgres`
   - Add server:
     - Host: `postgres` (inside docker network) or `localhost`
     - Port: `5432`
     - DB: `pystreamline`
     - User: `pystreamline_app`

## Login Audit Table
- Successful logins are stored in `user_login_events`.
- Captured fields:
  - `user_id`
  - `login_method` (`password` or `oauth`)
  - `login_provider` (`local`, `google`, `linkedin`, or `oauth`)
  - `login_at` (UTC ISO timestamp)
- Example query:
  ```sql
  SELECT u.email, COUNT(e.id) AS login_count, MAX(e.login_at) AS last_login_at
  FROM users u
  LEFT JOIN user_login_events e ON e.user_id = u.id
  GROUP BY u.email
  ORDER BY login_count DESC, u.email;
  ```

## Email Verification
- Password signup now creates a pending request in `signup_verification_requests` (not a user account).
- App sends a 6-digit OTP to the signup email using configured SMTP.
- After OTP verification, the real user row is created in `users` with `email_verified_at` set.
- OTP attempt/rate-limit state is stored in DB and login remains blocked until verification is complete.
- OAuth users are marked verified automatically because provider identity already verifies email ownership.

## Security Baseline
- Use strong, rotated DB passwords (no defaults in production).
- Restrict network access to PostgreSQL (private subnet/VPN only).
- Enable TLS for managed/Postgres production deployments.
- Use least-privilege app user credentials.
- Run periodic backups and test restores.
- Keep pgAdmin access restricted to admins only.

## Features
- User signup/login with stored profile details.
- Resume upload (`.pdf` or `.docx`) and job description input.
- AI match scoring with categories:
  - `Not Relevant`
  - `Good`
  - `Excellent`
  - `Perfect Match`
- On-screen AI bot (memoji launcher) with expand, minimize, and close controls.
