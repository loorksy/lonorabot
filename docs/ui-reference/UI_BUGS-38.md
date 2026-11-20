# UI_BUGS — defects found in Lonora-Desktop-37.html and fixed in Lonora-Desktop-38.html

Found by an automated pass over 63 screens, sheets, menus and cards at 390px and 1280px, light and dark (tap size, contrast, cut text, raw ids, number order, overflow, console errors), and by reading every screen and flow.

v37 had no horizontal overflow, no console errors and no screen that could not be left. "all" means 390 and 1280, light and dark. Contrast is measured on the real background.

| id or selector | screen | defect | fix applied | width / theme where seen |
|---|---|---|---|---|
| `.icon` (back, close, more, header buttons) | Most screens and sheets | Tap area 32–42px | Invisible hit area of at least 44px. Size and look unchanged | all |
| `.icon.cbtn`, `.icon.voice` | Chat (composer) | 40px | 44px hit area | all |
| `.head-avatar` | Chat header | 40px | 44px hit area | all |
| `.icon.u-view` | Settings › Usage | 36px | 44px hit area | all |
| `.pencil` | Agent page, identity, new agent | 34px | 44px hit area | all |
| `.switch` | Settings rows, schedules, skills, notifications | 48×28px | 44px hit area (`::after`, `::before` is the thumb) | all |
| `.btn.sm`, `.btn.small` | Cards, integrations, profile, sheets | 30–36px tall | 44px hit area | all |
| `[data-do="notif-ask"]` «تفعيل» | Settings › notifications | 63×36px | 44px hit area. Class `sm`, like the app's other small buttons | all |
| `.tabs>button` | Tasks, Usage | 36px tall | 44px hit area | all |
| `.chip` (list filters, «+») | Chats list | 40px tall | 44px hit area | 1280 light, dark |
| `.mode-chip` | Chat (composer) | 40px tall | 44px hit area | all |
| `.safety-cap` | Chat (trading agent) | 30px tall | 44px hit area | all |
| `.sg-take` | Chat (suggestions) | 36×26px | 44px hit area | all |
| `.u-link` | Settings › Usage | 36px tall | 44px hit area | all |
| `.ver-tap` | Settings › About | 30px tall | 44px hit area | all |
| `.link`, `.oa-link`, `.sup-line`, `.oa-line-body` | المستجدات, resolve card, agent page, notice lines | 19–42px | Removed with their features (see UI_CHANGES.md) | all |
| `.mcard-note` | Chat › approval card | «محاكاة محلية؛ لا يحدث تنفيذ خارجي» at 3.63:1 (dark), 3.41:1 (light), 12px | Note removed. `.mcard-note` uses `--muted` | all |
| `.pop-note` | Chat › mode menu | «محاكاة واجهة؛ لا تُمنح صلاحيات مالية حقيقية» at 2.66–4.07:1, 12px | Note removed. `.pop-note` uses `--muted` | all (worst: 1280 light) |
| `.tpl-row .tpl-code` | New agent › type | Internal codes («دور متخصّص · سوق محدَّد») at 3.63:1 / 3.41:1, 11px | Removed | all |
| `.welcome small` | Desktop welcome | 3.93:1 (dark), 3.13:1 (light), 12px | `--muted` | 1280 light, dark |
| `.oa-line .sep` | Notice and decision lines | «·» at 3.63:1 / 3.41:1 | Removed with the lines | all |
| `.u-yaxis`, `.u-xaxis`, `.ux-plot .yl`, `.ux-plot .xl` | Settings › Usage, chart cards | Axis labels at 3.63:1 (dark), 3.41:1 (light), 10.5px | `--muted` | all |
| `.as-sec`, `.as-end`, `.as-foot`, `.arch-note`, `.meta .stopped`, `.meta .edited`, `.st-t small`, `.auth-legal`, `.kbd-list .keys`, `.ux-field>label small`, `.ux-ci-t small`, `.oa-l small`, `.oa-input>span small`, `.od-line li.next` | Search, archive, messages, status, sign-in, shortcuts, generated cards, owner cards, order timeline | Small text in `--faint`: 3.63:1 (dark), 3.41:1 (light) | `--muted` (an existing token, 4.5:1 or more). `--faint` stays for icons and rules | all |
| `.mode-chip.lvl-autonomous` | Chat (composer, agent in Full) | Amber words at 3.6:1 | Words in the text color. Amber icon kept | 390 and 1280, light |
| `.oa-line-text` | Chat › resolve and decision lines | Decision text cut after one line («التغيير: سُجّلت العملية منفَّذ…») | Removed. The fixed cards are never folded | 390 light, dark |
| `.row small` in `agentStatus` | Settings › chat | Description cut after two lines («تحت اسم الوكيل: يحلّل، يبحث، ي…») | Shorter true sentence. Rows with a switch never cut their description | 390 light, dark |
| `#dialog[data-sheet="mcp"]` tool rows | Settings › MCP server | Raw tool names `search_news`, `get_article`, `save_note` (and `set_alert` after a schema change) | Arabic names: «البحث في الأخبار», «قراءة مقال», «حفظ ملاحظة», «ضبط تنبيه» | all |
| `.od-tech` | Trades › order sheet › «التفاصيل التقنية» | Raw ids and codes: OP-…, cl-…, TRADE_RETCODE_… | Section removed. The sheet shows the broker ticket and the account | all (when opened) |
| `[data-do="test-connection"]` | Settings › providers, MCP form | «اختبار الاتصال» only checks the fields; nothing connects | «فحص الحقول». Result: «الحقول مكتملة. لم يُتصل بمزود أو خادم خارجي.» | all |
| `[data-do="trade-close"]` sheet | Agent › الصفقات | Close action labelled «متابعة», with «هذا الإجراء محلي فقط.» | «إغلاق الصفقة» and «إلغاء», with a true sentence about the receipt | all |
| `[data-do="trade-edit"]` sheet | Agent › الصفقات | Save labelled «متابعة» | «حفظ التعديل» | all |
| `#dialog[data-sheet="tools"]` identity row | Chat › «+» | Sub «مراجعة صلاحيات الوكيل بالتفصيل», but the row opens name, role and model | «الاسم والدور والنموذج» | all |
| route `trades` without an account | Agent › الصفقات | Dead end: «اربط حساب تداول أولًا من الإعدادات.» with nothing to tap | Same sentence + «اختيار الحساب» or «ربط حساب في المحادثة» | all |
| `requestTrade()` | Agent › الصفقات | The owner's own close/edit posted an approval card asking the owner to approve himself, or opened a «دون تنفيذ» sheet | Runs once. The Execution Receipt arrives in the agent's chat | all |
| `.mic-tip` | Chat | The one-time mic tip stayed on screen after leaving the chat and covered the «رفض» button of an approval card | Removed when the route changes | 390 light, dark |
| `mdInline()` | Chat (agent text, generated tables) | Signed numbers reversed in Arabic lines: «(+$239)» read «(239$+)», «(+3.1%)» read «(3.1%+)» | Each signed number isolated left-to-right (`<bdi dir="ltr">`) | all |
| `snippet()`, `previewSearch()` | Chats list, reply quotes, banners, search | Raw markdown «**أفضل يوم:**», «###», table pipes. Signed numbers reversed | One plain line; signed numbers isolated | all |
| `.u-actions [data-do="budget"]` | Settings › Usage | «تعديل الحد» twice for one action | Once, on its card | all |
| agent reason for a sell | Chat | Sell orders said «والهدف عند المقاومة التالية» | «والهدف عند الدعم التالي» | all |
| `[data-do="toggle-agent"]` | Agent page | «إيقاف الوكيل» while the state it sets reads «متوقف مؤقتًا» | «إيقاف الوكيل مؤقتًا» / «استئناف الوكيل» | all |

