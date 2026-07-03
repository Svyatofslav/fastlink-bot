CREATE TRIGGER trg_webhook_events_audit_insert
    AFTER INSERT ON webhook_events
    FOR EACH ROW
    EXECUTE FUNCTION log_webhook_events_audit();

CREATE TRIGGER trg_webhook_events_audit_update
    AFTER UPDATE ON webhook_events
    FOR EACH ROW
    EXECUTE FUNCTION log_webhook_events_audit();
