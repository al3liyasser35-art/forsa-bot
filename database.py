import logging
from datetime import datetime
from typing import Optional

import config

logger = logging.getLogger(__name__)

# ─── Try to import psycopg2 ───────────────────────────────────────────────────
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor, execute_values
    from psycopg2.pool import ThreadedConnectionPool
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.warning("psycopg2 not available — running in memory-only mode.")

pool = None
DB_AVAILABLE = False

# ─── In-memory fallback storage ───────────────────────────────────────────────
_mem_users: dict[int, dict] = {}
_mem_jobs: list[dict] = []
_mem_subscriptions: list[dict] = []
_mem_sent_jobs: set[tuple] = set()
_mem_job_id_counter = 0
_mem_sub_id_counter = 0


def init_db():
    global pool, DB_AVAILABLE

    if not PSYCOPG2_AVAILABLE:
        logger.warning("Starting in memory-only mode (no psycopg2).")
        return

    if not config.DATABASE_URL or "your_password" in config.DATABASE_URL:
        logger.warning("DATABASE_URL not configured — running in memory-only mode.")
        return

    try:
        pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=config.DATABASE_URL)
        _create_tables()
        DB_AVAILABLE = True
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.warning("DB connection failed (%s) — running in memory-only mode.", e)


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
    if not DB_AVAILABLE:
        _mem_users[user_id] = {
            "user_id": user_id, "username": username,
            "full_name": full_name, "is_active": True,
            "last_seen_at": datetime.now(),
        }
        return
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
    if not DB_AVAILABLE:
        return _mem_users.get(user_id)
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        _release_conn(conn)


def get_all_active_users() -> list[dict]:
    if not DB_AVAILABLE:
        return [u for u in _mem_users.values() if u.get("is_active")]
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE is_active = TRUE")
            return [dict(r) for r in cur.fetchall()]
    finally:
        _release_conn(conn)


# ─── Jobs ─────────────────────────────────────────────────────────────────────

