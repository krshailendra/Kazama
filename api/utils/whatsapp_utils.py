from twilio.rest import Client
import os

# Use Twilio Sandbox credentials
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
FROM_NUMBER = "whatsapp:+14155238886"  # Twilio sandbox number
TO_NUMBER = os.getenv("USER_WHATSAPP_NUMBER")  # your WhatsApp (joined sandbox)

client = Client(ACCOUNT_SID, AUTH_TOKEN)

def send_whatsapp_message(body):
    try:
        message = client.messages.create(
            from_=FROM_NUMBER,
            body=body,
            to=TO_NUMBER
        )
        print(f"WhatsApp message sent: {body}")
        return True
    except Exception as e:
        print(f"Failed to send message: {e}")
        return False

def handle_incoming_whatsapp(data):
    msg = data.get("Body", "").strip().lower()
    if msg == "done":
        send_whatsapp_message("👏 Task marked as completed.")
    elif msg == "remind later":
        send_whatsapp_message("⏰ Reminder postponed.")
