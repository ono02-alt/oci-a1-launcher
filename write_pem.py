#!/usr/bin/env python3
"""
GitHub Secrets から取得した OCI_PRIVATE_KEY を
正しい改行付きの PEM ファイルとして /tmp/oci_api_key.pem に書き出す。

GitHub Secrets から環境変数経由で渡されるPEMは以下の問題が起きる:
  - 改行が '\n' リテラル（バックスラッシュ+n の2文字）になる
  - CR+LF (\r\n) が混入する
  - 先頭・末尾に余分な空白や改行が付く
このスクリプトはこれらを全て正規化する。
"""

import os
import sys

OCI_KEY_FILE = "/tmp/oci_api_key.pem"


def normalize_pem(raw: str) -> str:
    """PEM文字列を正規化して返す"""
    # 1. CR を除去
    text = raw.replace("\r", "")
    # 2. '\n' リテラル（2文字）を実際の改行に変換
    text = text.replace("\\n", "\n")
    # 3. 前後の空白・改行を除去
    text = text.strip()
    # 4. 末尾に必ず改行を付ける（OCI SDKが要求する場合がある）
    text = text + "\n"
    return text


def write_pem(pem_content: str, path: str) -> None:
    """PEMをファイルに書き出す"""
    with open(path, "w", newline="\n") as f:
        f.write(pem_content)
    os.chmod(path, 0o600)


def validate_pem(path: str) -> bool:
    """基本的なPEMフォーマット検証"""
    with open(path) as f:
        content = f.read()
    lines = content.strip().splitlines()
    if not lines:
        return False
    first = lines[0].strip()
    last = lines[-1].strip()
    return first.startswith("-----BEGIN") and last.startswith("-----END")


def main():
    raw = os.environ.get("OCI_PRIVATE_KEY", "")
    if not raw:
        print("ERROR: OCI_PRIVATE_KEY 環境変数が空です。")
        print("  GitHub の Settings -> Secrets -> OCI_PRIVATE_KEY を確認してください。")
        sys.exit(1)

    pem = normalize_pem(raw)
    write_pem(pem, OCI_KEY_FILE)

    if not validate_pem(OCI_KEY_FILE):
        print("ERROR: PEMファイルのフォーマットが不正です。")
        print("  OCI_PRIVATE_KEY が '-----BEGIN RSA PRIVATE KEY-----' で")
        print("  始まっているか確認してください。")
        # デバッグ用に先頭30文字を表示（秘密鍵本体は含まれない）
        with open(OCI_KEY_FILE) as f:
            first_line = f.readline().strip()
        print(f"  先頭行: {first_line[:60]}")
        sys.exit(1)

    line_count = pem.count("\n")
    print(f"✅ PEMファイル書き出し成功: {OCI_KEY_FILE} ({line_count}行)")


if __name__ == "__main__":
    main()
