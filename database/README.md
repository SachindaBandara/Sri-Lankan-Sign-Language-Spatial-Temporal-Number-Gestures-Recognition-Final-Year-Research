# MySQL Database Configuration

This guide configures MySQL for the Sri Lankan Sign Language Number Gestures Recognition application. The Flask backend uses Flask-SQLAlchemy, Flask-Migrate, and PyMySQL.

## Prerequisites

- MySQL 8.0.16 or later, or MariaDB 10.11 (migration-tested)
- MySQL command-line client or MySQL Workbench
- Python 3.11 or later
- The backend dependencies installed from `backend/requirements.txt`

## 1. Create the Database

Connect to MySQL as an administrator:

```powershell
mysql -u root -p
```

Create the database:

```sql
CREATE DATABASE sl_sign_learning
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

The local development configuration uses `root` at `127.0.0.1:3306` with an
empty password. If MySQL root has a password on your machine, put it in
`DB_PASSWORD` in the project-root `.env`. Verify the database is reachable:

```powershell
mysql -h 127.0.0.1 -P 3306 -u root sl_sign_learning
```

If you set a non-empty root password, use `-p` to have MySQL prompt for it.

## 2. Configure the Backend

From the project root, copy the example file only if you do not already have a
local `.env`:

```powershell
if (-not (Test-Path .env)) { Copy-Item backend\.env.example .env }
```

Set the following MySQL values in the project-root `.env`:

```dotenv
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=sl_sign_learning
DB_USER=root
DB_PASSWORD=
SECRET_KEY=replace-with-a-long-random-secret
```

The backend loads the project-root `.env` for both Flask CLI commands and
`python run.py`. Shell environment variables take precedence. `DB_PASSWORD` may
be empty for a local MySQL installation configured without a root password.
`DATABASE_URL` is also supported as an alternative to the `DB_*` settings.
When using the provided root account, keep MySQL local-only; use a dedicated
least-privilege database user for production.

Generate `SECRET_KEY` using a password manager or a cryptographically secure
secret generator. Never commit `.env`, database credentials, or `SECRET_KEY` to
Git. The project `.gitignore` excludes `.env`.

Install backend dependencies from the `backend` directory:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

When using the legacy `DATABASE_URL` format instead of `DB_*`, URL-encode
reserved characters in its username or password.

Optional production settings:

```dotenv
SESSION_COOKIE_SECURE=true
CORS_ORIGINS=https://app.example.com
```

Use `SESSION_COOKIE_SECURE=true` only when the application is served over HTTPS.

## 3. Apply Database Migrations

Run migrations from the `backend` directory:

```powershell
flask --app run.py db upgrade
```

This creates the application schema and applies all revisions under `migrations/versions/`.
The initial revision is an explicit frozen schema snapshot and does not import
the current ORM models. Once a revision has been applied to a shared database,
do not edit it; make later changes in a new revision.
Revision `0006_personalized_learning` adds per-operation progress, difficulty
adjustment history, persistent recommendations, and learning-path steps.
Revision `0007_number_identification_scoring` adds prompted number questions
and their correctness data. If a MySQL/MariaDB migration stops during
non-transactional DDL, correct the reported cause and rerun `db upgrade`;
revision 0007 resumes already-created tables and columns without deleting data.

For a new schema migration:

```powershell
flask --app run.py db migrate -m "describe the schema change"
flask --app run.py db upgrade
```

Review the generated migration under `backend/migrations/versions/` before applying it to shared or production data.

Check migration history:

```powershell
flask --app run.py db current
flask --app run.py db history
```

Do not use `db upgrade` in place of a reviewed backup and deployment procedure for production databases.

## Personalized Learning

The adaptive engine is transparent and rule-based. It uses only submitted
answers with a correctness result; skipped, invalid, and unanswered submissions
do not affect accuracy or difficulty. It raises a math operation by one level
after the configured minimum evidence, a qualifying recent and historical
accuracy, and a consecutive-correct streak. It lowers one level only after a
qualifying recent and historical accuracy plus a consecutive-incorrect streak.
Adjustments are persisted with their evidence and reason.

Difficulty values remain `easy`, `standard`, and `hard` in stored activity
history, displayed as Beginner, Intermediate, and Advanced. Adaptive selection
uses the saved level per operation; manual levels remain available. Defaults
can be tuned through the `PERSONALIZATION_*` settings in `backend/.env.example`.

The student dashboard API is `GET /api/personalized-learning/dashboard`.
Teachers can query that endpoint with an assigned `student_id` and retrieve the
authorized roster from `GET /api/personalized-learning/students`.
Recommendations, the current learning path, and the adjustment history are
also available through `/recommendations`, `/learning-path`, and
`/difficulty-history` under the same prefix.

Number-identification currently has no target-answer field, so its predictions
cannot establish student answer accuracy. The dashboard reports recognition
confidence and high-confidence recognition counts separately and does not use
them for math mastery or difficulty changes.

## 4. Start the Backend

```powershell
python run.py
```

The development API is available at `http://127.0.0.1:5000`. Verify database connectivity:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:5000/health"
```

The health endpoint confirms that the application is running, but database-dependent operations provide the stronger database connectivity check.

## Schema

Flask-Migrate manages the following learning-data tables:

| Table | Purpose |
|---|---|
| `users` | Student and teacher accounts |
| `teacher_students` | Explicit teacher-to-student assignments |
| `student_learning_sessions` | Learning session lifecycle and duration |
| `student_activity_attempts` | Arithmetic activity attempts and summaries |
| `learning_questions` | Server-generated questions |
| `student_question_attempts` | Answer attempts, retries, skips, and timing |
| `student_sign_recognition_logs` | Gesture recognition outcomes and confidence |
| `alembic_version` | Applied database migration revision |

Question answers remain server-controlled. Recognition confidence and mathematical correctness are stored as separate values.
Database check constraints validate account roles and grades, learning statuses,
nonnegative counters and durations, arithmetic results, answer-attempt states,
and recognition values. The summary checks also require an activity's valid
attempt count to equal its correct plus incorrect answers.

Learning-history foreign keys restrict deletion of users, sessions, activities,
and questions that have dependent records. Disable an account instead of
physically deleting it; this preserves the account's historical learning data.
Teacher-assignment links are not learning history and may be removed with their
associated accounts.

## Data Retention and Backup

Create a backup before migrations or production changes:

```powershell
mysqldump -h 127.0.0.1 -P 3306 -u root --single-transaction --routines --triggers sl_sign_learning > sl_sign_learning_backup.sql
```

Restore when required:

```powershell
mysql -h 127.0.0.1 -P 3306 -u root sl_sign_learning < sl_sign_learning_backup.sql
```

For scheduled production backups, use the database administrator's MySQL backup process, encrypt backups, restrict file access, and periodically test restoration.

## Inspection Queries

Check migration state:

```sql
USE sl_sign_learning;
SELECT * FROM alembic_version;
```

Check row counts:

```sql
SELECT 'users' AS table_name, COUNT(*) AS row_count FROM users
UNION ALL SELECT 'student_learning_sessions', COUNT(*) FROM student_learning_sessions
UNION ALL SELECT 'student_activity_attempts', COUNT(*) FROM student_activity_attempts
UNION ALL SELECT 'learning_questions', COUNT(*) FROM learning_questions
UNION ALL SELECT 'student_question_attempts', COUNT(*) FROM student_question_attempts
UNION ALL SELECT 'student_sign_recognition_logs', COUNT(*) FROM student_sign_recognition_logs;
```

Inspect recent sessions:

```sql
SELECT id, identifier, student_id, status, started_at, ended_at
FROM student_learning_sessions
ORDER BY started_at DESC
LIMIT 20;
```

## Security

- The example root account is for local development only; use a dedicated least-privilege account in production.
- Do not expose a MySQL root account with an empty password to a network.
- Store credentials in environment variables or a deployment secret manager.
- Restrict network access to the MySQL port.
- Use TLS for remote database connections.
- Keep MySQL and the PyMySQL package updated.
- Add database credentials to access-controlled secret storage, not source control.
- Provision teacher accounts and assignments through the trusted Flask CLI commands.

## Troubleshooting

### pip launcher points to an old folder or drive

Windows virtual environments are not reliable to move. If the error mentions an
old path such as `G:\Research Project\backend\.venv`, run these commands from
the current `backend` directory. Deactivate the environment first if it is
active; the removal targets only this backend's ignored `.venv` folder.

```powershell
Remove-Item -Recurse -Force .venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Use `python -m pip` for future installs so pip runs through the active Python
interpreter rather than a potentially stale `pip.exe` launcher.

### Access denied for user

- Confirm `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, and `DB_NAME` in the project-root `.env`.
- Confirm MySQL is reachable with:

  ```powershell
  mysql -h 127.0.0.1 -P 3306 -u root sl_sign_learning
  ```

- If the root account has a password, add `-p` to the command and set the same password in `DB_PASSWORD`.

### Unknown database

Create or select the database:

```sql
CREATE DATABASE sl_sign_learning
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

### Unknown MySQL server host or connection refused

- Confirm the MySQL service is running.
- Confirm the configured host and port.
- Check Windows Firewall and MySQL bind-address settings.
- Confirm `DB_HOST` and `DB_PORT` in the project-root `.env`.

### Migration state is missing or inconsistent

Check migration status:

```powershell
flask --app run.py db current
flask --app run.py db history
```

Back up the database before repairing migration state. Do not manually edit `alembic_version` or delete migration rows unless the change is intentional and has been reviewed.

### Database tables or migrations are missing

Set `SECRET_KEY` and the database settings in the project-root `.env`, then run:

```powershell
flask --app run.py db upgrade
```
