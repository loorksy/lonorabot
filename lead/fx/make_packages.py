"""Split the confirmed gaps into packages and steps; write fx/<pkg>/package.json and fx/packages.json."""
import json, os, sys
S = '/tmp/claude-0/-home-user-lonorabot/5d377f24-3ac2-5c89-bb02-ed3686a435ad/scratchpad'
gaps = {g['id']: g for g in json.load(open(f'{S}/work/gaps-confirmed.json'))}

def step(name, ids, notes): return dict(name=name, gaps=ids, notes=notes.strip())

P = {}
P['chat'] = dict(port=8841, wave=1, title='Chat header, the ⋮ chat menu, agent and group info, chat wallpaper',
  owns=['apps/web/src/shell/ChatMenu.tsx', 'apps/web/src/shell/ChatHeader.tsx',
        'the chat-menu, agent-info and members-permissions wiring in apps/web/src/shell/Shell.tsx',
        'apps/web/src/conversation/wallpaper.ts and the wallpaper rules in conversation.css', 'the new wallpaper sheet',
        'the agent status line in packages/core'],
  steps=[
    step('info-and-menu', ['agent_pages-1','agent_pages-2','chat_header-2','sheets_overlays-1','cleanliness-2','chat_header-1','sheets_overlays-2','chat_header-3','chat_header-6','cleanliness-3','chat_header-7','chat_header-8','chat_header-9','chat_header-11','sheets_overlays-3'], '''
Five of these entries are one defect seen by different auditors: the chat header (avatar, name) and the ⋮ row «معلومات الوكيل» / «معلومات المجموعة» must take the owner to the agent page or the group page (see the contracts table), not open the old form in a sheet. Package `agent` runs at the same time and owns AgentPage, GroupPage and IdentityPage; it makes sure those pages offer everything the old forms did. You only change where the chat sends the owner. Do not delete the old form files (pages/shell/bot-settings.tsx, pages/GroupPanel.tsx and so on): a later cleanup removes files nothing imports. Do remove the imports and wrappers your change leaves unused.
The ⋮ menu becomes a popover beside its button, as in the reference, on phone and desktop. Use the existing popover hook. Package `popover` is adding Back and Esc handling inside shell/lists/Popover.tsx itself, so do not add your own history handling and do not edit Popover.tsx.
Menu contents follow the reference for an agent chat and for a group chat, minus what the owner decisions remove. «مسح المحادثة» is red, asks for confirmation, and uses the same hide-history path the chat list's clear action uses (Q1: nothing is deleted). «خلفية المحادثة» is added in the next step, with its sheet.
sheets_overlays-3: after the extra rows leave the menu, check whether anything else still opens Knowledge or Goals as an old screen inside a sheet; if a path remains, send it to the shell's own page.'''),
    step('wallpaper-and-status', ['chat_header-4','chat_header-5','settings_root-1','calls_motion-6','chat_header-10','chat_header-12','calls_motion-3'], '''
The wallpaper choice is a per-device preference: store it the way the other device preferences are stored (find the existing module; do not add a second storage scheme). Build the sheet with the existing sheet system: the reference's patterns and intensity levels, the 0.3 s change fade, and the fade-in when a conversation opens. Add the «خلفية المحادثة» row to the ⋮ menu and to the settings root under the appearance group (SettingsRoot.tsx is edited by other packages too: keep your hunk to that one row).
chat_header-12: the status vocabulary lives in packages/core and is shared with mobile; keep `pnpm check` green for mobile.'''),
  ])
