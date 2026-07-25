#!/usr/bin/env python3
"""Send email with report URL via QQ SMTP."""
import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_email():
    sender = os.environ.get("QQ_MAIL_SENDER", "87612585@qq.com")
    receiver = os.environ.get("QQ_MAIL_RECEIVER", "87612585@qq.com")
    auth_code = os.environ.get("QQ_MAIL_AUTH_CODE")
    report_url = os.environ.get("REPORT_URL")
    report_date = os.environ.get("REPORT_DATE", "")
    report_period = os.environ.get("REPORT_PERIOD", "上午")

    if not auth_code:
        print("❌ Error: QQ_MAIL_AUTH_CODE not set")
        sys.exit(1)

    if not report_url:
        print("❌ Error: REPORT_URL not set")
        sys.exit(1)

    subject = f"财经热搜TOP10｜{report_date}{report_period}"

    body = f"""📊 今日财经热搜 TOP 10 报告已生成

📅 日期：{report_date} {report_period}
🔗 查看报告：{report_url}

本报告由 GitHub Actions 云端自动生成，数据来源：tophub.today
每天 10:00 和 15:00 自动更新。

---
🤖 云端定时任务 · GitHub Actions
"""

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = receiver
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        # QQ SMTP with SSL
        server = smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=30)
        server.login(sender, auth_code)
        server.sendmail(sender, [receiver], msg.as_string())
        server.quit()
        print(f"✅ Email sent to {receiver}")
        print(f"   Subject: {subject}")
        print(f"   Report URL: {report_url}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        sys.exit(1)


if __name__ == "__main__":
    send_email()
