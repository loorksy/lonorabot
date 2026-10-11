# Lonora — المخطط المعماري الكامل وتدفق النظام

> هذا الملف يصف البنية المستهدفة لـ **Lonora** كما تم الاتفاق عليها: إطار وكلاء دائمين مشتق من فلسفة وبنية Rakazo، مع Backend بلغة Python، وواجهة Web بـ React/TypeScript، وطبقة تشغيل دائمة، وتوجيه عالمي للنماذج، وصوت لحظي، وقدرات سوق ورسوم وتداول ومراقبة ضمن نفس Agent Runtime.

---

## 1. المخطط المعماري الكامل

```mermaid
flowchart TB

    U[المستخدم]

    subgraph CLIENT["طبقة العميل"]
        WEB[Web App<br/>React / TypeScript]
        TEXT[محادثة نصية]
        VOICEUI[مكالمة صوتية مباشرة]
        GROUPUI[مجموعات الوكلاء]
        SEARCHUI[البحث]
        SETTINGSUI[الإعدادات العامة]
        TRADEUI[واجهة السوق والتداول]
    end

    U --> WEB
    WEB --> TEXT
    WEB --> VOICEUI
    WEB --> GROUPUI
    WEB --> SEARCHUI
    WEB --> SETTINGSUI
    WEB --> TRADEUI

    subgraph API["طبقة API — Python / FastAPI"]
        AUTH[Authentication / Authorization]
        GATEWAY[API Gateway / REST / RPC]
        THREADAPI[Threads / Messages]
        RUNAPI[Runs / Steering]
        GROUPAPI[Groups]
        ROUTINEAPI[Routines]
        ARTAPI[Artifacts / Files]
        SEARCHAPI[Search]
        SETTINGSAPI[Global Settings]
        VOICEAPI[Voice Session API]
        TRADINGAPI[Trading API]
    end

    WEB -->|HTTPS / RPC| GATEWAY
    GATEWAY --> AUTH
    GATEWAY --> THREADAPI
    GATEWAY --> RUNAPI
    GATEWAY --> GROUPAPI
    GATEWAY --> ROUTINEAPI
    GATEWAY --> ARTAPI
    GATEWAY --> SEARCHAPI
    GATEWAY --> SETTINGSAPI
    GATEWAY --> VOICEAPI
    GATEWAY --> TRADINGAPI

    subgraph STATE["الحالة والتخزين الدائم"]
        PG[(PostgreSQL)]
        ART[(Artifact Storage)]

        BOTS[Bots]
        THREADS[Threads]
        MSGS[Messages]
        RUNS[Runs]
        EVENTS[Durable Thread Events]
        MEMORY[Memory Documents / MEMORY.md]
        SCRATCH[Scratchpad]
        SKILLS[Skills]
        ROUTINES[Routines]
        GROUPS[Groups]
        BOARDS[Boards / Tickets]
        WATCHES[Market Watches]
        TRJ[Trading Journal]
        SETTINGS[Global AI / Trading Settings]
    end

    THREADAPI --> PG
    RUNAPI --> PG
    GROUPAPI --> PG
    ROUTINEAPI --> PG
    SEARCHAPI --> PG
    SETTINGSAPI --> PG
    TRADINGAPI --> PG
    ARTAPI --> ART
    ARTAPI --> PG

    PG --- BOTS
    PG --- THREADS
    PG --- MSGS
    PG --- RUNS
    PG --- EVENTS
    PG --- MEMORY
    PG --- SCRATCH
    PG --- SKILLS
    PG --- ROUTINES
    PG --- GROUPS
    PG --- BOARDS
    PG --- WATCHES
    PG --- TRJ
    PG --- SETTINGS

    subgraph WORKER["Worker / التشغيل الدائم 24x7"]
        SCHED[Scheduler / Due Work]
        CLAIM[Run Claim<br/>Lease + Fence]
        BG[Background Worker]
        WAKE[Routine Wakeups]
        WATCHWORKER[Market Watch Processor]
        RECOVERY[Recovery / Reclaim Expired Runs]
        EVENTPUB[Event Publisher]
    end

    PG --> SCHED
    SCHED --> BG
    BG --> CLAIM
    WAKE --> CLAIM
    WATCHWORKER --> CLAIM
    RECOVERY --> CLAIM
    CLAIM -->|تشغيل Run| EXEC

    subgraph RUNTIME["Agent Runtime"]
        EXEC[Executor]

        STATE_MACHINE[Run State Machine]
        STEERING[Steering Consumption]
        WAITING[waiting_input / takeover / resume]
        CTX[Context Assembly]
        TOOLLOOP[Tool Loop]
        CHILD[Child Bots]
        SUBAGENT[Subagents]
        BOT2BOT[Bot-to-Bot Messaging]
        OUTCOME[Outcome Return]
        ENGAGE[Group Engagement / Silence]
        CANCEL[Cancellation / Stale Write Protection]
    end

    EXEC --> STATE_MACHINE
    EXEC --> STEERING
    EXEC --> WAITING
    EXEC --> CTX
    EXEC --> TOOLLOOP
    EXEC --> CHILD
    EXEC --> SUBAGENT
    EXEC --> BOT2BOT
    EXEC --> OUTCOME
    EXEC --> ENGAGE
    EXEC --> CANCEL

    subgraph CONTEXT["مصادر السياق"]
        HISTORY[Conversation History]
        MEMCTX[MEMORY.md / Memory]
        SCRATCHCTX[Scratchpad]
        SKILLCTX[Skills]
        REPLYCTX[Reply / Quote Context]
        STEERCTX[Steering Messages]
        TOOLCTX[Tool Results]
        GROUPCTX[Group Context]
        ROUTINECTX[Routine Context]
        ATTACHCTX[Attachments / Artifacts]
        MARKETCTX[Market / Account Context]
    end

    HISTORY --> CTX
    MEMCTX --> CTX
    SCRATCHCTX --> CTX
    SKILLCTX --> CTX
    REPLYCTX --> CTX
    STEERCTX --> CTX
    TOOLCTX --> CTX
    GROUPCTX --> CTX
    ROUTINECTX --> CTX
    ATTACHCTX --> CTX
    MARKETCTX --> CTX

    PG --> HISTORY
    PG --> MEMCTX
    PG --> SCRATCHCTX
    PG --> SKILLCTX
    PG --> STEERCTX
    PG --> GROUPCTX
    PG --> ROUTINECTX
    ART --> ATTACHCTX

    subgraph ROUTER["Global Model Router"]
        ROUTERCORE[Global Router]

        UNIFIED[Unified Mode]
        CUSTOM[Custom Capability Routing]

        CHAT[Conversation]
        REASON[Reasoning]
        RESEARCH[Research]
        VISION[Vision]
        REALTIME[Realtime Voice]
        STTROUTE[STT]
        TTSROUTE[TTS]
        BACKGROUND[Background]
    end

    CTX --> ROUTERCORE
    ROUTERCORE --> UNIFIED
    ROUTERCORE --> CUSTOM
    CUSTOM --> CHAT
    CUSTOM --> REASON
    CUSTOM --> RESEARCH
    CUSTOM --> VISION
    CUSTOM --> REALTIME
    CUSTOM --> STTROUTE
    CUSTOM --> TTSROUTE
    CUSTOM --> BACKGROUND

    subgraph MODELS["مزودو النماذج"]
        OPENAI[OpenAI]
        ANTHROPIC[Anthropic]
        DEEPSEEK[DeepSeek]
        ZAI[Z.ai]
        OPENROUTER[OpenRouter]
    end

    ROUTERCORE --> OPENAI
    ROUTERCORE --> ANTHROPIC
    ROUTERCORE --> DEEPSEEK
    ROUTERCORE --> ZAI
    ROUTERCORE --> OPENROUTER

    MODELS -->|Text / Tool Calls / Structured Output| TOOLLOOP

    subgraph TOOLS["Tool Runtime"]
        MEMTOOLS[Memory Tools]
        SKILLTOOLS[Skill Tools]
        ROUTINETOOLS[Routine Tools]
        SEARCHTOOLS[Search / Research Tools]
        FILETOOLS[Artifacts / File Tools]
        GROUPTOOLS[Group / Collaboration Tools]
        MCPTOOLS[MCP / Connector Tools]
        MARKETTOOLS[Market Tools]
        CHARTTOOLS[Chart Tools]
        ACCOUNTTOOLS[Account Tools]
        TRADETOOLS[Trade Tools]
        WATCHTOOLS[Watch Tools]
    end

    TOOLLOOP --> MEMTOOLS
    TOOLLOOP --> SKILLTOOLS
    TOOLLOOP --> ROUTINETOOLS
    TOOLLOOP --> SEARCHTOOLS
    TOOLLOOP --> FILETOOLS
    TOOLLOOP --> GROUPTOOLS
    TOOLLOOP --> MCPTOOLS
    TOOLLOOP --> MARKETTOOLS
    TOOLLOOP --> CHARTTOOLS
    TOOLLOOP --> ACCOUNTTOOLS
    TOOLLOOP --> TRADETOOLS
    TOOLLOOP --> WATCHTOOLS

    MEMTOOLS --> PG
    SKILLTOOLS --> PG
    ROUTINETOOLS --> PG
    FILETOOLS --> ART
    GROUPTOOLS --> PG
    WATCHTOOLS --> PG

    subgraph TRADING["طبقة السوق والتداول"]
        MARKET[Market Data]
        CHART[Chart Domain]
        IND[Indicators]
        ACCOUNT[Account / Positions / Orders]
        CONTROL[Trading ON / OFF<br/>Emergency Stop]
        EXECUTION[Execution Service]
        IDEMP[Idempotency]
        JOURNAL[Execution Journal]
        RECON[Broker Reconciliation]
        WATCHENG[Watch Engine]
    end

    MARKETTOOLS --> MARKET
    CHARTTOOLS --> CHART
    ACCOUNTTOOLS --> ACCOUNT
    TRADETOOLS --> CONTROL
    CONTROL --> EXECUTION
    EXECUTION --> IDEMP
    IDEMP --> JOURNAL
    JOURNAL --> RECON
    WATCHTOOLS --> WATCHENG

    MARKET --> MARKETCTX
    CHART --> MARKETCTX
    ACCOUNT --> MARKETCTX

    subgraph BROKERS["Broker Layer"]
        BROKERIF[Broker-neutral Interface]
        META[MetaApi Adapter / First Broker]
        FUTURE[Future Broker Adapters]
        FAKE[Demo / Fake Broker]
    end

    MARKET --> BROKERIF
    ACCOUNT --> BROKERIF
    RECON --> BROKERIF
    EXECUTION --> BROKERIF

    BROKERIF --> META
    BROKERIF --> FUTURE
    BROKERIF --> FAKE

    subgraph VOICE["الصوت الفوري"]
        WEBRTC[WebRTC Session]
        LIVEKIT[LiveKit Transport]
        STT[Speech-to-Text]
        SAMEAGENT[Same Agent Runtime]
        TTS[Text-to-Speech]
        BARGE[Barge-in / Interrupt]
    end

    VOICEUI --> WEBRTC
    WEBRTC --> LIVEKIT
    LIVEKIT --> STT
    STT --> SAMEAGENT
    SAMEAGENT --> CTX
    SAMEAGENT --> ROUTERCORE
    ROUTERCORE --> TTS
    TTS --> LIVEKIT
    LIVEKIT --> VOICEUI
    BARGE --> SAMEAGENT

    subgraph EVENTS_LAYER["الأحداث والتحديث اللحظي"]
        DURABLE[Durable Events]
        STREAM[Transient Streaming]
        WS[WebSocket / Event Stream]
        RECONNECT[Reconnect / Catch-up]
    end

    MSGS --> DURABLE
    RUNS --> DURABLE
    EXEC --> STREAM
    TOOLLOOP --> STREAM
    DURABLE --> WS
    STREAM --> WS
    WS --> WEB
    WEB --> RECONNECT
    RECONNECT --> EVENTS

    EXEC -->|Assistant Message| MSGS
    EXEC -->|Run State| RUNS
    EXEC -->|Durable Events| EVENTS
    EXEC --> EVENTPUB
    EVENTPUB --> EVENTS

    subgraph EXTERNAL["الأنظمة الخارجية"]
        NEWS[Web / News / Research]
        CONNECTORS[External Connectors / MCP]
        NOTIFY[Push / Email / Telegram]
    end

    SEARCHTOOLS --> NEWS
    MCPTOOLS --> CONNECTORS
    EVENTPUB --> NOTIFY
```

