import os
import json
import requests
from fastapi import FastAPI, Request, Query
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)
app = FastAPI()

SYSTEM_PROMPT = """
You are Parlant, a WhatsApp assistant.
Always reply in English.
Return ONLY valid JSON:

{
  "reply": string,
  "intent": string,
  "sentiment": "positive" | "neutral" | "frustrated",
  "confidence": number,
  "next_action": string
}
"""

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
    print("WHATSAPP TEMPLATE RESPONSE STATUS:", resp.status_code)
    print("WHATSAPP TEMPLATE RESPONSE BODY:", resp.text)


@app.post("/start")
def start(phone: str = Query(...)):
    send_initial_template(phone)
    return {"status": "template_sent"}

@app.get("/")
def verify(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == VERIFY_TOKEN:
        return int(q.get("hub.challenge"))
    return {"error": "verification failed"}

@app.post("/")
async def webhook(request: Request):
    payload = await request.json()
    value = payload["entry"][0]["changes"][0]["value"]

    if "messages" not in value:
        return {"status": "ignored"}

    msg = value["messages"][0]
    from_number = msg["from"]
    text = msg["text"]["body"]

    response = chat_parlant(from_number, text)
    send_text(from_number, response["reply"])
    return {"status": "ok"}

def chat_parlant(session: str, text: str):
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{session}: {text}"}
        ]
    )
    return json.loads(completion.choices[0].message.content)

def send_text(to, text):
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
    requests.post(url, headers=headers, json=payload)
