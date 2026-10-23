# How a complaint flows through the agent

Every complaint goes through one function, [`process_complaint()`](agent/pipeline.py). The live app, the inbox worker
and the batch run all call it. There is no agent framework (no LangGraph or LangChain): the flow is plain Python, and
all LLM traffic goes through [`agent/llm.py`](agent/llm.py) using the `anthropic` or `openai` SDK.

**The LLM reads and writes; code decides.** The LLM classifies the message, pulls out the clues and drafts the reply.
Code finds the transaction, decides the refund, checks the reply and picks the queue. The LLM never chooses the
outcome, the amount or the route.

In the diagrams, orange boxes are LLM calls and blue boxes are plain code.

## 1. The whole pipeline

```mermaid
flowchart TD
    IN(["Complaint message"]) --> UND

    subgraph UNDERSTAND ["UNDERSTAND: agent/extract.py"]
        UND["extract()<br/>intent, category, language,<br/>amount, date, counterparty"]
    end

    UND --> INTENT{"intent?"}

    INTENT -->|OUT_OF_SCOPE| OOS["No action needed<br/>outcome INFO_ONLY"]
    INTENT -->|"NEEDS_DETAILS<br/>not fraud, under 2 follow-ups"| ND["Ask the customer<br/>for the missing info"]
    INTENT -->|"COMPLAINT<br/>(or vague fraud,<br/>or follow-ups used up)"| FIND

    subgraph DECIDE_PATH ["Complaint path: agent/decision/"]
        FIND["find_transaction()<br/>matching.py"] --> DEC["decide()<br/>policy.py<br/>REFUND / DECLINE /<br/>INVESTIGATE / INFO_ONLY"]
    end

    OOS --> DRAFT
    ND --> DRAFT
    DEC --> DRAFT

    DRAFT["Draft reply<br/>agent/reply.py"] --> CHECK["Self-check<br/>agent/checks.py"]
    CHECK --> ROUTE["route()<br/>policy.py"]

    ROUTE --> S1(["ANSWERED"])
    ROUTE --> S2(["AWAITING_CUSTOMER"])
    ROUTE --> S3(["RESOLVED"])
    ROUTE --> S4(["PENDING_APPROVAL"])
    ROUTE --> S5(["FRAUD_QUEUE"])

    classDef llm fill:#fde2c8,stroke:#c2630a,color:#3d1f00
    classDef code fill:#d6e6fb,stroke:#2b5ea7,color:#0c2340
    class UND,DRAFT llm
    class FIND,DEC,CHECK,ROUTE,OOS,ND,INTENT code
```

The extract step and the draft step both have a code fallback. With `LLM_PROVIDER` unset, or when a call fails,
keyword rules and fixed templates do the work, so a complaint is never lost to an LLM error.

## 2. UNDERSTAND: how `extract.py` uses the LLM

```mermaid
flowchart TD
    START(["extract(complaint)"]) --> ON{"LLM enabled?"}

    ON -->|no| RULES["extract_rules()<br/>keyword and regex"]
    RULES --> RCOMP["intent is always COMPLAINT"]

    ON -->|yes| LLM1["extract_llm()<br/>one structured-output call<br/>JSON schema: intent, category,<br/>confidence, missing_info, clues"]
    LLM1 -->|"LLMError: timeout,<br/>bad JSON, over budget"| RULES

    LLM1 --> FIX["Code overrides 2 fields:<br/>language from detect_language()<br/>amount_approx from hedge words"]
    FIX --> NET{"Strong scam wording<br/>in the text?"}
    NET -->|yes| SCAM["Force SCAM_TRANSFER,<br/>intent COMPLAINT"]
    NET -->|no| ISCOMP{"intent is COMPLAINT?"}

    ISCOMP -->|no| OUT(["Extraction"])
    ISCOMP -->|yes| CC{"Keyword rules agree<br/>with the LLM category?"}

    CC -->|"agree, or rules<br/>found no keyword"| OUT
    CC -->|disagree| LLM2["crosscheck.py: second look<br/>LLM picks one of the two categories<br/>and must quote the message"]
    LLM2 --> QOK{"Quote really in the message,<br/>confidence high enough?"}
    QOK -->|yes| USE["Use the second-look category"]
    QOK -->|no| OFF["Keep the first category,<br/>flag CROSSCHECK_UNRESOLVED<br/>so an officer confirms it"]

    SCAM --> OUT
    RCOMP --> OUT
    USE --> OUT
    OFF --> OUT

    classDef llm fill:#fde2c8,stroke:#c2630a,color:#3d1f00
    classDef code fill:#d6e6fb,stroke:#2b5ea7,color:#0c2340
    class LLM1,LLM2 llm
    class RULES,RCOMP,FIX,NET,SCAM,ISCOMP,CC,QOK,USE,OFF,ON code
```

