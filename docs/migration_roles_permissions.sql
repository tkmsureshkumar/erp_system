-- =============================================================================
-- IRONLINE ACCESS ERP — Roles, Permissions & Approval Workflow Migration
-- Run this ONCE in your Supabase SQL editor before deploying the new release.
-- =============================================================================

-- ── Phase 1 : Soft-delete columns for master records ─────────────────────────
ALTER TABLE machines   ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;
ALTER TABLE customers  ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;
ALTER TABLE sites      ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;

-- Backfill existing records as active
UPDATE machines  SET is_active = true WHERE is_active IS NULL;
UPDATE customers SET is_active = true WHERE is_active IS NULL;
UPDATE sites     SET is_active = true WHERE is_active IS NULL;

-- ── Phase 2 : Lifecycle status for transactional records ─────────────────────
ALTER TABLE work_orders       ADD COLUMN IF NOT EXISTS record_status TEXT DEFAULT 'Draft';
ALTER TABLE machine_movements ADD COLUMN IF NOT EXISTS record_status TEXT DEFAULT 'Draft';
ALTER TABLE work_logs         ADD COLUMN IF NOT EXISTS record_status TEXT DEFAULT 'Draft';

-- Map existing work_logs to correct status based on is_draft
UPDATE work_logs SET record_status = 'Locked' WHERE is_draft = false AND record_status IS NULL;
UPDATE work_logs SET record_status = 'Draft'  WHERE is_draft = true  AND record_status IS NULL;

-- Backfill remaining records
UPDATE work_orders       SET record_status = 'Draft' WHERE record_status IS NULL;
UPDATE machine_movements SET record_status = 'Draft' WHERE record_status IS NULL;
UPDATE work_logs         SET record_status = 'Draft' WHERE record_status IS NULL;

-- ── Phase 3 : Edit / Delete request workflow table ───────────────────────────
CREATE TABLE IF NOT EXISTS edit_requests (
    id                  UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    record_type         TEXT        NOT NULL,           -- 'Work Order' | 'Movement' | 'Work Log'
    record_id           TEXT        NOT NULL,           -- UUID of the target record
    record_label        TEXT,                           -- Human-readable label (WO number, etc.)
    request_type        TEXT        NOT NULL DEFAULT 'EDIT',  -- 'EDIT' | 'DELETE'
    requested_by_id     TEXT,                           -- user_profiles.id
    requested_by_name   TEXT,
    requested_by_email  TEXT,
    reason              TEXT        NOT NULL,
    status              TEXT        DEFAULT 'Pending',  -- 'Pending' | 'Approved' | 'Rejected'
    reviewed_by_id      TEXT,
    reviewed_by_name    TEXT,
    reviewed_at         TIMESTAMPTZ,
    review_note         TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_edit_requests_status
    ON edit_requests(status);

CREATE INDEX IF NOT EXISTS idx_edit_requests_record
    ON edit_requests(record_type, record_id);

-- ── Verification queries (run after migration) ────────────────────────────────
-- SELECT column_name, data_type, column_default
--   FROM information_schema.columns
--  WHERE table_name IN ('machines','customers','sites','work_orders',
--                       'machine_movements','work_logs')
--    AND column_name IN ('is_active','record_status')
--  ORDER BY table_name, column_name;

-- SELECT COUNT(*) FROM edit_requests;