P['popover'] = dict(port=8842, wave=1, title='The popover system and the composer permission menu',
  owns=['apps/web/src/shell/lists/Popover.tsx', 'apps/web/src/conversation/PermissionMenu.tsx', 'the popover and permission-menu rules in the CSS files', 'the overlay-history hook'],
  steps=[
    step('history-and-polish', ['navigation-1','sheets_overlays-8','composer-13','shell_desktop-7','composer-6','calls_motion-7','settings_root-11'], '''
Back and Esc belong in one place: the popover hook. An open popover takes one history layer (reuse the overlay-history hook the sheets use), so system Back closes the popover and stays on the page; in the permission menu, Back on the «النموذج» page returns to its first page (design tree, back-order rules). Every popover in the app gets this from the hook, not from its call sites.
shell_desktop-7: the reference lets the dismissing click through to the row underneath. The owner's own report calls that a bug, so do the sound thing: the click that dismisses a menu does nothing else. Keep it tightly scoped so no later click is swallowed.
settings_root-11: the language menu in the settings root (SettingsRoot.tsx is edited by other packages too: keep your hunk to the language control).'''),
    step('permission-morph', ['composer-2','calls_motion-2'], '''
One piece of work: the permission menu takes shape out of the composer chip (the morph), can be dragged closed, and can be dragged sideways between its pages, with the springs, thresholds and reduced-motion behaviour in the design tree. Use shell/spring.ts. Keyboard and screen-reader behaviour of the menu must not get worse, and Back/Esc from the previous step must still work. Measure the motion in the browser against the reference (sample the element's rect over frames) and report the numbers.'''),
    step('model-page', ['composer-5','composer-4'], '''
composer-4: the two links in the permission menu go to `/app/providers` («ربط مزوّد نماذج») and `/app/broker` (choose or link a trading account); see the contracts table. Package `settings` retargets the same kind of link everywhere else and leaves PermissionMenu.tsx to you.
composer-5: the 7-day usage bars and the cost total need real data. Look at what the usage API already returns (the usage settings page reads it). If the data is there, render it in the reference's container. If one more field or filter is needed, add it to the existing route with a pytest. Never show invented numbers; when there is no usage, show the reference's empty line.'''),
  ])
P['composer'] = dict(port=8843, wave=1, title='Composer: the + sheet, mentions, slash commands, uploads',
  owns=['apps/web/src/conversation/Composer.tsx', 'apps/web/src/conversation/ToolsSheet.tsx', 'the composer helpers in packages/core (composer-mentions and new command helpers)', 'the composer rules in conversation.css'],
  steps=[
    step('sheet-and-mentions', ['composer-3','cleanliness-1','composer-9','cleanliness-7','composer-8','composer-10','composer-12','composer-14'], '''
Targets for the + sheet rows are in the contracts table (skills: `/app/skills?agent=<id>`; schedule: `/app/new-schedule?agent=<id>`). Leave the «الصلاحية» row as it is: a later step turns it into a page inside the sheet. Message.tsx belongs to package `messages`.'''),
    step('slash-commands', ['composer-1','messages-9'], '''
Build slash commands properly, not half. The reference list is مهمة · بحث · ملخص · جدولة · شارت · اتصال · صلاحيات · مسح, then the agent's skills. Commands that act at once (جدولة, شارت, اتصال, صلاحيات, مسح) call the actions the app already has; «مسح» uses the existing hide-history confirm (Q1), «اتصال» follows Q58 when voice is not configured. Commands that take text (مهمة, بحث, ملخص, a skill) must reach the agent as a real, server-validated part of the message: extend the message-create contract (Python and TypeScript) and show the command chip in the owner's bubble. A command must never bypass permission or money-safety gates: it only says what the owner asked for; the agent run is admitted exactly as any other message. Put parsing and option logic in packages/core with unit tests. If a text command cannot be given honest server meaning in this step, leave that one out of the list and say so; the shortcuts sheet must advertise only what works.'''),
    step('all-mention-and-upload', ['composer-11','messages-7','auth_states-6'], '''
composer-11: «@الكل» in group chats needs the server to address every member; check how group routing reads mentions (packages and apps/api messages code) and add it with pytest coverage.
messages-7 and auth_states-6 are one feature: an attachment shows in the owner's bubble at once with a progress ring, the percentage and a cancel control, and the composer stays usable. Use XMLHttpRequest upload progress or the existing API helper if it exposes progress; cancelling aborts the request and removes the pending bubble. Message.tsx belongs to package `messages`: keep your hunk there small.'''),
  ])