The three intents:

| Intent | Meaning | What happens next |
| --- | --- | --- |
| `COMPLAINT` | A specific problem, even with some details missing. Anything that could be fraud is always a complaint. | Find the transaction, apply policy, reply |
| `NEEDS_DETAILS` | Too general to act on ("my account has a problem") | Ask the customer for `missing_info`, at most 2 rounds |
| `OUT_OF_SCOPE` | Not a banking complaint (chit-chat, product questions, advice) | Polite answer, no case action |

Only the LLM can return `NEEDS_DETAILS` or `OUT_OF_SCOPE`. Two cases go down the complaint path anyway: a
`NEEDS_DETAILS` message in a fraud category (possible fraud never waits for a follow-up), and one whose 2 follow-ups
are used up. Both get a flag, so a person reviews them.

## 3. DRAFT and CHECK: the reply loop

```mermaid
flowchart TD
    D1["Draft<br/>LLM gets a customer-safe fact sheet:<br/>decision, amount, transaction"] --> C1{"checks.check()<br/>IDs and amounts exist,<br/>right refund, right language,<br/>no personal data"}
    C1 -->|pass| DONE(["Reply ready"])
    C1 -->|fail| D2["Redraft<br/>same call plus the problems<br/>as feedback"]
    D2 --> C2{"check again"}
    C2 -->|pass| DONE
    C2 -->|fail| T["Fixed template<br/>flag DRAFT_REJECTED"]
    T --> C3{"check template"}
    C3 -->|pass| HUMAN(["Reply ready,<br/>but a person must approve"])
    C3 -->|fail| HUMAN2(["flag CHECK_FAILED,<br/>officer fixes the reply"])

    classDef llm fill:#fde2c8,stroke:#c2630a,color:#3d1f00
    classDef code fill:#d6e6fb,stroke:#2b5ea7,color:#0c2340
    class D1,D2 llm
    class C1,C2,C3,T code
```

The check is code on purpose: you can't use the model to check the model. The drafter never sees internal reasons
or personal data such as the customer's age, so it cannot repeat them.

## 4. ROUTE: which queue a case lands in

[`policy.route()`](agent/decision/policy.py) is a few lines of code, checked in this order:

```mermaid
flowchart TD
    R(["Decision"]) --> A{"outcome is INVESTIGATE?"}
    A -->|yes| FT(["FRAUD_TEAM<br/>status FRAUD_QUEUE"])
    A -->|no| B{"DECLINE, or refund above<br/>AUTO_REFUND_LIMIT_MYR?"}
    B -->|yes| HA(["HUMAN_APPROVAL<br/>status PENDING_APPROVAL"])
    B -->|no| C{"any flag raised?"}
    C -->|yes| HA
    C -->|no| AR(["AUTO_RESOLVE<br/>status RESOLVED"])

    classDef code fill:#d6e6fb,stroke:#2b5ea7,color:#0c2340
    class A,B,C code
```

Flags come from matching (`NO_MATCH`, ...), the crosscheck (`CROSSCHECK_UNRESOLVED`), vague reports
(`VAGUE_FRAUD_REPORT`, `DETAILS_STILL_MISSING`) and the reply loop (`DRAFT_REJECTED`, `CHECK_FAILED`). Any flag stops
a case going out on its own.

Two cases skip `route()` entirely: `OUT_OF_SCOPE` messages end as `ANSWERED`, and follow-up questions end as
`AWAITING_CUSTOMER`, with no outcome or route yet.

## LLM calls per complaint

| Call | Where | When |
| --- | --- | --- |
| Extraction | `extract.extract_llm()` | Every complaint |
| Second look | `crosscheck.check()` | Only when the LLM and keyword rules disagree on the category |
| Reply draft | `reply.draft_*()` | Every complaint |
| Redraft | `reply.draft_*()` with feedback | Only when the first draft fails the check |

That's 2 calls normally and 4 at most. [`llm.Usage`](agent/llm.py) caps each complaint at
`LLM_MAX_CALLS_PER_COMPLAINT` (default 6) and `LLM_MAX_TOKENS_PER_COMPLAINT` (default 40,000). Calls, tokens and any
failure kinds are saved in the case record (`llm_usage`), and each step's timing is saved in `trace`.
