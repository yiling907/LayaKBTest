import os
from openai import AzureOpenAI


def get_client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
    )


def get_embedding(text: str) -> list[float]:
    client = get_client()
    deployment = os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"]
    response = client.embeddings.create(input=text, model=deployment)
    return response.data[0].embedding


def chat_completion(system_prompt: str, user_message: str) -> str:
    client = get_client()
    deployment = os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"]
    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.0,
    )
    return response.choices[0].message.content


def chat_with_tools(messages: list[dict], tools: list[dict]) -> object:
    """Chat completion with OpenAI function calling (tool use)."""
    client     = get_client()
    deployment = os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"]
    response   = client.chat.completions.create(
        model=deployment,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.0,
    )
    return response.choices[0]
