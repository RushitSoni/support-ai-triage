-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Core ticket record
CREATE TABLE IF NOT EXISTS tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL CHECK (source IN ('email','slack','webform')),
    external_id TEXT,                  -- provider's message/thread id
    requester_email TEXT,
    requester_name TEXT,
    subject TEXT,
    body_raw TEXT NOT NULL,
    body_redacted TEXT,                -- after PII scrub
    language TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    dedup_hash TEXT UNIQUE
);

-- Classification result (1:1 with ticket, versioned)
CREATE TABLE IF NOT EXISTS classifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id UUID REFERENCES tickets(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    category TEXT NOT NULL,            -- e.g. billing, bug, how_to, account, other
    intent TEXT,
    urgency TEXT CHECK (urgency IN ('low','medium','high','critical')),
    sentiment TEXT CHECK (sentiment IN ('positive','neutral','negative','angry')),
    confidence NUMERIC(4,3) NOT NULL,
    risk_flag BOOLEAN DEFAULT FALSE,   -- billing/legal/angry => TRUE
    raw_json JSONB NOT NULL,           -- full structured LLM output
    created_at TIMESTAMPTZ DEFAULT now()
);

-- RAG context used for a given response
CREATE TABLE IF NOT EXISTS retrieval_context (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id UUID REFERENCES tickets(id) ON DELETE CASCADE,
    source_doc_id TEXT NOT NULL,
    source_type TEXT CHECK (source_type IN ('kb_article','past_ticket','macro')),
    similarity_score NUMERIC(5,4),
    chunk_text TEXT,
    rank INT
);

-- The decision + resulting action
CREATE TABLE IF NOT EXISTS decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id UUID REFERENCES tickets(id) ON DELETE CASCADE,
    action TEXT CHECK (action IN ('auto_resolve','draft_for_review','escalate')),
    threshold_used NUMERIC(4,3),
    drafted_reply TEXT,
    routed_to TEXT,                    -- human/team the ticket was escalated to
    decided_at TIMESTAMPTZ DEFAULT now()
);

-- Outcome + human feedback (the core of the feedback loop)
CREATE TABLE IF NOT EXISTS outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id UUID REFERENCES decisions(id) ON DELETE CASCADE,
    was_correct BOOLEAN,               -- did the human agree with the routing/category?
    human_category TEXT,               -- correction, if any
    human_edited_reply TEXT,           -- edited version, if any
    csat_score SMALLINT,               -- optional, 1-5
    reopened BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    logged_at TIMESTAMPTZ DEFAULT now()
);

-- Config table for tunable thresholds (referenced in Section 5.3 of the roadmap)
CREATE TABLE IF NOT EXISTS config_thresholds (
    key TEXT PRIMARY KEY,
    value NUMERIC(4,3) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO config_thresholds (key, value) VALUES
    ('confidence_auto_resolve', 0.85),
    ('confidence_draft_review', 0.55),
    ('draft_confidence_auto_resolve', 0.80)
ON CONFLICT (key) DO NOTHING;

-- Daily rollup for the monitoring digest
CREATE MATERIALIZED VIEW IF NOT EXISTS daily_metrics AS
SELECT
    date_trunc('day', t.received_at) AS day,
    count(*) AS total_tickets,
    count(*) FILTER (WHERE d.action = 'auto_resolve') AS auto_resolved,
    count(*) FILTER (WHERE d.action = 'escalate') AS escalated,
    round(avg(c.confidence)::numeric, 3) AS avg_confidence,
    count(*) FILTER (WHERE o.was_correct = FALSE) AS misclassifications
FROM tickets t
LEFT JOIN classifications c ON c.ticket_id = t.id
LEFT JOIN decisions d ON d.ticket_id = t.id
LEFT JOIN outcomes o ON o.decision_id = d.id
GROUP BY 1;

-- Refresh with: REFRESH MATERIALIZED VIEW daily_metrics;
