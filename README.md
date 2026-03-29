# بوت فرصة 🎯

بوت تيليغرام للبحث عن الوظائف، مبني بـ Python وقاعدة بيانات PostgreSQL.

## المميزات

- 🔍 البحث عن الوظائف بكلمة مفتاحية وموقع جغرافي
- 🔔 الاشتراك في تنبيهات تصل تلقائياً عند نشر وظائف جديدة
- 📄 تصفح النتائج بالصفحات
- 📊 إحصائيات المستخدمين والوظائف
- 🌐 دعم مصادر متعددة: Adzuna، Reed، RemoteOK، Arbeitnow

## هيكل المشروع

```
فرصة/
├── main.py          # البوت الرئيسي والأوامر
├── database.py      # عمليات قاعدة البيانات PostgreSQL
├── jobs.py          # جلب الوظائف من المصادر المختلفة
├── config.py        # الإعدادات من متغيرات البيئة
├── requirements.txt # المكتبات المطلوبة
└── .env.example     # مثال على ملف الإعدادات
```

## التثبيت

### المتطلبات
- Python 3.11+
- PostgreSQL 14+

### الخطوات

**1. استنساخ المشروع وإنشاء بيئة افتراضية:**
```bash
cd فرصة
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # Linux/Mac
```

**2. تثبيت المكتبات:**
```bash
pip install -r requirements.txt
```

**3. إعداد قاعدة البيانات:**
```sql
CREATE DATABASE forsa_db;
```

**4. إعداد متغيرات البيئة:**
```bash
cp .env.example .env
# عدّل ملف .env بقيمك الصحيحة
```

**5. الحصول على توكن البوت:**
- تحدث مع [@BotFather](https://t.me/BotFather) على تيليغرام
- أنشئ بوتاً جديداً بـ `/newbot`
- انسخ التوكن إلى `TELEGRAM_BOT_TOKEN` في ملف `.env`

**6. تشغيل البوت:**
```bash
python main.py
```

## مصادر الوظائف

| المصدر | مجاني | يحتاج مفتاح API |
|--------|--------|----------------|
| [RemoteOK](https://remoteok.com) | ✅ | ❌ |
| [Arbeitnow](https://arbeitnow.com) | ✅ | ❌ |
| [Adzuna](https://developer.adzuna.com) | ✅ | ✅ |
| [Reed](https://www.reed.co.uk/developers) | ✅ | ✅ |

## أوامر البوت

| الأمر | الوصف |
|-------|-------|
| `/start` | القائمة الرئيسية |
| `/search` | البحث عن وظيفة |
| `/subscribe` | اشتراك في تنبيهات |
| `/mysubs` | عرض وإدارة الاشتراكات |
| `/stats` | إحصائيات البوت |
| `/help` | المساعدة |

## متغيرات البيئة

| المتغير | الوصف | القيمة الافتراضية |
|---------|-------|-----------------|
| `TELEGRAM_BOT_TOKEN` | توكن البوت | — |
| `DB_HOST` | مضيف PostgreSQL | `localhost` |
| `DB_PORT` | منفذ PostgreSQL | `5432` |
| `DB_NAME` | اسم قاعدة البيانات | `forsa_db` |
| `DB_USER` | مستخدم قاعدة البيانات | `postgres` |
| `DB_PASSWORD` | كلمة مرور قاعدة البيانات | — |
| `FETCH_INTERVAL_MINUTES` | دورة جلب الوظائف (بالدقائق) | `60` |
| `ADMIN_IDS` | معرفات المشرفين مفصولة بفاصلة | — |
| `ADZUNA_APP_ID` | معرف تطبيق Adzuna | — |
| `ADZUNA_APP_KEY` | مفتاح Adzuna | — |
| `REED_API_KEY` | مفتاح Reed | — |
