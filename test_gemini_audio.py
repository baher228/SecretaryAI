"""Standalone test: connect to Gemini Live, send a text prompt, verify audio comes back."""
import asyncio
import wave
from pathlib import Path

from google import genai
from google.genai import types

API_KEY = "AIzaSyAflKrE895J1C0XgFSJwJQ2ZamTva31k1o"
MODEL = "gemini-3.1-flash-live-preview"
VOICE = "Zephyr"
PROMPT = "Телефонный звонок только что подключён. Тепло поприветствуй звонящего и спроси, чем можешь помочь."

RECEIVE_SAMPLE_RATE = 24000
OUTPUT_WAV = Path("/home/ubuntu/repos/SecretaryAI/test_gemini_output.wav")


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
        print("Connected. Sending prompt via send_realtime_input...")
        await session.send_realtime_input(text=PROMPT)

        all_pcm: list[bytes] = []
        turn_complete = False

        print("Receiving audio...")
        async for response in session.receive():
            server_content = getattr(response, "server_content", None)

            # Check for transcripts
            output_tx = getattr(server_content, "output_transcription", None)
            if output_tx and getattr(output_tx, "text", None):
                print(f"  Transcript: {output_tx.text}")

            # Extract audio
            model_turn = getattr(server_content, "model_turn", None)
            for part in getattr(model_turn, "parts", []) or []:
                inline_data = getattr(part, "inline_data", None)
                data = getattr(inline_data, "data", None)
                if isinstance(data, bytes):
                    all_pcm.append(data)
                    print(f"  Audio chunk: {len(data)} bytes")

            # Also check response.data
            rdata = getattr(response, "data", None)
            if isinstance(rdata, bytes):
                all_pcm.append(rdata)
                print(f"  Audio data (response.data): {len(rdata)} bytes")

            if getattr(server_content, "turn_complete", False):
                print("  Turn complete!")
                turn_complete = True
                break

        total_pcm = b"".join(all_pcm)
        print(f"\nTotal PCM collected: {len(total_pcm)} bytes")
        print(f"Duration: {len(total_pcm) / (2 * RECEIVE_SAMPLE_RATE):.2f} seconds (at {RECEIVE_SAMPLE_RATE}Hz)")

        if total_pcm:
            with wave.open(str(OUTPUT_WAV), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(RECEIVE_SAMPLE_RATE)
                wf.writeframes(total_pcm)
            print(f"Saved to {OUTPUT_WAV}")
        else:
            print("NO AUDIO RECEIVED!")


if __name__ == "__main__":
    asyncio.run(main())
