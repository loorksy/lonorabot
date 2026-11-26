# Lonora Cloud website: registration and approval

The company website, the customer's portal account, and the staff admin panel (docs/cloud/DECISIONS.md D46, PHASES.md Phase W). It runs on Cloudflare Pages, with Pages Functions and a D1 database.

It lives in `cloud/site/` of this repository only until `loorksy/lonora-cloud` exists (D2). Nothing under `cloud/` is copied into the Lonora image, because the `Dockerfile` copies explicit paths (VISION Amendment 3 §7).

## بالعربية: دليل التشغيل خطوة خطوة

**ما يفعله:**
1. الزائر ينشئ حساباً عادياً: الاسم، والبريد، وكلمة المرور، والدولة، واللغة، ويوافق على الشروط وإفصاح المخاطر.
2. يبقى الحساب «بانتظار الموافقة».
3. من لوحة الإدارة توافق عليه أو ترفضه مع سبب يراه العميل.
4. حين تجهز نسخة Lonora الخاصة به تفعّله بعنوان النسخة ورابط الإعداد الأول، فيظهران له في صفحة حسابه مع زر «افتح في التطبيق».
5. كل قرار يُسجَّل باسم الموظف.

**لا يُطلب ولا يُخزَّن هنا:** بطاقة دفع، ولا مفتاح نموذج، ولا كلمة مرور الوسيط. هذه كلها تُدخَل داخل Lonora الخاص بالعميل، لا في الموقع.

### مرة واحدة: التجهيز

1. **الحساب والاشتراك:** حساب Cloudflare، وأضف إليه نطاق الشركة (مثلاً `lonora.app`، القرار D5). فعّل خطة **Workers Paid**: تشفير كلمات المرور يحتاج وقت معالجة أكبر مما تسمح به الخطة المجانية.
2. **أداة wrangler:** على جهازك، داخل هذا المجلد:
   ```
   npx wrangler@latest login
   ```
3. **قاعدة البيانات:**
   ```
   npx wrangler d1 create lonora_site
   ```
   ضع `database_id` الذي يظهر في `wrangler.toml`، ثم:
   ```
   npx wrangler d1 execute lonora_site --remote --file=schema.sql
   ```
4. **الحماية من الروبوتات (Turnstile):** من لوحة Cloudflare أنشئ Turnstile widget للنطاق.
   - ضع **Site Key** في `wrangler.toml` مكان `TURNSTILE_SITE_KEY`.
   - ضع المفتاح السري بالأمر (لا تكتبه في أي ملف):
     ```
     npx wrangler pages secret put TURNSTILE_SECRET --project-name lonora-site
     ```
5. **النشر:**
   ```
   npx wrangler pages deploy public --project-name lonora-site
   ```
   ثم من Pages › Custom domains اربط النطاق. اجعل `SITE_ORIGIN` في `wrangler.toml` هو العنوان نفسه تماماً، مثل `https://lonora.app`.
6. **حماية لوحة الإدارة (Cloudflare Access):** من Zero Trust › Access › Applications أنشئ تطبيقاً Self-hosted.
   - يغطي المسارين `lonora.app/admin*` و`lonora.app/api/admin*`.
   - سياسته: Allow لبريدك وبريد موظفيك فقط.
   - انسخ **Application Audience (AUD)** واسم الفريق `xxxx.cloudflareaccess.com` إلى `ACCESS_AUD` و`ACCESS_TEAM_DOMAIN`.
   - اكتب البريد المسموح في `ADMIN_EMAILS`، وافصل بين أكثر من بريد بفاصلة.
   - أعد النشر.

   الخادم يتحقق من توقيع Access في كل طلب إدارة، فلا يكفي معرفة الرابط.

### كل يوم

- **مراجعة الحسابات:** افتح `https://lonora.app/admin`.
  - تبويب «بانتظار الموافقة»: افتح التفاصيل، واضغط **موافقة** أو **رفض** مع سبب.
  - بعد الموافقة جهّز نسخة Lonora الخاصة به يدوياً على خادم جديد. اتبع `docs/operations.md`: المثبّت `install.sh`، والإعداد عبر رابط الإعداد الأول. هذا يدوي حتى تأتي المرحلة 3 فتؤتمته.
  - ضع عنوان نسخته (`https://…`) ورابط الإعداد، واضغط **تفعيل**.