def insert_jobs(jobs: list[dict]) -> int:
    global _mem_job_id_counter
    if not jobs:
        return 0
    if not DB_AVAILABLE:
        existing_ids = {j["external_id"] for j in _mem_jobs}
        count = 0
        for j in jobs:
            if j.get("external_id") not in existing_ids:
                _mem_job_id_counter += 1
                _mem_jobs.append({**j, "id": _mem_job_id_counter,
                                   "is_active": True, "fetched_at": datetime.now()})
                count += 1
        return count
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            rows = [
                (
                    j.get("external_id"), j.get("source"), j.get("title"),
                    j.get("company"), j.get("location"), j.get("category"),
                    j.get("description"), j.get("salary_min"), j.get("salary_max"),
                    j.get("currency"), j.get("url"), j.get("posted_at"),
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
    per_page = per_page or config.JOBS_PER_PAGE
    offset = (page - 1) * per_page

    if not DB_AVAILABLE:
        results = [j for j in _mem_jobs if j.get("is_active")]
        if keyword:
            kw = keyword.lower()
            results = [j for j in results if kw in (j.get("title") or "").lower()
                       or kw in (j.get("description") or "").lower()]
        if location:
            loc = location.lower()
            results = [j for j in results if loc in (j.get("location") or "").lower()]
        if category:
            cat = category.lower()
            results = [j for j in results if cat in (j.get("category") or "").lower()]
        results.sort(key=lambda j: j.get("fetched_at") or datetime.min, reverse=True)
        return results[offset:offset + per_page], len(results)

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
            return [dict(r) for r in cur.fetchall()], total
    finally:
        _release_conn(conn)


def get_new_jobs_for_subscription(user_id: int, keyword: str,
                                   location: str = "") -> list[dict]:
    if not DB_AVAILABLE:
        kw = keyword.lower()
        results = [
            j for j in _mem_jobs
            if j.get("is_active")
            and (kw in (j.get("title") or "").lower() or kw in (j.get("description") or "").lower())
            and (not location or location.lower() in (j.get("location") or "").lower())
            and (user_id, j["id"]) not in _mem_sent_jobs
        ]
        return results[:10]
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
            """, (f"%{keyword}%", f"%{keyword}%", location, f"%{location}%", user_id))
            return [dict(r) for r in cur.fetchall()]
    finally:
        _release_conn(conn)


def mark_job_sent(user_id: int, job_id: int):
    if not DB_AVAILABLE:
        _mem_sent_jobs.add((user_id, job_id))
        return
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO sent_jobs (user_id, job_id)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
            """, (user_id, job_id))
            conn.commit()
    finally:
        _release_conn(conn)


# ─── Subscriptions ────────────────────────────────────────────────────────────

def add_subscription(user_id: int, keyword: str, location: str = "") -> bool:
    global _mem_sub_id_counter
    if not DB_AVAILABLE:
        user_subs = [s for s in _mem_subscriptions if s["user_id"] == user_id]
        if len(user_subs) >= config.MAX_SUBSCRIPTIONS_PER_USER:
            return False
        already = any(s["keyword"] == keyword.strip() and s.get("location") == location.strip()
                      for s in user_subs)
        if already:
            return False
        _mem_sub_id_counter += 1
        _mem_subscriptions.append({
            "id": _mem_sub_id_counter, "user_id": user_id,
            "keyword": keyword.strip(), "location": location.strip(),
            "created_at": datetime.now(),
        })
        return True
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM subscriptions WHERE user_id = %s", (user_id,))
            if cur.fetchone()[0] >= config.MAX_SUBSCRIPTIONS_PER_USER:
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
    if not DB_AVAILABLE:
        before = len(_mem_subscriptions)
        _mem_subscriptions[:] = [
            s for s in _mem_subscriptions
            if not (s["id"] == sub_id and s["user_id"] == user_id)
        ]
        return len(_mem_subscriptions) < before
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
    if not DB_AVAILABLE:
        return sorted(
            [s for s in _mem_subscriptions if s["user_id"] == user_id],
            key=lambda s: s["created_at"], reverse=True
        )
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
    if not DB_AVAILABLE:
        active_user_ids = {u["user_id"] for u in _mem_users.values() if u.get("is_active")}
        return [
            {**s, "is_active": s["user_id"] in active_user_ids}
            for s in _mem_subscriptions
        ]
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT s.*, u.is_active FROM subscriptions s JOIN users u USING(user_id)")
            return [dict(r) for r in cur.fetchall()]
    finally:
        _release_conn(conn)


# ─── User Profile ─────────────────────────────────────────────────────────────

def save_user_profile(user_id: int, city: str, specialization: str,
                      education: str, email: str):
    if not DB_AVAILABLE:
        if user_id in _mem_users:
            _mem_users[user_id].update({
                "city": city, "specialization": specialization,
                "education": education, "email": email,
            })
        return
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            # Add profile columns if they don't exist yet
            cur.execute("""
                ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS city TEXT,
                    ADD COLUMN IF NOT EXISTS specialization TEXT,
                    ADD COLUMN IF NOT EXISTS education TEXT,
                    ADD COLUMN IF NOT EXISTS email TEXT
            """)
            cur.execute("""
                UPDATE users
                SET city = %s, specialization = %s, education = %s, email = %s
                WHERE user_id = %s
            """, (city, specialization, education, email, user_id))
            conn.commit()
    finally:
        _release_conn(conn)


def get_user_profile(user_id: int) -> dict:
    if not DB_AVAILABLE:
        u = _mem_users.get(user_id, {})
        return {k: u.get(k) for k in ("city", "specialization", "education", "email")}
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                cur.execute("""
                    SELECT city, specialization, education, email
                    FROM users WHERE user_id = %s
                """, (user_id,))
                row = cur.fetchone()
                return dict(row) if row else {}
            except Exception:
                conn.rollback()
                return {}
    finally:
        _release_conn(conn)


def get_stats() -> dict:
    if not DB_AVAILABLE:
        return {
            "active_users": sum(1 for u in _mem_users.values() if u.get("is_active")),
            "total_jobs": sum(1 for j in _mem_jobs if j.get("is_active")),
            "total_subscriptions": len(_mem_subscriptions),
        }
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
