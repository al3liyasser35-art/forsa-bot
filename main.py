"""
بوت فرصة 🎯 — بوت تيليغرام احترافي للبحث عن الوظائف في السوق السعودي
"""

import logging
import html
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import database as db
import jobs as job_fetcher

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# البيانات الثابتة
# ══════════════════════════════════════════════════════════════════════════════

SAUDI_CITIES = [
    "الرياض", "جدة", "مكة المكرمة", "المدينة المنورة", "الدمام",
    "الخبر", "الظهران", "الأحساء", "القطيف", "تبوك",
    "أبها", "خميس مشيط", "القصيم", "بريدة", "عنيزة",
    "حائل", "جازان", "نجران", "الباحة", "الطائف",
    "ينبع", "الجبيل", "رابغ", "الخرج", "القنفذة",
    "عرعر", "سكاكا", "الوجه", "أملج", "بيشة",
]

SPECIALIZATIONS = [
    "تقنية المعلومات", "هندسة البرمجيات", "الذكاء الاصطناعي",
    "الشبكات والأمن السيبراني", "قواعد البيانات", "تصميم الجرافيك",
    "المحاسبة والمالية", "الموارد البشرية", "التسويق الرقمي",
    "المبيعات", "خدمة العملاء", "الإدارة والأعمال",
    "الهندسة المدنية", "الهندسة الكهربائية", "الهندسة الميكانيكية",
    "الطب والتمريض", "الصيدلة", "التعليم والتدريب",
    "القانون", "الترجمة واللغات", "الإعلام والصحافة",
    "اللوجستيات والمشتريات", "العقارات", "السياحة والفندقة",
    "أخرى",
]

EDUCATION_LEVELS = [
    "ثانوية عامة أو أقل",
    "دبلوم",
    "بكالوريوس",
    "ماجستير",
    "دكتوراه",
]

# وظائف وهمية للاختبار
DUMMY_JOBS = [
    {
        "id": 1, "title": "مطور تطبيقات Flutter",
        "company": "شركة تقنية الرياض", "location": "الرياض",
        "category": "هندسة البرمجيات",
        "salary_min": 8000, "salary_max": 14000, "currency": "SAR",
        "url": "https://example.com/job/1",
        "posted_at": datetime(2026, 3, 27), "fetched_at": datetime(2026, 3, 28),
        "is_active": True,
        "description": "مطلوب مطور Flutter ذو خبرة لا تقل عن سنتين.",
    },
    {
        "id": 2, "title": "محاسب قانوني CPA",
        "company": "مجموعة الخليج للاستشارات", "location": "جدة",
        "category": "المحاسبة والمالية",
        "salary_min": 10000, "salary_max": 18000, "currency": "SAR",
        "url": "https://example.com/job/2",
        "posted_at": datetime(2026, 3, 26), "fetched_at": datetime(2026, 3, 28),
        "is_active": True,
        "description": "نبحث عن محاسب قانوني للانضمام لفريقنا المالي.",
    },
    {
        "id": 3, "title": "مدير تسويق رقمي",
        "company": "وكالة إبداع للتسويق", "location": "الدمام",
        "category": "التسويق الرقمي",
        "salary_min": 12000, "salary_max": 20000, "currency": "SAR",
        "url": "https://example.com/job/3",
        "posted_at": datetime(2026, 3, 25), "fetched_at": datetime(2026, 3, 28),
        "is_active": True,
        "description": "فرصة لمدير تسويق رقمي بخبرة 3 سنوات فأكثر.",
    },
    {
        "id": 4, "title": "أخصائي موارد بشرية",
        "company": "شركة الأفق للتوظيف", "location": "الرياض",
        "category": "الموارد البشرية",
        "salary_min": 7000, "salary_max": 11000, "currency": "SAR",
        "url": "https://example.com/job/4",
        "posted_at": datetime(2026, 3, 24), "fetched_at": datetime(2026, 3, 28),
        "is_active": True,
        "description": "مطلوب أخصائي موارد بشرية لشركة متنامية.",
    },
    {
        "id": 5, "title": "مهندس شبكات وأمن سيبراني",
        "company": "بنك الجزيرة", "location": "الرياض",
        "category": "الشبكات والأمن السيبراني",
        "salary_min": 15000, "salary_max": 25000, "currency": "SAR",
        "url": "https://example.com/job/5",
        "posted_at": datetime(2026, 3, 23), "fetched_at": datetime(2026, 3, 28),
        "is_active": True,
        "description": "مطلوب مهندس شبكات خبرة CCNA/CCNP للعمل في القطاع البنكي.",
    },
]

