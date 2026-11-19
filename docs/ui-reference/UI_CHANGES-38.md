# UI_CHANGES — Lonora-Desktop-38.html

Reference: `Lonora-Desktop-37.html`. Result: `Lonora-Desktop-38.html` (one file, same CSS tokens, fonts and icons; no new library or CDN).

How it was checked (headless Chrome, 390px and 1280px, light and dark):
- 82 end-to-end flows pass in all four combinations (chat list, search, sheets, forms, composer, the five cards, Ask/Full, trades page, attention list, settings).
- No console errors on 63 screens, sheets, menus and cards.
- 20 key screens show no overflow, cut text or reversed numbers at 320×640, 360×740, 600×900, 768×1024, landscape 844×390 (also with iPhone notch insets), 900×700, 1024×768, 1280×600, 1366×768 and 1920×1080.
- Every tap target is at least 44px. The one exception is the chat-header name, listed in UI_BUGS.md.
- Small text has 4.5:1 contrast. Signed numbers read left-to-right. No raw ids, codes or tool names appear.
- Hooks: every id, class, `data-*` attribute and value, action and route of v37 is still present, except those listed under "Removed hooks" below.

Screen names are the ones the app shows. "why" uses: **simpler**, **defect** (details in UI_BUGS.md) or **removed** (a feature Lonora no longer has).

## Changes

