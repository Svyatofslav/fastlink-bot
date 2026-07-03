CREATE INDEX IF NOT EXISTS ix_subscriptions_status_expires_at
    ON subscriptions (status, expires_at);

CREATE INDEX IF NOT EXISTS ix_payments_user_created_at_desc
    ON payments (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_payments_subscription_created_at_desc
    ON payments (subscription_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_refund_requests_status_created_at_desc
    ON refund_requests (status, created_at DESC);