---

## 2. المسار الأساسي للرسالة النصية

```mermaid
sequenceDiagram
    participant U as المستخدم
    participant W as Web
    participant A as API
    participant DB as PostgreSQL
    participant WK as Worker
    participant R as Agent Runtime
    participant MR as Global Model Router
    participant M as Model Provider
    participant T as Tools
    participant E as Events

    U->>W: يرسل رسالة
    W->>A: POST / message
    A->>DB: حفظ Message + seq + clientNonce
    A->>DB: إنشاء أو Steering لـ Run
    DB-->>WK: Run جاهز
    WK->>DB: Claim + Lease + Fence
    WK->>R: Execute Run
    R->>DB: تحميل السياق
    R->>MR: ModelRequest
    MR->>M: الطلب حسب التوجيه العالمي
    M-->>R: Text أو Tool Call

    alt Tool Call
        R->>T: تنفيذ الأداة
        T-->>R: ToolResult
        R->>MR: متابعة مع النتيجة
        MR->>M: continuation
        M-->>R: Final response
    end

    R->>DB: حفظ رسالة المساعد
    R->>DB: completed
    R->>E: durable + streaming events
    E-->>W: تحديث مباشر
    W-->>U: عرض النتيجة
```

---

## 3. مسار Steering أثناء عمل الوكيل