### Found while adapting to more browsers and sizes (patterns from open-webui and open-intelligent-ui)

| id or selector | screen | defect | fix applied | width / theme where seen |
|---|---|---|---|---|
| `body`, mobile `dialog`, `#headsup` | All | `viewport-fit=cover` without left/right safe areas: header buttons, composer, tab bar and sheets ran under the notch and rounded corners | Left/right `env(safe-area-inset-*)` on the page, the mobile sheet and the banner | 844×390 landscape with iPhone insets (47px), light and dark |
| `.oa-dl dd .ltr` | Trade Approval | «2346.80 ± 1.50» broke into «2346.80 ±» / «1.50» | Numbers stay on one line; the label wraps | 320, light and dark |
| `.ux-stat small`, `.ux-grid` | Generated answer cards | KPI label «نجاح الصفقات» cut with «…» in 58px tiles | Grid columns follow the card width (tiles at least 96px); labels wrap | 320, light and dark |
| `.row small` | Settings › Integrations, trades | Row second lines cut after two lines («خادم MCP · 2 قراءة · 1 كتابة غ…», «13:15 · بسعر السوق · 2344…») | Up to three lines at 360px and narrower | 320, light and dark |
| `.text`, `.md`, `.pv`, `.quote-text`, `.search-hit-sub`, `#headsup small` | Chat, chats list, replies, search, banner | Latin-only text took the Arabic direction: «Hello, ready?» read «?Hello, ready» | Text with no Arabic letter reads left-to-right | all |
| `#toast.has-action` | All | «تراجع» toast hid after 5.2s even with the pointer or focus on it | Waits while reached for, then 2.4s | 1280 (pointer), all (keyboard) |
| `#headsup` | All | Banner hid after 5.2s while the pointer was on «رد» | Waits while reached for, then 2.4s | 1280 (pointer), all (keyboard) |
| `#app.list-collapsed` | Desktop | The folded chat list unfolded on every reload; the rail arrow never changed direction | Fold remembered; arrow flips | 900 and wider, light and dark |
| `initial.theme`, `meta[name="theme-color"]` | First visit | Always dark on a light device; the browser bar started at #111111 | Follows the device on a first visit; bar starts at #0B0C10 | all |

## Not changed

| id or selector | screen | defect | why not changed | width / theme where seen |
|---|---|---|---|---|
| `.chat-name` | Chat header | The name is 21px tall | The avatar beside it opens the same page with a 44px area. A 44px name needs a new header layout (UI_CHANGES.md, Question 8) | all |
| `.pv span` | Chats list | Last-message preview ends with «…» | Intended: one line per chat. The chat shows the whole message | all |