# ══════════════════════════════════════════════════════════════════════════════
# حالات المحادثة
# ══════════════════════════════════════════════════════════════════════════════
(
    PROFILE_CITY,
    PROFILE_SPEC,
    PROFILE_EDU,
    PROFILE_EMAIL,
    SEARCH_KEYWORD,
    SEARCH_LOCATION,
    SUB_KEYWORD,
    SUB_LOCATION,
) = range(8)

# ══════════════════════════════════════════════════════════════════════════════
# لوحات المفاتيح
# ══════════════════════════════════════════════════════════════════════════════

def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗂 آخر الوظائف",    callback_data="menu:latest"),
            InlineKeyboardButton("🔍 بحث وظيفة",      callback_data="menu:search"),
        ],
        [
            InlineKeyboardButton("📋 ملفي الوظيفي",   callback_data="menu:profile"),
            InlineKeyboardButton("⚙️ إعداداتي",        callback_data="menu:settings"),
        ],
        [
            InlineKeyboardButton("🔔 اشتراكاتي",       callback_data="menu:subs"),
            InlineKeyboardButton("➕ اشتراك جديد",     callback_data="menu:new_sub"),
        ],
        [
            InlineKeyboardButton("📊 الإحصائيات",      callback_data="menu:stats"),
            InlineKeyboardButton("❓ المساعدة",         callback_data="menu:help"),
        ],
    ])


def _cities_keyboard(back_cb: str = "menu:profile") -> InlineKeyboardMarkup:
    rows = []
    cities = SAUDI_CITIES
    for i in range(0, len(cities), 3):
        row = [InlineKeyboardButton(c, callback_data=f"city:{c}") for c in cities[i:i+3]]
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data=back_cb)])
    return InlineKeyboardMarkup(rows)


def _spec_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(SPECIALIZATIONS), 2):
        row = [InlineKeyboardButton(s, callback_data=f"spec:{s}") for s in SPECIALIZATIONS[i:i+2]]
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="menu:profile")])
    return InlineKeyboardMarkup(rows)


def _edu_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(e, callback_data=f"edu:{e}")] for e in EDUCATION_LEVELS]
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="menu:profile")])
    return InlineKeyboardMarkup(rows)


# ══════════════════════════════════════════════════════════════════════════════
# مساعدات
# ══════════════════════════════════════════════════════════════════════════════

def _job_card(job: dict) -> str:
    salary = ""
    if job.get("salary_min") or job.get("salary_max"):
        lo = f"{job['salary_min']:,.0f}" if job.get("salary_min") else "?"
        hi = f"{job['salary_max']:,.0f}" if job.get("salary_max") else "?"
        cur = job.get("currency") or "SAR"
        salary = f"\n💰 <b>الراتب:</b> {lo} – {hi} {cur}"

    posted = ""
    if job.get("posted_at"):
        d = job["posted_at"]
        posted = f"\n🗓 <b>تاريخ النشر:</b> {d.strftime('%Y-%m-%d')}"

    return (
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💼 <b>{html.escape(job['title'])}</b>\n"
        f"🏢 <b>الشركة:</b> {html.escape(job.get('company') or 'غير محدد')}\n"
        f"📍 <b>الموقع:</b> {html.escape(job.get('location') or 'غير محدد')}\n"
        f"📂 <b>التخصص:</b> {html.escape(job.get('category') or 'عام')}"
        f"{salary}"
        f"{posted}\n"
        f"🔗 <a href='{job['url']}'>← عرض الوظيفة والتقديم</a>"
    )