P['messages'] = dict(port=8844, wave=1, title='Messages: bubbles, cards, streaming, reply preferences, rich content',
  owns=['apps/web/src/conversation/Conversation.tsx', 'apps/web/src/conversation/Message.tsx', 'apps/web/src/conversation/Cards.tsx', 'apps/web/src/conversation/prefs.ts', 'apps/web/src/conversation/ChatPrefsPage.tsx', 'the reply stream helper', 'the bubble, card and transcript rules in conversation.css'],
  steps=[
    step('bubbles-and-cards', ['messages-4','messages-6','messages-11','messages-12','messages-13','messages-14','messages-3'], '''
Other packages make small edits in Conversation.tsx at the same time (wallpaper, link targets, the empty-chat greeting): stay inside the parts your gaps need.
messages-3: the «أُنشئت مهمة · عرض المهمة» card must be a real, durable part of the conversation (it is still there after a reload), not client-only decoration. Look at how the task is created from a message and what the server writes; «عرض المهمة» opens `/app/tasks/<taskId>`.'''),
    step('reply-prefs', ['settings_a-1','settings_a-2','settings_a-3','settings_a-4','messages-1','messages-2'], '''
The five switches (stream word by word, formatted replies, interactive elements, why this interface, haptics) are per-device preferences in the existing prefs module, with the reference's defaults (design tree, settings defaults table). Each one must really change behaviour: stream off shows the reply when it is complete; formatting off shows plain text; interactive elements off renders generated UI as text; haptics off silences every vibration (wrap the one vibrate call so no caller can forget).
messages-1: the reveal is paced on the client, two words every 34 to 68 ms as in the reference, and it must never hold back a finished reply: when the final message arrives, what is left appears at once. Reduced motion and «بث الرد» off both skip the pacing. Put the pacing in a small pure helper with unit tests.
UiCard.tsx (generated UI) is shared with other packages: keep hunks small.'''),
    step('rich-content', ['messages-8','messages-10','sheets_overlays-5'], '''
messages-8 and messages-10 need data from the agent's structured reply. Check what the server already sends (the visual response contract in packages/core and the Python side). Render it in the reference's containers when the data exists; extend the contract only if that is small and clean, with tests on both sides. Do not invent evidence or suggestions on the client.
sheets_overlays-5: opening an image or a file from a chat uses the app's own sheet system with the reference's «صورة» and file sheets, not the old workspace dialog.'''),
  ])
