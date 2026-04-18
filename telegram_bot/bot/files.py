import base64
from pathlib import Path
import httpx
from pypdf import PdfReader
from openai import AsyncOpenAI
from bot.config import ZAI_API_KEY, ZAI_BASE_URL

vision_client = AsyncOpenAI(api_key=ZAI_API_KEY, base_url=ZAI_BASE_URL)

UPLOAD_DIR = Path("./data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def extract_pdf_text(file_path: Path, max_chars: int = 20000) -> str:
    """Extract text from a digital PDF. Returns up to max_chars chars."""
    try:
        reader = PdfReader(str(file_path))
        parts = []
        total = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            parts.append(text)
            total += len(text)
            if total >= max_chars:
                break
        return "\n".join(parts)[:max_chars]
    except Exception as e:
        return f"[PDF extraction failed: {e}]"


async def summarize_document(filename: str, content: str) -> str:
    """Use GLM-5.1 to produce a 2-4 sentence summary of a document."""
    if not content.strip() or content.startswith("[PDF extraction failed"):
        return content or "(empty document)"

    response = await vision_client.chat.completions.create(
        model="glm-5.1",
        messages=[
            {"role": "system", "content": "You summarize documents for a busy professional's personal secretary AI. Extract: what this document is, key dates/numbers/names, and any action items. 2-4 sentences max, plain text."},
            {"role": "user", "content": f"Filename: {filename}\n\nContent:\n{content}"},
        ],
        extra_body={"thinking": {"type": "disabled"}},
    )
    return response.choices[0].message.content or "(no summary)"


async def describe_image(file_path: Path) -> str:
    """Use GLM-4.5V to describe/extract from an image. Returns caption or extracted text."""
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    suffix = file_path.suffix.lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "gif": "gif"}.get(suffix, "jpeg")
    data_url = f"data:image/{mime};base64,{b64}"

    response = await vision_client.chat.completions.create(
        model="glm-4.5v",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image in 1-3 sentences. If it contains text (e.g. a business card, whiteboard, screenshot), transcribe the key text verbatim. If it's a document, extract any names, phone numbers, dates, amounts."},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
    )
    return response.choices[0].message.content or "(no description)"


async def transcribe_audio(file_path: Path) -> str:
    """Send audio to Z.AI's audio/transcriptions endpoint. Returns transcribed text."""
    url = f"{ZAI_BASE_URL.rstrip('/')}/audio/transcriptions"
    async with httpx.AsyncClient(timeout=60.0) as client:
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "audio/ogg")}
            data = {"model": "whisper-1"}
            headers = {"Authorization": f"Bearer {ZAI_API_KEY}"}
            response = await client.post(url, headers=headers, files=files, data=data)

    if response.status_code != 200:
        return f"[Transcription failed: {response.status_code} {response.text[:200]}]"

    result = response.json()
    return result.get("text", "(no text)")
