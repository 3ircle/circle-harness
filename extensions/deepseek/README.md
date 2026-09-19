# اکستنشن کروم اتصال چت دیپ‌سیک به لوکال‌هاست (DeepSeek to Localhost Bridge)

این اکستنشن کروم (مبتنی بر **Manifest V3**) به طور خودکار یا دستی پیام‌های خروجی و پاسخ‌های هوش مصنوعی دیپ‌سیک (DeepSeek) در سایت [chat.deepseek.com](https://chat.deepseek.com) را استخراج کرده و به سرور محلی شما به آدرس `http://localhost:8000/chat` با متد `POST` ارسال می‌کند.

---

## 🚀 ویژگی‌ها

- **تشخیص خودکار اتمام پاسخ (Auto-Send):** به محض اتمام تولید پاسخ دیپ‌سیک (و حذف دکمه Stop / کرسر تایپ)، پاسخ به صورت خودکار به `localhost:8000/chat` فرستاده می‌شود.
- **شنود دوسطحی (Dual-Layer Interceptor):**
  1. **ردگیری شبکه (Network Stream Interceptor):** شنود مستقیم جریان داده SSE به منظور استخراج بدون نقص و بلادرنگ متن و استدلال.
  2. **ردگیری ساختار صفحه (DOM MutationObserver):** به عنوان پشتیبان کامل برای اطمینان از استخراج متن در تمام شرایط و نسخه‌های چت.
- **دکمه ارسال دستی (Manual Send Button):** اضافه شدن دکمه اختصاصی `🚀 ارسال به localhost` در زیر هر پاسخ دیپ‌سیک جهت ارسال مجدد یا دلخواه هر پیام.
- **پشتیبانی از مدل‌های استدلالی (DeepSeek R1):** امکان تفکیک و ارسال بخش فکر کردن (`thinking` / `reasoning_content`) در کنار پاسخ نهایی.
- **عدم تداخل با CORS یا Mixed Content:** ارسال درخواست‌های POST از طریق Service Worker پس‌زمینه (Background Script) انجام می‌شود و با محدودیت‌های CORS یا خطای امنیتی HTTPS به HTTP مسدود نمی‌شود.
- **ویجت شناور در صفحه دیپ‌سیک:** دارای نمایشگر وضعیت اتصال سرور (سبز/قرمز)، سوئیچ ارسال خودکار، و دکمه تست سرور.
- **پنجره تنظیمات (Extension Popup):**
  - امکان تغییر آدرس سرور مقصد (پیش‌فرض: `http://localhost:8000/chat`).
  - فعال/غیرفعال‌سازی ارسال خودکار.
  - فعال/غیرفعال‌سازی ارسال بخش Thinking.
  - دکمه تست اتصال زنده با سرور.
  - تاریخچه آخرین پیام‌های ارسالی با وضعیت کد HTTP (مانند `200 OK`).

---

## 📦 ساختار فایل‌های اکستنشن

```text
extensions/deepseek/
├── manifest.json       # مانیفست اکستنشن کروم (Manifest V3)
├── background.js      # سرویس ورکر پس‌زمینه جهت ارسال درخواست‌های POST به localhost
├── inject.js          # اسکریپت تزریقی در محیط صفحه اصلی برای اینترسپت استریم چت
├── content.js         # اسکریپت پردازش DOM، افزودن دکمه‌ها و ویجت کنترل به صفحه
├── content.css        # استایل‌های ویجت شناور و دکمه‌های پیام
├── popup.html         # رابط کاربری پنجره اکستنشن (Popup)
├── popup.js           # منطق پنجره اکستنشن و مدیریت تنظیمات
├── popup.css          # استایل‌های مدرن پنجره اکستنشن
├── icons/             # آیکون‌های اکستنشن در ابعاد ۱۶، ۴۸ و ۱۲۸
└── README.md          # راهنمای نصب و استفاده
```

---

## 📥 نحوه نصب در گوگل کروم (Google Chrome / Brave / Edge)

1. مرورگر کروم را باز کنید و به آدرس زیر بروید:
   ```text
   chrome://extensions
   ```
2. در گوشه بالا سمت راست، گزینه **Developer mode** (حالت توسعه‌دهنده) را فعال کنید.
3. روی دکمه **Load unpacked** (بارگذاری بسته باز نشده) کلیک کنید.
4. پوشه زیر را انتخاب کنید:
   ```text
   C:\Users\3ircle\Documents\projects\circle-harness\extensions\deepseek
   ```
5. اکستنشن با نام **DeepSeek to Localhost Bridge** به مرورگر شما افزوده می‌شود!

---

## 📡 قالب داده ارسالی (JSON Payload)

درخواست‌ها با متد **`POST`** و هدر `Content-Type: application/json` به آدرس `http://localhost:8000/chat` ارسال می‌شوند:

```json
{
  "message": "متن پاسخ تولید شده توسط دیپ‌سیک...",
  "thinking": "متن فرآیند فکر کردن و استدلال مدل در صورت وجود (اختیاری)",
  "role": "assistant",
  "model": "deepseek-chat",
  "timestamp": "2026-09-19T11:00:00.000Z",
  "source": "deepseek-web",
  "url": "https://chat.deepseek.com/a/chat/s/...",
  "session_id": "...",
  "manual": false
}
```

---

## 🧪 تست سریع با سرور تستی یا جنگو

برای تست، می‌توانید سرور لوکال جنگو یا یک اسکریپت ساده پایتون اجرا کنید:

```bash
python -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(length)
        print('=== Received from DeepSeek ===')
        print(data.decode('utf-8'))
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{\"status\": \"received\"}')

print('Test server running on http://localhost:8000/chat...')
HTTPServer(('localhost', 8000), Handler).serve_forever()
"
```
