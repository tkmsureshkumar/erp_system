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

-- ── Phase 4 : Site — GST & Billing address fields ────────────────────────────
ALTER TABLE sites ADD COLUMN IF NOT EXISTS gst_number      TEXT;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS bill_to_address TEXT;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS ship_to_address TEXT;

-- ── Phase 5 : Machine Compliance Records table ────────────────────────────────
CREATE TABLE IF NOT EXISTS machine_compliance_records (
    id              UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    machine_id      UUID        NOT NULL,
    compliance_type TEXT        NOT NULL,  -- 'TPI' | 'PUC' | 'Form 11' | 'Insurance' | 'Other'
    custom_type     TEXT,                  -- label when compliance_type = 'Other'
    issue_date      DATE,
    expiry_date     DATE,
    document_url    TEXT,
    remarks         TEXT,
    is_active       BOOLEAN     DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mcr_machine ON machine_compliance_records(machine_id);
CREATE INDEX IF NOT EXISTS idx_mcr_type    ON machine_compliance_records(compliance_type);
CREATE INDEX IF NOT EXISTS idx_mcr_expiry  ON machine_compliance_records(expiry_date);

-- ── Phase 6 : Operator — unique Employee Code ────────────────────────────────
ALTER TABLE operators ADD COLUMN IF NOT EXISTS emp_code TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_operators_emp_code ON operators(emp_code);

-- ── Phase 7 : Machine Movement — transport details for Load events ───────────
ALTER TABLE machine_movements ADD COLUMN IF NOT EXISTS transporter_name  TEXT;
ALTER TABLE machine_movements ADD COLUMN IF NOT EXISTS vehicle_number    TEXT;
ALTER TABLE machine_movements ADD COLUMN IF NOT EXISTS driver_name       TEXT;
ALTER TABLE machine_movements ADD COLUMN IF NOT EXISTS driver_contact    TEXT;
ALTER TABLE machine_movements ADD COLUMN IF NOT EXISTS lr_challan_number TEXT;
ALTER TABLE machine_movements ADD COLUMN IF NOT EXISTS dispatch_remarks  TEXT;

-- ── Verification queries (run after migration) ────────────────────────────────
-- SELECT column_name, data_type, column_default
--   FROM information_schema.columns
--  WHERE table_name IN ('machines','customers','sites','work_orders',
--                       'machine_movements','work_logs')
--    AND column_name IN ('is_active','record_status')
--  ORDER BY table_name, column_name;

-- SELECT COUNT(*) FROM edit_requests;