P['settings'] = dict(port=8845, wave=1, title='Settings: replace the old tabbed screen, integrations, providers, trading account',
  owns=['the route table for settings pages (shell/routes.ts, shell/pages.tsx)', 'apps/web/src/shell/settings/IntegrationsPage.tsx', 'apps/web/src/shell/settings/ConnectionPages.tsx', 'apps/web/src/shell/settings/UsagePage.tsx', 'the new models page', 'the three old rows in SettingsRoot.tsx', 'the old settings overlay files'],
  steps=[
    step('legacy-trio', ['navigation-3','settings_root-2','settings_root-3','settings_root-4','settings_root-5','settings_root-6','settings_b-2','settings_b-3','settings_b-4','cleanliness-4','cleanliness-6'], '''
These entries are one job. The reference has no «النماذج العالمية», «الصوت» or «التداول» rows in the settings root, and no tab strip inside settings. The lead's decision:
- Remove the three rows and the old tabbed overlay.
- Model routing and the allowed-models list keep all their logic and API calls and move to a new inner page `/app/models`, built from the settings primitives, opened by a «النماذج» row under التكاملات › الذكاء الاصطناعي next to «مزوّدو النماذج». The duplicate provider/key form goes away: `/app/provider/<id>` is the one form.
- Voice: a «المكالمات الصوتية» row in the same section shows readiness from the voice status API and opens `/app/provider/openai`. That is also the Q58 target. No GPT-Live or WebRTC wording; Arabic copy in the Q19 vocabulary.
- Trading: the stop/resume control for new trades (the global brake) gets a row with a confirm sheet under التكاملات › حسابات التداول. This is a money-safety control: it must stay reachable, keep its exact server calls and wording, and exits stay allowed. The duplicate broker form goes away: `/app/broker` is the one form.
- `/app/settings?tab=models`, `?tab=voice`, `?tab=trading` keep working as redirects to the new places.
- Retarget every remaining in-app link to the old tabs, except in PermissionMenu.tsx (package `popover` does it) and AgentPage.tsx (package `agent` does it).
- Delete the old overlay files once nothing imports them. Keep components that pages/Trading.tsx or others still import.
Update the Playwright specs that open the old tabs so they assert the new places.'''),
    step('integrations-detail', ['settings_b-1','settings_b-8','settings_b-9','settings_b-6','settings_b-13','settings_b-12','settings_b-10'], '''
settings_b-1 is high: the trading account page must show the real balance, broker name and server from the API; find why it is empty (wrong field, missing fetch) and fix the cause.
settings_b-6: the «النموذج» field after a successful test, the model in each provider row, and removing a provider. Removing needs a server route: refuse, with a clear message, while the provider is still used by routing or by an agent, and cover it with pytest. Credentials never appear in responses or logs.
MetaApi plus «تجريبي» only (Q52).'''),
    step('skills-and-old-pages', ['settings_b-7','navigation-4','cleanliness-5','tokens-3'], '''
Old root pages (navigation-4, cleanliness-5), the lead's decision under Q57: `/app/memory` becomes an alias of `/app/knowledge`; `/app/trading` becomes an alias of `/app/integrations`; `/app/market` becomes an alias of `/app`, and the generated-UI `market` route opens the chart sheet through the existing open-chart event. Check tests/web and tests/*.py for uses of these routes and update them. Do not delete Market.tsx, Trading.tsx or Knowledge.tsx themselves here; a later cleanup removes files nothing imports. List in notes_for_lead every owner-facing function that loses its page this way (for example the economic calendar), so the owner can be told.
tokens-3: after the steps above, list which old-palette screens are still reachable and from where. Port the small ones to reference containers; for money-related surfaces change containers only, never logic. Report what remains.
settings_b-7: enable/disable, last used and «الرجوع إلى الإصدار N» need server support; use what the skills API already has and extend it only if small, with pytest.'''),
  ])
P['profile'] = dict(port=8846, wave=1, title='Owner profile, notifications, device pages, owner name, theme switch',
  owns=['apps/web/src/shell/settings/OwnerPage.tsx', 'apps/web/src/shell/settings/NotifyPages.tsx', 'apps/web/src/shell/settings/DevicePages.tsx', 'the owner name and avatar helper', 'the theme switch, sign-out sheet and version footer in SettingsRoot.tsx', 'apps/web/src/hooks/useTheme.ts'],
  steps=[
    step('owner-and-notify', ['shell_desktop-1','shell_desktop-2','settings_a-9','messages-5','settings_a-7','cleanliness-10','settings_a-8','settings_a-11','settings_a-12','settings_a-13','settings_a-14','settings_root-10','settings_a-6','settings_root-9','settings_root-12'], '''
One helper gives the owner's display name and initial everywhere (rail, settings, profile, desktop welcome, the empty-chat greeting): the form of address, else the name, else the e-mail local part. messages-5 touches Conversation.tsx and conversation.css, which belong to package `messages`: keep that hunk to the empty-chat block.
settings_a-13 changes server defaults for proactive contact (calls off, a daily limit): change the default for agents that have no saved setting, never rewrite what an owner saved, and cover it with pytest.
settings_root-12: the footer shows a version that changes with each deploy; the server already exposes a build id (see the version route and UpdateBar). Show it in the reference's form.
settings_a-7: the five Arabic time-zone names from the reference, plus the owner's current zone if it is not one of them, so nobody loses a saved value.'''),
    step('theme-switch', ['settings_root-7','calls_motion-1','tokens-7'], '''
One feature: the night-mode switch reveals the new theme with the growing circle from the switch (720 ms, the easing in the design tree) where View Transitions exist, and with the 280 ms thumb slide and a plain swap where they do not. Reduced motion: an instant swap. Verify in Chrome by sampling during the transition, and check the fallback path by disabling `document.startViewTransition` in a test.'''),
  ])
