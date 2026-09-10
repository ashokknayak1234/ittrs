-- ============================================================
-- ITTRS Migration: tickets + raw_complaints + RLS
-- Managed by Supabase CLI — viewable/editable in Supabase GUI
-- ============================================================

-- 1. raw_complaints: stores the imported CSV dataset (source of truth)
CREATE TABLE raw_complaints (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    date_received           date,
    product                 text,
    sub_product             text,
    issue                   text,
    sub_issue               text,
    complaint_narrative     text,
    company_public_response text,
    company                 text,
    state                   text,
    zip_code                text,
    tags                    text,
    consumer_consent        text,
    submitted_via           text,
    date_sent_to_company    date,
    company_response        text,
    timely_response         text,
    consumer_disputed       text,
    complaint_id            text,
    created_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_raw_complaints_product ON raw_complaints (product);
CREATE INDEX idx_raw_complaints_company ON raw_complaints (company);
CREATE INDEX idx_raw_complaints_state   ON raw_complaints (state);

-- 2. tickets: AI-processed triage & routing output
CREATE TABLE tickets (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_text       text NOT NULL,
    category             text NOT NULL,
    severity             text NOT NULL,
    team                 text NOT NULL,
    sla_risk_level       text NOT NULL,
    decision_rationale   text NOT NULL,
    escalation_status    text NOT NULL DEFAULT 'Normal',
    is_overridden        boolean NOT NULL DEFAULT false,
    override_reason      text,
    created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_tickets_category   ON tickets (category);
CREATE INDEX idx_tickets_severity   ON tickets (severity);
CREATE INDEX idx_tickets_team       ON tickets (team);
CREATE INDEX idx_tickets_sla_risk   ON tickets (sla_risk_level);
CREATE INDEX idx_tickets_created_at ON tickets (created_at DESC);

-- 3. Enable Row Level Security on both tables
ALTER TABLE raw_complaints ENABLE ROW LEVEL SECURITY;
ALTER TABLE tickets        ENABLE ROW LEVEL SECURITY;

-- 4. Policies — block ALL public/anon/authenticated access.
--    service_role key bypasses RLS, so backend retains full access.
--    This means NO data is visible through the Supabase REST API
--    unless you use the service_role key from a trusted backend.

-- raw_complaints: deny everyone
CREATE POLICY "raw_complaints_deny_anon"
    ON raw_complaints FOR ALL
    TO anon
    USING (false)
    WITH CHECK (false);

CREATE POLICY "raw_complaints_deny_authenticated"
    ON raw_complaints FOR ALL
    TO authenticated
    USING (false)
    WITH CHECK (false);

-- tickets: deny everyone
CREATE POLICY "tickets_deny_anon"
    ON tickets FOR ALL
    TO anon
    USING (false)
    WITH CHECK (false);

CREATE POLICY "tickets_deny_authenticated"
    ON tickets FOR ALL
    TO authenticated
    USING (false)
    WITH CHECK (false);

-- 5. Revoke default grants so tables are invisible to PostgREST
--    even if someone tries to use the API directly.
REVOKE ALL ON raw_complaints FROM anon, authenticated;
REVOKE ALL ON tickets        FROM anon, authenticated;

-- 6. Grant explicit access to service_role (default, but make it explicit)
GRANT ALL ON raw_complaints TO service_role;
GRANT ALL ON tickets        TO service_role;
