import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import httpx
from app.config import settings
from app.core.logging import logger


async def send_brevo_email(
    to_email: str,
    to_name: str | None,
    subject: str,
    html_content: str,
    text_content: str | None = None,
) -> bool:
    """
    Send an email via Brevo API or SMTP.
    Falls back to console logging in development mode if no API key or SMTP credentials are configured.
    """
    to_name = to_name or to_email

    # 1. Try Brevo REST API v3
    if settings.BREVO_API_KEY and settings.BREVO_API_KEY.strip() and not settings.BREVO_API_KEY.startswith("xkeysib-your_"):
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "accept": "application/json",
            "api-key": settings.BREVO_API_KEY.strip(),
            "content-type": "application/json",
        }

        # Extract clean email address if formatted as 'Name <email@domain.com>'
        sender_email = settings.BREVO_SENDER_EMAIL.strip()
        sender_name = settings.BREVO_SENDER_NAME.strip()
        if "<" in sender_email and ">" in sender_email:
            parts = sender_email.split("<")
            if not sender_name or sender_name == "Mundus Waste Tracking":
                sender_name = parts[0].strip() or sender_name
            sender_email = parts[1].replace(">", "").strip()

        payload = {
            "sender": {
                "name": sender_name,
                "email": sender_email,
            },
            "to": [{"email": to_email, "name": to_name}],
            "subject": subject,
            "htmlContent": html_content,
        }

        if text_content:
            payload["textContent"] = text_content

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code in (200, 201, 202):
                    logger.info(f"Brevo email sent successfully to {to_email} (status {resp.status_code})")
                    return True
                else:
                    logger.error(f"Brevo API error: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"Failed to send email via Brevo API: {e}")

    # 2. Try SMTP fallback if configured
    if settings.SMTP_USER and settings.SMTP_PASSWORD:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{settings.BREVO_SENDER_NAME} <{settings.BREVO_SENDER_EMAIL}>"
            msg["To"] = f"{to_name} <{to_email}>"

            if text_content:
                msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.BREVO_SENDER_EMAIL, [to_email], msg.as_string())
                logger.info(f"Email sent via SMTP to {to_email}")
                return True
        except Exception as e:
            logger.error(f"Failed to send email via SMTP: {e}")

    # 3. Development fallback log
    logger.info(
        f"[BREVO EMAIL DISPATCH (DEV)] To: {to_name} <{to_email}> | Subject: {subject}\nContent: {text_content or html_content[:200]}"
    )
    return True


def format_site_flagged_email(
    site_name: str,
    sector: str | None,
    reporter_name: str | None,
    site_id: int,
    timestamp_str: str,
    photo_url: str | None = None,
) -> tuple[str, str, str]:
    """Return (subject, html_content, text_content) for site full alert."""
    subject = f"[Mundus] {site_name} reported full"
    sector_str = f" ({sector})" if sector else ""
    site_url = f"{settings.FRONTEND_ORIGIN}/contractor/sites/{site_id}"
    reporter_display = reporter_name or "A community reporter"

    photo_block = ""
    if photo_url:
        photo_block = f"""
        <div style="margin: 15px 0;">
            <p style="margin: 5px 0; font-weight: bold;">Evidence Photo:</p>
            <img src="{photo_url}" alt="Reporter evidence photo" style="max-width: 100%; border-radius: 6px; border: 1px solid #e2e8f0;" />
        </div>"""

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <h2 style="color: #d97706; margin-top: 0;">⚠️ Dump Point Reported Full</h2>
        <p>Hello,</p>
        <p><strong>{reporter_display}</strong> has flagged <strong>{site_name}{sector_str}</strong> as requiring immediate waste clearance.</p>
        <div style="background: #f8fafc; padding: 15px; border-radius: 6px; margin: 15px 0;">
            <p style="margin: 5px 0;"><strong>Site:</strong> {site_name}</p>
            {f'<p style="margin: 5px 0;"><strong>Sector:</strong> {sector}</p>' if sector else ''}
            <p style="margin: 5px 0;"><strong>Reported at:</strong> {timestamp_str}</p>
        </div>
        {photo_block}
        <p>Please dispatch field personnel to conduct clearance and complete the before/after check-in verification:</p>
        <p style="margin: 25px 0;">
            <a href="{site_url}" style="background: #0b3d2c; color: #ffffff; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">View Site on Mundus Field App</a>
        </p>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
        <p style="color: #64748b; font-size: 12px;">Mundus Municipal Waste Evacuation System — Akwa Ibom State</p>
    </div>
    """

    text_content = f"""
    [Mundus] Dump Point Reported Full
    Site: {site_name}{sector_str}
    Reported by: {reporter_display}
    Time: {timestamp_str}
    {f"Evidence photo: {photo_url}" if photo_url else ""}

    View site details: {site_url}
    """

    return subject, html_content, text_content


def format_password_reset_otp_email(otp: str, full_name: str | None = None) -> tuple[str, str, str]:
    """Return (subject, html_content, text_content) for a password reset OTP email."""
    subject = "[Mundus] Your Password Reset OTP"
    display_name = full_name or "User"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <h2 style="color: #0b3d2c; margin-top: 0;">🔐 Password Reset Verification</h2>
        <p>Hello {display_name},</p>
        <p>We received a request to reset your Mundus account password. Use the verification code below to complete your password reset:</p>
        <div style="background: #f1f5f9; padding: 20px; text-align: center; border-radius: 8px; margin: 25px 0;">
            <span style="font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #0f172a; font-family: monospace;">{otp}</span>
        </div>
        <p style="color: #475569; font-size: 14px;">This code is valid for <strong>15 minutes</strong> and can only be used once.</p>
        <p style="color: #64748b; font-size: 13px;">If you did not request a password reset, you can safely ignore this email — your account remains secure.</p>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
        <p style="color: #64748b; font-size: 12px;">Mundus Municipal Waste Evacuation System — Akwa Ibom State</p>
    </div>
    """

    text_content = f"""
    [Mundus] Password Reset Verification
    Hello {display_name},

    Your password reset OTP is: {otp}

    This code is valid for 15 minutes. If you did not request this, please ignore this email.
    """

    return subject, html_content, text_content