P['updates'] = dict(port=8847, wave=1, title='Updates, tasks, schedules and search results',
  owns=['apps/web/src/shell/domain/UpdatesPages.tsx', 'apps/web/src/shell/domain/TasksPages.tsx', 'apps/web/src/shell/domain/SchedulesPages.tsx', 'the attention provider and the attention routes on the server', 'apps/web/src/shell/lists/UnifiedSearch.tsx', 'the domain skeletons in shell/Skeleton.tsx'],
  steps=[
    step('alerts', ['updates_tasks-1','updates_tasks-3','updates_tasks-2','updates_tasks-4','updates_tasks-10'], '''
updates_tasks-1 is high and partly a server fix: the alerts list must show each alert once and must not show ones that no longer apply (for example «التداول الجديد متوقف» after trading resumed). Fix it at the source (the attention history query or its projection), with pytest, and keep the journal append-only: filter what is shown, never delete or rewrite rows.
updates_tasks-3: «تحديد الكل كمقروء» and the three counts (tab dot, rail dot, page count) must agree. A critical alert that still needs the owner's action may stay open, but then the control must say so honestly instead of looking broken.'''),
    step('tasks-and-search', ['updates_tasks-5','updates_tasks-6','updates_tasks-7','chats_list-1','cleanliness-9'], '''
updates_tasks-6: «عند تحقق شرط» is always offered in the schedule form. Package `agent` links to `/app/new-schedule?agent=<id>&kind=condition` for «مراقبة جديدة»: make the form honour `kind=condition` by preselecting that option.
Search results: a task opens `/app/tasks/<taskId>`; a file opens the files page editor, not the old Artifacts viewer.'''),
  ])
P['shell'] = dict(port=8848, wave=1, title='Shell: scroll memory, tab lens, routes, desktop behaviour, call motion',
  owns=['apps/web/src/shell/navigation.tsx', 'apps/web/src/shell/pager.ts', 'apps/web/src/shell/lens.ts', 'apps/web/src/shell/FloatingTabBar.tsx', 'apps/web/src/shell/chrome.ts', 'apps/web/src/shell/flip.ts', 'aliases, redirects and section mapping in shell/routes.ts', 'keyboard shortcuts and search dismissal in Shell.tsx', 'apps/web/src/shell/ShortcutsSheet.tsx', 'the call CSS'],
  steps=[
    step('scroll-and-lens', ['navigation-2','shell_phone-2','shell_phone-1','shell_phone-4','calls_motion-8'], '''
navigation-2 and shell_phone-2 are one high defect: every page remembers its scroll position per history entry; going back, switching tabs and returning from a chat or an inner page land where the owner was. Find the cause the auditors point to (the cleanup that overwrites the saved value) and fix the mechanism once, for all pages, with a Playwright spec that scrolls, leaves and returns on phone and desktop.
shell_phone-1 is high: after a tab change the lens must move once. Record the lens position over frames before and after your fix and report it.
shell_phone-4 and calls_motion-8: use the springs and easings in the design tree; the lens changes its own width instead of being scaled.'''),
    step('desktop-and-routes', ['shell_desktop-3','shell_desktop-4','shell_desktop-6','chats_list-3','navigation-5','navigation-6','auth_states-8','calls_motion-4','calls_motion-5'], '''
Package `settings` adds settings routes and aliases in routes.ts and pages.tsx at the same time: keep your hunks there small and separate.
navigation-5: generated UI may navigate only to an explicit list of real pages, through the shell's own navigation so the unsaved-edits guard applies. Package `settings` changes the `market` entry of that list; leave that entry to it.
The shortcuts sheet's «/» row belongs to package `composer`.'''),
  ])
