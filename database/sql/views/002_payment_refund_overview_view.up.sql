CREATE OR REPLACE VIEW payment_refund_overview_view AS
SELECT
    p.id AS payment_id,
    p.status AS payment_status,
    p.amount,
    p.currency,
    p.paid_at,
    p.refundable,
    p.refunded_amount,
    u.id AS user_id,
    u.telegram_id,
    u.username,
    rr.id AS refund_request_id,
    rr.status AS refund_request_status,
    rr.reason AS refund_reason,
    r.id AS refund_id,
    r.status AS refund_status,
    r.amount AS refund_amount,
    r.completed_at AS refund_completed_at
FROM payments p
JOIN users u ON u.id = p.user_id
LEFT JOIN refund_requests rr ON rr.payment_id = p.id
LEFT JOIN refunds r ON r.payment_id = p.id;