```mermaid
sequenceDiagram
    participant U as المستخدم
    participant API as API
    participant DB as PostgreSQL
    participant R as Run الجاري
    participant EX as Executor

    U->>API: رسالة جديدة أثناء Run نشط
    API->>DB: حفظ Message
    API->>DB: إنشاء SteeringMessage
    DB-->>EX: Steering متاح
    EX->>DB: Claim steering
    EX->>R: إضافة التعليمات الجديدة للسياق الجاري
    R-->>EX: متابعة التنفيذ بالتوجيه الجديد
```

---

## 4. مسار الاستعادة بعد تعطل Worker

```mermaid
sequenceDiagram
    participant A as Worker A
    participant DB as PostgreSQL
    participant B as Worker B

    A->>DB: Claim Run / fence=12
    A--xDB: Worker A يتعطل
    Note over DB: تنتهي lease
    B->>DB: Reclaim Run / fence=13
    B->>DB: Execute + Complete
    A->>DB: محاولة كتابة متأخرة fence=12
    DB-->>A: رفض stale_lease
```

---

## 5. بناء Context للوكيل

```mermaid
flowchart LR
    CURRENT[Current Message]
    HISTORY[Conversation History]
    MEMORY[MEMORY.md]
    SEM[Semantic Memory]
    SCRATCH[Scratchpad]
    SKILLS[Skills]
    STEERING[Steering]
    REPLY[Reply Context]
    TOOLS[Previous Tool Results]
    GROUP[Group Context]
    ROUTINE[Routine Context]
    ATT[Attachments]
    MARKET[Market / Account State]

    CURRENT --> CTX[Context Assembly]
    HISTORY --> CTX
    MEMORY --> CTX
    SEM --> CTX
    SCRATCH --> CTX
    SKILLS --> CTX
    STEERING --> CTX
    REPLY --> CTX
    TOOLS --> CTX
    GROUP --> CTX
    ROUTINE --> CTX
    ATT --> CTX
    MARKET --> CTX

    CTX --> ROUTER[Global Model Router]
```