P['tokens'] = dict(port=8849, wave=1, title='Tokens, the old palette, boot and failure screens, icons',
  owns=['packages/ui-tokens', 'apps/web/src/styles.css', 'apps/web/src/theme.overrides.css', 'apps/web/src/App.tsx', 'apps/web/index.html and the manifest', 'apps/web/src/shell/StatePage.tsx', 'the rich-response (visual) CSS'],
  steps=[
    step('palette', ['tokens-1','cleanliness-12','tokens-4','tokens-2','tokens-5','agent_pages-7','updates_tasks-9','updates_tasks-8','settings_a-10','settings_root-8','auth_states-9'], '''
tokens-1 is high. One name must never carry two meanings: `--muted`, `--accent` and `--primary` mean what the reference says everywhere. Give what is left of the old layer its own names, and check every use in the old CSS so no old screen changes for the worse (other packages are removing most old screens at the same time; you make the remaining ones readable and stop the name clash). Add the contrast check the auditor suggests for tab labels.
agent_pages-7 and updates_tasks-9 are one defect (a Tailwind utility named like the button modifier draws a ring on every outline button): fix the cause once.
The last five are small CSS fixes in shell.css, lists.css and settings.css, files that other packages also edit: keep each hunk to its own rule.'''),
    step('boot-and-states', ['shell_desktop-5','cleanliness-15','auth_states-2','auth_states-1','auth_states-7','tokens-6','tokens-8'], '''
The first three are one defect: the boot screen uses the Lonora mark (shell/LogoMark.tsx) and the reference look.
auth_states-1 is high: when the app cannot start (the server is down or the first requests fail), the owner sees the maintenance screen with its retry, in the reference style, not a bare error card. auth_states-7: the same screen appears when the server goes away mid-session (502, 504, or the request never completes), and it clears by itself when the server is back. Do not show maintenance for an ordinary offline state: that is the network strip's job.'''),
    step('icons', ['cleanliness-11'], '''
Replace every lucide-react icon that still renders on a reachable surface with the app's own `Icon` set from @lonora/ui-web, adding a glyph to that set, in its existing style, only when none fits. Other packages are editing many of these files: change only the icon import and its use, nothing around it. Do not remove the lucide-react dependency; the cleanup step does that once nothing imports it. Report the files that still import it and why.'''),
  ])
P['agent'] = dict(port=8850, wave=1, title='Agent, group and identity pages; the new-agent flow',
  owns=['apps/web/src/shell/agent/ (AgentPage, GroupPage, IdentityPage, AgentSheet, WatchesSheet, MandateSheet, the avatar sheet)', 'the new-agent and new-group flow'],
  steps=[
    step('agent-page', ['agent_pages-3','agent_pages-8','agent_pages-4','settings_b-5','sheets_overlays-4','sheets_overlays-9'], '''
An extra job with no audit id, do it first: package `chat` is changing the chat header and the ⋮ menu so that «معلومات الوكيل» and «معلومات المجموعة» open your pages instead of the old AgentSettings and GroupSettings forms. Compare what those old forms let the owner do (pages/shell/bot-settings.tsx and what it renders, such as supervision settings, account authority and the avatar studio; pages/GroupPanel.tsx GroupSettings) with the agent page, the identity page and the group page. Anything the owner could do there and could no longer reach gets a place in your pages, in reference containers, with its logic and server calls unchanged. Money-related settings (account authority, mandate, limits) keep their exact behaviour: change containers only. Do not delete the old files; a later cleanup does.
Links: voice settings go to `/app/provider/openai` (Q58), «اربط حسابًا» goes to `/app/broker`, «مراقبة جديدة» goes to `/app/new-schedule?agent=<id>&kind=condition` (package `updates` makes the form honour `kind=condition`). «إيقاف الوكيل» stays hidden on Lonora (Q38).
sheets_overlays-4: one avatar editor, the app's own sheet. Lonora keeps its own avatar (Q42).'''),
    step('new-agent-flow', ['agent_pages-5','agent_pages-6'], '''
The new-agent flow has real steps with their own titles, and header Back goes one step back, as the reference and the design tree's back-order rules say. Package `settings` and package `shell` edit routes.ts and pages.tsx at the same time: keep your hunks there small. Wording follows Q19 (no «بوت»). MetaApi plus «تجريبي» only (Q52). Package `forms` later replaces native selects across the app: do not start that here.'''),
  ])
