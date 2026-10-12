from src.app.observability.logging import get_logger
from src.modules.communications.infrastructure.email.base import BaseEmailProvider

logger = get_logger("email.mock")


class MockEmailProvider(BaseEmailProvider):
    def __init__(self):
        self.sent_emails: list[dict[str, str]] = []

    async def send_email(self, to_email: str, subject: str, html_body: str) -> bool:
        logger.info("📧 [MOCK EMAIL DISPATCHED] To: %s | Subject: %s", to_email, subject)
        self.sent_emails.append({"to": to_email, "subject": subject, "body": html_body})
        return True
