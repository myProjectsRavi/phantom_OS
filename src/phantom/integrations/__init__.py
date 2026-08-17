"""Optional public integration bridges."""

from phantom.integrations.local_llm_bridge import LocalLLMBridge
from phantom.integrations.neurovault_bridge import NeurovaultBridge

__all__ = ["LocalLLMBridge", "NeurovaultBridge"]
