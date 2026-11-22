# Draft — VISION.md Amendment 2

**Status: Draft for the owner.** It becomes binding only when the owner issues it. Once issued, a Claude Code session
appends it verbatim under "## Owner amendments" in `VISION.md`, with the issue date, in a pull request of its own
(task P1-T1).

---

### Amendment 2 (YYYY-MM-DD): Lonora Cloud, one dedicated installation per customer

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
     profile or trading data, except by restoring that installation's own backup at the owner's request;
   - place, modify, close, cancel or approve any order, or change any agent's mode or pauses.
4. **Plans limit hosting resources only:** CPU, memory, disk, backup retention, snapshot frequency, regions, domains and
   support level. Nothing in a plan limits a trading decision, an agent's activity or model use (P1). Model access stays
   API keys the owner provides (section 12); the operator sells no model access.
5. **P5 addition.** When `LONORA_HOSTED_PORTAL_URL` is set, the app MAY also show, outside conversations and only in the
   sign-in and settings areas: one "Account and billing" link to the operator's portal, and the operator's notices about
   maintenance, billing or suspension. No portal function is built inside Lonora.
6. **Hosting hooks are additive.** Changes made to Lonora for hosting (machine-readable `lonora` output, the one-time
   setup link, origin-certificate TLS, `lonora quiesce`, a push relay, connecting the mobile app by QR code, the
   diagnostics bundle) are off by default for self-hosted installations, read the trading journal at most, and MUST NOT
   change section 6 or any agent behaviour.
7. **The control plane is a separate system.** The portal, billing, provisioning, administration and support software
   MUST NOT be part of the Lonora image.
8. **P4 is unchanged.** Claude Code may build and maintain Lonora and the control plane. Neither runs Claude Code or the
   Claude Agent SDK as Lonora's engine.
9. **Suspension.** When the operator stops an installation (non-payment, abuse, security or the owner's request), it
   first warns the owner, then runs `lonora quiesce`. Open broker positions stay open and are the owner's; the operator
   never closes or changes them.
