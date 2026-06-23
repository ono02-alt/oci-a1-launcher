#!/usr/bin/env python3
"""
OCI Ampere A1 インスタンス自動作成スクリプト
- 容量不足エラーが解消されるまでリトライし続ける
- レート制限エラー(429)時は待機時間を延長する
- 作成成功時にメール通知を送信する
- GitHub Actions の6時間制限に対応したステート保存機能付き
"""

import oci
import time
import json
import os
import sys
import smtplib
import random
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

# ─────────────────────────────────────────────
# ロギング設定
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 定数
# ─────────────────────────────────────────────
STATE_FILE = "/tmp/oci_launcher_state.json"
# 通常のリトライ間隔（秒）: レート制限に引っかからない最小値として60秒を基本とする
BASE_INTERVAL_SECONDS = 60
# 429(レート制限)発生時の追加待機（秒）
RATE_LIMIT_EXTRA_WAIT = 120
# 最大リトライ間隔（秒）
MAX_INTERVAL_SECONDS = 300
# GitHub Actionsの制限より少し前（秒）にセーフに終了するための余裕
SAFE_SHUTDOWN_BEFORE_SECONDS = 600  # 10分前にシャットダウン
# GitHub Actions のジョブ最大時間（秒）: 6時間 = 21600秒
GITHUB_ACTIONS_MAX_SECONDS = 21600


# ─────────────────────────────────────────────
# 環境変数から設定を読み込む
# ─────────────────────────────────────────────
def load_config():
    """環境変数から設定を取得する"""
    required = [
        "OCI_USER_OCID",
        "OCI_TENANCY_OCID",
        "OCI_FINGERPRINT",
        "OCI_PRIVATE_KEY",
        "OCI_REGION",
        "OCI_AVAILABILITY_DOMAIN",
        "OCI_SUBNET_OCID",
        "OCI_IMAGE_OCID",
        "NOTIFICATION_EMAIL",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASSWORD",
    ]
    config = {}
    missing = []
    for key in required:
        val = os.environ.get(key, "")
        if not val:
            missing.append(key)
        config[key] = val

    if missing:
        logger.error(f"必須の環境変数が設定されていません: {', '.join(missing)}")
        sys.exit(1)

    # オプション設定
    config["INSTANCE_NAME"] = os.environ.get("INSTANCE_NAME", "ampere-a1-free")
    config["OCPU_COUNT"] = int(os.environ.get("OCPU_COUNT", "4"))
    config["MEMORY_GB"] = int(os.environ.get("MEMORY_GB", "24"))
    config["BOOT_VOLUME_GB"] = int(os.environ.get("BOOT_VOLUME_GB", "50"))
    config["SSH_PUBLIC_KEY"] = os.environ.get("SSH_PUBLIC_KEY", "")

    return config


# ─────────────────────────────────────────────
# OCI クライアントの初期化
# ─────────────────────────────────────────────
def build_oci_config(cfg):
    """OCI SDK用のconfigとComputeClientを構築する"""
    # 秘密鍵は環境変数から直接読み込む（ファイルに書かず、メモリ内で処理）
    private_key_content = cfg["OCI_PRIVATE_KEY"].replace("\\n", "\n")

    oci_config = {
        "user": cfg["OCI_USER_OCID"],
        "tenancy": cfg["OCI_TENANCY_OCID"],
        "fingerprint": cfg["OCI_FINGERPRINT"],
        "region": cfg["OCI_REGION"],
        "key_content": private_key_content,
    }

    try:
        oci.config.validate_config(oci_config)
    except oci.exceptions.InvalidConfig as e:
        logger.error(f"OCI設定が無効です: {e}")
        sys.exit(1)

    return oci_config


