CREATE TRIGGER trg_support_tickets_set_updated_at
    BEFORE UPDATE ON support_tickets
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();
