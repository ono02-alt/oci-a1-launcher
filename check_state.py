#!/usr/bin/env python3
"""
GitHub Actions から呼び出されるステート確認スクリプト。
インスタンスが既に作成済みの場合は GITHUB_OUTPUT に instance_created=true を出力する。
"""
import json
import os
import sys

STATE_FILE = "/tmp/oci_launcher_state.json"
github_output = os.environ.get("GITHUB_OUTPUT", "")

if os.path.exists(STATE_FILE):
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        print("=== 前回のステート ===")
        print(json.dumps(state, indent=2, ensure_ascii=False))

        if state.get("instance_created"):
            print("\nインスタンスは既に作成済みです。このセッションをスキップします。")
            if github_output:
                with open(github_output, "a") as fh:
                    fh.write("instance_created=true\n")
            sys.exit(0)
        else:
            print("\nインスタンスはまだ作成されていません。処理を継続します。")
            if github_output:
                with open(github_output, "a") as fh:
                    fh.write("instance_created=false\n")
    except (json.JSONDecodeError, IOError) as e:
        print(f"ステートファイルの読み込みに失敗しました: {e}")
        if github_output:
            with open(github_output, "a") as fh:
                fh.write("instance_created=false\n")
else:
    print("ステートなし（初回実行）")
    if github_output:
        with open(github_output, "a") as fh:
            fh.write("instance_created=false\n")