---

## 6. تعاون الوكلاء

```mermaid
flowchart TB
    USER[المستخدم]
    MAIN[Main Agent]

    USER --> MAIN

    MAIN -->|مهمة دائمة| CHILD[Child Bot]
    MAIN -->|مهمة مؤقتة| SUB[Subagent]
    MAIN -->|رسالة لوكيل معروف| PEER[Peer Agent]

    CHILD --> CHILDOUT[Persistent Thread / State]
    SUB --> SUBOUT[Temporary Outcome]
    PEER --> PEEROUT[Outcome Return]

    CHILDOUT --> MAIN
    SUBOUT --> MAIN
    PEEROUT --> MAIN

    MAIN --> FINAL[النتيجة النهائية]
```

### الفرق

- **Child Bot**: وكيل دائم له هوية وThread وحالة مستقلة.
- **Subagent**: تنفيذ فرعي مؤقت ومحدود.
- **Bot-to-Bot**: وكيل موجود يرسل مهمة أو رسالة إلى وكيل موجود آخر.
- **Group Chat**: عدة وكلاء يشتركون في Thread واحد، ولا يجب أن يرد الجميع دائمًا.

---

## 7. تدفق Group Chat

```mermaid
flowchart LR
    U[User Message]
    GT[Group Thread]
    E[Engagement / Mention Logic]

    A1[Technical Agent]
    A2[News Agent]
    A3[Account Agent]

    U --> GT
    GT --> E

    E -->|يتفاعل| A1
    E -->|يصمت| A2
    E -->|يتفاعل عند الحاجة| A3

    A1 --> GT
    A3 --> GT
```

