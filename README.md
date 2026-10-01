# ⬇️ عبوري داونلودر

موقع عربي (RTL) للتحميل من **يوتيوب، تيك توك، إنستغرام، فيسبوك، X/تويتر** وأكثر من 1000 منصة ثانية —
مبني على [yt-dlp](https://github.com/yt-dlp/yt-dlp).

**المميزات:**
- 🔎 بحث باسم الأغنية/الفيديو في يوتيوب واختيار النتيجة
- 🔗 لصق رابط مباشر من أي منصة مدعومة
- 🎬 تحميل فيديو MP4 بجودات متعددة (أعلى جودة / 1080 / 720 / 480)
- 🎵 تحميل صوت MP3 أو M4A
- 🌙 واجهة عربية داكنة متجاوبة مع الموبايل

## ⚠️ ملاحظة مهمة عن GitHub

**GitHub Pages ما يشغّل بايثون** — يستضيف صفحات ثابتة (HTML/CSS/JS) فقط،
وهذا الموقع يحتاج سيرفر خلفي (yt-dlp + ffmpeg). لذلك:

1. ارفع هذا المشروع على **GitHub** كريبو عادي (الكود كامل).
2. اربط الريبو بخدمة استضافة مجانية تشغّل الباك إند (خطوة واحدة):
   - **[Render](https://render.com)** — خدمة Web مجانية، تتعرف على `Procfile` تلقائياً.
   - **[Railway](https://railway.app)** — نشر بزر واحد من GitHub.
   - **[Hugging Face Spaces](https://huggingface.co/spaces)** — مجاني، اختر Docker SDK.

الواجهة الأمامية (`static/index.html`) تُقدَّم من نفس السيرفر، فما تحتاج GitHub Pages أبداً.

## 🚀 التشغيل محلياً

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

يحتاج `ffmpeg` مثبتاً على النظام (لتحويل MP3/MP4). على Ubuntu:

```bash
sudo apt install ffmpeg
```

## 🌐 النشر على Render (مثال)

1. ارفع المشروع على GitHub.
2. في Render: **New → Web Service →** اختر الريبو.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
5. Render يوفّر `ffmpeg` افتراضياً. ✅

## 📁 هيكل المشروع

```
├── app.py              # الباك إند (FastAPI + yt-dlp)
├── requirements.txt
├── Procfile            # لخدمات النشر (Render/Railway)
├── runtime.txt         # نسخة بايثون
├── static/
│   └── index.html      # الواجهة العربية (RTL)
└── README.md
```

## 🔌 API

| الطريقة | المسار | الوصف |
|---|---|---|
| GET | `/api/search?q=...` | بحث يوتيوب |
| GET | `/api/info?url=...` | معلومات رابط |
| GET | `/api/formats?url=...` | معلومات + الصيغ المتاحة |
| POST | `/api/download` | `{"url": "...", "preset": "video_720"}` → ملف |
| GET | `/api/health` | فحص |

الصيغ: `video_best` `video_1080` `video_720` `video_480` `audio_mp3` `audio_m4a`

## ⚖️ تنبيه

للاستخدام الشخصي فقط. احترم حقوق النشر وشروط استخدام المنصات.
