import os
import json
import requests

from fastapi import FastAPI, Request, Query
from fastapi.responses import PlainTextResponse
from openai import OpenAI
from dotenv import load_dotenv

# ==================================================
# ENV + CONFIG
# ==================================================
load_dotenv()

PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ==================================================
# GROQ CLIENT (OPENAI-COMPATIBLE)
# ==================================================
groq_client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# ==================================================
# FASTAPI APP
# ==================================================
app = FastAPI(title="WhatsApp + Parlant + Groq")

# ==================================================
# PARLANT SYSTEM PROMPT
# ==================================================
SYSTEM_PROMPT = """
You are Parlant, a WhatsApp conversation intelligence engine.

Rules:
- Always reply in English
- Be concise, polite, and helpful
- Ask follow-up questions if needed
- Decide what should happen next

Return ONLY valid JSON in this exact format:

{
  "reply": string,
  "intent": string,
  "sentiment": "positive" | "neutral" | "frustrated",
  "confidence": number,
  "next_action": string
}
"""

# ==================================================
# SEND INITIAL WHATSAPP TEMPLATE
# ==================================================
def send_initial_template(phone: str):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": "lad_telephony",
            "language": {"code": "en"}
        }
    }

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    resp = requests.post(url, headers=headers, json=payload)
    print("TEMPLATE STATUS:", resp.status_code)
    print("TEMPLATE BODY:", resp.text)

# ==================================================
# START CONVERSATION
# ==================================================
@app.post("/start")
def start(phone: str = Query(..., description="Phone number with country code")):
    send_initial_template(phone)
    return {"status": "template_sent"}

# ==================================================
# WEBHOOK VERIFICATION (META)
# ==================================================
@app.get("/")
def verify(request: Request):
    params = request.query_params

    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == VERIFY_TOKEN
    ):
        return PlainTextResponse(
            content=params.get("hub.challenge"),
            status_code=200
        )

    return PlainTextResponse(content="Verification failed", status_code=403)

# ==================================================
# RECEIVE WHATSAPP MESSAGES
# ==================================================
@app.post("/")
async def webhook(request: Request):
    payload = await request.json()
    value = payload["entry"][0]["changes"][0]["value"]

    # Ignore delivery/read receipts
    if "messages" not in value:
        return {"status": "ignored"}

    msg = value["messages"][0]
    from_number = msg["from"]
    text = msg["text"]["body"]

    session_id = f"whatsapp:{from_number}"

    parlant_response = chat_parlant(session_id, text)

    send_text(from_number, parlant_response["reply"])

    return {"status": "ok"}

# ==================================================
# PARLANT ENGINE (GROQ)
# ==================================================
def chat_parlant(session_id: str, user_text: str):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"""
Session ID: {session_id}
User message: {user_text}
"""
        }
    ]

    try:
        completion = groq_client.chat.completions.create(
            model="llama3-70b-8192",
            messages=messages,
            temperature=0.2
        )

        raw = completion.choices[0].message.content.strip()
        return json.loads(raw)

    except Exception as e:
        print("GROQ ERROR:", str(e))
        # Safety fallback — never fail WhatsApp webhook
        return {
            "reply": "Thanks for your message. A support agent will follow up shortly.",
            "intent": "fallback",
            "sentiment": "neutral",
            "confidence": 0.1,
            "next_action": "human_handoff"
        }

# ==================================================
# SEND NORMAL WHATSAPP TEXT
# ==================================================
def send_text(to: str, text: str):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    resp = requests.post(url, headers=headers, json=payload)
    print("TEXT STATUS:", resp.status_code)
    print("TEXT BODY:", resp.text)
