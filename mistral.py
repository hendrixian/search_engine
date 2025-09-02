import httpx
import os
from tenacity import retry, wait_random_exponential, stop_after_attempt

def get_mistral_api_key():
    """Get Mistral API key from environment with better error handling"""
    key = os.getenv("MISTRAL_API_KEY")
    if not key:
        # Try alternative environment variable names
        key = os.getenv("MISTRAL_KEY") or os.getenv("mistral_api_key")
    
    if not key:
        print("❌ MISTRAL_API_KEY environment variable not set")
        print("Available env vars:", [k for k in os.environ.keys() if 'mistral' in k.lower()])
        raise ValueError("MISTRAL_API_KEY environment variable not set")
    
    print("✅ Mistral API key loaded successfully")
    return key

MISTRAL_API_KEY = get_mistral_api_key()
MISTRAL_MODEL = "mistral-small"

@retry(wait=wait_random_exponential(multiplier=1, min=4, max=10), 
      stop=stop_after_attempt(8))
def call_mistral(question, context):
    """
    Legacy Mistral API call function - maintained for backward compatibility
    For enhanced features, use enhanced_mistral.py instead
    """
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
        "max_tokens": 2048,
        "stream": False
    }

    try:
        response = httpx.post("https://api.mistral.ai/v1/chat/completions", json=body, headers=headers, timeout=60)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"❌ Mistral API error: {e}"

# Import enhanced functionality
try:
    from enhanced_mistral import call_mistral_enhanced, EnhancedMistralAI
    print("✅ Enhanced Mistral AI features loaded successfully")
    enhanced_available = True
except ImportError as e:
    print(f"⚠️ Enhanced Mistral features not available: {e}")
    enhanced_available = False
    call_mistral_enhanced = None
    EnhancedMistralAI = None