---

## 8. تدفق Routine

```mermaid
flowchart LR
    R[Routine]
    SCH[Schedule]
    DUE[Due]
    CLAIM[Durable Claim]
    RUN[Run]
    AGENT[Same Agent Runtime]
    TOOLS[Tools]
    RESULT[Message / Outcome]

    R --> SCH
    SCH --> DUE
    DUE --> CLAIM
    CLAIM --> RUN
    RUN --> AGENT
    AGENT --> TOOLS
    TOOLS --> AGENT
    AGENT --> RESULT
```

---

## 9. تدفق Market Watch

```mermaid
flowchart LR
    CREATE[Create Watch]
    DB[(PostgreSQL)]
    WORKER[Worker]
    MARKET[Market Data]
    COND{Condition Met?}
    WAKE[Wake Agent]
    RUN[Run]
    RESULT[Analysis / Alert / Action]

    CREATE --> DB
    DB --> WORKER
    WORKER --> MARKET
    MARKET --> COND
    COND -->|لا| WORKER
    COND -->|نعم| WAKE
    WAKE --> RUN
    RUN --> RESULT
```

---

## 10. تدفق تحليل السوق

```mermaid
flowchart TB
    REQUEST[طلب المستخدم: حلل XAUUSDm]
    AGENT[Agent Runtime]
    MARKET[Market Tool]
    CHART[Chart Tool]
    ACCOUNT[Account Tool]
    RESEARCH[Research Tool]

    QUOTE[Quote]
    CANDLES[Candles]
    IND[Indicators]
    POS[Positions / Orders]
    NEWS[News / Macro Context]

    REASON[Model Reasoning]
    FINAL[تحليل نهائي]

    REQUEST --> AGENT

    AGENT --> MARKET
    AGENT --> CHART
    AGENT --> ACCOUNT
    AGENT --> RESEARCH

    MARKET --> QUOTE
    MARKET --> CANDLES
    CHART --> IND
    ACCOUNT --> POS
    RESEARCH --> NEWS

    QUOTE --> REASON
    CANDLES --> REASON
    IND --> REASON
    POS --> REASON
    NEWS --> REASON

    REASON --> FINAL
```

