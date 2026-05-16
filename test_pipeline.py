"""Test the exact audio pipeline: Gemini Live → _extract_audio → resample → WAV → verify."""
import asyncio
import array
import wave
from pathlib import Path

from google import genai
from google.genai import types

API_KEY = "AIzaSyAflKrE895J1C0XgFSJwJQ2ZamTva31k1o"
MODEL = "gemini-3.1-flash-live-preview"
VOICE = "Zephyr"
PROMPT = "Телефонный звонок только что подключён. Тепло поприветствуй звонящего и спроси, чем можешь помочь."

RECEIVE_SAMPLE_RATE = 24000
PLAYBACK_SAMPLE_RATE = 48000

OUT_24K = Path("/home/ubuntu/repos/SecretaryAI/test_24k.wav")
OUT_48K = Path("/home/ubuntu/repos/SecretaryAI/test_48k.wav")


def _resample_pcm16(data: bytes, src_rate: int, dst_rate: int) -> bytes:
    if src_rate == dst_rate:
        return data
    aligned = len(data) // 2 * 2
    src = array.array("h")
    src.frombytes(data[:aligned])
    ratio = src_rate / dst_rate
    n = len(src)
    dst_count = int(n / ratio)
    dst = array.array("h", (src[min(int(i * ratio), n - 1)] for i in range(dst_count)))
    return dst.tobytes()


def _extract_audio(response, server_content):
    """Exact copy of GeminiLiveSession._extract_audio"""
    chunks = []
    model_turn = getattr(server_content, "model_turn", None)
    for part in getattr(model_turn, "parts", []) or []:
        inline_data = getattr(part, "inline_data", None)
        data = getattr(inline_data, "data", None)
        if isinstance(data, bytes):
            chunks.append(data)
    if chunks:
        return chunks
    data = getattr(response, "data", None)
    return [data] if isinstance(data, bytes) else []


async def main():
    client = genai.Client(
        http_options={"api_version": "v1beta"},
        api_key=API_KEY,
    )

    config = types.LiveConnectConfig(
        responseModalities=[types.Modality.AUDIO],
        systemInstruction="Ты — секретарь. Отвечай кратко и по-русски.",
        speechConfig=types.SpeechConfig(
            voiceConfig=types.VoiceConfig(
                prebuiltVoiceConfig=types.PrebuiltVoiceConfig(voiceName=VOICE)
            )
        ),
        inputAudioTranscription=types.AudioTranscriptionConfig(),
        outputAudioTranscription=types.AudioTranscriptionConfig(),
    )

    print(f"Connecting to {MODEL}...")
    async with client.aio.live.connect(model=MODEL, config=config) as session:
        print("Connected. Sending prompt...")
        await session.send_realtime_input(text=PROMPT)

        all_pcm: list[bytes] = []
        chunk_count = 0

        async for response in session.receive():
            server_content = getattr(response, "server_content", None)

            # Extract using the exact same function as the app
            audio_chunks = _extract_audio(response, server_content)
            for chunk in audio_chunks:
                all_pcm.append(chunk)
                chunk_count += 1

            output_tx = getattr(server_content, "output_transcription", None)
            if output_tx and getattr(output_tx, "text", None):
                print(f"  Transcript: {output_tx.text}")

            if getattr(server_content, "turn_complete", False):
                print("  Turn complete!")
                break

        total_pcm = b"".join(all_pcm)
        print(f"\nChunks extracted: {chunk_count}")
        print(f"Total PCM: {len(total_pcm)} bytes")
        print(f"Duration at 24kHz: {len(total_pcm) / (2 * RECEIVE_SAMPLE_RATE):.2f}s")

        # Write 24kHz WAV
        with wave.open(str(OUT_24K), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(RECEIVE_SAMPLE_RATE)
            wf.writeframes(total_pcm)
        print(f"Saved 24kHz WAV: {OUT_24K} ({OUT_24K.stat().st_size} bytes)")

        # Resample to 48kHz (same as app does)
        pcm_48k = _resample_pcm16(total_pcm, RECEIVE_SAMPLE_RATE, PLAYBACK_SAMPLE_RATE)
        print(f"Resampled to 48kHz: {len(pcm_48k)} bytes")
        print(f"Duration at 48kHz: {len(pcm_48k) / (2 * PLAYBACK_SAMPLE_RATE):.2f}s")

        # Write 48kHz WAV
        with wave.open(str(OUT_48K), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(PLAYBACK_SAMPLE_RATE)
            wf.writeframes(pcm_48k)
        print(f"Saved 48kHz WAV: {OUT_48K} ({OUT_48K.stat().st_size} bytes)")

        # Verify WAV file is valid
        with wave.open(str(OUT_48K), "rb") as wf:
            print(f"\nWAV verification:")
            print(f"  Channels: {wf.getnchannels()}")
            print(f"  Sample width: {wf.getsampwidth()}")
            print(f"  Frame rate: {wf.getframerate()}")
            print(f"  Frames: {wf.getnframes()}")
            print(f"  Duration: {wf.getnframes() / wf.getframerate():.2f}s")

        # Check for silence (all zeros)
        pcm_arr = array.array("h")
        pcm_arr.frombytes(pcm_48k)
        max_val = max(abs(s) for s in pcm_arr) if pcm_arr else 0
        avg_val = sum(abs(s) for s in pcm_arr) / len(pcm_arr) if pcm_arr else 0
        print(f"\n  Peak amplitude: {max_val} (max 32767)")
        print(f"  Avg amplitude: {avg_val:.0f}")
        if max_val < 100:
            print("  WARNING: Audio appears to be SILENCE!")
        else:
            print("  Audio appears to have content (not silent)")


if __name__ == "__main__":
    asyncio.run(main())
