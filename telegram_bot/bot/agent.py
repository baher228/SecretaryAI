import json
import time
from typing import AsyncIterator
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


async def run_agent(user_message: str, history: list) -> AsyncIterator[tuple[str, list | None]]:
    """
    Yields (chunk, None) for incremental text deltas.
    Final yield is ("", updated_history) as a sentinel to hand back the final history.
    """
    t0 = time.perf_counter()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [
        {"role": "user", "content": user_message}
    ]

    for iteration in range(1, 11):
        t_call = time.perf_counter()
        response = await client.chat.completions.create(
            model=ZAI_MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            extra_body={"thinking": {"type": "disabled"}},
        )
        print(f"[agent] iter={iteration} glm_call={time.perf_counter()-t_call:.2f}s", flush=True)

        msg = response.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            print(f"[agent] total={time.perf_counter()-t0:.2f}s iterations={iteration}", flush=True)
            yield (msg.content or "", None)
            out_history = [m for m in messages if m.get("role") != "system"]
            yield ("", out_history)
            return

        for call in msg.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            t_tool = time.perf_counter()
            result = await execute_tool(call.function.name, args)
            print(f"[agent] tool={call.function.name} dur={time.perf_counter()-t_tool:.3f}s", flush=True)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, default=str),
            })

        t_stream = time.perf_counter()
        stream = await client.chat.completions.create(
            model=ZAI_MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            extra_body={"thinking": {"type": "disabled"}},
            stream=True,
        )

        full_text = ""
        chunk_count = 0
        first_chunk_t = None
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                delta_content = chunk.choices[0].delta.content
                chunk_count += 1
                if first_chunk_t is None:
                    first_chunk_t = time.perf_counter() - t_stream
                    print(f"[agent] first_chunk_at={first_chunk_t:.2f}s len={len(delta_content)}", flush=True)
                full_text += delta_content
                yield (delta_content, None)

        print(f"[agent] stream_call={time.perf_counter()-t_stream:.2f}s chunks={chunk_count}", flush=True)
        print(f"[agent] total={time.perf_counter()-t0:.2f}s iterations=stream", flush=True)

        messages.append({"role": "assistant", "content": full_text})
        out_history = [m for m in messages if m.get("role") != "system"]
        yield ("", out_history)
        return

    print(f"[agent] total={time.perf_counter()-t0:.2f}s LIMIT REACHED", flush=True)
    yield ("Reached tool-call iteration limit.", None)
    yield ("", [m for m in messages if m.get("role") != "system"])
