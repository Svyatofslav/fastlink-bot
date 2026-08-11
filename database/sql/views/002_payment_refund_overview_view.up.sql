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
FROM payments AS p
INNER JOIN users AS u ON p.user_id = u.id
LEFT JOIN refund_requests AS rr ON p.id = rr.payment_id
LEFT JOIN refunds AS r ON p.id = r.payment_id;
