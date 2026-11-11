# Reference 37: audit of the web app, November 2026

The web app was compared with `Lonora-Desktop-37.html`, `DESIGN_TREE_37.md` and the owner's own comparison report
(52 rows), surface by surface, at phone and desktop size. Each difference an auditor reported was checked by a
second reader before it counted. 174 were reported and 162 confirmed. The full entries (reference evidence, app
evidence, what the owner sees, the suggested fix, the verifier's note) are in `audit-37-gaps.json`.

Differences the owner's decisions (`OWNER_DECISIONS.md`) call for are not gaps and are not listed: no «حول» section,
no support or bug sheets, no terms or privacy pages, no privacy data actions, no browser notification settings, no
spend cap.

Confirmed gaps: 15 high, 56 medium, 91 low. The work is split into packages; the last two
columns say which package and step fixes each gap.

| Gap | Severity | Where | What the owner sees | Package | Step |
| --- | --- | --- | --- | --- | --- |
| agent_pages-1 | high | both | Chat header avatar/name and ⋮ «معلومات الوكيل» open the old edit-form sheet, not the agent page | chat | info-and-menu |
| agent_pages-2 | high | both | Group chat avatar/name opens the old GroupSettings toggle form instead of the group page | chat | info-and-menu |
| auth_states-1 | high | both | Startup failure shows an unstyled error card instead of the maintenance screen | tokens | boot-and-states |
| chat_header-2 | high | both | «معلومات الوكيل/المجموعة» (avatar, name, ⋮ row) opens the old AgentSettings/GroupSettings form in a sheet instead of the agent or group page | chat | info-and-menu |
| cleanliness-1 | high | both | «المهارات» in the + sheet opens the Settings root (dead end) | composer | sheet-and-mentions |
| composer-1 | high | both | Slash commands (/) are missing entirely, but the shortcuts sheet still advertises them | composer | slash-commands |
| composer-3 | high | both | «المهارات» in the + sheet throws the owner out of the chat to the Settings root | composer | sheet-and-mentions |
| navigation-2 | high | both | Scroll position is not remembered: going back to a page always lands at the top | shell | scroll-and-lens |
| settings_b-1 | high | both | Trading account page shows an empty balance (and loses broker name/server) | settings | integrations-detail |
| settings_root-4 | high | both | «الصوت» is a dead end, and the Q58 «Open voice settings» button lands on it | settings | legacy-trio |
| sheets_overlays-1 | high | both | Tapping the chat header (avatar or name) opens an old «معلومات الوكيل» settings sheet instead of the agent page | chat | info-and-menu |
| shell_phone-1 | high | phone | Tab lens slides twice after every phone tab change (snaps back to the old tab, then springs again) | shell | scroll-and-lens |
| shell_phone-2 | high | phone | Scroll position per page is lost: switching tabs or returning from an inner page or a chat lands at the top, and the chat-list filters reappear | shell | scroll-and-lens |
| tokens-1 | high | both | Two token systems share --muted/--accent/--primary with opposite meanings: Knowledge tab labels are invisible | tokens | palette |
| updates_tasks-1 | high | both | Updates alerts show every history row: duplicates and stale «التداول الجديد متوقف» rows | updates | alerts |
| agent_pages-3 | medium | both | Agent page «التداول والأمان» row leaves the page for the chat instead of opening the sheet in place | agent | agent-page |
| agent_pages-4 | medium | both | Agent page watches lack «مراقبة جديدة» and «تمديد ساعتين» | agent | agent-page |
| agent_pages-7 | medium | both | Every «outline» button gets an extra blue 1px ring from a Tailwind utility clash | tokens | palette |
| auth_states-3 | medium | both | Field errors are not shown under each field; forms use one summary line, toasts or browser bubbles | forms | errors-and-loading |
| auth_states-7 | medium | both | Server down mid-session never reaches the maintenance screen when the proxy answers 502/504 or the request fails | tokens | boot-and-states |
| calls_motion-1 | medium | both | Theme switch never shows the growing circle: the new theme appears at once | profile | theme-switch |
| calls_motion-3 | medium | phone | During a call the chat header cuts off the call duration («في مكالمة · …») | chat | wallpaper-and-status |
| chat_header-1 | medium | both | The ⋮ chat menu opens as a bottom sheet (centred modal on desktop) instead of the reference's popover beside the button | chat | info-and-menu |
| chat_header-3 | medium | both | «مسح المحادثة» (red, with confirmation) is missing from the ⋮ menu | chat | info-and-menu |
| chat_header-4 | medium | both | Chat background cannot be chosen: wallpaper hard-coded to «Lonora» at «خفيفة», no picker sheet, no 0.3s fade | chat | wallpaper-and-status |
| chat_header-6 | medium | both | ⋮ menu adds «المعرفة», «الأهداف», «المهام المجدولة», which repeat the agent page and the «+» sheet and open old panels | chat | info-and-menu |
| chats_list-1 | medium | both | A task result in unified search opens the Tasks board, not that task | updates | tasks-and-search |
| cleanliness-11 | medium | both | Two icon sets: lucide-react still renders in reachable surfaces | tokens | icons |
| cleanliness-12 | medium | both | Second token system (shadcn grey palette and .legacy-surface button rules) still live | tokens | palette |
| cleanliness-2 | medium | both | Chat header avatar/name and ⋮ «معلومات الوكيل» open the old AgentSettings form in a sheet, not the agent page | chat | info-and-menu |
| cleanliness-3 | medium | both | ⋮ menu has extra «المعرفة»/«الأهداف»/«المهام المجدولة» rows that open old screens, duplicating the agent page | chat | info-and-menu |
| cleanliness-4 | medium | both | Settings rows «النماذج العالمية»/«الصوت»/«التداول» open the old SettingsOverlay with its own tab bar and palette | settings | legacy-trio |
| cleanliness-7 | medium | both | + sheet «جدولة» opens an empty schedules list instead of the new-schedule form | composer | sheet-and-mentions |
| cleanliness-9 | medium | both | A search result for a file opens the old Artifacts viewer, not the files page editor | updates | tasks-and-search |
| composer-10 | medium | both | @ list shows the raw role «personal» for Lonora and rows do not fill the list width | composer | sheet-and-mentions |
| composer-11 | medium | both | No «@الكل» in group chats | composer | all-mention-and-upload |
| composer-2 | medium | both | The permission menu is a plain popover, not the morph out of the composer; no drag-to-close or side-drag back | popover | permission-morph |
| composer-4 | medium | both | Composer menu links land on the old legacy Settings tabs («ربط مزوّد نماذج», «اختيار حساب التداول») | popover | model-page |
| composer-7 | medium | both | «الصلاحية» in the + sheet is not a page inside the sheet | permsheet | permission-page |
| messages-1 | medium | both | Streaming reply arrives in bursts, not two words every 34-68ms | messages | reply-prefs |
| messages-3 | medium | both | «تحويل إلى مهمة» only shows a toast; no «أُنشئت مهمة · عرض المهمة» card in the chat | messages | bubbles-and-cards |
| messages-4 | medium | both | Bubble width ignores the reference's 68% (desktop) and 88% (phone ≤430px) caps | messages | bubbles-and-cards |
| messages-6 | medium | both | Unstyled raw error line «تعذر إكمال الطلب. أعد المحاولة.» appears in the transcript when offline | messages | bubbles-and-cards |
| navigation-1 | medium | both | System Back with the permission menu (or any popover) open leaves the chat and leaves the menu floating on the next page | popover | history-and-polish |
| navigation-3 | medium | both | «النماذج العالمية · الصوت · التداول» open an old tabbed screen with no back button, its own tab strip, and a ?tab= that does not follow the tab | settings | legacy-trio |
| settings_a-1 | medium | both | «تجربة المحادثة» is missing «بث الرد كلمة بكلمة» and «تنسيق الردود» under الردود | messages | reply-prefs |
| settings_a-12 | medium | both | The «الجهاز» section disappears when no passkey device exists, and «مكالمة» can be chosen with nothing to ring | profile | owner-and-notify |
| settings_a-13 | medium | both | Per-agent «التواصل الاستباقي» defaults allow calls and set no daily limit (the reference has calls off and a limit of 5) | profile | owner-and-notify |
| settings_a-2 | medium | both | The «الواجهات التفاعلية» section (عناصر تفاعلية في الردود · سبب اختيار الواجهة) is missing | messages | reply-prefs |
| settings_a-7 | medium | both | Time zone is a raw list of 419 IANA identifiers, not the reference's five Arabic names | profile | owner-and-notify |
| settings_a-8 | medium | both | The primary «حفظ» is disabled until an edit, so it shows as a grey bar instead of the ivory primary | profile | owner-and-notify |
| settings_b-2 | medium | both | «النماذج العالمية» opens the old settings overlay with its own provider/key form | settings | legacy-trio |
| settings_b-3 | medium | both | «التداول» settings row opens an old duplicate broker form and hides the trading stop/resume control in the old look | settings | legacy-trio |
| settings_b-4 | medium | both | Voice settings is a dead end with untranslated GPT-Live/WebRTC copy (Q58 target) | settings | legacy-trio |
| settings_b-6 | medium | both | Provider form has no «النموذج» field; provider rows show no model and cannot be removed | settings | integrations-detail |
| settings_root-1 | medium | both | «خلفية المحادثة» row and sheet are missing; the wallpaper is fixed to Lonora at the light level | chat | wallpaper-and-status |
| settings_root-2 | medium | both | The old tabbed settings screen (?tab=models/voice/trading) traps navigation: the address does not follow the tab, there is no back button, and the Settings tab does not leave it | settings | legacy-trio |
| settings_root-3 | medium | both | «النماذج العالمية» duplicates the provider key form and keeps model routing and allowed models in old cards outside «مزوّدو النماذج» | settings | legacy-trio |
| settings_root-5 | medium | both | «التداول» settings tab duplicates the global brake and an old broker form; «اربط حسابًا» on the agent page goes there instead of the broker form | settings | legacy-trio |
| settings_root-6 | medium | both | «ربط مزوّد نماذج» (composer model menu) and the model error card's fix button open the old ?tab=models screen instead of «مزوّدو النماذج» | settings | legacy-trio |
| settings_root-7 | medium | both | Night-mode switch: the circle reveal never plays; the theme swaps at once | profile | theme-switch |
| sheets_overlays-2 | medium | both | The chat ⋮ menu is a full bottom sheet, not the reference popover, and it lacks «خلفية المحادثة» and «مسح المحادثة» | chat | info-and-menu |
| sheets_overlays-6 | medium | both | Native <select> is still used in many forms; only SelectField has the custom listbox | forms | select |
| sheets_overlays-7 | medium | both | SelectField listbox: no upward opening, no keyboard navigation, no Home/End, no type-ahead, no pair icons | forms | select |
| sheets_overlays-8 | medium | both | System Back does not close an open popover menu first | popover | history-and-polish |
| shell_desktop-1 | medium | desktop | Desktop welcome greets the e-mail local part and ignores the owner's chosen name or form of address | profile | owner-and-notify |
| tokens-2 | medium | both | Rich (v1) agent replies render Markdown with the old palette: grey code chips, blue links, grey table headers | tokens | palette |
| tokens-3 | medium | both | Legacy-palette screens are still reachable from settings and chat (old cards, 9px radii, #ececee text, internal tab strip) | settings | skills-and-old-pages |
| updates_tasks-3 | medium | both | «تحديد الكل كمقروء» leaves critical alerts unread and stays visible; the tab dot and the page count different items | updates | alerts |
| updates_tasks-6 | medium | both | «عند تحقق شرط» and the condition field are missing unless a linked trading agent is picked | updates | tasks-and-search |
| updates_tasks-7 | medium | both | Conditional schedules (watches) are missing from المهام › مجدولة and from «المواعيد القادمة» | updates | tasks-and-search |
| agent_pages-5 | low | both | New-agent flow is one route with hidden steps: wrong titles, and header back leaves the flow | agent | new-agent-flow |
| agent_pages-6 | low | both | Trading-setup account/pair fields use the old BrokerPairPicker look and the old «بوت التداول» wording | agent | new-agent-flow |
| agent_pages-8 | low | both | «يشرف على» section shown on every agent, not only on supervisors | agent | agent-page |
| auth_states-2 | low | both | Boot screen «جارٍ فتح مساحة العمل…» with a plain letter L is the old look | tokens | boot-and-states |
| auth_states-4 | low | both | Several data pages show a blank area while loading instead of a skeleton | forms | errors-and-loading |
| auth_states-6 | low | both | No upload ring with percentage and cancel for attachments | composer | all-mention-and-upload |
| auth_states-8 | low | both | An unknown one-segment route shows the 404 inside a chat header | shell | desktop-and-routes |
| auth_states-9 | low | both | Sign-in and setup headings are regular weight instead of bold | tokens | palette |
| calls_motion-2 | low | both | The permission menu does not take shape out of the composer; it opens as a small floating popover | popover | permission-morph |
| calls_motion-4 | low | both | The call capsule's mute and press changes are abrupt (transitions missing) | shell | desktop-and-routes |
| calls_motion-5 | low | both | The call screen's wave stops moving whenever nobody is speaking | shell | desktop-and-routes |
| calls_motion-6 | low | both | The chat wallpaper does not fade in when a conversation opens | chat | wallpaper-and-status |
| calls_motion-7 | low | both | Select menus and the skin-tone picker appear without their pop-in | popover | history-and-polish |
| calls_motion-8 | low | phone | Tab-bar fold and chats-header search use a third easing and stretch the search field | shell | scroll-and-lens |
| chat_header-10 | low | both | Gold star after Lonora's name in the chat header uses a lucide icon, a hard-coded colour and inline styles | chat | wallpaper-and-status |
| chat_header-11 | low | both | The ⋮ button stays disabled until agents and groups finish loading | chat | info-and-menu |
| chat_header-12 | low | both | The detailed status line can show words outside the reference vocabulary («يعمل», «الخدمة تحتاج إلى انتباه») | chat | wallpaper-and-status |
| chat_header-5 | low | both | Settings has no «خلفية المحادثة» row under the appearance group | chat | wallpaper-and-status |
| chat_header-7 | low | both | «الشارت» appears for every agent, and «المراقبات» does not require a linked account | chat | info-and-menu |
| chat_header-8 | low | both | Group ⋮ menu shows «ملفات الوكيل» | chat | info-and-menu |
| chat_header-9 | low | both | «مهمة جديدة» from the chat loses the chat's agent | chat | info-and-menu |
| chats_list-3 | low | phone | Tapping empty space under the search results does not close the search | shell | desktop-and-routes |
| cleanliness-10 | low | both | Owner time-zone picker lists about 400 raw IANA ids (Asia/Damascus …) | profile | owner-and-notify |
| cleanliness-13 | low | both | Unreachable files from the older interface (about 60 KB) and dead CSS | cleanup | dead-code |
| cleanliness-14 | low | both | Form fields: old screens lack id/name; text inputs on new pages lack autocomplete | forms | errors-and-loading |
| cleanliness-15 | low | both | Boot screen «جارٍ فتح مساحة العمل…» shows a letter «L», not the Lonora bars mark | tokens | boot-and-states |
| cleanliness-5 | low | both | Old pages still reachable at /app/market, /app/trading, /app/memory: double titles, an unreadable tab strip, no reference home | settings | skills-and-old-pages |
| cleanliness-6 | low | both | In-app buttons still send the owner to the old settings tabs instead of the reference pages | settings | legacy-trio |
| cleanliness-8 | low | both | Every live revision refetches about 12 endpoints; version and profile come from several hooks (about 45 requests on load) | cleanup | dead-code |
| composer-12 | low | both | Picked @mentions are not drawn as chips in the field (mirror layer left empty) | composer | sheet-and-mentions |
| composer-13 | low | both | Permission menu: Esc on «النموذج» closes everything and a second chip tap reopens instead of closing | popover | history-and-polish |
| composer-14 | low | both | One-time mic hint («اضغط للإملاء / اضغط مطولًا لتسجيل رسالة صوتية») never shows | composer | sheet-and-mentions |
| composer-5 | low | both | Model page has no 7-day usage bars and no cost total | popover | model-page |
| composer-6 | low | both | Permission menu page 1 bleeds outside the menu while «النموذج» is open | popover | history-and-polish |
| composer-8 | low | both | + sheet rows lack subtitles and keep an extra «رسالة صوتية» row | composer | sheet-and-mentions |
| composer-9 | low | both | «جدولة» opens the routines list instead of the new-schedule form | composer | sheet-and-mentions |
| messages-10 | low | both | Out-of-scope replies have no suggestion rows (.qr-list) under the bubble | messages | rich-content |
| messages-11 | low | both | Answered question card keeps all its option rows instead of collapsing to a check badge | messages | bubbles-and-cards |
| messages-12 | low | both | Live steps header shows «N خطوات» without «· Xث» until the reply is committed | messages | bubbles-and-cards |
| messages-13 | low | both | Waiting and sending bubbles drop their time | messages | bubbles-and-cards |
| messages-14 | low | both | «تحويل إلى مهمة» offered on photo and file messages | messages | bubbles-and-cards |
| messages-2 | low | both | Message menu lacks «عرض كنص / عرض الواجهة» for generated-UI messages | messages | reply-prefs |
| messages-5 | low | both | Empty chat has no large avatar and greets with the e-mail local part («مرحبًا ahmed») | profile | owner-and-notify |
| messages-7 | low | both | No upload ring with cancel in the bubble; uploads block the composer instead | composer | all-mention-and-upload |
| messages-8 | low | both | Supervisor answers have no evidence rows (.ev-list) inside the bubble | messages | rich-content |
| messages-9 | low | both | Slash-command chip never appears in the owner's bubble (no / commands at all) | composer | slash-commands |
| navigation-4 | low | both | Leftover old root pages /app/memory, /app/trading and /app/market in the legacy look | settings | skills-and-old-pages |
| navigation-5 | low | both | Generated UI can navigate to the wrong set of pages, and bypasses the unsaved-edits guard | shell | desktop-and-routes |
| navigation-6 | low | both | Redirects my-profile and reach-me show a 404 | shell | desktop-and-routes |
| settings_a-10 | low | both | The profile hero avatar renders small: there is no `.avatar.big` rule | tokens | palette |
| settings_a-11 | low | both | In «سجل التغييرات», quiet-hours on and off entries look like the same entry twice | profile | owner-and-notify |
| settings_a-14 | low | both | The text-size step reads «الافتراضي» instead of «افتراضي» | profile | owner-and-notify |
| settings_a-3 | low | phone | The «اللمس · الاهتزاز» switch is missing and vibration ignores any preference | messages | reply-prefs |
| settings_a-4 | low | both | The «الكتابة» heading shows «يكتب»: a shared msgid takes the typing-status translation | messages | reply-prefs |
| settings_a-6 | low | both | Contact-method options and the settings value read «الرسالة» and «اتصال» instead of «رسالة» and «مكالمة» | profile | owner-and-notify |
| settings_a-9 | low | both | The profile name field is empty while settings and the avatar show the email name | profile | owner-and-notify |
| settings_b-10 | low | both | Storage page shows the browser quota in MB (4096.00 م.ب) so the bar is empty | settings | integrations-detail |
| settings_b-12 | low | both | Usage «حسب الوكيل» / «حسب النموذج» cards are empty boxes with no empty line | settings | integrations-detail |
| settings_b-13 | low | both | Untranslated identifiers in this area: provider ids, Streamable HTTP, skill ids | settings | integrations-detail |
| settings_b-5 | low | both | Agent page «link an account» goes to the legacy trading tab, not the broker form | agent | agent-page |
| settings_b-7 | low | both | Integrations skills rows lack enable/disable, last used and «الرجوع إلى الإصدار N», and show the raw skill id | settings | skills-and-old-pages |
| settings_b-8 | low | both | Trading account row lacks broker name and symbol count | settings | integrations-detail |
| settings_b-9 | low | both | Symbol cells show a letter placeholder instead of pair icons and Arabic names | settings | integrations-detail |
| settings_root-10 | low | both | Reach-mode value reads «الرسالة» instead of «رسالة» (catalog msgid collision) | profile | owner-and-notify |
| settings_root-11 | low | both | Language menu is a generic menu-pop, not the reference's lang-pop matched to the pill | popover | history-and-polish |
| settings_root-12 | low | both | Version footer shows the static API version «0.2.0», which does not change between deploys | profile | owner-and-notify |
| settings_root-8 | low | both | Install (and permission) sheet steps lose their 1. 2. 3. numbering | tokens | palette |
| settings_root-9 | low | both | Sign-out confirm sheet title lacks the question mark («تسجيل الخروج؟») | profile | owner-and-notify |
| sheets_overlays-11 | low | both | Leftover second overlay system: unused Board.tsx dialogs and the shadcn primitives in @lonora/ui-web | cleanup | dead-code |
| sheets_overlays-3 | low | both | Knowledge and Goals open as old legacy screens inside the sheet, with a duplicated title and a native select | chat | info-and-menu |
| sheets_overlays-4 | low | both | A second avatar editor, «استوديو الأفتار», opens as a shadcn/Base UI dialog stacked over the sheet | agent | agent-page |
| sheets_overlays-5 | low | both | Opening a file or image from a chat uses the old workspace-dialog overlay instead of a «صورة» / file sheet | messages | rich-content |
| sheets_overlays-9 | low | both | «تفاصيل التفويض» falls back to the old AgentPermissions panel with a Base UI popover or dialog inside the sheet | agent | agent-page |
| shell_desktop-2 | low | desktop | Owner avatar initial differs between the rail, the settings and the profile | profile | owner-and-notify |
| shell_desktop-3 | low | desktop | Rail highlights «المحادثات» on pages that belong to Settings or Tasks (Files, new scheduled task, recovery, lab) | shell | desktop-and-routes |
| shell_desktop-4 | low | desktop | Shortcuts sheet shows «Ctrl /» as «Ctrl» followed by a bare slash, not a key | shell | desktop-and-routes |
| shell_desktop-5 | low | both | Boot screen shows a plain letter «L» instead of the Lonora mark | tokens | boot-and-states |
| shell_desktop-6 | low | desktop | ⌘/Ctrl K does nothing while the chat list is collapsed | shell | desktop-and-routes |
| shell_desktop-7 | low | desktop | Clicking outside the ⋮ list menu also opens the chat row under the pointer | popover | history-and-polish |
| shell_phone-4 | low | phone | Lens stretch uses scaleX, which distorts its rounded ends and shadow mid-way; the reference widens the lens itself | shell | scroll-and-lens |
| tokens-4 | low | both | A second, violet accent remains in legacy switches and in the trading mandate sheet | tokens | palette |
| tokens-5 | low | both | Body-level styles still use the old layer: Geist font, --background, 14px/1.65; boot screen shows a placeholder «L» | tokens | palette |
| tokens-6 | low | phone | Initial theme-color, manifest colours and Safari mask-icon are black/violet, not charcoal/ivory | tokens | boot-and-states |
| tokens-7 | low | both | Theme switch: circle lasts 640ms instead of 720ms, and the no-View-Transitions path skips the 280ms thumb slide | profile | theme-switch |
| tokens-8 | low | both | High-contrast is defined twice and the generated tokens are dead, so generative cards ignore «تباين أعلى» | tokens | boot-and-states |
| updates_tasks-10 | low | both | Domain skeletons are 50px avatar rows, unlike the reference's icon rows and tab strip | updates | alerts |
| updates_tasks-2 | low | both | Updates: alerts skeleton beside empty-state text in the other sections; load errors look empty | updates | alerts |
| updates_tasks-4 | low | both | Tapping an alert leaves المستجدات instead of opening its details sheet | updates | alerts |
| updates_tasks-5 | low | both | المهام: going back from «جدولة مهمة» or a task resets the tab to «نشطة» | updates | tasks-and-search |
| updates_tasks-8 | low | both | Empty-state icon sits at the right edge instead of centred above the text | tokens | palette |
| updates_tasks-9 | low | both | Tailwind's `.outline` utility draws a blue 1px ring around every `btn outline` button | tokens | palette |
