"""PHANTOM core data models."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

# ── Perception ─────────────────────────────


class CaptureMode(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    FOCUSED = "focused"
    RECORDING = "recording"


class UIElementType(str, Enum):
    BUTTON = "button"
    TEXT_FIELD = "text_field"
    MENU = "menu"
    MENU_ITEM = "menu_item"
    TAB = "tab"
    CODE_BLOCK = "code_block"
    TERMINAL = "terminal"
    STATUS_BAR = "status_bar"
    TITLE_BAR = "title_bar"
    LINK = "link"
    TABLE = "table"
    NOTIFICATION = "notification"
    DIALOG = "dialog"
    ICON = "icon"
    UNKNOWN = "unknown"


@dataclass
class AppInfo:
    name: str = ""
    bundle_id: str = ""
    window_title: str = ""


@dataclass
class CaptureResult:
    image: Any = None  # np.ndarray
    timestamp: float = field(default_factory=time.time)
    monitor_info: dict = field(default_factory=dict)


@dataclass
class UIElement:
    type: UIElementType = UIElementType.UNKNOWN
    bounds: tuple = (0, 0, 0, 0)
    text: str = ""
    confidence: float = 0.0
    interactive: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class PerceptionFrame:
    timestamp: float = field(default_factory=time.time)
    app_name: str = ""
    app_bundle_id: str = ""
    window_title: str = ""
    screen_type: str = "unknown"
    elements: list[UIElement] = field(default_factory=list)
    text_content: dict = field(default_factory=dict)
    cursor_position: tuple = (0, 0)
    active_element: Optional[UIElement] = None
    is_typing: bool = False
    is_reading: bool = False
    is_navigating: bool = False
    idle_seconds: float = 0.0
    metadata: dict = field(default_factory=dict)


# ── Actions ────────────────────────────────


class ActionType(str, Enum):
    KEYSTROKE = "keystroke"
    MOUSE_CLICK = "mouse_click"
    CLIPBOARD_COPY = "clipboard_copy"
    CLIPBOARD_PASTE = "clipboard_paste"
    APP_SWITCH = "app_switch"
    TAB_SWITCH = "tab_switch"
    FILE_OPEN = "file_open"
    FILE_SAVE = "file_save"
    URL_NAVIGATE = "url_navigate"
    COMMAND_RUN = "command_run"
    SHORTCUT = "shortcut"
    MOUSE_SCROLL = "mouse_scroll"
    WINDOW_RESIZE = "window_resize"
    UNKNOWN = "unknown"


class PhantomActionType(str, Enum):
    TYPE_TEXT = "type_text"
    PRESS_KEY = "press_key"
    MOUSE_CLICK = "mouse_click"
    MOUSE_MOVE = "mouse_move"
    CLIPBOARD_COPY = "clipboard_copy"
    CLIPBOARD_PASTE = "clipboard_paste"
    CLIPBOARD_SET = "clipboard_set"
    APP_ACTIVATE = "app_activate"
    APP_OPEN = "app_open"
    URL_OPEN = "url_open"
    FILE_OPEN = "file_open"
    FILE_MOVE = "file_move"
    RUN_COMMAND = "run_command"
    SEQUENCE = "sequence"
    WAIT = "wait"
    NOTIFICATION = "notification"


@dataclass
class UserAction:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: ActionType = ActionType.UNKNOWN
    app_name: str = ""
    window_title: str = ""
    timestamp: float = field(default_factory=time.time)
    data: dict = field(default_factory=dict)
    duration_ms: float = 0


@dataclass
class ActionRequest:
    type: PhantomActionType = PhantomActionType.NOTIFICATION
    params: dict = field(default_factory=dict)
    requires_approval: bool = False
    undo_action: Optional[dict] = None
    timeout_seconds: int = 10
    source: str = ""


@dataclass
class ActionResult:
    success: bool = False
    action_type: PhantomActionType = PhantomActionType.NOTIFICATION
    error: Optional[str] = None
    undo_info: Optional[dict] = None
    duration_ms: float = 0
    metadata: dict = field(default_factory=dict)


# ── Intent ──────────────────────────────────


class IntentType(str, Enum):
    COPY_PASTE_TRANSFER = "copy_paste_transfer"
    DATA_ENTRY = "data_entry"
    APP_SWITCHING = "app_switching"
    CODING = "coding"
    WRITING = "writing"
    WEB_RESEARCH = "web_research"
    DEBUG_ERROR = "debug_error"
    RESPOND_TO_MESSAGE = "respond_to_message"
    BROWSING = "browsing"
    IDLE = "idle"
    UNKNOWN = "unknown"


@dataclass
class IntentResult:
    intent: IntentType = IntentType.UNKNOWN
    confidence: float = 0.0
    source_app: str = ""
    target_app: str = ""
    context: dict = field(default_factory=dict)
    suggested_automation: Optional[dict] = None


# ── Prediction ──────────────────────────────


@dataclass
class PredictedAction:
    action_type: ActionType = ActionType.UNKNOWN
    target_app: str = ""
    confidence: float = 0.0
    expected_in_seconds: float = 0.0
    preparation: Optional[dict] = None
    source: str = ""


# ── Patterns ────────────────────────────────


@dataclass
class LearnedPattern:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    signature: str = ""
    steps: list[dict] = field(default_factory=list)
    frequency: int = 0
    confidence: float = 0.0
    last_seen: float = 0
    created_at: float = field(default_factory=time.time)
    approved: bool = False
    auto_execute: bool = False
    tags: list[str] = field(default_factory=list)


# ── Recipes ──────────────────────────────────


@dataclass
class RecipeTrigger:
    type: str = ""
    config: dict = field(default_factory=dict)


@dataclass
class RecipeCondition:
    type: str = ""
    params: dict = field(default_factory=dict)
    negate: bool = False


@dataclass
class RecipeStep:
    type: str = ""
    params: dict = field(default_factory=dict)
    delay_after: float = 0.0
    condition: Optional[str] = None
    on_error: str = "continue"
    max_retries: int = 1


@dataclass
class Recipe:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""
    version: str = "1.0"
    author: str = "user"
    trigger: Optional[RecipeTrigger] = None
    conditions: list[RecipeCondition] = field(default_factory=list)
    steps: list[RecipeStep] = field(default_factory=list)
    variables: dict = field(default_factory=dict)
    enabled: bool = True
    source: str = "user"
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_run: Optional[float] = None
    run_count: int = 0
    success_rate: float = 1.0


# ── Safety ───────────────────────────────────


class TrustLevel(str, Enum):
    SUGGEST_ONLY = "suggest_only"
    APPROVE_EACH = "approve_each"
    APPROVE_NEW = "approve_new"
    AUTO_EXECUTE = "auto_execute"


class TriggerType(str, Enum):
    APP_SWITCH = "app_switch"
    CONTENT_MATCH = "content_match"
    SCHEDULE = "schedule"
    IDLE = "idle"
    HOTKEY = "hotkey"
    PATTERN_MATCH = "pattern_match"


@dataclass
class TriggerEvent:
    type: str = TriggerType.APP_SWITCH.value
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