def _pagination_keyboard(page: int, total: int, per_page: int,
                          prefix: str) -> InlineKeyboardMarkup:
    row = []
    if page > 1:
        row.append(InlineKeyboardButton("◀️ السابق", callback_data=f"{prefix}:{page-1}"))
    row.append(InlineKeyboardButton(f"📄 {page}", callback_data="noop"))
    if page * per_page < total:
        row.append(InlineKeyboardButton("▶️ التالي", callback_data=f"{prefix}:{page+1}"))
    back = [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="menu:home")]
    return InlineKeyboardMarkup([row, back])


# ══════════════════════════════════════════════════════════════════════════════
# /start — رسالة الترحيب
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.username or "", user.full_name)

    welcome = (
        f"🌟 <b>أهلاً وسهلاً، {html.escape(user.first_name)}!</b>\n\n"
        "╔══════════════════════╗\n"
        "║   🎯  بوت  فُرصة   ║\n"
        "╚══════════════════════╝\n\n"
        "🚀 <b>مساعدك الذكي للتوظيف في السوق السعودي</b>\n\n"
        "📌 <b>ما الذي يقدمه البوت؟</b>\n"
        "┣ 🗂 عرض أحدث الوظائف المتاحة\n"
        "┣ 🔍 البحث الدقيق بالتخصص والمدينة\n"
        "┣ 🔔 تنبيهات فورية بوظائف تناسبك\n"
        "┣ 📋 ملف وظيفي كامل يُبرز مؤهلاتك\n"
        "┗ ⚙️ إعدادات مخصصة لكل مستخدم\n\n"
        "👇 <b>اختر من القائمة للبدء:</b>"
    )

    target = update.message or update.callback_query.message
    if update.callback_query:
        await update.callback_query.edit_message_text(
            welcome, reply_markup=_main_menu_keyboard(), parse_mode="HTML"
        )
    else:
        await target.reply_text(
            welcome, reply_markup=_main_menu_keyboard(), parse_mode="HTML"
        )


# ══════════════════════════════════════════════════════════════════════════════
# آخر الوظائف
# ══════════════════════════════════════════════════════════════════════════════

