import os
import httpx
from openai import OpenAI


def get_chat_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ["ARK_API_KEY"],
        base_url=os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
    )


def get_embedding(text: str) -> list[float]:
    api_key = os.environ["ARK_API_KEY"]
    model = os.environ["ARK_EMBEDDING_MODEL"]
    embedding_url = os.environ.get("ARK_EMBEDDING_BASE_URL")

    if embedding_url and "multimodal" in embedding_url:
        # Multimodal embedding endpoint requires a different input format
        resp = httpx.post(
            embedding_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "input": [{"type": "text", "text": text}]},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["data"]["embedding"]

    base_url = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.embeddings.create(input=text, model=model)
    return response.data[0].embedding


def chat_completion(system_prompt: str, user_message: str) -> str:
    client = get_chat_client()
    model = os.environ["ARK_CHAT_MODEL"]
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.0,
    )
    return response.choices[0].message.content


def chat_with_tools(messages: list[dict], tools: list[dict]) -> object:
    """Chat completion with tool calling."""
    client = get_chat_client()
    model = os.environ["ARK_CHAT_MODEL"]
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.0,
    )
    return response.choices[0]
