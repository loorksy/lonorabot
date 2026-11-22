# Draft — VISION.md Amendment 3

**Status: Draft for the owner.** It becomes binding only when the owner issues it. Once issued, a Claude Code session
appends it verbatim under "## Owner amendments" in `VISION.md`, with the issue date, in a pull request of its own
(task P1-T1).

---

### Amendment 3 (YYYY-MM-DD): Lonora Cloud, one dedicated installation per customer

The owner decided that Lonora is also offered as a hosted service in which every customer has a separate space
(«كل مستخدم له مساحة منفصلة»), and that the product stays the delegated trading agent it is today
(«وكيل تداول مثل ما هو عليه لكن متعدد المستخدمين»). It is not a trading platform. The following replaces or adds to the
mandate:

1. **Section 17, last item, is replaced by:** "Each Lonora installation serves a single owner. Lonora is offered
   self-hosted and as Lonora Cloud, in which the operator runs one dedicated installation per customer. A single
   installation shared by several owners remains out of scope."
2. **The customer is the owner.** In Lonora Cloud each customer is the owner of their installation for every clause of
   this mandate, including P1, sections 4, 6, 7, 8, 9 and 12. The operator of Lonora Cloud is not an owner and has no
   owner authority.
3. **The operator MUST NOT:**
   - sign in to an installation as its owner, or hold any credential that does;
   - read, copy or transmit an installation's secrets, broker credentials, model keys, conversations, memory, owner
     profile or trading data, except by restoring that installation's own backup at the owner's request, and except
     the one pass of a broker password to MetaApi that item 10 provides;
   - place, modify, close, cancel or approve any order, or change any agent's mode or pauses.
4. **Plans limit hosting resources only:** CPU, memory, disk, backup retention, snapshot frequency, regions, domains,
   the number of broker connections the operator provides (item 10), and support level. Nothing in a plan limits a trading decision, an agent's activity or model use (P1). Model access stays
   API keys the owner provides (section 12); the operator sells no model access.
5. **P5 addition.** When `LONORA_HOSTED_PORTAL_URL` is set, the app MAY also show, outside conversations and only in the
   sign-in and settings areas: one "Account" link to the operator's portal (in an app-store build, only where the
   store's payments policy allows it), and the operator's notices about maintenance, billing or suspension. No portal
   function is built inside Lonora, and nothing is sold inside the app.
6. **Hosting hooks are additive.** Changes made to Lonora for hosting (machine-readable `lonora` output, the one-time
   setup link, origin-certificate TLS, `lonora quiesce`, a push relay, connecting the mobile app by QR code, the
   diagnostics bundle, and the hosted provisioning path of item 10) are off by default for self-hosted installations,
   read the trading journal at most, and MUST NOT change section 6 or any agent behaviour.
7. **The control plane is a separate system.** The portal, billing, provisioning, administration and support software
   MUST NOT be part of the Lonora image.
8. **P4 is unchanged.** Claude Code may build and maintain Lonora and the control plane. Neither runs Claude Code or the
   Claude Agent SDK as Lonora's engine.
9. **Suspension.** When the operator stops an installation (non-payment, abuse, security or the owner's request), it
   first warns the owner, then runs `lonora quiesce`. Open broker positions stay open and are the owner's; the operator
   never closes or changes them.
10. **Broker connections in Lonora Cloud.** The owner connects a MetaTrader account with only the account number, the
    server and the password their broker gave them («لا يحتاج المستخدم غير رقم الحساب والخادم وكلمة المرور، وليس
    توكن»). The operator's MetaApi account provides the connection and the operator pays for it («يتم محاسبتنا نحن على
    استخدام المستخدم»). In Lonora Cloud only:
    - the MetaApi API token step of section 9.2 does not apply: the owner never creates or enters a MetaApi token;
    - the operator's provisioning service is the only holder of the operator's MetaApi API token. At the request of an
      owner's installation it creates, deploys, undeploys, updates and removes that owner's MetaApi accounts, and gives
      the installation a token narrowed to that installation's own accounts, renewed before it expires;
    - the broker password goes from the Secret card (7.2) through the provisioning service to MetaApi once, in memory.
      The operator never stores or logs it;
    - the provisioning service MUST NOT use the operator's token to read account data beyond connection state, or to
      place, modify, close or cancel any order. Every use of it is audited and shown to the owner;
    - the execution door (section 6) and every order path in the installation are unchanged: the installation trades
      with its narrowed token exactly as it trades today;
    - connections are a hosting resource under item 4. A plan may include a number of connections and bill more; it
      never limits trading on a connected account.
11. **Hosting never narrows the agent.** Lonora is an open agent like Grok Bot («يستطيع الاتصال بأي خادم … أي API أو
    MCP أو تثبيت أي بلوجن»). Lonora Cloud keeps every capability of the
    self-hosted product: the workspace's internet egress, any command-line tool or package (7.1, 12.2), owner-trusted
    MCP servers and skill sources, and secrets of any kind (7.2). Hosting may add only these limits, all on the workspace:
    - the operator's own domain and services are added to the denied names, so a workspace cannot reach other
      customers' installations or the control plane;
    - outbound SMTP port 25 is blocked;
    - the abuse ladder of the operator's acceptable-use policy (notify, throttle, stop the workspace), which never stops
      Lonora itself and acts without notice only against an attack in progress.
12. **Trading scope.** VISION Amendment 2 (MetaTrader only, any symbol the owner's broker offers, no other venue)
    applies to Lonora Cloud unchanged.