async def show_latest_jobs(update: Update, ctx: ContextTypes.DEFAULT_TYPE, page: int = 1):
    per_page = 3
    offset = (page - 1) * per_page
    total = len(DUMMY_JOBS)
    jobs_page = DUMMY_JOBS[offset:offset + per_page]

    header = (
        f"🗂 <b>آخر الوظائف المتاحة</b>\n"
        f"📊 إجمالي: <b>{total}</b> وظيفة | صفحة {page}/{-(-total // per_page)}\n\n"
    )
    cards = "\n\n".join(_job_card(j) for j in jobs_page)

    keyboard = _pagination_keyboard(page, total, per_page, "latest_page")

    target = update.callback_query.message
    try:
        await target.edit_text(
            header + cards,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except Exception:
        await target.reply_text(
            header + cards,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# الملف الوظيفي — محادثة متعددة الخطوات
# ══════════════════════════════════════════════════════════════════════════════

async def start_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    profile = db.get_user_profile(update.effective_user.id)
    current = ""
    if profile and any(profile.get(k) for k in ("city", "specialization", "education", "email")):
        current = (
            "\n\n📌 <b>ملفك الحالي:</b>\n"
            f"🏙 المدينة: {profile.get('city') or '—'}\n"
            f"💼 التخصص: {profile.get('specialization') or '—'}\n"
            f"🎓 الشهادة: {profile.get('education') or '—'}\n"
            f"📧 الإيميل: {profile.get('email') or '—'}"
        )

    await query.edit_message_text(
        f"📋 <b>إعداد الملف الوظيفي</b>{current}\n\n"
        "🏙 <b>الخطوة 1/4:</b> اختر <b>مدينتك</b>:",
        parse_mode="HTML",
        reply_markup=_cities_keyboard(),
    )
    return PROFILE_CITY


async def profile_got_city(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    city = query.data.split(":", 1)[1]
    ctx.user_data["profile_city"] = city

    await query.edit_message_text(
        f"✅ المدينة: <b>{city}</b>\n\n"
        "💼 <b>الخطوة 2/4:</b> اختر <b>تخصصك الوظيفي</b>:",
        parse_mode="HTML",
        reply_markup=_spec_keyboard(),
    )
    return PROFILE_SPEC


async def profile_got_spec(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    spec = query.data.split(":", 1)[1]
    ctx.user_data["profile_spec"] = spec

    await query.edit_message_text(
        f"✅ التخصص: <b>{spec}</b>\n\n"
        "🎓 <b>الخطوة 3/4:</b> اختر <b>مستوى شهادتك</b>:",
        parse_mode="HTML",
        reply_markup=_edu_keyboard(),
    )
    return PROFILE_EDU


async def profile_got_edu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    edu = query.data.split(":", 1)[1]
    ctx.user_data["profile_edu"] = edu

    await query.edit_message_text(
        f"✅ الشهادة: <b>{edu}</b>\n\n"
        "📧 <b>الخطوة 4/4:</b> أرسل <b>بريدك الإلكتروني</b>:",
        parse_mode="HTML",
    )
    return PROFILE_EMAIL


async def profile_got_email(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    if "@" not in email or "." not in email:
        await update.message.reply_text(
            "⚠️ البريد الإلكتروني غير صحيح. أعد الإدخال:"
        )
        return PROFILE_EMAIL

    user_id = update.effective_user.id
    db.save_user_profile(
        user_id=user_id,
        city=ctx.user_data.get("profile_city", ""),
        specialization=ctx.user_data.get("profile_spec", ""),
        education=ctx.user_data.get("profile_edu", ""),
        email=email,
    )

    await update.message.reply_text(
        "🎉 <b>تم حفظ ملفك الوظيفي بنجاح!</b>\n\n"
        f"🏙 المدينة: <b>{ctx.user_data.get('profile_city')}</b>\n"
        f"💼 التخصص: <b>{ctx.user_data.get('profile_spec')}</b>\n"
        f"🎓 الشهادة: <b>{ctx.user_data.get('profile_edu')}</b>\n"
        f"📧 الإيميل: <b>{html.escape(email)}</b>\n\n"
        "سنستخدم هذه البيانات لإرسال وظائف تناسبك تماماً! 🚀",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="menu:home")
        ]]),
    )
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════════════════════
# إعداداتي
# ══════════════════════════════════════════════════════════════════════════════

async def show_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    profile = db.get_user_profile(user.id)
    subs = db.get_user_subscriptions(user.id)

    city = profile.get("city") or "—" if profile else "—"
    spec = profile.get("specialization") or "—" if profile else "—"
    edu = profile.get("education") or "—" if profile else "—"
    email = profile.get("email") or "—" if profile else "—"

    text = (
        "⚙️ <b>إعداداتي</b>\n\n"
        "👤 <b>معلوماتي:</b>\n"
        f"┣ 🆔 المعرّف: <code>{user.id}</code>\n"
        f"┣ 👤 الاسم: <b>{html.escape(user.full_name)}</b>\n"
        f"┗ 🔗 يوزرنيم: @{html.escape(user.username or 'لا يوجد')}\n\n"
        "📋 <b>ملفي الوظيفي:</b>\n"
        f"┣ 🏙 المدينة: <b>{html.escape(city)}</b>\n"
        f"┣ 💼 التخصص: <b>{html.escape(spec)}</b>\n"
        f"┣ 🎓 الشهادة: <b>{html.escape(edu)}</b>\n"
        f"┗ 📧 الإيميل: <b>{html.escape(email)}</b>\n\n"
        f"🔔 <b>الاشتراكات:</b> {len(subs)} اشتراك نشط"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ تعديل الملف الوظيفي", callback_data="menu:profile")],
        [InlineKeyboardButton("🔔 إدارة الاشتراكات",    callback_data="menu:subs")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية",    callback_data="menu:home")],
    ])

    await update.callback_query.edit_message_text(
        text, parse_mode="HTML", reply_markup=keyboard
    )


# ══════════════════════════════════════════════════════════════════════════════
# البحث
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    await target.reply_text(
        "🔍 <b>البحث عن وظيفة</b>\n\n"
        "اكتب كلمة البحث (مثال: مطور، محاسب، مهندس):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 رجوع", callback_data="menu:home")
        ]]),
    )
    return SEARCH_KEYWORD


