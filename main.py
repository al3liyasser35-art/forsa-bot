"""
بوت فرصة - بوت تيليغرام للبحث عن الوظائف
"""

import logging
import html
from datetime import datetime

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes,
    filters
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

# ─── Conversation states ───────────────────────────────────────────────────────
SEARCH_KEYWORD, SEARCH_LOCATION = range(2)
SUB_KEYWORD, SUB_LOCATION = range(2, 4)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _job_card(job: dict) -> str:
    salary = ""
    if job.get("salary_min") or job.get("salary_max"):
        lo = f"{job['salary_min']:,.0f}" if job.get("salary_min") else "?"
        hi = f"{job['salary_max']:,.0f}" if job.get("salary_max") else "?"
        cur = job.get("currency") or ""
        salary = f"\n💰 <b>الراتب:</b> {lo} – {hi} {cur}"

    posted = ""
    if job.get("posted_at"):
        posted = f"\n🗓 <b>النشر:</b> {job['posted_at'].strftime('%Y-%m-%d')}"

    return (
        f"💼 <b>{html.escape(job['title'])}</b>\n"
        f"🏢 {html.escape(job.get('company') or 'غير محدد')}\n"
        f"📍 {html.escape(job.get('location') or 'غير محدد')}"
        f"{salary}"
        f"{posted}\n"
        f"🔗 <a href='{job['url']}'>عرض الوظيفة</a>"
    )


def _pagination_keyboard(page: int, total: int,
                          per_page: int, prefix: str) -> InlineKeyboardMarkup:
    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton("◀️ السابق", callback_data=f"{prefix}:{page-1}"))
    if page * per_page < total:
        buttons.append(InlineKeyboardButton("▶️ التالي", callback_data=f"{prefix}:{page+1}"))
    return InlineKeyboardMarkup([buttons]) if buttons else InlineKeyboardMarkup([[]])


# ─── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.username or "", user.full_name)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 بحث عن وظيفة", callback_data="menu:search"),
         InlineKeyboardButton("📬 اشتراكاتي", callback_data="menu:subs")],
        [InlineKeyboardButton("➕ اشتراك جديد", callback_data="menu:new_sub"),
         InlineKeyboardButton("📊 الإحصائيات", callback_data="menu:stats")],
        [InlineKeyboardButton("❓ المساعدة", callback_data="menu:help")],
    ])

    await update.message.reply_text(
        f"👋 أهلاً <b>{html.escape(user.first_name)}</b>!\n\n"
        "🎯 أنا <b>بوت فرصة</b> — مساعدك للبحث عن الوظائف.\n"
        "اختر ما تريد من القائمة أدناه:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


# ─── /help ─────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 <b>الأوامر المتاحة:</b>\n\n"
        "/start — القائمة الرئيسية\n"
        "/search — البحث عن وظيفة\n"
        "/subscribe — إنشاء اشتراك لتنبيهات وظائف\n"
        "/mysubs — عرض اشتراكاتي\n"
        "/stats — إحصائيات البوت\n"
        "/help — هذه الرسالة\n\n"
        "💡 <b>كيف يعمل البوت؟</b>\n"
        "• ابحث عن وظيفة بكلمة مفتاحية وموقع جغرافي.\n"
        "• اشترك في تنبيهات لتصلك الوظائف الجديدة تلقائياً."
    )
    target = update.message or update.callback_query.message
    await target.reply_text(text, parse_mode="HTML")


# ─── Search conversation ───────────────────────────────────────────────────────

async def cmd_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    await target.reply_text(
        "🔍 <b>البحث عن وظيفة</b>\n\nأدخل كلمة البحث (مثال: مطور، محاسب، مهندس):",
        parse_mode="HTML",
    )
    return SEARCH_KEYWORD