| id or selector | screen | before | after | why |
|---|---|---|---|---|
| `.composer .mode-chip` (`data-do="mode"`) | Chat (composer) | Three levels: «دون تنفيذ» · «تنفيذ بموافقة» · «تنفيذ مفوَّض» | Two modes: «يستأذن» (Ask) · «وكّله» (Full). Same chip, same place | removed (ladder, delegation) |
| `.no-trade` (`data-do="sf-noacct"`) | Chat header (trading agent without an account) | Eye chip «دون تنفيذ» that opened a sheet | Removed. The account row is on the agent page | removed («trading not started» state) |
| `.mode-pop .mp-page.p1` (`mp-level`) | Chat › mode menu | «مستوى الصلاحية»: a ladder of 3 radios with long notes, a «تفاصيل التفويض» row and the note «محاكاة واجهة؛ لا تُمنح صلاحيات مالية حقيقية» | The Mandate: «التفويض · ‹agent›». Current mode «الآن: يستأذن» with one plain line, then one button for the other mode. The model row is kept | simpler, removed |
| `mpLevel` › `requestAuthority()` | Chat › mode menu | «تنفيذ مفوَّض» opened the delegation sheet: Custom/Full, markets, actions, 12h/24h/7d, passkey signing | «وكّله» switches in one tap | removed (delegation, passkey) |
| `.pop-opt.danger-opt` (`mp-down-ok`) | Chat › mode menu, page 2 | Leaving Full showed a warning page and «تأكيد: …» | No warning page. The button applies the mode it shows | simpler (duplicate confirmation) |
| `.mp-model-row` › model page | Chat › mode menu › النموذج | Line «خلال 7 أيام · دون سقف لهذا الوكيل» | Line removed | removed (agent caps) |
| `setLevel()` toast | Any place that changes the mode | Toast with the level name. Log «تغيير صلاحيات تجريبي» | Toast «‹agent›: وكّله · سُحب طلب موافقة واحد». Switching to Full withdraws that agent's pending Trade Approvals («سُحب — لم يُرسل شيء») | simpler (in Full nothing waits for approval) |
| `#dialog[data-sheet="tools"]` › members page | Group chat › «+» › members | «صلاحيات الأعضاء», «افتح محادثة الوكيل لتعديل صلاحياته», research agent «دون صلاحيات» | «تفويض الأعضاء»: each trading member with its mode. Research agent: «يجمع المعلومات ويلخّصها، ولا يتداول» | simpler |
| `#dialog[data-sheet="tools"]` › mode page | Chat › «+» › التفويض | Title «صلاحيات ‹agent›». Identity row sub «مراجعة صلاحيات الوكيل بالتفصيل» (it opens name/role/model) | Title «التفويض · ‹agent›». Sub «الاسم والدور والنموذج» | defect (words ≠ destination) |
| `/permission` slash command | Chat (composer) | «صلاحيات أعضاء المجموعة» / «غيّر صلاحيات الوكيل» | «تفويض أعضاء المجموعة» / «التفويض: يستأذن أو وكّله» | simpler (one name for one thing) |
| First agent message | New chat | «…وغيّر صلاحياتي من الشريحة بجانب حقل الكتابة». Group: «لكل وكيل صلاحيات مستقلة» | Hint removed. Group: «لكل وكيل تفويضه الخاص» | simpler (repeated explanation) |
| Agent answer to «وكّله» / «يستأذن» in text | Chat | «يُغيَّر مستوى الصلاحية من الشريحة… الرسائل النصية لا تغيّر التفويض» | The agent posts the Mandate card | simpler (Mandate card) |
| route `permission-details` | Chat › mode menu | Page «تفاصيل التفويض» (scope, actions, duration, passkey) | Removed. The catalog entry opens the members' Mandate | removed |
| `nav [data-do="tab"]` route `updates` · `.desktop-rail [data-rail="updates"]` | Tab bar / desktop rail | «المستجدات»: agent stories, notifications, upcoming schedules, «آخر الإجراءات», «عرض السجل كاملًا» | «يحتاج انتباهك»: one list `#nx-attention-list` (pending approvals, unconfirmed trades, Secret and Mandate cards, unread alerts). Tap opens the right chat at the card (`sf-jump` / `notification`), never approves. Badge = count | simpler |
| `.stories .story.ring` | المستجدات | Row of agent avatars with rings | Removed (the chat list already shows them) | simpler |
| `.link` «عرض السجل كاملًا», «تحديد الكل كمقروء» | المستجدات | Two links | «تحديد التنبيهات كمقروءة», shown only when there are alerts | simpler |
| empty state | يحتاج انتباهك | «لا توجد تنبيهات» + «لا توجد مواعيد مفعّلة» + «لا يوجد نشاط بعد» | «لا شيء يحتاج انتباهك الآن.» + «فتح المحادثات» | simpler (one sentence + next action) |
| route `activity` | Settings › About · المستجدات | Page «سجل الإجراءات» and its rows | Removed | removed |
| routes `goals`, `new-goal`, `data-form="goal"` | Agent page | Row «الأهداف», goal list, «إضافة هدف», goal form | Removed | removed |
| agent page `.group` rows | Agent page | الهوية والنموذج · المعرفة · المهارات · الأهداف · المهام المجدولة · الملفات · الصفقات | الهوية والنموذج · المهارات · المعرفة · الملفات · المهام المجدولة · الصفقات (Lonora's order) | simpler, removed (goals) |
| `.sup-line`, supervision section | Agent page | «يشرف على …» / «يتبع …» line and section with «إضافة إشراف» | Removed. Lonora leads a flat team | removed (supervision) |
| agent page `<h3>` + `[data-do="sf-sheet"]` row | Agent page | «التداول والأمان». Sub «التداول · الصفقات الجديدة · القيود · حدود الحساب». No account: row «دون تنفيذ» | «التداول»: the mode line and one plain status line. No account: «حساب التداول · اختر حسابًا» or «… اربطه في المحادثة» | removed, simpler |
| agent page note under the rows | Agent page | «تُغيَّر الصلاحيات من الشريحة… ربط الخدمات من الإعدادات ← التكاملات.» | Removed | simpler (repeated explanation) |
| `[data-do="toggle-agent"]` | Agent page | «إيقاف الوكيل» / «تشغيل الوكيل» | «إيقاف الوكيل مؤقتًا» / «استئناف الوكيل» (the agent pause is kept; it is not a trading stop) | defect (words ≠ the state they set) |
| `#dialog[data-sheet="safety"]` (`sf-sheet`) | Agent page › التداول | «التداول والأمان»: trading switch `.sf-switch`, new-trades switch, restrictions with «رفع القيد», account limits, pause/resume trading | «التداول»: the Mandate as two radio rows (current mode and the other) and any unconfirmed operations to settle | removed (Stop, limits, restrictions) |
| `#dialog[data-sheet="emergency"]` (`ag-emg`, `ag-emg-sign`) | Agent page | «قاعدة الطوارئ» sheet with passkey signing | Removed | removed (Stop) |
| `#dialog[data-sheet="sup"]` (`ag-newsup`, `ag-sup-*`, `ag-unsup`) | Agent page · new agent | Supervision picker | Removed | removed (supervision) |
| route `agent-type` | New agent | Templates plus a «الإشراف على وكلاء آخرين» capability switch and two notes | The three templates | removed, simpler |
| `.tpl-row .tpl-code` | New agent | Internal codes under each template («دور متخصّص · سوق محدَّد») in faint text, and the line «اختر قالبًا؛ يُشتق نوع الوكيل من دوره ونطاق عمله.» | Removed. Each template keeps its name and one line | defect (internal wording, 3.6:1), simpler |
| new-agent note | New agent | «يبدأ بمستوى «تنفيذ بموافقة»: يُعرض عليك كل أمر قبل إرساله. يُغيَّر المستوى من محادثته» | «يبدأ بوضع «يستأذن»: كل صفقة تزيد المخاطرة تنتظر موافقتك. يُغيَّر من محادثته.» | simpler |
| `data-form="identity"` submit | Agent › الهوية والنموذج | Changing the account or pair cancelled the mandate: «أُلغي التفويض… المستوى الآن «تنفيذ بموافقة»» | The mode stays | removed (mandates bound to an account) |
| `[data-do="acct-remove"]` | Settings › trading account | «يتوقف ‹agent› عن التنفيذ («دون تنفيذ»)، ويُلغى أي تفويض موقَّع…» | «لن يتداول ‹agent› حتى تختار له حسابًا آخر.» The mode is not touched | simpler |
| route `broker`, `data-form="broker"` | Settings › Integrations | Form: broker, account type, number, password, server, «اختبار الاتصال», long note | Opens Lonora's chat with «اربط حساب تداول جديد» ready. Lonora asks for number and server in a message, the password in a Secret card | removed (form), simpler |
| `[data-do="go"]` «إضافة حساب تداول» | Settings › Integrations · trading account | «إضافة حساب تداول» / «ربط حساب تداول» | «ربط حساب في المحادثة» (same place) | simpler |
| `acctFields` note | Agent identity · new trading agent | «اربط حساب تداول من الإعدادات ← التكاملات لاختيار الزوج من رموزه» | «اربط حسابًا من محادثة Lonora…» | simpler |
| `[data-do="cap-telegram"]`, `#dialog[data-sheet="cred"]` | Settings › Integrations › Telegram | Sheet with a paste field (`data-cred`) and «حفظ» (`cap-cred-save`) | A Secret card in Lonora's chat («ربط Telegram» · «رمز البوت»). Once saved, the sheet shows «محفوظ · لا يُعرض مرة أخرى» and «فصل» | removed (old credential sheet) |
| `#dialog[data-sheet="mcp"]` tool rows | Settings › MCP server | `search_news`, `get_article`, `save_note`, `set_alert` | «البحث في الأخبار», «قراءة مقال», «حفظ ملاحظة», «ضبط تنبيه» | defect (raw tool names) |
| `[data-do="test-connection"]` | Settings › providers · MCP form | «اختبار الاتصال» (it only checks the fields) | «فحص الحقول». Result: «الحقول مكتملة. لم يُتصل بمزود أو خادم خارجي.» | defect (words ≠ action) |
| `.u-actions [data-do="budget"]` | Settings › Usage | «تعديل الحد» twice (on the card and in the action row) | Once, on its card | simpler (duplicate) |
| Help FAQ | Settings › Help | «هل يستطيع الوكيل تنفيذ عمليات مالية؟ لا، إلا إذا اخترت «تنفيذ مفوَّض» ووقّعت…» | «هل يتداول الوكيل بنفسه؟ حسب تفويضه: …» | removed (old text) |
| sign-in slide | Sign-in | «…ويمكنك إيقافها في أي لحظة» | «كل وكيل يستأذنك قبل أي صفقة تزيد المخاطرة، حتى توكّله بلمسة.» | removed (Stop text) |
| settings row `owner` | Settings | «الملف الشخصي · مشترك بين جميع وكلائك» | «الملف الشخصي · ما أعرفه عنك» | simpler |
| route `owner` `<h3>` | Settings › profile | «ما يعرفه وكلاؤك عنك» | «ما أعرفه عنك» | simpler |
| reach option `activity` | Settings › notifications | «سجل النشاط فقط — يُسجَّل في المستجدات دون أي تنبيه» | Removed. The default stays «إشعار» | removed |
| device row | Settings › notifications | «… · مسجَّل لمفتاح المرور» | «يصل التنبيه إلى هذا الجهاز فقط» | removed (passkey) |
| urgent row sub | Settings › notifications | «عملية غير مؤكَّدة أو قيد على حسابك» | «طلب موافقة أو عملية غير مؤكَّدة» | removed (restrictions) |
| `[data-do="notif-ask"]` | Settings › notifications | `primary small`, 36px tall | `primary sm` (the app's small button) with a 44px hit area | defect (tap target) |
| route `about` | Settings › About | Version 37, row «سجل الإجراءات», download «Lonora-Desktop-37.html» | Version 38, no log row, download «Lonora-Desktop-38.html» | removed |
| desktop welcome | 1280, empty chat pane | «المستجدات», «الصلاحيات مستقلة لكل وكيل» | «يحتاج انتباهك», «لكل وكيل تفويضه: يستأذن أو وكّله» | simpler |
| seeded alert | يحتاج انتباهك | «أعدّ … موجز اليوم: لا مستجدات عاجلة. افتح محادثته لقراءته» | «لا مستجدات عاجلة اليوم» | simpler |
| `.mcard` Trade Approval (`approve` / `reject`, `data-mid`) | Chat | Approval card with the note «محاكاة محلية؛ لا يحدث تنفيذ خارجي». Could end «انتهت المراجعة أو تغير النطاق» | Fixed card: «طلب موافقة · XAUUSD», side and volume, الدخول, وقف الخسارة, جني الربح, «صالحة ما دام السعر ضمن», «بكلمات الوكيل: …», «موافقة» / «رفض». Ends «تمت الموافقة — أُرسل إلى الوسيط» · «مرفوض — لم يُرسل شيء» · «خرج السعر عن الهامش — لم يُرسل شيء» · «سُحب — لم يُرسل شيء». No time limit. One use | simpler |
| `.mcard.act-receipt` `#nx-receipt-‹mid›` | Chat | Order line `.od-chat.s-‹state›` («أمر … · عرض التفاصيل») | Execution Receipt: «إيصال التنفيذ · XAUUSD», the action as the title, broker ticket, volume, fill price (modify: new SL/TP; cancel: ticket), «أكّده الوسيط», the agent's reason | simpler |
| `.oa` Settle (`resolve_operation`, `data-oa-mid`) | Chat | Countdown, note and reference inputs (`data-oa-in="note"`, `"ref"`), «إضافة ملاحظة أو مرجع الوسيط», long consequence lines | «عملية غير مؤكدة»: «نُفذت» · «لم تُنفذ» · «غير معروفة». No timer. Never folded | simpler |
| `.oa.act-secret` (`data-oa-in`) | Chat (Lonora) | Credentials in a sheet | Masked fields in the card. Afterwards only «حُفظت». Values are never stored or shown | simpler |
| `.oa.act-trading_mode` `#nx-mandate-‹mid›` | Chat | None: a text reply pointed at the chip | Mandate: the current mode (read live) and one button for the other mode | simpler |
| old owner-action kinds | Chat · sheet `data-sheet="oa"` | «التنفيذ المفوَّض», «حدود الحساب», «رفع القيد», «استئناف التداول», «بدء التداول», «فتح صفقات جديدة», «وكيل جديد», «الإشراف», «مصدر جديد», «بيانات اعتماد», «نموذج الوكيل» | Removed. Credentials go to Secret, operations to Settle, mode to Mandate | removed |
| `.msg.k-notice .notice` («تراجع», `oa-undo-notice`) | Chat | Silent «watch changed» / «stop tightened» lines with an undo | Removed. The agent says it in its own message | removed |
| `.oa-exp` countdown, decision lines | Chat (cards) | «ينتهي الطلب خلال …», «لا شيء · استُبدل بطلب أحدث», «لا شيء · انتهت مهلة الطلب» | Removed. A card ends only by its own outcomes | removed |
| card type `tpl` «وكيل جديد · من إصدار سابق» | Chat | Line for agent-creation cards from older versions | Removed (older saves are migrated) | removed |
| approve / reject toasts | Chat | «تمت الموافقة · أُرسل الأمر». On a card that had ended: «انتهت المراجعة أو تغير النطاق», «لم تعد الصفقة متاحة» | «طلب موافقة · تمت الموافقة / مرفوض / سُحب». On a card that has ended: «سبقت الإجابة على هذا الطلب» | simpler |
| `#dialog[data-sheet="order"]` `.od-tech` | Trades › order | «التفاصيل التقنية»: رقم العملية (OP-…), معرّف الأمر (cl-…), الخادم, رمز رد الوسيط (TRADE_RETCODE_…) | Broker ticket and account only | defect (raw ids and codes) |
| route `trades` | Agent › الصفقات | The owner's own close/edit made an approval card for the owner, or a «دون تنفيذ» sheet. Note «تخضع الأزرار لمستوى صلاحيات الوكيل…» | Runs once. The receipt arrives in the agent's chat. Note removed | defect (dead end) |
| `[data-do="trade-close"]` sheet | Trades | «إغلاق الصفقة التوضيحية» / «هذا الإجراء محلي فقط.» / «متابعة» | «إغلاق الصفقة؟» / «تُغلق الصفقة التوضيحية كاملة، ويصلك إيصال التنفيذ في المحادثة.» / «إلغاء» + «إغلاق الصفقة» | defect (words ≠ action) |
| `[data-do="trade-edit"]` sheet, `data-form="trade"` | Trades | «تعديل صفقة توضيحية» / «متابعة» | «تعديل الوقف والهدف» / «حفظ التعديل». Price fields left-to-right | defect (words ≠ action) |
| route `trades` without account | Trades | «اربط حساب تداول أولًا من الإعدادات.» and nothing to tap | One sentence + «اختيار الحساب» or «ربط حساب في المحادثة» | defect (dead end) |
| `.wt-acts` → `#nx-wt-more-‹watch›` (`wt-menu`) | Watches sheet · agent page | Three small buttons per row: «إيقاف مؤقت», «تمديد ساعتين», «إلغاء» | One «⋯» per row. The menu holds «إيقاف مؤقت / استئناف», «تمديد ساعتين», «إلغاء المراقبة» | simpler (secondary actions in a menu) |
| order from chat | Chat | «أعددتُ الأمر. وافق عليه…», «التداول متوقف حاليًا…», «خارج نطاق التفويض الموقَّع…» | Ask: a Trade Approval card with the agent's reason. Full: «أرسلتُ شراء 0.10 ذهب بسعر السوق إلى الوسيط.» then the receipt | simpler |
| agent status «بانتظار قرارك» | Chat header · agent sheet | «قرار مطلوب: التنفيذ المفوَّض» | «قرار مطلوب: طلب موافقة» | removed |
| `.safety-row .safety-cap` | Chat (trading agent, under the header) | «التداول متوقف», a restriction with its time, unconfirmed operations | Shown only for unconfirmed operations: «عملية غير مؤكدة» (opens the trading sheet) | removed (Stop, restrictions) |
| `modeLine()` on the agent page and trading sheet | Agent page · التداول | «دون تنفيذ · …», «تنفيذ مفوَّض · جميع الأزواج · حد الخسارة اليومي…», «دون حد مالي» | «التفويض: يستأذن» or «التفويض: وكّله», and one plain line under it («عملية غير مؤكدة بانتظارك» when there is one) | removed (limits), simpler |
| Lonora's brief (planned preview) | Chat (Lonora) | «قيود نشطة على الصفقات الجديدة», «لم يُلمس حد الخسارة اليومي» | Removed | removed |
| Lonora's reply about a team agent | Chat (Lonora) | «لا أشرف على ‹agent› حاليًا… إضافة ‹agent› إلى إشرافي» | Lonora reads the team's work without a grant | removed (supervision) |
| words in the agent's reason / sent line | Chat | «شراء 0.10 الذهب», sell target «عند المقاومة التالية» | «شراء 0.10 ذهب», sell target «عند الدعم التالي» | defect (wrong words) |
| small controls (see UI_BUGS.md) | All | Tap areas of 19–42px | An invisible hit area of at least 44px. Size and look unchanged | defect |
| small grey text (see UI_BUGS.md) | Several | `--faint` text at about 3.6:1 | `--muted` (an existing token) | defect |
| `.mode-chip.lvl-autonomous` | Chat (light) | «وكّله» words in amber, 3.6:1 | Words in the text color. Amber icon kept | defect |
| `.mic-tip` | Chat | The one-time tip stayed over other screens and covered «رفض» | Removed when the route changes | defect |
| chat-prefs `agentStatus` row | Settings › chat | Description cut after two lines | Shorter true sentence. Setting rows with a switch never cut their description | defect |
| `mdInline()` | Chat (agent text, tables) | «(+$239)» shown as «(239$+)» | Signed numbers isolated left-to-right | defect |
| `snippet()`, `previewSearch()` | Chats list · replies · banners · search | Raw «**», «###», table pipes. Signed numbers reversed | One plain line | defect |
| Words that still named permissions | Group chat, group page, «+» commands, Help, Terms | «كل وكيل هنا يحتفظ بصلاحياته الخاصة», «لا يحتاج إلى صلاحيات», «كل عضو يحتفظ بصلاحياته…», command «صلاحيات», «…ونموذجه وصلاحياته», «الوكلاء والصلاحيات… سحبها» | «لكل وكيل هنا تفويضه الخاص», «لا يحتاج إلى تفويض», «لكل عضو تفويضه. لا يوجد تفويض مشترك للمجموعة.», command «التفويض», «…دوره ونموذجه», «الوكلاء والتفويض: «يستأذن» أو «وكّله»…» | removed (old vocabulary) |
| `.mp-back` on the model page | Chat › mode menu › النموذج | `aria-label` «رجوع إلى الصلاحيات» | «رجوع إلى التفويض» (the page it returns to) | simpler (one name) |
| focus-session answer | Chat (generated card) | «…في سجل الإجراءات» | Sentence ends at the duration (the log page is removed) | removed |
| developer reference comment | Inside the file (not shown) | Described v37 only | A v38 note at its top lists what replaced what | simpler |
| Lab (developer only) | Settings › Lab | Grants, limits, lifts, passkey device, emergency rule, notices | The fixed cards: Trade Approval and its states, Mandate, Secret, Settle | removed |
| older saves (`seedV38`) | Start-up | Old levels, grants, limits, goals, notices, supervision | Mapped once: analysis/supervised → «يستأذن», autonomous → «وكّله». Removed items dropped | removed |

### Patterns taken from open-webui and open-intelligent-ui

Same tokens, icons and screens. These change how the app behaves across browsers and devices; nothing new appears on screen.

| id or selector | screen | before | after | why |
|---|---|---|---|---|
| `body` safe-area padding, mobile `dialog`, `#headsup` | All (phones in landscape) | `viewport-fit=cover` but only top and bottom insets were used. Header, composer, tab bar and sheets ran under the notch and rounded corners | Left and right safe areas are respected. Zero on devices without them | defect |
| `html` | All | Text could be inflated by iOS on rotation | `text-size-adjust: 100%` | defect |
| `meta[name="theme-color"]`, `initial.theme` | First visit | Always dark. The browser bar started at #111111, a color the app does not use | A first visit follows the device's light or dark setting. A saved choice always wins. The bar starts at the app's own #0B0C10 | simpler |
| `#app.list-collapsed` (`desktop-collapse`) | Desktop (900px and wider) | The folded chat list unfolded on every reload. The rail arrow pointed the same way folded or not | The fold is remembered (`S.listCollapsed`). The arrow flips when folded | defect |
| `#toast.has-action` | All | A toast with «تراجع» disappeared after 5.2s, even with the pointer or focus on it | It waits while reached for, then 2.4s more. Plain toasts are unchanged | defect (timing) |
| `#headsup` | All (message in another chat) | Hid after 5.2s while the pointer was on «رد» | Waits while reached for, then 2.4s more | defect (timing) |
| `textBody()` `.text`, `.md`, `.pv`, `.quote-text`, `.search-hit-sub`, `#headsup small` | Chat, chats list, replies, search, banner | Latin-only text took the Arabic direction: «Hello, ready?» read «?Hello, ready» | Text with no Arabic letter reads left-to-right. Text with any Arabic letter stays right-to-left, even when it starts with «XAUUSD» | defect |
| `.oa-dl` rows | Trade Approval, Receipt, Settle, order sheet | At 320px «2346.80 ± 1.50» broke across two lines | A number stays on one line; the label wraps instead | defect |
| `.ux-grid`, `.ux-stat small` | Generated answer cards | Fixed columns: at 320px three KPI tiles squeezed to 58px and «نجاح الصفقات» was cut with «…» | Columns follow the card's own width: a tile stays at least 96px, then the grid wraps. Labels wrap instead of being cut. Unchanged at 390px and wider | defect |
| `.row small` | Lists (integrations, trades, settings) | Second lines cut after two lines at 320px | Up to three lines at 360px and narrower | defect |

## New hooks ("nx-")

| new hook | screen | what it is |
|---|---|---|
| `#nx-wt-more-‹watchId›` | Watches sheet, agent page | The «⋯» button of one watch row. Opens the watch menu |
| `#nx-mandate-‹messageId›` | Chat | Root of the Mandate card |
| `#nx-receipt-‹messageId›` | Chat | Root of the Execution Receipt card |
| `#nx-attention-list` | يحتاج انتباهك | The one list |
| action `wt-menu` | Watches | Opens the menu for `#nx-wt-more-‹id›` |
| class `act-receipt` | Chat | Execution Receipt card |
| class `act-trading_mode` | Chat | Mandate card |
| class `st-pending` on `.mcard` | Chat | Trade Approval waiting for the owner. The other states use the existing `st-approved`, `st-rejected`, `st-drifted`, `st-withdrawn` |

## Removed hooks

Every id, class, `data-*` attribute and value, action and route from v37 is still in v38, except the ones below. Two hooks only look missing to a text search: `data-sheet="safety"` is still set through `sheet(…,{id:"safety"})`, and `st-superseded` is still set through `st-${state}` (a Secret card replaced by a newer one).

The removed classes below are no longer produced by any markup. Their old CSS rules were left untouched and unused.

**Removed ids**

| id | screen | element |
|---|---|---|
| `mk-l-‹messageId›` | Chat (delegation card) | Label «الأسواق» of the markets picker |

**Removed classes**

| class | screen | element |
|---|---|---|
| `all` | Delegation card | «جميع رموز الحساب» option (`.oa-dd-opt.all`) |
| `col` | Delegation card | Markets field (`.oa-f.col`) |
| `danger-opt` | Mode menu, page 2 | «تأكيد: …» when leaving Full |
| `edit` | Account-limits card | Limit being edited (`.oa-lim.edit`) |
| `is-busy` | Passkey steps | Busy «تسجيل الجهاز» / «التوقيع» button |
| `k-notice` | Chat | «تراجع» notice line |
| `ring` | المستجدات | Agent story ring |
| `s-‹state›` | Chat | Order line `.od-chat` (replaced by the Execution Receipt) |
| `sf-switch` | Trading sheet | Trading on/off switch |
| `soon` | Cards | Countdown close to expiry (`.oa-exp.soon`) |
| `undone` | Chat | Notice after «تراجع» |

**Removed `data-*` attributes and values**

| hook | screen | element |
|---|---|---|
| `data-cred` | Credential sheet | Paste field |
| `data-oa-exp` | Cards | Countdown |
| `data-oa-in="dev"` | Passkey step | Device name field |
| `data-oa-in="note"`, `data-oa-in="ref"` | Resolve card | Note and broker reference |
| `data-sheet="oa"` | Sheet | Owner-action sheet (delegation, limits, lift) |
| `data-sheet="emergency"` | Agent page | Emergency rule |
| `data-sheet="sup"` | Agent page | Supervision picker |
| `data-form="broker"` | Settings | Broker form (now chat + Secret card) |
| `data-form="goal"` | Agent page | Goal form |
| `data-form="permission-custom"` | Delegation sheet | Custom delegation form |

**Removed routes:** `activity` (سجل الإجراءات), `goals`, `new-goal` (الأهداف).

**Removed actions** (with their buttons):
- Delegation and passkey: `activate-permission`, `customize-permission`, `permission-details`, `permissions`, `oa-go`, `oa-sign`, `oa-device`, `oa-back`, `oa-set`, `oa-tog`, `oa-num`, `oa-mk`, `oa-mkall`, `oa-mksym`, `oa-lim`, `oa-cancel`, `oa-more`, `mp-down-ok`.
- Trading switch, limits and restrictions: `sf-trading`, `sf-pause`, `sf-resume`, `sf-limits`, `sf-lift`, `sf-noacct`.
- Emergency rule: `ag-emg`, `ag-emg-sign`.
- Supervision: `ag-newsup`, `ag-sup-add`, `ag-sup-pick`, `ag-sup-save`, `ag-sup-one`, `ag-unsup`.
- Old credential sheet: `cap-cred-save`.
- Notices: `oa-undo-notice`.
- Lab: `lab-device`, `lab-notice`.

## Questions

These need a new screen, setting or behaviour, so they were not added:

1. **Agent page: «الطريقة» and per-agent tasks.** Lonora's agent pages have "method and skills" and "tasks". v37 has only «المهارات» and a global «المهام» tab. Should there be a «الطريقة» page and a «المهام» row on the agent page?
2. **«ما يجري الآن».** VISION 7.1.5 describes a view that lists running workspace processes, with one tap to stop each. v37 has no such screen. Add it?
3. **Agents that do not trade.** «مساعد الأبحاث» and «رفيق» show no mode. Is that right, or should every agent show the Mandate?
4. **Usage budget.** Settings › Usage keeps «تعديل الحد» for model spending. It is not a trading limit, so it was kept. Is it still part of Lonora?
5. **Agent pause.** «إيقاف الوكيل مؤقتًا» is kept as the owner's pause (VISION 4.7, Amendment 1). Confirm it should stay on the agent page.
6. **Drift without a price feed.** «خرج السعر عن الهامش» can only be shown from the Lab, because the prototype has no live price. Should normal use simulate drift?
7. **Sell in short Arabic.** The chat understands «بيع 0.20 ذهب» but not «بع 0.20 ذهب», because «بع» clashes with «بعد». Should the demo parser accept it?
8. **Chat-header name.** The name in the chat header is 21px tall. The avatar beside it opens the same page with a 44px area. Making the name 44px would need a different header layout. Change it?

From open-webui and open-intelligent-ui. Each needs a new option, control or server, so none was added:

9. **«حسب النظام» theme.** open-webui has a theme that keeps following the device's light/dark setting. v38 follows it only on a first visit. Add the option to the theme switch?
10. **Show/hide on the Secret card.** open-webui lets the owner reveal a key while typing it. The Secret card's buttons come from the server, so the server would have to supply this one. Add it?
11. **Time in «يحتاج انتباهك».** open-webui's inbox groups items by «اليوم / هذا الأسبوع / أقدم» and shows how long each has waited. Show the waiting time on each row?
12. **Resizable chat list.** open-webui lets you drag the sidebar edge on desktop. v38 only folds and unfolds the list. Add dragging?
13. **A real connection check.** open-webui verifies a provider or MCP connection against the server. The prototype has no server, so «فحص الحقول» only checks the fields. Wire it to the server when there is one?