async def search_got_keyword(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["search_keyword"] = update.message.text.strip()
    await update.message.reply_text(
        "📍 أدخل المدينة أو اضغط /skip للبحث في كل المدن:"
    )
    return SEARCH_LOCATION


async def search_got_location(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["search_location"] = update.message.text.strip()
    return await _do_search(update, ctx, page=1)


async def search_skip_location(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["search_location"] = ""
    return await _do_search(update, ctx, page=1)


async def _do_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE, page: int):
    keyword  = ctx.user_data.get("search_keyword", "")
    location = ctx.user_data.get("search_location", "")

    # ابحث في الوظائف الوهمية أولاً ثم قاعدة البيانات
    dummy_results = [
        j for j in DUMMY_JOBS
        if (not keyword or keyword in j["title"] or keyword in j.get("category", ""))
        and (not location or location in j.get("location", ""))
    ]
    db_results, db_total = db.search_jobs(keyword=keyword, location=location, page=page)
    all_results = dummy_results + db_results
    total = len(dummy_results) + db_total

    if not all_results:
        await update.message.reply_text(
            "😕 لم أجد وظائف مطابقة.\nجرّب كلمة مختلفة أو اضغط /skip لتخطي الموقع.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="menu:home")
            ]]),
        )
        return ConversationHandler.END

    loc_text = f" في <b>{html.escape(location)}</b>" if location else ""
    header = (
        f"✅ وجدت <b>{total}</b> وظيفة لـ «{html.escape(keyword)}»{loc_text}\n\n"
    )
    cards = "\n\n".join(_job_card(j) for j in all_results[:config.JOBS_PER_PAGE])
    keyboard = _pagination_keyboard(page, total, config.JOBS_PER_PAGE,
                                    f"search:{keyword}:{location}")
    await update.message.reply_text(
        header + cards,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════════════════════
# الاشتراكات
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_subscribe(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    await target.reply_text(
        "🔔 <b>اشتراك جديد</b>\n\n"
        "أدخل الكلمة المفتاحية للوظائف التي تريد متابعتها\n"
        "مثال: مطور، محاسب، مدير:",
        parse_mode="HTML",
    )
    return SUB_KEYWORD


async def sub_got_keyword(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["sub_keyword"] = update.message.text.strip()
    await update.message.reply_text(
        "📍 أدخل المدينة أو اضغط /skip لمتابعة كل المدن:"
    )
    return SUB_LOCATION


async def sub_got_location(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["sub_location"] = update.message.text.strip()
    return await _save_subscription(update, ctx)


async def sub_skip_location(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["sub_location"] = ""
    return await _save_subscription(update, ctx)


async def _save_subscription(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyword  = ctx.user_data.get("sub_keyword", "")
    location = ctx.user_data.get("sub_location", "")

    ok = db.add_subscription(user_id, keyword, location)
    loc_text = f" في <b>{html.escape(location)}</b>" if location else ""
    msg = (
        f"✅ تم الاشتراك في تنبيهات <b>{html.escape(keyword)}</b>{loc_text}!\n"
        "سأُرسل لك الوظائف الجديدة فور توفرها 🚀"
        if ok else
        f"⚠️ وصلت للحد الأقصى ({config.MAX_SUBSCRIPTIONS_PER_USER} اشتراكات) "
        "أو هذا الاشتراك موجود مسبقاً."
    )
    await update.message.reply_text(
        msg, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="menu:home")
        ]]),
    )
    return ConversationHandler.END


async def show_subs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    subs = db.get_user_subscriptions(user_id)
    target = update.callback_query.message

    if not subs:
        await target.edit_text(
            "📭 <b>ليس لديك اشتراكات حالياً.</b>\n"
            "استخدم زر «اشتراك جديد» لإضافة تنبيه وظيفي.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ اشتراك جديد",    callback_data="menu:new_sub")],
                [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="menu:home")],
            ]),
        )
        return

    lines = ["🔔 <b>اشتراكاتي الحالية:</b>\n"]
    buttons = []
    for s in subs:
        loc = f" ← {s['location']}" if s.get("location") else ""
        lines.append(f"• {html.escape(s['keyword'])}{html.escape(loc)}")
        buttons.append([InlineKeyboardButton(
            f"🗑 حذف: {s['keyword']}{loc}",
            callback_data=f"delsub:{s['id']}",
        )])

    buttons.append([InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="menu:home")])
    await target.edit_text(
        "\n".join(lines), parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ══════════════════════════════════════════════════════════════════════════════
# الإحصائيات والمساعدة
# ══════════════════════════════════════════════════════════════════════════════

async def show_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stats = db.get_stats()
    await update.callback_query.edit_message_text(
        "📊 <b>إحصائيات بوت فرصة</b>\n\n"
        f"👥 المستخدمون النشطون : <b>{stats['active_users']}</b>\n"
        f"💼 الوظائف المتاحة    : <b>{stats['total_jobs'] + len(DUMMY_JOBS)}</b>\n"
        f"🔔 الاشتراكات الفعالة : <b>{stats['total_subscriptions']}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="menu:home")
        ]]),
    )


