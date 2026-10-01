import os
import requests
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv(override=True)

def discover_active_groq_model(api_key: str) -> str:
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        res = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=5)
        if res.status_code == 200:
            models_data = res.json().get("data", [])
            # فلترة الموديلات واستبعاد الصوتية والتخصصية
            active_ids = [
                m["id"] for m in models_data 
                if "id" in m and not m["id"].startswith(("canopylabs/", "whisper-", "playai/", "qwen-qwq"))
            ]

            priority_candidates = [
                "llama-3.3-70b-versatile",
                "llama3-70b-8192",
                "llama3-8b-8192",
                "mixtral-8x7b-32768",
                "gemma2-9b-it"
            ]

            for candidate in priority_candidates:
                if candidate in active_ids:
                    return candidate

            if active_ids:
                return active_ids[0]
    except Exception:
        pass

    return "llama3-70b-8192"

def get_llm(temperature: float = 0.2) -> ChatGroq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or "YourActualGroqApiKey" in api_key:
        raise ValueError("❌ GROQ_API_KEY غير مضاف في ملف .env!")

    model_name = discover_active_groq_model(api_key)
    return ChatGroq(groq_api_key=api_key, model_name=model_name, temperature=temperature)
