import os
from openai import OpenAI, AsyncOpenAI

# --- API Key Setup ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY environment variable is not set.")

# --- Sync + Async Clients ---
sync_client = OpenAI(api_key=OPENAI_API_KEY)
async_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# --- Streaming Helper (async generator) ---
async def stream_chat_response(messages, model="gpt-4o", temperature=0.7):
    """
    Yields the streaming response from OpenAI as chunks of text.

    Usage:
        async for chunk in stream_chat_response([...]):
            print(chunk)
    """
    stream = await async_client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        stream=True,
    )

    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content

# --- Synchronous GPT Task Runner with Token Tracking ---
def run_gpt_task(prompt: str, system: str = "", model: str = "gpt-4o") -> tuple[str, int]:
    response = sync_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=4096,
    )
    content = response.choices[0].message.content.strip()
    tokens_used = response.usage.total_tokens
    return content, tokens_used