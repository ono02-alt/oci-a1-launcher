# OCI Ampere A1 インスタンス自動作成ランチャー

Oracle Cloud Infrastructure (OCI) の Always Free 枠である **Ampere A1 (VM.Standard.A1.Flex)** は、空き容量不足で作成できないことが多いです。このスクリプトは空き容量が出るまで自動でリトライし、作成に成功したらメールで通知します。

**完全無料で動作します。**
- 実行環境: GitHub Actions (無料枠)
- OCI: Always Free tier
- 通知: Gmail SMTP (無料)

---

## ファイル構成

```
/oci-a1-launcher/
├── /oci-a1-launcher/oci_a1_launcher.py          # メインスクリプト
├── /oci-a1-launcher/requirements.txt             # Python依存パッケージ
├── /oci-a1-launcher/README.md                    # このファイル
└── /oci-a1-launcher/.github/
    └── /oci-a1-launcher/.github/workflows/
        └── /oci-a1-launcher/.github/workflows/oci_a1_launcher.yml  # GitHub Actionsワークフロー
```

---

## 動作の仕組み

1. **GitHub Actions** がスクリプトを実行する
2. **60秒間隔**でOCI APIにインスタンス作成をリクエストし続ける
3. レート制限エラー(429)が発生した場合は **120〜150秒待機** してから再試行する
4. **5時間55分**が経過したら現在の試行回数などのステートをキャッシュに保存し、終了する
5. ワークフロー終了後、**`workflow_run`トリガー**によって自動的に次のセッションが起動する
6. インスタンス作成に成功したら**メール通知**を送り、正常終了する（次のセッションは起動しない）

---

## セットアップ手順

### 1. OCI側の事前準備

#### APIキーの作成

