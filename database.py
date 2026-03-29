import logging
from datetime import datetime
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from psycopg2.pool import ThreadedConnectionPool

import config

logger = logging.getLogger(__name__)

pool: Optional[ThreadedConnectionPool] = None


def init_db():
    """Initialize connection pool and create tables."""
    global pool
    pool = ThreadedConnectionPool(
        minconn=1,
        maxconn=10,
        dsn=config.DATABASE_URL
    )
    _create_tables()
    logger.info("Database initialized successfully.")


def _get_conn():
    return pool.getconn()


def _release_conn(conn):
    pool.putconn(conn)


def _create_tables():
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id      BIGINT PRIMARY KEY,
                    username     TEXT,
                    full_name    TEXT,
                    language     TEXT DEFAULT 'ar',
                    is_active    BOOLEAN DEFAULT TRUE,
                    created_at   TIMESTAMPTZ DEFAULT NOW(),
                    last_seen_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    id           SERIAL PRIMARY KEY,
                    external_id  TEXT UNIQUE,
                    source       TEXT NOT NULL,
                    title        TEXT NOT NULL,
                    company      TEXT,
                    location     TEXT,
                    category     TEXT,
                    description  TEXT,
                    salary_min   NUMERIC,
                    salary_max   NUMERIC,
                    currency     TEXT,
                    url          TEXT NOT NULL,
                    posted_at    TIMESTAMPTZ,
                    fetched_at   TIMESTAMPTZ DEFAULT NOW(),
                    is_active    BOOLEAN DEFAULT TRUE
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_category ON jobs(category);
                CREATE INDEX IF NOT EXISTS idx_jobs_location ON jobs(location);
                CREATE INDEX IF NOT EXISTS idx_jobs_fetched_at ON jobs(fetched_at DESC);

                CREATE TABLE IF NOT EXISTS subscriptions (
                    id          SERIAL PRIMARY KEY,
                    user_id     BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                    keyword     TEXT NOT NULL,
                    location    TEXT,
                    category    TEXT,
                    created_at  TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(user_id, keyword, location)
                );

                CREATE TABLE IF NOT EXISTS sent_jobs (
                    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                    job_id  INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
                    sent_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (user_id, job_id)
                );
            """)
            conn.commit()
    finally:
        _release_conn(conn)


# ─── Users ────────────────────────────────────────────────────────────────────

def upsert_user(user_id: int, username: str, full_name: str):
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, username, full_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET username = EXCLUDED.username,
                    full_name = EXCLUDED.full_name,
                    last_seen_at = NOW()
            """, (user_id, username, full_name))
            conn.commit()
    finally:
        _release_conn(conn)


def get_user(user_id: int) -> Optional[dict]:
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            return dict(cur.fetchone()) if cur.rowcount else None
    finally:
        _release_conn(conn)


def get_all_active_users() -> list[dict]:
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE is_active = TRUE")
            return [dict(r) for r in cur.fetchall()]
    finally:
        _release_conn(conn)


# ─── Jobs ─────────────────────────────────────────────────────────────────────

def insert_jobs(jobs: list[dict]) -> int:
    """Bulk insert jobs, skip duplicates. Returns count of new rows."""
    if not jobs:
        return 0
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            rows = [
                (
                    j.get("external_id"),
                    j.get("source"),
                    j.get("title"),
                    j.get("company"),
                    j.get("location"),
                    j.get("category"),
                    j.get("description"),
                    j.get("salary_min"),
                    j.get("salary_max"),
                    j.get("currency"),
                    j.get("url"),
                    j.get("posted_at"),
                )
                for j in jobs
            ]
            execute_values(cur, """
                INSERT INTO jobs
                    (external_id, source, title, company, location, category,
                     description, salary_min, salary_max, currency, url, posted_at)
                VALUES %s
                ON CONFLICT (external_id) DO NOTHING
            """, rows)
            inserted = cur.rowcount
            conn.commit()
            return inserted
    finally:
        _release_conn(conn)


def search_jobs(keyword: str = "", location: str = "",
                category: str = "", page: int = 1,
                per_page: int = None) -> tuple[list[dict], int]:
    """Returns (jobs, total_count)."""
    per_page = per_page or config.JOBS_PER_PAGE
    offset = (page - 1) * per_page

    filters = ["is_active = TRUE"]
    params: list = []

    if keyword:
        filters.append("(title ILIKE %s OR description ILIKE %s)")
        params += [f"%{keyword}%", f"%{keyword}%"]
    if location:
        filters.append("location ILIKE %s")
        params.append(f"%{location}%")
    if category:
        filters.append("category ILIKE %s")
        params.append(f"%{category}%")

    where = "WHERE " + " AND ".join(filters)

    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"SELECT COUNT(*) FROM jobs {where}", params)
            total = cur.fetchone()["count"]

            cur.execute(
                f"SELECT * FROM jobs {where} ORDER BY fetched_at DESC LIMIT %s OFFSET %s",
                params + [per_page, offset]
            )
            rows = [dict(r) for r in cur.fetchall()]
            return rows, total
    finally:
        _release_conn(conn)


def get_new_jobs_for_subscription(user_id: int, keyword: str,
                                   location: str = "") -> list[dict]:
    """Jobs matching the subscription that haven't been sent yet."""
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT j.* FROM jobs j
                WHERE j.is_active = TRUE
                  AND (j.title ILIKE %s OR j.description ILIKE %s)
                  AND (%s = '' OR j.location ILIKE %s)
                  AND j.id NOT IN (
                      SELECT job_id FROM sent_jobs WHERE user_id = %s
                  )
                ORDER BY j.fetched_at DESC
                LIMIT 10
            """, (
                f"%{keyword}%", f"%{keyword}%",
                location, f"%{location}%",
                user_id
            ))
            return [dict(r) for r in cur.fetchall()]
    finally:
        _release_conn(conn)


def mark_job_sent(user_id: int, job_id: int):
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO sent_jobs (user_id, job_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
            """, (user_id, job_id))
            conn.commit()
    finally:
        _release_conn(conn)


# ─── Subscriptions ────────────────────────────────────────────────────────────

def add_subscription(user_id: int, keyword: str, location: str = "") -> bool:
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM subscriptions WHERE user_id = %s", (user_id,))
            count = cur.fetchone()[0]
            if count >= config.MAX_SUBSCRIPTIONS_PER_USER:
                return False
            cur.execute("""
                INSERT INTO subscriptions (user_id, keyword, location)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, keyword, location) DO NOTHING
            """, (user_id, keyword.strip(), location.strip()))
            conn.commit()
            return True
    finally:
        _release_conn(conn)


def remove_subscription(sub_id: int, user_id: int) -> bool:
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM subscriptions WHERE id = %s AND user_id = %s",
                (sub_id, user_id)
            )
            conn.commit()
            return cur.rowcount > 0
    finally:
        _release_conn(conn)


def get_user_subscriptions(user_id: int) -> list[dict]:
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM subscriptions WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,)
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        _release_conn(conn)


def get_all_subscriptions() -> list[dict]:
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT s.*, u.is_active FROM subscriptions s JOIN users u USING(user_id)")
            return [dict(r) for r in cur.fetchall()]
    finally:
        _release_conn(conn)


def get_stats() -> dict:
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM users WHERE is_active = TRUE) AS active_users,
                    (SELECT COUNT(*) FROM jobs WHERE is_active = TRUE)  AS total_jobs,
                    (SELECT COUNT(*) FROM subscriptions)                AS total_subscriptions
            """)
            return dict(cur.fetchone())
    finally:
        _release_conn(conn)
