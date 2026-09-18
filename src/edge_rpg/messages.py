from dataclasses import dataclass
from enum import StrEnum
from queue import Queue, Full
import logging


class Kind(StrEnum):
    GPS_UPDATED = "GpsUpdated"
    GPS_INVALID = "GpsInvalid"
    CELL_ENTERED = "CellEntered"
    CELL_BLOCKED = "CellBlocked"
    EXPLORATION_UPDATED = "ExplorationUpdated"
    SCENE_OBSERVED = "SceneObserved"
    THRESHOLD = "ExplorationThresholdReached"
    EVENT_CREATED = "GameEventCreated"
    NPC_INTERACTION = "NpcInteractionStarted"
    VOICE_INTENT = "VoiceIntentDetected"
    QUEST_UPDATED = "QuestUpdated"
    UI_REFRESH = "UiRefreshRequested"


@dataclass(frozen=True)
class Message:
    kind: Kind
    payload: dict


class EventBus:
    """Bounded worker-to-world queue; only main thread owns SQLite/world."""
    def __init__(self):
        self.queue = Queue(maxsize=256)
        self.listeners = []

    def publish(self, kind, **payload):
        try:
            self.queue.put_nowait(Message(kind, payload))
        except Full:
            logging.getLogger("WORLD").warning("event_queue_full kind=%s", kind)

    def notify(self, kind, **payload):
        message = Message(kind, payload)
        for listener in self.listeners:
            listener(message)
