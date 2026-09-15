import mail


def test_parse_recipients():
    assert mail.parse_recipients("a@gmail.com, b@gmail.com") == [
        "a@gmail.com",
        "b@gmail.com",
    ]
    assert mail.parse_recipients("  ") == []


def test_send_xlsx(monkeypatch):
    sent: dict = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"] = host
            sent["port"] = port

        def starttls(self):
            sent["tls"] = True

        def login(self, user, password):
            sent["user"] = user

        def send_message(self, msg):
            sent["to"] = msg["To"]
            sent["subject"] = msg["Subject"]
            sent["names"] = [p.get_filename() for p in msg.iter_attachments()]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mail, "load_dotenv", lambda path: None)
    monkeypatch.setenv("SMTP_USER", "sender@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-pass")
    monkeypatch.setenv("EMAIL_FROM", "sender@gmail.com")
    n = mail.send_xlsx(
        to=["a@gmail.com", "b@gmail.com"],
        subject="Sunday Report 2026 week 2",
        body="attached",
        filename="2026_week_02_spreads.xlsx",
        data=b"PK fake",
    )
    assert n == 2
    assert sent["host"] == "smtp.gmail.com"
    assert sent["port"] == 587
    assert sent["tls"] is True
    assert sent["user"] == "sender@gmail.com"
    assert sent["to"] == "a@gmail.com, b@gmail.com"
    assert sent["subject"] == "Sunday Report 2026 week 2"
    assert sent["names"] == ["2026_week_02_spreads.xlsx"]
