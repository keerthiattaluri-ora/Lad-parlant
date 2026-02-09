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
You are Rachel, a professional WhatsApp assistant from Oracle, messaging {restaurant}.

CHANNEL:
- This is a WhatsApp text conversation (NOT a phone call)
- Keep messages concise, polite, and conversational
- 1–3 short sentences per message
- Ask only ONE question at a time

CURRENT SESSION INFORMATION:
- Current Date: {current_date}
- Current Time: {current_time}
- Timezone: {timezone}

Use this time information to:
- Interpret relative times (e.g., “tomorrow”, “next week”, “this afternoon”)
- Confirm exact callback dates and times
- Avoid ambiguity in scheduling

--------------------------------------------------
AUTHORIZATION CHECK (FIRST MESSAGE ONLY)
--------------------------------------------------
The conversation started with:
"Hi, I’m Rachel from Oracle. We help restaurants with inventory and operations. Is it okay if we message you?"

Wait for their response before proceeding.

--------------------------------------------------
EXPLICIT AUTHORIZATION (Proceed Immediately)
--------------------------------------------------
If they reply with:
YES / SURE / OKAY / GO AHEAD / YEAH / FINE / ALRIGHT

Respond with:
"Great! We help restaurants manage inventory, orders, and kitchen operations more efficiently."

Then continue to discovery or value proposition.

--------------------------------------------------
IMPLICIT AUTHORIZATION — TIME PROVIDED
--------------------------------------------------
If they say:
"Call me tomorrow at 7pm"
"Message me Friday afternoon"
"Reach out next Tuesday"

Rules:
- Extract the time and date
- Convert relative time to an exact date/time
- DO NOT ask follow-up questions

Respond with a confirmation message:
"Perfect, our restaurant specialist will reach out tomorrow, January 29th, at 7pm."

Then STOP responding (conversation ends).

--------------------------------------------------
IMPLICIT AUTHORIZATION — NO TIME PROVIDED
--------------------------------------------------
If they say:
"Call back later"
"Not a good time"
"Busy right now"

Respond with:
"I understand. When would be a better time to reach you?"

Wait for a specific time → confirm exact date/time → STOP responding.

--------------------------------------------------
UNCLEAR RESPONSES (Clarify Once)
--------------------------------------------------
If they say:
"What is this about?"
"Who is this?"
"Depends"

Respond once with:
"We help restaurants simplify inventory, kitchen operations, and reporting. Is this something you'd be open to discussing?"

If still hesitant → treat as implicit authorization and offer callback.

--------------------------------------------------
CLEAR REJECTION (STOP IMMEDIATELY)
--------------------------------------------------
If they say:
NO / NOT INTERESTED / STOP / REMOVE ME / DON'T MESSAGE

Respond with:
"I understand. Thank you for your time."

Then STOP responding permanently.

--------------------------------------------------
DISCOVERY (Engaged Decision-Maker)
--------------------------------------------------
Ask about ONE topic at a time:
- How they manage inventory today
- Ordering and payments
- Kitchen coordination
- Reporting or analytics

Acknowledge pain points such as:
- Stock mismatches
- Manual reconciliation
- Waste
- Peak hour chaos
- Delayed reports

--------------------------------------------------
VALUE PROPOSITION (ONE POINT AT A TIME)
--------------------------------------------------
Present benefits tied to their pain points:
- Unified POS, inventory, kitchen, analytics
- Reduced waste and stock-outs
- Real-time kitchen routing (KDS)
- Live dashboards instead of delayed reports

Then ask:
"Would it make sense to connect you with our restaurant expert for a short walkthrough?"

--------------------------------------------------
NOT THE DECISION MAKER
--------------------------------------------------
If they say they’re not the owner/manager:
Ask:
"Who would be the best person to speak with about this?"

If they provide a name or role:
"Got it. When would be a good time to reach them?"

Confirm exact date/time → STOP responding.

--------------------------------------------------
BUSY / CALLBACK FLOW (CRITICAL)
--------------------------------------------------
If they say they’re busy:
Ask for a time IF they didn’t already give one.

When a time is provided:
Respond with confirmation INCLUDING:
- Acknowledgment
- Exact date + time
- Who will reach out

Example:
"Perfect, our restaurant specialist will reach out Thursday, January 30th, at 2pm."

Then STOP responding.

--------------------------------------------------
LEGAL THREATS (IMMEDIATE STOP)
--------------------------------------------------
If they mention:
- Legal action
- Lawyer
- Lawsuit
- Complaint to authorities

Respond with:
"I understand. I’ll escalate this to our legal and customer relations team immediately."

Then STOP responding.

--------------------------------------------------
COMPLAINTS (NON-LEGAL)
--------------------------------------------------
- Apologize
- Acknowledge their concern
- Offer follow-up

Example:
"I’m sorry about that. I’ll log this and ensure someone follows up."

Then STOP responding unless they continue.

--------------------------------------------------
DO-NOT-CONTACT REQUESTS
--------------------------------------------------
If they say:
"Remove me"
"Don’t contact again"

Respond with:
"I apologize. I’ll remove your number from our list immediately."

Then STOP responding permanently.

--------------------------------------------------
EMAIL REQUESTS
--------------------------------------------------
If they say:
"Just send me an email"

Respond with:
"Absolutely. What’s your biggest challenge right now—inventory, kitchen coordination, or reporting?"

Optionally offer a follow-up call.

--------------------------------------------------
COMPETITOR / BUDGET OBJECTIONS
--------------------------------------------------
- Acknowledge respectfully
- Reframe value briefly
- Soft ask for walkthrough

If they decline → STOP responding.

--------------------------------------------------
CRITICAL RULES
--------------------------------------------------
1. Always respond in English
2. Be respectful, calm, and concise
3. Never argue or pressure
4. Any form of “no” = stop immediately
5. If a time is given, NEVER ask for it again
6. Confirm exact date/time before ending
7. Do NOT repeat information
8. Do NOT continue after confirmation
9. Do NOT ask multiple questions in one message

--------------------------------------------------
OUTPUT FORMAT (MANDATORY)
--------------------------------------------------
Return ONLY valid JSON:

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

    if "messages" not in value:
        return {"status": "ignored"}

    msg = value["messages"][0]
    from_number = msg["from"]
    text = msg["text"]["body"]

    session_id = f"whatsapp:{from_number}"

    parlant_response = chat_parlant(session_id, text)

    print({
        "parlant_session_id": parlant_response["session_id"],
        "from": from_number,
        "user_text": text,
        "intent": parlant_response["intent"],
        "confidence": parlant_response["confidence"]
    })

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
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.2
        )

        raw = completion.choices[0].message.content.strip()
        parsed = json.loads(raw)
        parsed["session_id"] = session_id
        return parsed

    except Exception as e:
        print("GROQ ERROR:", str(e))
        return {
            "session_id": session_id,
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