- **إيقاف مؤقت:** **إيقاف** مع سبب، و**إعادة التفعيل** لاحقاً. الإيقاف هنا لحساب الموقع فقط. لا يغيّر شيئاً في صفقاته ولا في وكلائه (التعديل 3، البند 9).
- **تصدير القائمة:** زر «تصدير CSV». الخلايا التي قد يشغّلها برنامج الجداول كمعادلة تُعطَّل.
- **حذف شخص بطلبه:** «حذف بطلبه». يُحذف الحساب وجلساته، ويبقى في السجل أثر مشفّر فقط.
- **نسخة احتياطية للقائمة:**
  ```
  npx wrangler d1 export lonora_site --remote --output lonora-site-backup.sql
  ```
  وD1 يحفظ أيضاً تاريخ 30 يوماً (Time Travel).

### الاختبار على جهازك

```
npm test
```
34 اختباراً تغطي:
- التسجيل، والبريد المكرر، والحقول الخاطئة، والروبوت، والإغراق، والمصدر الغريب؛
- الدخول والجلسات وتسجيل الخروج؛
- لوحة الإدارة: رفض أي طلب بلا توقيع Access صحيح، والقرارات، والسجل، والحذف، والتصدير.

### ما زال مسودة

نصوص الشروط والخصوصية وإفصاح المخاطر مسودات معلَّمة حتى يراجعها محامٍ (D20). أرقام نسخها في `TERMS_VERSION` و`RISK_VERSION` و`PRIVACY_VERSION`، وتُحفظ مع كل حساب وافق عليها. غيّر الرقم حين يتغير النص.

## English: runbook

**What it does:**
1. A visitor creates a normal account with name, email, password, country and language, and accepts the terms and the risk disclosure.
2. The account stays `pending`.
3. Staff approve it, or reject it with a reason the customer sees.
4. Once the customer's dedicated Lonora exists, staff activate the account with its address and setup link. The customer's account page then shows them, with "Open in the app".
5. Every staff decision is audited with the staff email.

**Never asked for or stored here:** card data, model keys and broker passwords. Those are entered inside the customer's own Lonora.

### One-time setup

1. **Account and plan:** a Cloudflare account with the company domain (D5). Enable **Workers Paid**: password hashing, PBKDF2 at 100,000 iterations (the Workers maximum), needs more CPU than the free plan allows.
2. **wrangler:** `npx wrangler@latest login`.
3. **Database:**
   ```
   npx wrangler d1 create lonora_site
   ```
   Put the `database_id` in `wrangler.toml`, then:
   ```
   npx wrangler d1 execute lonora_site --remote --file=schema.sql
   ```
4. **Turnstile:** create a widget for the domain.
   - Put the site key in `wrangler.toml`.
   - Set the secret with:
     ```
     npx wrangler pages secret put TURNSTILE_SECRET --project-name lonora-site
     ```
5. **Deploy:**
   ```
   npx wrangler pages deploy public --project-name lonora-site
   ```
   Attach the custom domain, and set `SITE_ORIGIN` to exactly that origin.
6. **Cloudflare Access:** create a self-hosted application.
   - It covers `/admin*` and `/api/admin*`.
   - Its policy allows only the staff emails.
   - Copy the AUD and the team domain into `ACCESS_AUD` and `ACCESS_TEAM_DOMAIN`, and list the staff in `ADMIN_EMAILS`.
   - Redeploy.

   The functions verify the Access JWT on every admin call (signature, audience, issuer, expiry, allowed email).

### Daily use

- **Review:**
  1. Open `/admin`, then the "pending" tab: approve, or reject with a reason.
  2. After approval, install the customer's Lonora on a new server by hand (`docs/operations.md`).
  3. Activate with its `https://` address and setup link.
- **Suspend and reinstate:** they affect the portal account only. They never touch the customer's trades or agents (Amendment 3 §9).
- **Export:** CSV, with formula cells neutralised.
- **Delete on request:** removes the account and its sessions; the audit keeps only a hash.
- **Backup:**
  ```
  npx wrangler d1 export lonora_site --remote --output lonora-site-backup.sql
  ```
  D1 also has 30 days of Time Travel.

### Security notes

- **Registration:**
  - same-origin POSTs only;
  - Turnstile, refused when no secret is set;
  - a honeypot;
  - a rate limit of 5 an hour per address;
  - the same answer for a new and an existing email (no enumeration).
- **Sign-in:** the same answer for a wrong password and an unknown email, with a dummy hash checked so that timing matches; rate limits of 20 per 15 minutes per address and 8 per 15 minutes per email.
- **Sessions:**
  - 32-byte random tokens, stored hashed;
  - the cookie is `__Host-`, HttpOnly, Secure, SameSite=Lax;
  - 30 days.
- **Headers:** CSP, nosniff, frame-ancestors 'none', Permissions-Policy and COOP on every response.
- **Logs:** no request body, email, password or token is ever logged.

### Tests

`npm test` runs 34 tests with Node's built-in test runner. They use an in-memory SQLite in place of D1, and stub Turnstile and Access.