1. [OCI コンソール](https://cloud.oracle.com) にログイン
2. 右上のプロフィールアイコン → **「マイ・プロファイル」**
3. 左メニュー **「APIキー」** → **「APIキーの追加」**
4. **「APIキー・ペアの生成」** を選択 → **「秘密キーのダウンロード」**（`.pem`ファイル）
5. 表示された設定プレビューから以下をメモ:
   - `user=` の値 → `OCI_USER_OCID`
   - `tenancy=` の値 → `OCI_TENANCY_OCID`
   - `fingerprint=` の値 → `OCI_FINGERPRINT`
   - `region=` の値 → `OCI_REGION`

#### テナンシーOCIDの確認

1. OCI コンソール右上プロフィール → **「テナンシー: xxx」**
2. 表示される OCID をコピー → `OCI_TENANCY_OCID`

#### アベイラビリティドメインの確認

1. OCI コンソール → **「コンピュート」** → **「インスタンス」** → **「インスタンスの作成」**
2. 「配置」セクションのアベイラビリティドメイン名をメモ（例: `xxxx:AP-TOKYO-1-AD-1`）
3. → `OCI_AVAILABILITY_DOMAIN`

> **Tip**: AD-1で容量不足が続く場合は AD-2 や AD-3 に変更してみてください

#### VCN・サブネットの準備

まだVCNがない場合:

1. OCI コンソール → **「ネットワーキング」** → **「仮想クラウド・ネットワーク」**
2. **「VCNウィザードの起動」** → **「インターネット接続性を持つVCNの作成」**
3. 作成後、パブリックサブネットのOCIDをメモ → `OCI_SUBNET_OCID`

#### イメージOCIDの確認

1. OCI コンソール → **「コンピュート」** → **「インスタンス」** → **「インスタンスの作成」**
2. 「イメージとシェイプ」で **「イメージの変更」** → Ubuntu 22.04 などを選択
3. イメージ名の右の `▼` → **「イメージOCIDのコピー」** → `OCI_IMAGE_OCID`

---

### 2. GitHubリポジトリの作成

1. GitHub で新しい**プライベートリポジトリ**を作成（秘密鍵を含むためプライベート推奨）
2. このリポジトリのファイルをすべてアップロード:
   - `oci_a1_launcher.py`
   - `requirements.txt`
   - `.github/workflows/oci_a1_launcher.yml`

**スマホからのアップロード手順:**
1. GitHubアプリ または ブラウザで GitHub を開く
2. リポジトリ → **「Add file」** → **「Create new file」**
3. ファイル名と内容を入力して **「Commit changes」**
4. `.github/workflows/oci_a1_launcher.yml` はパスごと入力（スラッシュで自動的にディレクトリ作成）

---

### 3. GitHub Secrets の設定

リポジトリ → **「Settings」** → **「Secrets and variables」** → **「Actions」** → **「New repository secret」**

#### 必須のシークレット

| シークレット名 | 内容 | 例 |
|---|---|---|
| `OCI_USER_OCID` | ユーザーOCID | `ocid1.user.oc1..aaaaa...` |
| `OCI_TENANCY_OCID` | テナンシーOCID | `ocid1.tenancy.oc1..aaaaa...` |
| `OCI_FINGERPRINT` | APIキーのフィンガープリント | `aa:bb:cc:dd:...` |
| `OCI_PRIVATE_KEY` | 秘密鍵の内容（PEMファイル全体） | `-----BEGIN RSA PRIVATE KEY-----\n...` |
| `OCI_REGION` | リージョン識別子 | `ap-tokyo-1` |
| `OCI_AVAILABILITY_DOMAIN` | アベイラビリティドメイン | `xxxx:AP-TOKYO-1-AD-1` |
| `OCI_SUBNET_OCID` | サブネットOCID | `ocid1.subnet.oc1..aaaaa...` |
| `OCI_IMAGE_OCID` | OSイメージOCID | `ocid1.image.oc1..aaaaa...` |
| `NOTIFICATION_EMAIL` | 通知先メールアドレス | `your@gmail.com` |
| `SMTP_HOST` | SMTPサーバー | `smtp.gmail.com` |
| `SMTP_PORT` | SMTPポート | `587` |
| `SMTP_USER` | Gmailアドレス | `your@gmail.com` |
| `SMTP_PASSWORD` | Gmailアプリパスワード | `xxxx xxxx xxxx xxxx` |

#### オプションのシークレット（未設定時はデフォルト値を使用）

| シークレット名 | 内容 | デフォルト値 |
|---|---|---|
| `INSTANCE_NAME` | インスタンス表示名 | `ampere-a1-free` |
| `OCPU_COUNT` | OCPUコア数 | `4` |
| `MEMORY_GB` | メモリ(GB) | `24` |
| `BOOT_VOLUME_GB` | ブートボリューム(GB) | `50` |
| `SSH_PUBLIC_KEY` | SSH公開鍵 | （なし） |

#### 秘密鍵（PEMファイル）の設定方法

PEMファイルの内容をそのままシークレットに貼り付けます。改行が含まれていても問題ありません。

```
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA...（省略）
-----END RSA PRIVATE KEY-----
```

#### Gmailアプリパスワードの取得

1. Googleアカウント → **「セキュリティ」** → **「2段階認証プロセス」**（有効にする）
2. **「アプリパスワード」** → アプリ名を入力 → **「作成」**
3. 表示された16文字のパスワードを `SMTP_PASSWORD` に設定

---

### 4. ワークフローの起動

1. GitHubリポジトリ → **「Actions」** タブ
2. **「OCI A1 Launcher」** を選択
3. **「Run workflow」** → **「Run workflow」** をクリック

> `force_restart` は通常 `false` のままでOKです。途中からやり直したい場合のみ `true` を入力してください。

---

## 実行状況の確認

### GitHub Actions ダッシュボード

- リポジトリ → **「Actions」** → 最新の実行をクリック
- **「OCI A1 インスタンス作成スクリプトを実行」** ステップのログでリアルタイムに試行状況を確認できる

### ログの見方

```
2025-01-01 12:00:00 [INFO] セッション #1 開始
2025-01-01 12:00:01 [INFO] [試行 #1] インスタンス作成を試みます... (経過: 1秒, 残り: 21599秒)
2025-01-01 12:00:01 [INFO] 容量不足エラー(500 InternalError): Out of host capacity.
2025-01-01 12:00:01 [INFO] 容量不足。60 秒後に再試行します...
```

### 実行サマリー

各ジョブ実行後、**「Summary」** タブに最新のステート（試行回数・セッション数・最終エラー）が表示される

---

## リトライ間隔の仕様

| 状況 | 待機時間 |
|---|---|
| 通常（容量不足） | 50〜70秒（ジッタあり） |
| レート制限エラー(429) | 120〜150秒 |
| 最大待機時間 | 300秒 |

- **60秒を基本間隔**としているのは、OCI APIのレート制限に引っかからない実績のある最小値です（参考: [oci-capacity-fixer](https://github.com/Vishal-Pandiyan/oci-capacity-fixer)）
- ±10秒のジッタを加えることで複数セッションの同時リトライによる競合を防ぎます

---

## セッション引き継ぎの仕組み

```
セッション#1 (最大5時間55分)
  ↓ 残り10分になったら安全に終了 (exit 0)
  ↓ ステートをGitHub Actionsキャッシュに保存
  ↓ (試行回数・最終エラーなどを保持)
  ↓ workflow_run トリガーで自動起動
セッション#2 (最大5時間55分)
  ↓ キャッシュからステートを復元
  ↓ 試行回数を引き継いで継続
  ...繰り返し...
セッション#N
  ✅ 作成成功 → メール通知 → 終了 (次のセッションは起動しない)
```

---

## トラブルシューティング

### 「致命的エラーで終了した」場合

- Actionsログを確認する
- OCI_USER_OCID, OCI_TENANCY_OCID などのOCIDが正しいか確認
- OCI_PRIVATE_KEY の内容が正しく設定されているか確認（`-----BEGIN`で始まっているか）
- OCI_AVAILABILITY_DOMAIN の形式を確認（例: `BnSg:AP-TOKYO-1-AD-1`）

### メールが届かない場合

- GmailのアプリパスワードがSMTP_PASSWORDに設定されているか確認（通常のパスワードではない）
- SMTP_PORT が `587` になっているか確認

### 「次のセッションが起動しない」場合

- Actionsの「Settings」→「Actions」→「General」→「Workflow permissions」が「Read and write permissions」になっているか確認
- または手動で再度 **「Run workflow」** を実行

### 一時停止したい場合

リポジトリ → **「Actions」** → **「OCI A1 Launcher」** → **「...」** → **「Disable workflow」**

---

## 注意事項

- OCI Always Free の A1 枠は **4 OCPU / 24 GB RAM** まで無料です。デフォルト設定でこの上限いっぱいを使用します
- GitHub Actions の無料枠は**パブリックリポジトリなら無制限**、プライベートリポジトリは月2,000分です。長時間実行する場合は**パブリックリポジトリ**を推奨します（ただし秘密鍵はSecretsで管理されるため安全です）
- 一度インスタンスが作成されても、スクリプトを止め忘れると**新たな課金が発生する可能性があります**。作成成功メール受信後はワークフローを無効化してください
