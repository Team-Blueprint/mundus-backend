import asyncio
import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.notifications.brevo import send_brevo_email, format_site_flagged_email


async def main():
    recipient = sys.argv[1] if len(sys.argv) > 1 else (settings.SMTP_USER or "covenantmonday863@gmail.com")
    print(f"=== Testing Brevo Email Notification ===")
    print(f"Brevo API Key: {settings.BREVO_API_KEY[:15]}..." if settings.BREVO_API_KEY else "No Brevo Key found")
    print(f"Sender Email: {settings.BREVO_SENDER_EMAIL}")
    print(f"Recipient: {recipient}")
    print(f"========================================")

    subject, html_content, text_content = format_site_flagged_email(
        site_name="Nwaniba Road Dump Point",
        sector="Sector 4 · Uyo Urban Core",
        reporter_name="Adaeze Okoro",
        site_id=1,
        timestamp_str="26 Sep 2026, 01:40 AM",
    )

    print("Sending email...")
    success = await send_brevo_email(
        to_email=recipient,
        to_name="Mundus Supervisor",
        subject=subject,
        html_content=html_content,
        text_content=text_content,
    )

    if success:
        print("Test email dispatched successfully!")
    else:
        print("Failed to dispatch test email.")


if __name__ == "__main__":
    asyncio.run(main())
