import logging

import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import settings

logger = logging.getLogger("qanoonai")


async def send_password_reset_email(email: str, token: str) -> None:
    if not settings.smtp_host or not settings.smtp_user:
        logger.warning("SMTP not configured — password reset email not sent to %s", email)
        return

    base_url = settings.frontend_url
    reset_url = f"{base_url}/reset-password?token={token}"

    msg = MIMEMultipart("alternative")
    msg["From"] = settings.smtp_from
    msg["To"] = email
    msg["Subject"] = "Reset your QanoonAI password"

    html = f"""\
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color: #1f1f1f;">Reset Your Password</h2>
      <p>You requested a password reset for your QanoonAI account.</p>
      <p>Click the button below to set a new password. This link expires in 1 hour.</p>
      <a href="{reset_url}" style="display: inline-block; background: #A21CAF; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; margin: 16px 0;">
        Reset Password
      </a>
      <p style="color: #666; font-size: 14px;">If you didn't request this, you can safely ignore this email.</p>
    </div>
    """

    msg.attach(MIMEText(html, "html"))

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_pass,
        start_tls=True,
    )
