-- ITTRS Migration: customer satisfaction loop + SLA alerts
-- Adds columns to support the "Customer not satisfied" escalation workflow.

ALTER TABLE tickets
    ADD COLUMN satisfaction_status text NOT NULL DEFAULT 'Normal',
    ADD COLUMN sla_alerted        boolean NOT NULL DEFAULT false;

-- Index for quick dashboard queries on escalating/satisfaction state
CREATE INDEX idx_tickets_satisfaction ON tickets (satisfaction_status);
CREATE INDEX idx_tickets_sla_alerted  ON tickets (sla_alerted);