---

## 11. تدفق تنفيذ صفقة

```mermaid
sequenceDiagram
    participant U as المستخدم
    participant A as Agent
    participant TT as Trade Tool
    participant C as Trading Control
    participant EX as Execution Service
    participant J as Trading Journal
    participant B as Broker Adapter
    participant BR as Broker
    participant RC as Reconciliation

    U->>A: طلب تداول
    A->>TT: Structured Trade Call
    TT->>C: التحقق من Trading ON/OFF

    alt Trading OFF
        C-->>TT: trade_disabled
        TT-->>A: رفض العملية
    else Trading ON
        C->>EX: السماح بالتنفيذ
        EX->>J: إنشاء operation_id
        EX->>B: تنفيذ الطلب
        B->>BR: Broker API
        BR-->>B: Result / Timeout
        B-->>EX: Broker result

        alt نتيجة مؤكدة
            EX->>J: Final success/failure
        else نتيجة غامضة
            EX->>RC: reconcile
            RC->>BR: فحص orders/positions
            BR-->>RC: actual state
            RC->>J: final reconciled state
        end

        EX-->>TT: ToolResult
        TT-->>A: نتيجة التداول
    end
```

---

## 12. قاعدة الرمز الحقيقي للوسيط

```mermaid
flowchart LR
    BROKER[Broker]
    SYMBOL[XAUUSDm]
    MARKET[Market]
    CHART[Chart]
    ANALYSIS[Agent Analysis]
    WATCH[Watch]
    TRADE[Trade]
    JOURNAL[Journal]

    BROKER --> SYMBOL
    SYMBOL --> MARKET
    SYMBOL --> CHART
    SYMBOL --> ANALYSIS
    SYMBOL --> WATCH
    SYMBOL --> TRADE
    SYMBOL --> JOURNAL
```

> لا يتم استبدال `XAUUSDm` تلقائيًا بـ `XAUUSD`.

---

## 13. تدفق الصوت الفوري

```mermaid
sequenceDiagram
    participant U as المستخدم
    participant W as WebRTC
    participant L as LiveKit
    participant STT as STT
    participant A as Same Agent Runtime
    participant R as Global Model Router
    participant T as Tools
    participant TTS as TTS

    U->>W: صوت مباشر
    W->>L: Audio Stream
    L->>STT: الصوت
    STT->>A: Transcript
    A->>R: Context + request
    R-->>A: Text / Tool Call

    alt Tool Call
        A->>T: تنفيذ الأداة
        T-->>A: ToolResult
        A->>R: Continuation
        R-->>A: Final response
    end

    A->>TTS: النص النهائي/المتدفق
    TTS->>L: Audio
    L->>W: Stream
    W-->>U: صوت مباشر
```

---

## 14. الصوت والتداول يستخدمان نفس المسار

```mermaid
flowchart LR
    VOICE[Voice]
    TRANSCRIPT[Transcript]
    AGENT[Same Agent]
    TRADE[Trade Tool]
    CONTROL[Trading Control]
    EXEC[Execution Service]
    BROKER[Broker]

    VOICE --> TRANSCRIPT
    TRANSCRIPT --> AGENT
    AGENT --> TRADE
    TRADE --> CONTROL
    CONTROL --> EXEC
    EXEC --> BROKER
```

> لا يوجد مسار تداول خاص بالصوت يتجاوز أدوات الوكيل العادية.

---

## 15. التوجيه العالمي للنماذج

