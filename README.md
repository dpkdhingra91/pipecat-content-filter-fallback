# pipecat-content-filter-fallback

A [Pipecat](https://github.com/pipecat-ai/pipecat) `FrameProcessor` that catches Azure OpenAI Responsible AI content-filter 400s mid-turn and replaces them with a static fallback assistant turn — so your voice agent doesn't stall in silence when the RAI classifier false-positives on benign input.

~70 lines, drops into any Pipecat pipeline that uses Azure OpenAI.

## The problem

Azure's default Responsible AI policy is tuned conservatively. In a voice-agent setting — where the user is speaking spontaneously about whatever — false positives happen. A candidate describes a product launch with the phrase "go-to-market" and the classifier marks it `sexual: severity=medium`. A user mentions "we crushed our targets" and gets `violence: severity=medium`.

When this happens, Azure returns a 400 with `error: content_filter`. The Pipecat LLM service emits an `ErrorFrame`. The assistant aggregator commits nothing. **The bot goes silent in the middle of a turn.** The user reloads. A fresh session spawns. Often the rich half-completed transcript is overwritten.

You can't fix this entirely server-side. Even Azure's relaxed RAI policy (`severityThreshold=High` on all categories) catches some false positives. You need a client-side safety net.

## What this gives you

A processor that sits between your LLM and TTS, watches for content-filter ErrorFrames, and replaces them with an `LLMTextFrame` containing fallback text:

> "Sorry, let me rephrase that — could you tell me a bit more about your last point?"

TTS speaks it. The assistant aggregator commits it as a normal turn. The conversation continues.

After 3 consecutive filtered turns, the processor switches to a wrap-up text instead of looping fallbacks forever — the conversation has clearly moved into territory the model can't handle, time to end gracefully.

## Install

```bash
pip install pipecat-content-filter-fallback
```

## Wire it up

Position: **after `llm`, before `tts`**.

```python
from pipecat.pipeline.pipeline import Pipeline
from pipecat_content_filter_fallback import ContentFilterFallbackProcessor

content_filter = ContentFilterFallbackProcessor()

pipeline = Pipeline([
    transport.input(),
    stt,
    context_aggregator.user(),
    llm,
    content_filter,           # ← here
    tts,
    transport.output(),
    context_aggregator.assistant(),
])
```

## Customize the fallback text

Subclass and override the class attributes:

```python
class MyFallback(ContentFilterFallbackProcessor):
    FALLBACK_TEXT = "Hmm, let me try that differently — can you tell me more about your role?"
    WRAPUP_TEXT = "Thanks — I think we have what we need to wrap up here."
    MAX_CONSECUTIVE = 5  # tolerate more strikes before wrap-up
```

## Pair with relaxed RAI policy

This processor is your *durable* safety net. To reduce the rate of strikes in the first place, also configure a relaxed RAI policy on your Azure OpenAI deployment:

```bash
az cognitiveservices account deployment update \
  --resource-group <rg> \
  --name <account> \
  --deployment-name <model> \
  --rai-policy-name relaxed-v1
```

Where `relaxed-v1` has `severityThreshold=High` on Hate/Sexual/Violence/Selfharm for both Prompt and Completion. See [Azure docs on custom RAI policies](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/content-filters).

## When NOT to use this

- Your domain genuinely has policy-sensitive content (medical, legal triage) — a fallback that pretends nothing happened might be wrong. Build an explicit "I can't help with that" branch instead.
- You're not on Azure OpenAI. The processor specifically matches `content_filter` and `ResponsibleAIPolicyViolation` error strings; other providers won't trigger it (and you wouldn't need it).

## Origin

Extracted from a production voice-interview pipeline (Sarvam STT → Azure OpenAI gpt-4.5 → Sarvam TTS via Pipecat) where ~1 in 300 turns was triggering an Azure RAI false positive. The processor + relaxed policy together dropped the silent-bot rate from "user-noticeable, weekly" to "log-only, monthly."

## Related projects

- 🎯 [`pipecat-sarvam-azure-starter`](https://github.com/dpkdhingra91/pipecat-sarvam-azure-starter) — canonical Sarvam + Azure voice pipeline this processor was extracted from.
- 💾 [`pipecat-transcript-checkpoint`](https://github.com/dpkdhingra91/pipecat-transcript-checkpoint) — per-turn transcript persistence sibling.
- 🎙️ [`pipecat-bot-speaking-observer`](https://github.com/dpkdhingra91/pipecat-bot-speaking-observer) — turn-gate orchestration sibling.

## License

MIT — see [LICENSE](LICENSE).
