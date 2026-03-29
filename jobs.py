"""
Job fetching from multiple sources:
  - Adzuna API  (https://developer.adzuna.com)
  - Reed API    (https://www.reed.co.uk/developers/jobseeker)
  - RemoteOK    (free, no key needed)
  - Arbeitnow   (free, no key needed)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Forsa-Bot/1.0"})
TIMEOUT = 15


# ─── Adzuna ───────────────────────────────────────────────────────────────────

def fetch_adzuna(keyword: str = "software", location: str = "",
                 page: int = 1, results_per_page: int = 20) -> list[dict]:
    if not config.ADZUNA_APP_ID or not config.ADZUNA_APP_KEY:
        logger.debug("Adzuna credentials not set, skipping.")
        return []

    country = config.ADZUNA_COUNTRY
    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
    params = {
        "app_id": config.ADZUNA_APP_ID,
        "app_key": config.ADZUNA_APP_KEY,
        "what": keyword,
        "where": location,
        "results_per_page": results_per_page,
        "content-type": "application/json",
    }

    try:
        resp = SESSION.get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("Adzuna fetch error: %s", e)
        return []

    jobs = []
    for item in data.get("results", []):
        jobs.append({
            "external_id": f"adzuna_{item['id']}",
            "source": "adzuna",
            "title": item.get("title", ""),
            "company": item.get("company", {}).get("display_name", ""),
            "location": item.get("location", {}).get("display_name", ""),
            "category": item.get("category", {}).get("label", ""),
            "description": item.get("description", ""),
            "salary_min": item.get("salary_min"),
            "salary_max": item.get("salary_max"),
            "currency": "GBP",
            "url": item.get("redirect_url", ""),
            "posted_at": _parse_date(item.get("created")),
        })
    return jobs


# ─── Reed ─────────────────────────────────────────────────────────────────────

def fetch_reed(keyword: str = "developer", location: str = "",
               results_to_take: int = 20) -> list[dict]:
    if not config.REED_API_KEY:
        logger.debug("Reed API key not set, skipping.")
        return []

    try:
        resp = SESSION.get(
            "https://www.reed.co.uk/api/1.0/search",
            params={"keywords": keyword, "locationName": location,
                    "resultsToTake": results_to_take},
            auth=(config.REED_API_KEY, ""),
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("Reed fetch error: %s", e)
        return []

    jobs = []
    for item in data.get("results", []):
        jobs.append({
            "external_id": f"reed_{item['jobId']}",
            "source": "reed",
            "title": item.get("jobTitle", ""),
            "company": item.get("employerName", ""),
            "location": item.get("locationName", ""),
            "category": "",
            "description": item.get("jobDescription", ""),
            "salary_min": item.get("minimumSalary"),
            "salary_max": item.get("maximumSalary"),
            "currency": "GBP",
            "url": item.get("jobUrl", ""),
            "posted_at": _parse_date(item.get("date")),
        })
    return jobs


# ─── RemoteOK (free) ──────────────────────────────────────────────────────────

def fetch_remoteok(tag: str = "dev") -> list[dict]:
    try:
        resp = SESSION.get(
            f"https://remoteok.com/api?tag={tag}",
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("RemoteOK fetch error: %s", e)
        return []

    jobs = []
    for item in data:
        if not isinstance(item, dict) or "id" not in item:
            continue
        jobs.append({
            "external_id": f"remoteok_{item['id']}",
            "source": "remoteok",
            "title": item.get("position", ""),
            "company": item.get("company", ""),
            "location": "Remote",
            "category": ", ".join(item.get("tags", [])),
            "description": item.get("description", ""),
            "salary_min": None,
            "salary_max": None,
            "currency": "USD",
            "url": item.get("url", ""),
            "posted_at": _parse_timestamp(item.get("epoch")),
        })
    return jobs


# ─── Arbeitnow (free, includes remote + visa sponsorship) ────────────────────

def fetch_arbeitnow(keyword: str = "", location: str = "") -> list[dict]:
    params: dict = {}
    if keyword:
        params["search"] = keyword
    if location:
        params["location"] = location

    try:
        resp = SESSION.get(
            "https://arbeitnow.com/api/job-board-api",
            params=params,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("Arbeitnow fetch error: %s", e)
        return []

    jobs = []
    for item in data.get("data", []):
        jobs.append({
            "external_id": f"arbeitnow_{item['slug']}",
            "source": "arbeitnow",
            "title": item.get("title", ""),
            "company": item.get("company_name", ""),
            "location": item.get("location", ""),
            "category": ", ".join(item.get("tags", [])),
            "description": item.get("description", ""),
            "salary_min": None,
            "salary_max": None,
            "currency": None,
            "url": item.get("url", ""),
            "posted_at": _parse_timestamp(item.get("created_at")),
        })
    return jobs


# ─── Aggregate fetch (used by scheduler) ─────────────────────────────────────

def fetch_all(keyword: str = "developer") -> list[dict]:
    """Fetch from all available sources and return merged list."""
    all_jobs: list[dict] = []

    all_jobs += fetch_adzuna(keyword=keyword)
    all_jobs += fetch_reed(keyword=keyword)
    all_jobs += fetch_remoteok(tag=keyword)
    all_jobs += fetch_arbeitnow(keyword=keyword)

    logger.info("Fetched %d jobs for keyword '%s'", len(all_jobs), keyword)
    return all_jobs


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _parse_timestamp(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except Exception:
        return None
