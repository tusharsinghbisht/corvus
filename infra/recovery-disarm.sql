-- Apply ONLY to a restored database, with application services stopped.
-- A backup may predate a completed/billed request. Never replay its old queue.
BEGIN;
UPDATE analyst_policies SET enabled=false,version=version+1,updated_at=now();
UPDATE triage_attempts SET status='unknown',completed_at=now(),
    error_code='restored_backup_requires_reapproval'
WHERE status IN ('pending_collection','collecting','awaiting_approval','queued','requesting');
DO $$ BEGIN
IF to_regclass('investigation_steps') IS NOT NULL THEN
 UPDATE investigation_steps SET state=CASE WHEN model_request THEN 'unknown' ELSE 'failed' END,
 completed_at=now(),error_code='restored_backup_requires_reapproval' WHERE state='running';
END IF;
END $$;
DELETE FROM sessions;
INSERT INTO audit_events(action) VALUES('recovery.queue_disarmed');
COMMIT;
