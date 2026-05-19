"""pipecat-content-filter-fallback — Azure OpenAI RAI false-positive guard for Pipecat.

A `FrameProcessor` that catches Azure OpenAI `content_filter` 400s mid-turn
and replaces them with a static fallback assistant turn, so a false-positive
strike doesn't stall the voice agent in silence.
"""

from .processor import ContentFilterFallbackProcessor

__all__ = ["ContentFilterFallbackProcessor"]
__version__ = "0.1.0"
