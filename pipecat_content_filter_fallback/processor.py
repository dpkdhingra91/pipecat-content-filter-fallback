"""ContentFilterFallbackProcessor — keep voice agents alive through RAI false-positives."""

import logging

from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

logger = logging.getLogger(__name__)


class ContentFilterFallbackProcessor(FrameProcessor):
    """Catches Azure OpenAI `content_filter` 400s and replaces them with a
    static fallback assistant turn so the conversation keeps flowing.

    Real-world failure mode this fixes: a candidate's totally innocuous
    answer gets classified by Azure's default RAI policy as
    `sexual: severity=high` / `hate: severity=medium` / etc — false positive.
    The LLM emits an `ErrorFrame`, the assistant_aggregator commits nothing,
    the bot goes silent mid-turn, the user reloads the page and a fresh
    session starts.

    With this processor in place: the ErrorFrame gets swallowed and replaced
    with an `LLMTextFrame` containing a generic fallback string. TTS speaks
    the fallback, assistant_aggregator commits it as a normal turn, the
    conversation continues.

    Position in pipeline: **after `llm`, before `tts`**. The fallback frame
    must reach TTS so it becomes spoken audio; if you place this after TTS
    you'll get a silent assistant turn.

    After `MAX_CONSECUTIVE` filtered turns in a row, the processor switches
    from the gentle fallback to a wrap-up text — the assumption being that
    the conversation has moved into territory the model can't handle, and
    rather than keep producing fallbacks indefinitely, gracefully end.

    Tunable:
        FALLBACK_TEXT: spoken on a single content-filter strike
        WRAPUP_TEXT: spoken once consecutive strikes hit the limit
        MAX_CONSECUTIVE: how many consecutive filters before wrap-up
    """

    FALLBACK_TEXT = (
        "Sorry, let me rephrase that — could you tell me a bit more about your last point?"
    )
    WRAPUP_TEXT = (
        "Thanks for your time. We've covered enough ground for this round; "
        "we'll wrap up here."
    )
    MAX_CONSECUTIVE = 3

    def __init__(self):
        super().__init__()
        self._this_turn_filtered = False
        self._consecutive = 0

    @staticmethod
    def _is_content_filter(frame: ErrorFrame) -> bool:
        msg = str(getattr(frame, "error", "") or "")
        return "content_filter" in msg or "ResponsibleAIPolicyViolation" in msg

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMFullResponseStartFrame):
            self._this_turn_filtered = False
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, ErrorFrame) and self._is_content_filter(frame):
            self._this_turn_filtered = True
            self._consecutive += 1
            text = (
                self.WRAPUP_TEXT
                if self._consecutive >= self.MAX_CONSECUTIVE
                else self.FALLBACK_TEXT
            )
            logger.warning(
                "[content_filter] caught (consecutive=%d); injecting %s",
                self._consecutive,
                "wrapup" if self._consecutive >= self.MAX_CONSECUTIVE else "fallback",
            )
            await self.push_frame(LLMTextFrame(text), direction)
            return  # swallow the ErrorFrame

        if isinstance(frame, LLMFullResponseEndFrame):
            if not self._this_turn_filtered:
                # Clean turn — reset the consecutive counter.
                self._consecutive = 0
            await self.push_frame(frame, direction)
            return

        await self.push_frame(frame, direction)
