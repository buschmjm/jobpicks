"""SMTP email abstraction for digest and transactional mail."""

from __future__ import annotations

import os
import re
import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Protocol


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def html_to_plain(html_body: str) -> str:
    """Best-effort HTML → plain text for multipart/alternative."""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", html_body)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"(?i)</li>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    user: str | None
    password: str | None
    email_from: str
    app_base_url: str
    use_tls: bool
    use_ssl: bool

    @classmethod
    def from_env(cls) -> SmtpConfig:
        port = int(os.environ.get("SMTP_PORT", "587"))
        use_ssl = _env_bool("SMTP_USE_SSL", default=port == 465)
        use_tls = _env_bool("SMTP_USE_TLS", default=not use_ssl)
        return cls(
            host=os.environ.get("SMTP_HOST", "localhost"),
            port=port,
            user=os.environ.get("SMTP_USER") or None,
            password=os.environ.get("SMTP_PASSWORD") or None,
            email_from=os.environ.get("EMAIL_FROM", "noreply@localhost"),
            app_base_url=os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/"),
            use_tls=use_tls,
            use_ssl=use_ssl,
        )

    def is_configured(self) -> bool:
        if os.environ.get("EMAIL_BACKEND", "").lower() == "log":
            return True
        host = self.host.strip().lower()
        if not host or host in {"localhost", "127.0.0.1"}:
            return False
        return bool(self.user and self.password and self.email_from)


def email_backend_status() -> dict[str, object]:
    """Lightweight SMTP readiness for ops dashboards and deploy smoke tests."""
    backend = os.environ.get("EMAIL_BACKEND", "smtp").strip().lower()
    if backend == "log":
        return {"backend": "log", "configured": True, "ready": True}
    config = SmtpConfig.from_env()
    configured = config.is_configured()
    return {
        "backend": "smtp",
        "configured": configured,
        "ready": configured,
        "host": config.host,
        "port": config.port,
        "use_tls": config.use_tls,
        "use_ssl": config.use_ssl,
        "from_domain": config.email_from.split("@")[-1] if "@" in config.email_from else None,
    }


class EmailSender(Protocol):
    def send_html(
        self,
        to: str,
        subject: str,
        html_body: str,
        *,
        list_unsubscribe_url: str | None = None,
    ) -> None: ...


@dataclass
class SmtpEmailSender:
    config: SmtpConfig

    def send_html(
        self,
        to: str,
        subject: str,
        html_body: str,
        *,
        list_unsubscribe_url: str | None = None,
    ) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.config.email_from
        msg["To"] = to
        if list_unsubscribe_url:
            msg["List-Unsubscribe"] = f"<{list_unsubscribe_url}>"
            msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

        plain = html_to_plain(html_body)
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if self.config.use_ssl:
            smtp_cls: type[smtplib.SMTP] = smtplib.SMTP_SSL
        else:
            smtp_cls = smtplib.SMTP

        with smtp_cls(self.config.host, self.config.port, timeout=30) as smtp:
            if self.config.use_tls and not self.config.use_ssl:
                smtp.starttls()
            if self.config.user and self.config.password:
                smtp.login(self.config.user, self.config.password)
            smtp.sendmail(self.config.email_from, [to], msg.as_string())


@dataclass
class LoggingEmailSender:
    """Dev/test sender that records messages instead of using SMTP."""

    sent: list[tuple[str, str, str]]

    def send_html(
        self,
        to: str,
        subject: str,
        html_body: str,
        *,
        list_unsubscribe_url: str | None = None,
    ) -> None:
        _ = list_unsubscribe_url
        self.sent.append((to, subject, html_body))


def get_email_sender() -> EmailSender:
    if os.environ.get("EMAIL_BACKEND", "").lower() == "log":
        return LoggingEmailSender(sent=[])
    return SmtpEmailSender(SmtpConfig.from_env())
