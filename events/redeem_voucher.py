"""You cashed in vouchers."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class RedeemVoucher(BaseEvent):
    name = "RedeemVoucher"
    priority = NORMAL
    keep = ("Type", "Amount",)
    summary = "Redeemed {Type} vouchers: {Amount:,} credits"