async def search_got_keyword(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["search_keyword"] = update.message.text.strip()
    await update.message.reply_text(
        "📍 أدخل الموقع الجغرافي أو أرسل /skip للبحث في كل المواقع:"
    )
    return SEARCH_LOCATION


async def search_got_location(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["search_location"] = update.message.text.strip()
    return await _do_search(update, ctx, page=1)


async def search_skip_location(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["search_location"] = ""
    return await _do_search(update, ctx, page=1)


async def _do_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE, page: int):
    keyword = ctx.user_data.get("search_keyword", "")
    location = ctx.user_data.get("search_location", "")

    results, total = db.search_jobs(keyword=keyword, location=location, page=page)

    if not results:
        await update.message.reply_text(
            "😕 لم أجد وظائف مطابقة. جرّب كلمة مختلفة أو اتركها فارغة."
        )
        return ConversationHandler.END

    header = (
        f"✅ وجدت <b>{total}</b> وظيفة "
        f"لـ «{html.escape(keyword)}»"
        + (f" في «{html.escape(location)}»" if location else "")
        + f" — صفحة {page}:\n\n"
    )
    cards = "\n\n──────────────\n\n".join(_job_card(j) for j in results)

    keyboard = _pagination_keyboard(page, total, config.JOBS_PER_PAGE,
                                    f"search:{keyword}:{location}")
    await update.message.reply_text(
        header + cards,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    return ConversationHandler.END


# ─── Subscription conversation ─────────────────────────────────────────────────

async def cmd_subscribe(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    await target.reply_text(
        "🔔 <b>اشتراك جديد</b>\n\nأدخل الكلمة المفتاحية للوظائف التي تريد متابعتها:",
        parse_mode="HTML",
    )
    return SUB_KEYWORD


async def sub_got_keyword(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["sub_keyword"] = update.message.text.strip()
    await update.message.reply_text(
        "📍 أدخل الموقع أو أرسل /skip لمتابعة كل المواقع:"
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
    keyword = ctx.user_data.get("sub_keyword", "")
    location = ctx.user_data.get("sub_location", "")

    ok = db.add_subscription(user_id, keyword, location)
    if ok:
        await update.message.reply_text(
            f"✅ تم الاشتراك في تنبيهات <b>{html.escape(keyword)}</b>"
            + (f" في <b>{html.escape(location)}</b>" if location else "")
            + ".\nسأُرسل لك الوظائف الجديدة فور توفرها!",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"⚠️ لقد وصلت للحد الأقصى ({config.MAX_SUBSCRIPTIONS_PER_USER} اشتراكات) "
            "أو هذا الاشتراك موجود مسبقاً."
        )
    return ConversationHandler.END


# ─── /mysubs ───────────────────────────────────────────────────────────────────

async def cmd_mysubs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    subs = db.get_user_subscriptions(user_id)

    target = update.message or update.callback_query.message

    if not subs:
        await target.reply_text("📭 ليس لديك اشتراكات حالياً.\nاستخدم /subscribe لإضافة اشتراك.")
        return

    lines = ["📬 <b>اشتراكاتك الحالية:</b>\n"]
    buttons = []
    for s in subs:
        loc = f" – {s['location']}" if s.get("location") else ""
        lines.append(f"• <b>{html.escape(s['keyword'])}</b>{html.escape(loc)}")
        buttons.append([InlineKeyboardButton(
            f"🗑 حذف: {s['keyword']}{loc}",
            callback_data=f"delsub:{s['id']}"
        )])

    await target.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ─── /stats ────────────────────────────────────────────────────────────────────

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stats = db.get_stats()
    target = update.message or update.callback_query.message
    await target.reply_text(
        "📊 <b>إحصائيات بوت فرصة:</b>\n\n"
        f"👥 المستخدمون النشطون: <b>{stats['active_users']}</b>\n"
        f"💼 الوظائف المتاحة: <b>{stats['total_jobs']}</b>\n"
        f"🔔 الاشتراكات الفعالة: <b>{stats['total_subscriptions']}</b>",
        parse_mode="HTML",
    )


# ─── Callback query router ─────────────────────────────────────────────────────

async def callback_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("menu:"):
        action = data.split(":")[1]
        if action == "search":
            await cmd_search(update, ctx)
        elif action == "subs":
            await cmd_mysubs(update, ctx)
        elif action == "new_sub":
            await cmd_subscribe(update, ctx)
        elif action == "stats":
            await cmd_stats(update, ctx)
        elif action == "help":
            await cmd_help(update, ctx)

    elif data.startswith("delsub:"):
        sub_id = int(data.split(":")[1])
        ok = db.remove_subscription(sub_id, update.effective_user.id)
        await query.edit_message_text(
            "✅ تم حذف الاشتراك." if ok else "❌ لم يُعثر على الاشتراك."
        )

    elif data.startswith("search:"):
        _, keyword, location, page_str = data.split(":", 3)
        page = int(page_str)
        ctx.user_data["search_keyword"] = keyword
        ctx.user_data["search_location"] = location
        results, total = db.search_jobs(keyword=keyword, location=location, page=page)
        if not results:
            await query.edit_message_text("لا مزيد من النتائج.")
            return
        header = (
            f"✅ <b>{total}</b> وظيفة — صفحة {page}:\n\n"
        )
        cards = "\n\n──────────────\n\n".join(_job_card(j) for j in results)
        keyboard = _pagination_keyboard(page, total, config.JOBS_PER_PAGE,
                                        f"search:{keyword}:{location}")
        await query.edit_message_text(
            header + cards,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )


# ─── Scheduler: notify subscribers ────────────────────────────────────────────

async def notify_subscribers(app: Application):
    """Called periodically to fetch new jobs and notify subscribers."""
    logger.info("Running scheduled job fetch...")

    # Collect unique keywords from all subscriptions
    all_subs = db.get_all_subscriptions()
    keywords = list({s["keyword"] for s in all_subs if s.get("is_active")})

    for kw in keywords:
        new_jobs = job_fetcher.fetch_all(keyword=kw)
        if new_jobs:
            inserted = db.insert_jobs(new_jobs)
            logger.info("Inserted %d new jobs for '%s'", inserted, kw)

    # Now notify each subscriber
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
                    text=f"🔔 <b>وظيفة جديدة لاشتراكك «{html.escape(sub['keyword'])}»:</b>\n\n"
                         + _job_card(job),
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                db.mark_job_sent(user_id, job["id"])
            except Exception as e:
                logger.warning("Failed to notify user %s: %s", user_id, e)


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    db.init_db()

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Search conversation
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

    # Subscribe conversation
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
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("mysubs", cmd_mysubs))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(search_conv)
    app.add_handler(sub_conv)
    app.add_handler(CallbackQueryHandler(callback_router))

    # Scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        notify_subscribers,
        "interval",
        minutes=config.FETCH_INTERVAL_MINUTES,
        args=[app],
        next_run_time=datetime.now(),
    )
    scheduler.start()

    logger.info("🚀 بوت فرصة يعمل الآن...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