async def show_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text(
        "❓ <b>المساعدة</b>\n\n"
        "🗂 <b>آخر الوظائف</b> — أحدث الوظائف المنشورة\n"
        "🔍 <b>بحث وظيفة</b> — ابحث بكلمة مفتاحية ومدينة\n"
        "📋 <b>ملفي الوظيفي</b> — سجّل مدينتك وتخصصك وشهادتك\n"
        "⚙️ <b>إعداداتي</b> — اعرض كل بياناتك المحفوظة\n"
        "🔔 <b>اشتراكاتي</b> — تنبيهات وظيفية تصلك تلقائياً\n\n"
        "📞 <b>للتواصل:</b> @admin",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="menu:home")
        ]]),
    )


# ══════════════════════════════════════════════════════════════════════════════
# موجّه الـ Callback
# ══════════════════════════════════════════════════════════════════════════════

async def callback_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data in ("menu:home", "menu:start"):
        await cmd_start(update, ctx)
    elif data == "menu:latest":
        await show_latest_jobs(update, ctx, page=1)
    elif data == "menu:settings":
        await show_settings(update, ctx)
    elif data == "menu:subs":
        await show_subs(update, ctx)
    elif data == "menu:stats":
        await show_stats(update, ctx)
    elif data == "menu:help":
        await show_help(update, ctx)
    elif data == "noop":
        pass
    elif data.startswith("delsub:"):
        sub_id = int(data.split(":")[1])
        ok = db.remove_subscription(sub_id, update.effective_user.id)
        await query.edit_message_text(
            "✅ تم حذف الاشتراك." if ok else "❌ لم يُعثر على الاشتراك.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="menu:home")
            ]]),
        )
    elif data.startswith("latest_page:"):
        page = int(data.split(":")[1])
        await show_latest_jobs(update, ctx, page=page)
    elif data.startswith("search:"):
        parts = data.split(":", 3)
        keyword, location, page_str = parts[1], parts[2], parts[3]
        ctx.user_data["search_keyword"] = keyword
        ctx.user_data["search_location"] = location
        dummy_results = [
            j for j in DUMMY_JOBS
            if (not keyword or keyword in j["title"] or keyword in j.get("category", ""))
            and (not location or location in j.get("location", ""))
        ]
        db_results, db_total = db.search_jobs(keyword=keyword, location=location,
                                               page=int(page_str))
        all_results = dummy_results + db_results
        total = len(dummy_results) + db_total
        if not all_results:
            await query.edit_message_text("لا مزيد من النتائج.")
            return
        header = f"✅ <b>{total}</b> وظيفة — صفحة {page_str}:\n\n"
        cards = "\n\n".join(_job_card(j) for j in all_results[:config.JOBS_PER_PAGE])
        keyboard = _pagination_keyboard(int(page_str), total, config.JOBS_PER_PAGE,
                                        f"search:{keyword}:{location}")
        await query.edit_message_text(
            header + cards, parse_mode="HTML",
            reply_markup=keyboard, disable_web_page_preview=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# الجدولة
# ══════════════════════════════════════════════════════════════════════════════

async def notify_subscribers(app: Application):
    logger.info("Running scheduled job fetch...")
    all_subs = db.get_all_subscriptions()
    keywords = list({s["keyword"] for s in all_subs if s.get("is_active")})

    for kw in keywords:
        new_jobs = job_fetcher.fetch_all(keyword=kw)
        if new_jobs:
            db.insert_jobs(new_jobs)

    for sub in all_subs:
        if not sub.get("is_active"):
            continue
        user_id = sub["user_id"]
        new_for_user = db.get_new_jobs_for_subscription(
            user_id, sub["keyword"], sub.get("location", "")
        )
        for job in new_for_user:
            try:
                await app.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"🔔 <b>وظيفة جديدة تناسب اشتراكك «{html.escape(sub['keyword'])}»</b>\n\n"
                        + _job_card(job)
                    ),
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                db.mark_job_sent(user_id, job["id"])
            except Exception as e:
                logger.warning("Failed to notify user %s: %s", user_id, e)


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    db.init_db()
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # محادثة الملف الوظيفي
    profile_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_profile, pattern="^menu:profile$")],
        states={
            PROFILE_CITY: [CallbackQueryHandler(profile_got_city, pattern="^city:")],
            PROFILE_SPEC: [CallbackQueryHandler(profile_got_spec, pattern="^spec:")],
            PROFILE_EDU:  [CallbackQueryHandler(profile_got_edu,  pattern="^edu:")],
            PROFILE_EMAIL:[MessageHandler(filters.TEXT & ~filters.COMMAND, profile_got_email)],
        },
        fallbacks=[
            CommandHandler("start", cmd_start),
            CallbackQueryHandler(cmd_start, pattern="^menu:home$"),
        ],
        per_message=False,
    )

    # محادثة البحث
    search_conv = ConversationHandler(
        entry_points=[
            CommandHandler("search", cmd_search),
            CallbackQueryHandler(cmd_search, pattern="^menu:search$"),
        ],
        states={
            SEARCH_KEYWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_got_keyword)],
            SEARCH_LOCATION: [
                CommandHandler("skip", search_skip_location),
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_got_location),
            ],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
        per_message=False,
    )

    # محادثة الاشتراك
    sub_conv = ConversationHandler(
        entry_points=[
            CommandHandler("subscribe", cmd_subscribe),
            CallbackQueryHandler(cmd_subscribe, pattern="^menu:new_sub$"),
        ],
        states={
            SUB_KEYWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, sub_got_keyword)],
            SUB_LOCATION: [
                CommandHandler("skip", sub_skip_location),
                MessageHandler(filters.TEXT & ~filters.COMMAND, sub_got_location),
            ],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(profile_conv)
    app.add_handler(search_conv)
    app.add_handler(sub_conv)
    app.add_handler(CallbackQueryHandler(callback_router))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        notify_subscribers, "interval",
        minutes=config.FETCH_INTERVAL_MINUTES,
        args=[app], next_run_time=datetime.now(),
    )
    scheduler.start()

    logger.info("🚀 بوت فرصة يعمل الآن...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