# ─────────────────────────────────────────────
# ステート管理（GitHub Actions 6時間制限対応）
# ─────────────────────────────────────────────
def load_state():
    """前回のセッションのステートを読み込む"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            logger.info(
                f"ステートを復元しました: 試行回数={state.get('attempt_count', 0)}, "
                f"開始時刻={state.get('first_start_time', 'unknown')}"
            )
            return state
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"ステートファイルの読み込みに失敗しました: {e}")
    return {
        "attempt_count": 0,
        "first_start_time": datetime.now(timezone.utc).isoformat(),
        "last_error": None,
        "session_count": 0,
    }


def save_state(state):
    """現在のステートをファイルに保存する"""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except IOError as e:
        logger.warning(f"ステートファイルの保存に失敗しました: {e}")


# ─────────────────────────────────────────────
# メール通知
# ─────────────────────────────────────────────
def send_email(cfg, subject, body):
    """GmailのSMTPでメールを送信する"""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = cfg["SMTP_USER"]
        msg["To"] = cfg["NOTIFICATION_EMAIL"]
        msg.attach(MIMEText(body, "plain", "utf-8"))

        port = int(cfg["SMTP_PORT"])
        with smtplib.SMTP(cfg["SMTP_HOST"], port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
            server.sendmail(cfg["SMTP_USER"], cfg["NOTIFICATION_EMAIL"], msg.as_string())

        logger.info(f"メール送信成功: {subject}")
    except Exception as e:
        logger.error(f"メール送信失敗: {e}")


def notify_success(cfg, instance_data, state):
    """インスタンス作成成功時のメール通知"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    body = f"""
OCI Ampere A1 インスタンスの作成に成功しました！

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
インスタンス情報
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
インスタンス名  : {instance_data.display_name}
インスタンスID  : {instance_data.id}
シェイプ        : {instance_data.shape}
アベイラビリティ: {instance_data.availability_domain}
状態            : {instance_data.lifecycle_state}
作成日時        : {now}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
実行統計
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
総試行回数      : {state['attempt_count']}回
セッション数    : {state['session_count']}回
最初の試行開始  : {state['first_start_time']}

OCIコンソールでSSH鍵を確認し、インスタンスへの接続をお試しください。
""".strip()

    send_email(cfg, "✅ OCI A1インスタンス作成成功", body)


def notify_session_end(cfg, state, reason):
    """セッション終了（6時間制限前）のメール通知"""
    body = f"""
OCI A1インスタンス作成スクリプトのセッションが終了しました。

理由: {reason}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
現在の状態
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
総試行回数   : {state['attempt_count']}回
セッション数 : {state['session_count']}回
最終エラー   : {state.get('last_error', 'なし')}
最初の開始   : {state['first_start_time']}

