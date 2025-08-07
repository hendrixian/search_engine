import httpx
import os
from tenacity import retry, wait_random_exponential, stop_after_attempt


MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")  # Set this in your environment
MISTRAL_MODEL = "mistral-small"  # Change to "mistral-medium" or "mistral-large" if you have access

if not MISTRAL_API_KEY:
    raise ValueError("MISTRAL_API_KEY environment variable not set")

@retry(wait=wait_random_exponential(multiplier=1, min=4, max=10), 
      stop=stop_after_attempt(3))

def call_mistral(question, context):
    system_prompt = (
        "You are an academic assistant. Answer clearly, using only the context provided below. "
        "If you are unsure, say you don't know."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}
    ]

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }

    body = {
        "model": MISTRAL_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 512,
        "stream": False
    }

    try:
        response = httpx.post("https://api.mistral.ai/v1/chat/completions", json=body, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"❌ Mistral API error: {e}"
