CREATE OR REPLACE FUNCTION log_webhook_events_audit()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO webhook_events_audit (event_id, operation, old_row, new_row)
        VALUES (NEW.id, 'INSERT', NULL, row_to_json(NEW)::jsonb);
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO webhook_events_audit (event_id, operation, old_row, new_row)
        VALUES (NEW.id, 'UPDATE', row_to_json(OLD)::jsonb, row_to_json(NEW)::jsonb);
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
