"""A chat message arrived (wing, squadron, local, direct, NPC...). The message reader (personality/messages.py) decides whether to read it out."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class ReceiveText(BaseEvent):
    name = "ReceiveText"
    priority = LOW
    keep = ("From", "From_Localised", "Message", "Message_Localised", "Channel")
    summary = "Message from {From}"
