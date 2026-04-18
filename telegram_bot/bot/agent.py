import json
from openai import AsyncOpenAI
from bot.config import ZAI_API_KEY, ZAI_BASE_URL, ZAI_MODEL
from bot.tools import TOOL_SCHEMAS, execute_tool

client = AsyncOpenAI(api_key=ZAI_API_KEY, base_url=ZAI_BASE_URL)

SYSTEM_PROMPT = """You are a personal AI secretary assistant communicating with your owner via Telegram.

You have access to a database of phone calls (handled by a separate voice agent) and tasks.

Behavior rules:
- Be concise. This is a chat, not an essay.
- For ambiguous destructive actions (creating tasks), briefly confirm intent before calling the tool.
- Reference calls by ID and a short identifier like "Tuesday call with Maria".
- Use list_recent_calls first, then get_call_details only if the user wants deeper info.
- Respond in English."""


async def run_agent(user_message: str, history: list) -> tuple[str, list]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [
        {"role": "user", "content": user_message}
    ]

    for _ in range(10):
        response = await client.chat.completions.create(
            model=ZAI_MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )
        msg = response.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            out_history = [m for m in messages if m.get("role") != "system"]
            return (msg.content or ""), out_history

        for call in msg.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            result = await execute_tool(call.function.name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, default=str),
            })

    return "Reached tool-call iteration limit.", messages
