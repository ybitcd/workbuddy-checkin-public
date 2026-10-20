#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WorkBuddy 签到结果 · SMTP 邮件通知（可选）

默认仅在签到失败时发邮件；SUCCESS_NOTIFY=true 时成功也发。
所需环境变量：MAIL_USER / MAIL_PASS / MAIL_TO（必填）
              MAIL_HOST（默认 smtp.qq.com）/ MAIL_PORT（默认 465）
本地测试：python scripts/notify_email.py --test
"""
import json
import os
import smtplib
import sys
import traceback
from datetime import datetime, timezone, timedelta
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

CST = timezone(timedelta(hours=8))

def load_result(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None

def _first(*vals):
    for v in vals:
        if v is not None:
            return v
    return "-"

def brief(result):
    """只提取白名单结论字段，原始接口响应不进邮件。"""
    detail = result.get("detail") or {}
    cred = detail.get("credential")
    if isinstance(cred, dict):
        cred = cred.get("mode") or cred
    return "\n".join([
        "状态     : %s" % result.get("status", "unknown"),
        "动作     : %s" % (result.get("action") or "-"),
        "消息     : %s" % (result.get("msg") or "-"),
        "本次积分 : %s" % _first(result.get("points"), detail.get("points")),
        "余额     : %s" % _first(result.get("balance"),
                                 detail.get("total_credits"),
                                 detail.get("credit")),
        "凭据通道 : %s" % (cred if cred else "-"),
    ])

def build_mail(user, to_list, result, run_url):
    ok = result.get("status") == "ok"
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    subject = ("WorkBuddy 签到成功 %s" if ok
               else "WorkBuddy 签到失败 %s") % now
    lines = ["WorkBuddy 每日自动签到通知", "时间：%s" % now, "", brief(result), ""]
    if run_url:
        lines += ["运行详情：%s" % run_url, ""]
    lines.append("（本邮件由 GitHub Actions 自动发送，请勿回复）")
    msg = MIMEText("\n".join(lines), "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr(("WorkBuddy 签到机器人", user))
    msg["To"] = ", ".join(to_list)
    return msg

def build_test_mail(user, to_list):
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    msg = MIMEText(
        "这是一封测试邮件。\n时间：%s\n收到即说明 SMTP 通道配置正确。" % now,
        "plain", "utf-8")
    msg["Subject"] = Header("WorkBuddy 签到 · 邮件通道测试 %s" % now, "utf-8")
    msg["From"] = formataddr(("WorkBuddy 签到机器人", user))
    msg["To"] = ", ".join(to_list)
    return msg

def send(host, port, user, password, to_list, msg):
    if port == 465:
        smtp = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        smtp = smtplib.SMTP(host, port, timeout=30)
        try:
            smtp.starttls()
        except smtplib.SMTPException:
            pass
    try:
        smtp.login(user, password)
        smtp.sendmail(user, to_list, msg.as_string())
    finally:
        try:
            smtp.quit()
        except Exception:
            pass

def main():
    argv = sys.argv[1:]
    do_test = "--test" in argv
    result_path = argv[0] if (argv and "--test" not in argv) else "result.json"

    user = os.environ.get("MAIL_USER", "").strip()
    password = os.environ.get("MAIL_PASS", "").strip()
    to_raw = os.environ.get("MAIL_TO", "").strip()
    host = os.environ.get("MAIL_HOST", "smtp.qq.com").strip()
    try:
        port = int(os.environ.get("MAIL_PORT", "465").strip())
    except ValueError:
        port = 465

    if not (user and password and to_raw):
        print("[mail] 未配置 MAIL_USER / MAIL_PASS / MAIL_TO，跳过邮件通知。")
        return 0
    to_list = [x.strip() for x in to_raw.split(",") if x.strip()]

    if do_test:
        msg = build_test_mail(user, to_list)
        subject = "邮件通道测试"
    else:
        result = load_result(result_path)
        if result is None:
            print("[mail] 未找到签到结果文件（%s），跳过邮件通知。" % result_path)
            return 0
        status = result.get("status")
        success_notify = (os.environ.get("SUCCESS_NOTIFY", "")
                          .strip().lower() == "true")
        if status == "ok" and not success_notify:
            print("[mail] 签到成功且未开启 SUCCESS_NOTIFY，按策略不发邮件。")
            return 0
        run_url = "%s/%s/actions/runs/%s" % (
            os.environ.get("GITHUB_SERVER_URL",
                           "https://github.com").rstrip("/"),
            os.environ.get("GITHUB_REPOSITORY", ""),
            os.environ.get("GITHUB_RUN_ID", ""))
        msg = build_mail(user, to_list, result, run_url)
        subject = "签到成功" if status == "ok" else "签到失败"

    try:
        send(host, port, user, password, to_list, msg)
        print("[mail] 邮件已发送：%s → %s（%s）"
              % (user, ", ".join(to_list), subject))
        return 0
    except Exception as e:
        print("::warning::邮件通知发送失败：%s" % str(e)[:160])
        traceback.print_exc(limit=1)
        return 0

if __name__ == "__main__":
    sys.exit(main())