def format_password_reset_email(reset_url: str, full_name: str | None = None) -> tuple[str, str, str]:
    """Return (subject, html_content, text_content) for a contractor password reset email."""
    subject = "[Mundus] Reset your password"
    display_name = full_name or "Contractor"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <h2 style="color: #0b3d2c; margin-top: 0;">🔐 Password Reset Request</h2>
        <p>Hello {display_name},</p>
        <p>We received a request to reset your Mundus contractor account password. Click the button below to set a new password. This link expires in <strong>1 hour</strong> and can only be used once.</p>
        <p style="margin: 25px 0;">
            <a href="{reset_url}" style="background: #0b3d2c; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">Reset Password</a>
        </p>
        <p style="color: #64748b; font-size: 13px;">Or copy this link into your browser:<br><a href="{reset_url}" style="color: #0b3d2c;">{reset_url}</a></p>
        <p style="color: #64748b; font-size: 13px;">If you did not request a password reset, you can safely ignore this email — your password will not change.</p>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
        <p style="color: #64748b; font-size: 12px;">Mundus Municipal Waste Evacuation System — Akwa Ibom State</p>
    </div>
    """

    text_content = f"""
    [Mundus] Password Reset Request
    Hello {display_name},

    Reset your password here: {reset_url}

    This link expires in 1 hour. If you did not request this, ignore this email.
    """

    return subject, html_content, text_content



def format_staff_invite_email(full_name: str, email: str, temp_password: str, login_url: str) -> tuple[str, str, str]:
    """Return (subject, html_content, text_content) for a new staff invite email."""
    subject = "[Mundus] You've been added as agency staff"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <h2 style="color: #0b3d2c; margin-top: 0;">👋 Welcome to Mundus</h2>
        <p>Hello {full_name},</p>
        <p>You've been added as a staff member on the Mundus Waste Tracking platform. Here are your login details:</p>
        <div style="background: #f8fafc; padding: 15px; border-radius: 6px; margin: 15px 0; font-family: monospace;">
            <p style="margin: 5px 0;"><strong>Email:</strong> {email}</p>
            <p style="margin: 5px 0;"><strong>Temporary Password:</strong> {temp_password}</p>
        </div>
        <p>Please log in and change your password immediately.</p>
        <p style="margin: 25px 0;">
            <a href="{login_url}" style="background: #0b3d2c; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">Log In to Mundus</a>
        </p>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
        <p style="color: #64748b; font-size: 12px;">Mundus Municipal Waste Evacuation System — Akwa Ibom State</p>
    </div>
    """

    text_content = f"""
    [Mundus] You've been added as agency staff

    Hello {full_name},
    Email: {email}
    Temporary Password: {temp_password}

    Log in here: {login_url}
    Please change your password after logging in.
    """

    return subject, html_content, text_content