P['forms'] = dict(port=8851, wave=2, title='Forms: the select control, field errors, skeletons, autocomplete',
  owns=['apps/web/src/shell/settings/ui.tsx (SelectField and field primitives)'],
  steps=[
    step('select', ['sheets_overlays-7','sheets_overlays-6'], '''
First make the one select control complete: opens upward when there is no room below, full keyboard navigation (arrows, Home, End, type-ahead, Esc, Enter), the pop-in, option icons where the reference has them, correct listbox roles. Then replace every native <select> on a reachable surface with it.'''),
    step('errors-and-loading', ['auth_states-3','auth_states-4','cleanliness-14'], '''
One shared way to show an error under its field (message tied to the input with aria-describedby, focus moves to the first invalid field), used by every form. Skeletons use shell/Skeleton.tsx shapes that match each page's real layout.'''),
  ])
P['permsheet'] = dict(port=8852, wave=2, title='«الصلاحية» as a page inside the + sheet',
  owns=['the «الصلاحية» row of ToolsSheet.tsx'], steps=[step('permission-page', ['composer-7'], 'Reuse the permission menu content from PermissionMenu.tsx as a page inside the sheet; one implementation, two hosts.')])
P['cleanup'] = dict(port=8853, wave=2, title='Dead code, the second overlay system, duplicate requests',
  owns=['whatever nothing imports any more'],
  steps=[step('dead-code', ['cleanliness-13','sheets_overlays-11','cleanliness-8'], '''
Delete files, exports, CSS rules, catalog strings and dependencies that nothing reachable uses any more (prove it: no import, no route, no test). cleanliness-8: do the safe part only, as the verifier's note says; the periodic reconcile and reconnect refresh are safety nets for trading freshness and stay.''')])

seen = {}
for name, p in P.items():
    for s in p['steps']:
        for i in s['gaps']:
            assert i in gaps, (name, i)
            assert i not in seen, (i, seen.get(i), name)
            seen[i] = name
missing = sorted(set(gaps) - set(seen))
assert not missing, missing
FX = f'{S}/fx'
keep = ['id','title','category','sev','platform','effort','reference_evidence','app_evidence','owner_sees','fix_plan','files','report_rows']
for name, p in P.items():
    os.makedirs(f'{FX}/{name}/shots', exist_ok=True)
    out = dict(package=name, title=p['title'], wave=p['wave'], port=p['port'], worktree=f'/home/user/wt/{name}', branch=f'fx/{name}', owns=p['owns'], steps=[])
    for s in p['steps']:
        entries = []
        for i in s['gaps']:
            g = gaps[i]; e = {k: g.get(k) for k in keep}
            e['verifier_note'] = (g.get('verdict') or {}).get('fix_note', '')
            entries.append(e)
        out['steps'].append(dict(name=s['name'], lead_notes=s['notes'], gaps=entries))
    json.dump(out, open(f'{FX}/{name}/package.json', 'w'), ensure_ascii=False, indent=1)
summary = {n: dict(title=p['title'], port=p['port'], wave=p['wave'], owns=p['owns'], steps=[dict(name=s['name'], gaps=s['gaps']) for s in p['steps']]) for n, p in P.items()}
json.dump(summary, open(f'{FX}/packages.json', 'w'), ensure_ascii=False, indent=1)
for n, p in P.items():
    print(n, p['wave'], p['port'], [(s['name'], len(s['gaps'])) for s in p['steps']], sum(len(s['gaps']) for s in p['steps']))
print('total', len(seen))