```mermaid
flowchart TB
    AGENTS[كل وكلاء Lonora]
    ROUTER[Global Model Router]

    UNIFIED[Unified Mode]
    CUSTOM[Custom Capability Routing]

    CONV[Conversation]
    REASON[Reasoning]
    RESEARCH[Research]
    VISION[Vision]
    VOICE[Realtime Voice]
    STT[STT]
    TTS[TTS]
    BG[Background]

    OPENAI[OpenAI]
    ANTHROPIC[Anthropic]
    DEEPSEEK[DeepSeek]
    ZAI[Z.ai]
    OR[OpenRouter]

    AGENTS --> ROUTER
    ROUTER --> UNIFIED
    ROUTER --> CUSTOM

    CUSTOM --> CONV
    CUSTOM --> REASON
    CUSTOM --> RESEARCH
    CUSTOM --> VISION
    CUSTOM --> VOICE
    CUSTOM --> STT
    CUSTOM --> TTS
    CUSTOM --> BG

    ROUTER --> OPENAI
    ROUTER --> ANTHROPIC
    ROUTER --> DEEPSEEK
    ROUTER --> ZAI
    ROUTER --> OR
```

> لا يوجد Model/Provider مستقل لكل Agent أو Routine. التوجيه عالمي، مع إمكانية تسجيل الـmodel الفعلي المستخدم داخل Run metadata.

---

## 16. التشغيل أثناء إغلاق المتصفح

```mermaid
flowchart LR
    CLOSED[Browser Closed]
    PG[(PostgreSQL)]
    WORKER[Worker]
    ROUTINE[Routines]
    WATCH[Market Watches]
    RUNS[Runs]
    AGENT[Agent Runtime]
    RESULT[Durable Messages / Events]
    REOPEN[User Reopens Web]

    CLOSED -. لا يوقف .-> PG
    PG --> WORKER
    ROUTINE --> WORKER
    WATCH --> WORKER
    WORKER --> RUNS
    RUNS --> AGENT
    AGENT --> RESULT
    RESULT --> PG
    PG --> REOPEN
```

---

## 17. دورة النظام الكاملة

```mermaid
flowchart TB
    USER[المستخدم]
    INPUT[نص / صوت / Routine / Watch / Group / Agent]
    API[API]
    DB[(PostgreSQL)]
    RUN[Run]
    WORKER[Worker]
    LEASE[Lease + Fence]
    CONTEXT[Context Assembly]
    ROUTER[Global Model Router]
    MODEL[LLM]
    TOOLS[Tools]
    RESULT[Result]
    EVENT[Durable Event]
    UI[Web / Voice]
    FUTURE[Memory / Routine / Watch / Future Run]

    USER --> INPUT
    INPUT --> API
    API --> DB
    DB --> RUN
    RUN --> WORKER
    WORKER --> LEASE
    LEASE --> CONTEXT
    CONTEXT --> ROUTER
    ROUTER --> MODEL
    MODEL -->|Tool Call| TOOLS
    TOOLS --> MODEL
    MODEL --> RESULT
    RESULT --> DB
    DB --> EVENT
    EVENT --> UI
    RESULT --> FUTURE
    FUTURE --> DB
```

---

## 18. المبدأ المعماري الأساسي

Lonora ليس مجموعة أنظمة منفصلة:

```text
Chat System
Voice System
Trading System
Scheduler
Agent System
```

بل إطار واحد:

```text
Persistent Agent Runtime
        │
        ├── Conversation
        ├── Memory
        ├── Skills
        ├── Tools
        ├── Routines
        ├── Collaboration
        ├── Voice
        ├── Market
        ├── Chart
        ├── Trading
        └── Watches
```

جميع القدرات تستخدم نفس:

- هوية الوكيل
- Thread
- Context
- Memory
- Tool Runtime
- Run lifecycle
- Worker
- Security
- Events
- PostgreSQL durable state

وهذا هو جوهر تصميم Lonora.
