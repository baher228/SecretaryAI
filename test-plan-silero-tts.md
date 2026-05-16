# Test Plan: Silero TTS — Russian Native Voice Synthesis (PR #12)

## What Changed
New TTS provider (Silero) added alongside Edge TTS. Silero runs locally with no API key and provides 5 Russian-native speakers. Dashboard gains a "Voice" tab showing provider config and voice gallery. Two new API endpoints serve voice configuration data.

## Important Context
- **Silero TTS is NOT used for the Gemini Live greeting** — the greeting uses Gemini's native audio
- **Silero TTS IS used for**: template responses, reminder calls, and fallback replies (see `secretary.py:589,648,1562,2107`)
- **Live call testing limitation**: Outbound calls from this VM may be discarded before user picks up. Inbound calls (user calls bot) are more reliable.

---

## Test 1: Voice API Returns Correct Silero Configuration (Shell)
**Status: COMPLETED — PASSED**

1. `GET /api/v1/voice/providers`
2. Assertions (all passed):
   - `current_provider` = `"silero"`
   - `available_providers` = `["edge_tts", "silero"]`
   - `silero.speaker` = `"xenia"`, `silero.model_id` = `"v5_5_ru"`, `silero.sample_rate` = `48000`
   - `silero.available_voices.ru` has 5 items: aidar, baya, kseniya, xenia, eugene

## Test 2: Silero Voices Endpoint (Shell)
**Status: COMPLETED — PASSED**

1. `GET /api/v1/voice/silero/voices`
2. Assertions (all passed):
   - `"ru"` key has 5 voice objects with id/name/gender fields
   - Speaker IDs: aidar, baya, kseniya, xenia, eugene

## Test 3: Dashboard Voice Tab (Browser — Recorded)
**Status: COMPLETED — PASSED**

1. Navigate to `http://localhost:8000/dashboard` → click "Voice" tab
2. Assertions (all passed):
   - Provider card: "Silero (Russian Native)"
   - Speaker card: "xenia"
   - Sample Rate card: "48000 Hz"
   - 5 Silero voice cards shown, Xenia has green "Active" badge
   - Edge TTS section shows DmitryNeural + SvetlanaNeural

## Test 4: Status Tab Voice TTS Card (Browser — Recorded)
**Status: COMPLETED — PASSED**

1. Dashboard → Status tab
2. Assertions (all passed):
   - Voice TTS card exists with green dot + "Silero" text

## Test 5: Standalone Silero TTS Synthesis Verification (Shell)
**NEW — replaces unreliable live call test**

1. Run Python script that uses the TTSEngine to synthesize Russian text via Silero
2. Verify the output is a valid WAV file with correct properties
3. Assertions:
   - Synthesis returns a valid file path (not None) and status "generated"
   - Output file is a `.wav` file (Silero outputs WAV, Edge TTS outputs MP3)
   - File size > 10KB (not empty/corrupt)
   - WAV sample rate matches configured 48000 Hz
   - Audio duration > 0.5 seconds (real speech, not silence)
   - Peak amplitude > 1000 (not silent)
   - **Why adversarial**: If Silero wasn't loaded or synthesis failed, the file would be None or empty. If Edge TTS was accidentally used instead, the output would be .mp3 not .wav.

## Test 6: Multi-Speaker Synthesis — All 5 Speakers Produce Different Audio (Shell)
1. Synthesize the same Russian text with all 5 speakers: aidar, baya, kseniya, xenia, eugene
2. Assertions:
   - All 5 produce valid WAV files
   - All 5 have different file sizes (different speakers = different audio waveforms)
   - **Why adversarial**: If speaker selection was broken (always using the same speaker), all files would be identical in size.

## Test 7: Provider Routing — Edge TTS Fallback Works (Shell)
1. Change TTS_PROVIDER to "edge_tts" and synthesize
2. Assertions:
   - Output is `.mp3` (Edge TTS format), not `.wav` (Silero format)
   - **Why adversarial**: If the provider routing was broken, changing TTS_PROVIDER wouldn't change the output format.

## Not Tested (Blocked)
- **Live Telegram call with Silero voice**: Outbound calls from VM showed DISCARDED_CALL. User needs to call the bot directly (inbound) to hear Silero TTS during a template/reminder response. Note: even if the call works, Silero is only triggered for specific response types (templates, reminders), not the Gemini Live greeting.
