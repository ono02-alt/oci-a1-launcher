#!/usr/bin/env python3
"""
OCI Secrets の形式を診断するスクリプト。
値は表示せず、形式（プレフィックス・長さ）のみをログ出力する。
401 NotAuthenticated のデバッグに使う。
"""

import os
import sys
import re


def check(name: str, value: str, validators: list) -> bool:
    ok = True
    for label, fn in validators:
        if not fn(value):
            print(f"❌ {name}: {label}")
            ok = False
    if ok:
        masked = value[:12] + "..." if len(value) > 12 else value[:4] + "..."
        print(f"✅ {name}: OK (先頭={masked}, 長さ={len(value)})")
    return ok


def main():
    all_ok = True
    print("=" * 55)
    print("OCI 設定診断")
    print("=" * 55)

    checks = {
        "OCI_USER_OCID": [
            ("'ocid1.user.' で始まる必要があります",
             lambda v: v.startswith("ocid1.user.")),
            ("空でない必要があります", lambda v: bool(v)),
        ],
        "OCI_TENANCY_OCID": [
            ("'ocid1.tenancy.' で始まる必要があります",
             lambda v: v.startswith("ocid1.tenancy.")),
            ("空でない必要があります", lambda v: bool(v)),
        ],
        "OCI_FINGERPRINT": [
            ("'aa:bb:cc:...' 形式である必要があります (16組のhex:区切り)",
             lambda v: bool(re.fullmatch(
                 r'[0-9a-f]{2}(:[0-9a-f]{2}){15}', v.strip().lower()))),
        ],
        "OCI_REGION": [
            ("空でない必要があります", lambda v: bool(v)),
            ("'ap-' 'us-' 'eu-' 等で始まる形式が一般的です",
             lambda v: any(v.startswith(p) for p in
                           ["ap-", "us-", "eu-", "me-", "af-", "sa-", "ca-", "il-", "mx-"])),
        ],
        "OCI_AVAILABILITY_DOMAIN": [
            ("空でない必要があります", lambda v: bool(v)),
            ("':' を含む必要があります (例: xxxx:AP-TOKYO-1-AD-1)",
             lambda v: ":" in v),
        ],
        "OCI_SUBNET_OCID": [
            ("'ocid1.subnet.' で始まる必要があります",
             lambda v: v.startswith("ocid1.subnet.")),
        ],
        "OCI_IMAGE_OCID": [
            ("'ocid1.image.' で始まる必要があります",
             lambda v: v.startswith("ocid1.image.")),
        ],
    }

    for key, validators in checks.items():
        value = os.environ.get(key, "").strip()
        if not value:
            print(f"❌ {key}: 値が空です（Secretが未設定）")
            all_ok = False
            continue
        result = check(key, value, validators)
        if not result:
            all_ok = False

    # PEMファイルの確認
    pem_path = "/tmp/oci_api_key.pem"
    print()
    if os.path.exists(pem_path):
        with open(pem_path) as f:
            lines = f.readlines()
        first = lines[0].strip() if lines else ""
        last = lines[-1].strip() if lines else ""
        if "BEGIN" in first and "END" in last:
            print(f"✅ PEMファイル: OK ({len(lines)}行, 先頭='{first}')")
        else:
            print(f"❌ PEMファイル: フォーマット不正")
            print(f"   先頭行: '{first}'")
            print(f"   末尾行: '{last}'")
            all_ok = False
    else:
        print(f"❌ PEMファイル: {pem_path} が存在しません")
        all_ok = False

    print("=" * 55)

    if not all_ok:
        print("\n上記の ❌ 項目を修正してから再実行してください。")
        print("修正方法は README の「トラブルシューティング」を参照してください。")
        sys.exit(1)

    print("\n✅ 全項目OK。認証設定は正しい形式です。")
    print("それでも401エラーが出る場合は以下を確認してください:")
    print("  1. OCI_FINGERPRINT が OCI_USER_OCID のユーザーに登録された公開鍵と一致しているか")
    print("  2. OCI_USER_OCID と OCI_TENANCY_OCID を取り違えていないか")
    print("  3. OCIコンソールの「マイ・プロファイル」->「APIキー」にフィンガープリントが表示されているか")


if __name__ == "__main__":
    main()
