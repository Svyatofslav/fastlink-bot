from enum import StrEnum


class SubscriptionStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    DISABLED = "disabled"
    EXPIRED = "expired"


class DisabledReason(StrEnum):
    EXPIRED = "expired"
    REFUNDED = "refunded"
    ADMIN_DISABLED = "admin_disabled"
    FRAUD_SUSPECTED = "fraud_suspected"
    PAYMENT_CANCELED = "payment_canceled"
    SYSTEM_ERROR = "system_error"


class PaymentProvider(StrEnum):
    YOOKASSA = "yookassa"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    WAITING_FOR_CAPTURE = "waiting_for_capture"
    SUCCEEDED = "succeeded"
    CANCELED = "canceled"
    REFUNDED_PARTIALLY = "refunded_partially"
    REFUNDED_FULLY = "refunded_fully"


class RefundRequestStatus(StrEnum):
    NEW = "new"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSED = "processed"
    FAILED = "failed"


class RefundStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class NotificationType(StrEnum):
    SUB_EXPIRES_3D = "sub_expires_3d"
    SUB_EXPIRES_1D = "sub_expires_1d"
    TRAFFIC_80 = "traffic_80"
    TRAFFIC_95 = "traffic_95"
    TRAFFIC_100 = "traffic_100"
    REFUND_PROCESSED = "refund_processed"
    PAYMENT_SUCCEEDED = "payment_succeeded"


class NotificationDeliveryStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"


class AdminActionType(StrEnum):
    LOGIN = "login"
    LOGOUT = "logout"
    CREATE_ADMIN = "create_admin"
    UPDATE_ADMIN = "update_admin"
    DISABLE_ADMIN = "disable_admin"
    ENABLE_ADMIN = "enable_admin"
    CREATE_SERVER = "create_server"
    UPDATE_SERVER = "update_server"
    DELETE_SERVER = "delete_server"
    CREATE_TARIFF = "create_tariff"
    UPDATE_TARIFF = "update_tariff"
    DELETE_TARIFF = "delete_tariff"
    BAN_USER = "ban_user"
    UNBAN_USER = "unban_user"
    DISABLE_SUBSCRIPTION = "disable_subscription"
    ENABLE_SUBSCRIPTION = "enable_subscription"
    APPROVE_REFUND = "approve_refund"
    REJECT_REFUND = "reject_refund"
    PROCESS_REFUND = "process_refund"


class WebhookEventStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
