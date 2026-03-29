"""
Job fetching from multiple sources:
  - JSearch API  (via RapidAPI) — المصدر الرئيسي ✅
  - Arbeitnow    (free, no key needed)
  - RemoteOK     (free, no key needed)
  - Adzuna API   (optional)
  - Reed API     (optional)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Forsa-Bot/1.0"})
TIMEOUT = 20


# ══════════════════════════════════════════════════════════════════════════════
# JSearch (RapidAPI) — المصدر الرئيسي
# ══════════════════════════════════════════════════════════════════════════════

JSEARCH_HOST = "jsearch.p.rapidapi.com"
JSEARCH_BASE = "https://jsearch.p.rapidapi.com"


def _jsearch_headers() -> dict:
    return {
        "X-RapidAPI-Key": config.RAPIDAPI_KEY,
        "X-RapidAPI-Host": JSEARCH_HOST,
    }


def fetch_jsearch(keyword: str = "developer", location: str = "",
                  page: int = 1, num_pages: int = 1) -> list[dict]:
    """
    جلب الوظائف من JSearch API عبر RapidAPI.
    يدعم البحث بالكلمة المفتاحية والموقع الجغرافي.
    """
    if not config.RAPIDAPI_KEY:
        logger.debug("RAPIDAPI_KEY غير مضبوط، تخطي JSearch.")
        return []

    query = keyword
    if location:
        query = f"{keyword} in {location}"

    params = {
        "query": query,
        "page": str(page),
        "num_pages": str(num_pages),
        "date_posted": "all",
        "language": "ar",          # تفضيل النتائج العربية
    }

    try:
        resp = SESSION.get(
            f"{JSEARCH_BASE}/search",
            headers=_jsearch_headers(),
            params=params,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("JSearch fetch error: %s", e)
        return []

    return [_parse_jsearch_item(item) for item in data.get("data", [])]


def fetch_jsearch_details(job_id: str) -> Optional[dict]:
    """جلب تفاصيل وظيفة محددة بـ job_id."""
    if not config.RAPIDAPI_KEY:
        return None
    try:
        resp = SESSION.get(
            f"{JSEARCH_BASE}/job-details",
            headers=_jsearch_headers(),
            params={"job_id": job_id, "extended_publisher_details": "false"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data", [])
        return _parse_jsearch_item(items[0]) if items else None
    except Exception as e:
        logger.error("JSearch details error: %s", e)
        return None


def fetch_jsearch_estimated_salary(job_title: str, location: str = "Saudi Arabia") -> Optional[dict]:
    """جلب تقدير الراتب لمسمى وظيفي."""
    if not config.RAPIDAPI_KEY:
        return None
    try:
        resp = SESSION.get(
            f"{JSEARCH_BASE}/estimated-salary",
            headers=_jsearch_headers(),
            params={"job_title": job_title, "location": location, "radius": "100"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data", [])
        return items[0] if items else None
    except Exception as e:
        logger.error("JSearch salary error: %s", e)
        return None


def _parse_jsearch_item(item: dict) -> dict:
    """تحويل عنصر JSearch إلى صيغة موحدة."""
    # الراتب
    salary_min = item.get("job_min_salary")
    salary_max = item.get("job_max_salary")
    currency   = item.get("job_salary_currency") or "USD"
    period     = item.get("job_salary_period") or ""

    # تحويل الراتب السنوي إلى شهري تقريباً
    if period and "YEAR" in period.upper():
        if salary_min:
            salary_min = round(salary_min / 12)
        if salary_max:
            salary_max = round(salary_max / 12)

    # الموقع
    city    = item.get("job_city") or ""
    country = item.get("job_country") or ""
    state   = item.get("job_state") or ""
    location_parts = [p for p in [city, state, country] if p]
    location_str = ", ".join(location_parts) or "غير محدد"

    # تاريخ النشر
    posted_at = None
    ts = item.get("job_posted_at_timestamp")
    if ts:
        try:
            posted_at = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except Exception:
            pass

    # رابط التقديم
    apply_url = (
        item.get("job_apply_link")
        or item.get("job_google_link")
        or "https://www.google.com/search?q=" + requests.utils.quote(
            f"{item.get('job_title', '')} {item.get('job_employer_name', '')}"
        )
    )

    return {
        "external_id": f"jsearch_{item.get('job_id', '')}",
        "source": "jsearch",
        "title": item.get("job_title", ""),
        "company": item.get("employer_name") or item.get("job_employer_name", ""),
        "location": location_str,
        "category": item.get("job_category") or _guess_category(item.get("job_title", "")),
        "description": (item.get("job_description") or "")[:800],
        "salary_min": salary_min,
        "salary_max": salary_max,
        "currency": currency,
        "url": apply_url,
        "posted_at": posted_at,
        # حقول إضافية مفيدة للعرض
        "_employment_type": item.get("job_employment_type") or "",
        "_is_remote": item.get("job_is_remote", False),
        "_publisher": item.get("job_publisher") or "",
        "_required_experience": item.get("job_required_experience", {}).get(
            "required_experience_in_months"
        ),
    }


def _guess_category(title: str) -> str:
    """تخمين الفئة من المسمى الوظيفي."""
    title_lower = title.lower()
    mapping = {
        "تقنية المعلومات":         ["developer", "engineer", "مطور", "مهندس برمجيات", "software"],
        "الذكاء الاصطناعي":        ["ai", "machine learning", "data scientist", "nlp"],
        "الشبكات والأمن السيبراني": ["network", "security", "devops", "cloud", "سيبراني"],
        "المحاسبة والمالية":        ["accountant", "finance", "محاسب", "مالي", "auditor"],
        "الموارد البشرية":          ["hr", "human resource", "موارد بشرية", "recruitment"],
        "التسويق الرقمي":           ["marketing", "seo", "social media", "تسويق"],
        "المبيعات":                 ["sales", "مبيعات", "business development"],
        "خدمة العملاء":             ["customer", "support", "خدمة عملاء"],
        "الهندسة المدنية":          ["civil", "construction", "هندسة مدنية"],
        "الطب والتمريض":            ["doctor", "nurse", "medical", "طبيب", "ممرض"],
    }
    for category, keywords in mapping.items():
        if any(kw in title_lower for kw in keywords):
            return category
    return "عام"


# ══════════════════════════════════════════════════════════════════════════════
# بناء بطاقة الوظيفة المُحسّنة لـ JSearch
# ══════════════════════════════════════════════════════════════════════════════

def format_jsearch_card(job: dict) -> str:
    """بطاقة عرض وظيفة JSearch بتفاصيل إضافية."""
    salary = ""
    if job.get("salary_min") or job.get("salary_max"):
        lo  = f"{job['salary_min']:,.0f}" if job.get("salary_min") else "?"
        hi  = f"{job['salary_max']:,.0f}" if job.get("salary_max") else "?"
        cur = job.get("currency") or "USD"
        salary = f"\n💰 <b>الراتب:</b> {lo} – {hi} {cur}/شهر"

    emp_type = job.get("_employment_type", "")
    remote   = "🌐 عن بُعد" if job.get("_is_remote") else ""
    extras   = " · ".join(filter(None, [emp_type, remote]))

    posted = ""
    if job.get("posted_at"):
        posted = f"\n🗓 <b>النشر:</b> {job['posted_at'].strftime('%Y-%m-%d')}"

    publisher = f"\n📰 <b>المصدر:</b> {job['_publisher']}" if job.get("_publisher") else ""

    return (
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💼 <b>{job['title']}</b>\n"
        f"🏢 <b>الشركة:</b> {job.get('company') or 'غير محدد'}\n"
        f"📍 <b>الموقع:</b> {job.get('location') or 'غير محدد'}\n"
        f"📂 <b>التخصص:</b> {job.get('category') or 'عام'}"
        + (f"\n⚡ {extras}" if extras else "")
        + salary
        + posted
        + publisher
        + f"\n🔗 <a href='{job['url']}'>← التقديم على الوظيفة</a>"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Arbeitnow (مجاني)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_arbeitnow(keyword: str = "", location: str = "") -> list[dict]:
    params: dict = {}
    if keyword:
        params["search"] = keyword
    if location:
        params["location"] = location
    try:
        resp = SESSION.get(
            "https://arbeitnow.com/api/job-board-api",
            params=params, timeout=TIMEOUT,
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
            "description": item.get("description", "")[:800],
            "salary_min": None, "salary_max": None, "currency": None,
            "url": item.get("url", ""),
            "posted_at": _parse_timestamp(item.get("created_at")),
        })
    return jobs


# ══════════════════════════════════════════════════════════════════════════════
# RemoteOK (مجاني)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_remoteok(tag: str = "dev") -> list[dict]:
    try:
        resp = SESSION.get(
            f"https://remoteok.com/api?tag={tag}", timeout=TIMEOUT
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
            "description": item.get("description", "")[:800],
            "salary_min": None, "salary_max": None, "currency": "USD",
            "url": item.get("url", ""),
            "posted_at": _parse_timestamp(item.get("epoch")),
        })
    return jobs


# ══════════════════════════════════════════════════════════════════════════════
# Adzuna (اختياري)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_adzuna(keyword: str = "software", location: str = "",
                 page: int = 1, results_per_page: int = 20) -> list[dict]:
    if not config.ADZUNA_APP_ID or not config.ADZUNA_APP_KEY:
        return []
    url = f"https://api.adzuna.com/v1/api/jobs/{config.ADZUNA_COUNTRY}/search/{page}"
    params = {
        "app_id": config.ADZUNA_APP_ID, "app_key": config.ADZUNA_APP_KEY,
        "what": keyword, "where": location,
        "results_per_page": results_per_page, "content-type": "application/json",
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
            "description": item.get("description", "")[:800],
            "salary_min": item.get("salary_min"),
            "salary_max": item.get("salary_max"),
            "currency": "GBP",
            "url": item.get("redirect_url", ""),
            "posted_at": _parse_date(item.get("created")),
        })
    return jobs


# ══════════════════════════════════════════════════════════════════════════════
# Reed (اختياري)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_reed(keyword: str = "developer", location: str = "",
               results_to_take: int = 20) -> list[dict]:
    if not config.REED_API_KEY:
        return []
    try:
        resp = SESSION.get(
            "https://www.reed.co.uk/api/1.0/search",
            params={"keywords": keyword, "locationName": location,
                    "resultsToTake": results_to_take},
            auth=(config.REED_API_KEY, ""), timeout=TIMEOUT,
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
            "description": item.get("jobDescription", "")[:800],
            "salary_min": item.get("minimumSalary"),
            "salary_max": item.get("maximumSalary"),
            "currency": "GBP",
            "url": item.get("jobUrl", ""),
            "posted_at": _parse_date(item.get("date")),
        })
    return jobs


# ══════════════════════════════════════════════════════════════════════════════
# الدالة الرئيسية للجلب المُجمَّع
# ══════════════════════════════════════════════════════════════════════════════

def fetch_all(keyword: str = "developer", location: str = "") -> list[dict]:
    """
    يجلب من جميع المصادر المتاحة ويعيد قائمة موحدة.
    JSearch هو المصدر الأولوي إذا كان RAPIDAPI_KEY مضبوطاً.
    """
    all_jobs: list[dict] = []

    # JSearch أولاً (الأدق والأشمل)
    jsearch = fetch_jsearch(keyword=keyword, location=location, num_pages=2)
    all_jobs += jsearch

    # مصادر مجانية إضافية
    all_jobs += fetch_arbeitnow(keyword=keyword, location=location)
    all_jobs += fetch_remoteok(tag=keyword)

    # مصادر اختيارية
    all_jobs += fetch_adzuna(keyword=keyword, location=location)
    all_jobs += fetch_reed(keyword=keyword, location=location)

    logger.info(
        "Fetched %d jobs (jsearch=%d) for '%s' in '%s'",
        len(all_jobs), len(jsearch), keyword, location or "any"
    )
    return all_jobs


def search_live(keyword: str = "", location: str = "",
                page: int = 1) -> list[dict]:
    """
    بحث مباشر (live) عبر JSearch يُستخدم من البوت فوراً.
    يعيد قائمة جاهزة للعرض.
    """
    return fetch_jsearch(keyword=keyword, location=location, page=page, num_pages=1)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

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