GitHub Actionsが次のワークフローを自動で起動し、処理を再開します。
""".strip()

    send_email(cfg, f"🔄 OCI A1ランチャー: セッション#{state['session_count']}終了", body)


# ─────────────────────────────────────────────
# インスタンス作成
# ─────────────────────────────────────────────
def create_instance(compute_client, cfg, state):
    """
    Ampere A1インスタンスの作成を試みる。
    - 成功: instance_dataを返す
    - 容量不足(InternalError/LimitExceeded): Noneを返す
    - レート制限(429): 長めに待機してNoneを返す
    - その他エラー: 例外をraise
    """
    details = oci.core.models.LaunchInstanceDetails(
        compartment_id=cfg["OCI_TENANCY_OCID"],
        availability_domain=cfg["OCI_AVAILABILITY_DOMAIN"],
        display_name=cfg["INSTANCE_NAME"],
        shape="VM.Standard.A1.Flex",
        shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
            ocpus=float(cfg["OCPU_COUNT"]),
            memory_in_gbs=float(cfg["MEMORY_GB"]),
        ),
        source_details=oci.core.models.InstanceSourceViaImageDetails(
            source_type="image",
            image_id=cfg["OCI_IMAGE_OCID"],
            boot_volume_size_in_gbs=cfg["BOOT_VOLUME_GB"],
        ),
        create_vnic_details=oci.core.models.CreateVnicDetails(
            subnet_id=cfg["OCI_SUBNET_OCID"],
            assign_public_ip=True,
        ),
        metadata=(
            {"ssh_authorized_keys": cfg["SSH_PUBLIC_KEY"]}
            if cfg["SSH_PUBLIC_KEY"]
            else {}
        ),
        freeform_tags={"created_by": "oci-a1-launcher", "purpose": "always-free"},
    )

    try:
        response = compute_client.launch_instance(details)
        return response.data
    except oci.exceptions.ServiceError as e:
        status = e.status
        code = e.code or ""
        message = e.message or ""

        if status == 429 or "TooManyRequests" in code:
            logger.warning(f"レート制限エラー(429): {message}")
            state["last_error"] = f"429 TooManyRequests: {message}"
            return "RATE_LIMITED"

        # 容量不足・内部エラー系（リトライ対象）
        capacity_error_codes = [
            "InternalError",
            "NotAuthorizedOrNotFound",
            "LimitExceeded",
            "Out of host capacity",
        ]
        if status in (500, 503) or any(c in code for c in capacity_error_codes) or \
                "capacity" in message.lower() or "limit" in message.lower():
            logger.info(f"容量不足エラー({status} {code}): {message}")
            state["last_error"] = f"{status} {code}: {message}"
            return None

        # その他のエラー（致命的）
        logger.error(f"予期しないエラー({status} {code}): {message}")
        raise


# ─────────────────────────────────────────────
# メインループ
# ─────────────────────────────────────────────
def main():
    logger.info("=" * 60)
    logger.info("OCI Ampere A1 インスタンス自動作成スクリプト 起動")
    logger.info("=" * 60)

    cfg = load_config()
    oci_config = build_oci_config(cfg)

    # ComputeClientはNoneRetryStrategyで初期化（リトライはこのスクリプト側で制御）
    compute_client = oci.core.ComputeClient(
        oci_config,
        retry_strategy=oci.retry.NoneRetryStrategy(),
    )

    state = load_state()
    state["session_count"] = state.get("session_count", 0) + 1
    session_start = time.time()

    logger.info(f"セッション #{state['session_count']} 開始")
    logger.info(f"総試行回数（前回までの累計）: {state['attempt_count']}")

    interval = BASE_INTERVAL_SECONDS

    while True:
        elapsed = time.time() - session_start
        remaining = GITHUB_ACTIONS_MAX_SECONDS - elapsed

        # GitHub Actions 6時間制限の10分前になったら安全に終了
        if remaining <= SAFE_SHUTDOWN_BEFORE_SECONDS:
            logger.info(
                f"GitHub Actions の制限まで残り{int(remaining)}秒。安全に終了します。"
            )
            save_state(state)
            notify_session_end(cfg, state, "GitHub Actions 6時間制限に近づいたため終了")
            sys.exit(0)

        state["attempt_count"] += 1
        attempt = state["attempt_count"]
        logger.info(
            f"[試行 #{attempt}] インスタンス作成を試みます... "
            f"(経過: {int(elapsed)}秒, 残り: {int(remaining)}秒)"
        )

        result = create_instance(compute_client, cfg, state)

        if result == "RATE_LIMITED":
            # レート制限: 長めに待ってリトライ
            wait = RATE_LIMIT_EXTRA_WAIT + random.uniform(0, 30)
            logger.warning(f"レート制限のため {int(wait)} 秒待機します...")
            save_state(state)
            time.sleep(wait)
            # 通常間隔に戻す
            interval = BASE_INTERVAL_SECONDS
            continue

        if result is not None:
            # 成功！
            logger.info(f"✅ インスタンス作成成功！ ID: {result.id}")
            state["last_error"] = None
            state["instance_created"] = True
            state["instance_id"] = result.id
            save_state(state)
            notify_success(cfg, result, state)
            # GITHUB_OUTPUT に instance_created=true を書き込む
            # → 次のセッションで check_state.py がこれを読み取り、ループを止める
            github_output = os.environ.get("GITHUB_OUTPUT", "")
            if github_output:
                with open(github_output, "a") as fh:
                    fh.write("instance_created=true\n")
            sys.exit(0)

        # 容量不足 → 次の試行まで待機
        # ジッタ付きの待機（レート制限に引っかかりにくくするため）
        jitter = random.uniform(-10, 10)
        wait = max(BASE_INTERVAL_SECONDS, min(interval + jitter, MAX_INTERVAL_SECONDS))
        logger.info(f"容量不足。{int(wait)} 秒後に再試行します...")

        save_state(state)
        time.sleep(wait)


if __name__ == "__main__":
    main()
