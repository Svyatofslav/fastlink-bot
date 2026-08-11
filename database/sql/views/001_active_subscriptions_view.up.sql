CREATE OR REPLACE VIEW active_subscriptions_view AS
SELECT
    s.id AS subscription_id,
    s.status,
    s.starts_at,
    s.expires_at,
    s.data_limit_bytes,
    s.data_used_bytes,
    s.auto_renew,
    u.id AS user_id,
    u.telegram_id,
    u.username,
    srv.id AS server_id,
    srv.name AS server_name,
    srv.country_name,
    t.id AS tariff_id,
    t.name AS tariff_name,
    t.duration_days,
    t.price_amount,
    t.price_currency
FROM subscriptions AS s
INNER JOIN users AS u ON s.user_id = u.id
INNER JOIN servers AS srv ON s.server_id = srv.id
LEFT JOIN tariffs AS t ON s.tariff_id = t.id
WHERE s.status = 'ACTIVE';
