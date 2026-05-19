# Project: SWING24/7 ゴルフ打席 自動予約システム

最終更新: 2026-05-19

---

## 1. プロジェクト概要

**目的:** SWING24/7 茅場町店（`https://swing24-kayabacho.revn.jp`）のゴルフ打席を、毎日自動で予約・管理するシステム。

**実行環境:** GitHub Actions（Ubuntu）で毎日 10:53 JST に自動実行。Playwright（ヘッドレス Chromium）でサイトを操作する。

**主要機能:**
- 予約サイトへのログインと空き打席の自動予約
- 明日のキャンセル待ち登録
- 確定予約を Google Calendar へ自動同期

**使用技術:**
| 要素 | 内容 |
|------|------|
| 言語 | Python 3.12 |
| ブラウザ自動化 | Playwright (Chromium) |
| 実行基盤 | GitHub Actions |
| カレンダー連携 | Google Calendar API v3（サービスアカウント） |
| 秘密情報管理 | GitHub Secrets |

---

## 2. システム構成

```
golf_reserve/
├── reserve.py            # メイン自動予約スクリプト（毎日 cron 実行）
├── golf_cancel.py        # 手動キャンセル＆再予約スクリプト
├── sync_calendar.py      # Google Calendar 同期スクリプト
├── requirements.txt      # Python 依存関係
├── .github/
│   └── workflows/
│       ├── reserve.yml           # 定期自動予約ワークフロー
│       └── cancel_and_rebook.yml # 手動キャンセル＆再予約ワークフロー
└── Project.md            # 本ドキュメント
```

**GitHub Secrets（必須）:**
| Secret 名 | 内容 |
|-----------|------|
| `SWING24_USERNAME` | ログイン ID |
| `SWING24_PASSWORD` | ログインパスワード |
| `GOOGLE_CALENDAR_ID` | 同期先カレンダー ID（Gmail アドレス） |
| `GOOGLE_CALENDAR_CREDENTIALS` | サービスアカウント JSON（base64 または生 JSON） |

**スケジュール（reserve.yml）:** 毎日 `01:53 UTC`（= 10:53 JST）に自動実行。`workflow_dispatch` でも手動実行可能。

**手動キャンセル（cancel_and_rebook.yml）:** `workflow_dispatch` 専用。iPhone ショートカット等からトリガーする。

---

## 3. 詳細ロジック

### 3-1. 打席・スロット設定

打席は3つあり、event_id でサイト上の要素を特定する:

```python
EVENT_IDS = {1: 15, 2: 22, 3: 23}  # 打席番号 → event_id
```

予約優先順位（上から順に試みる）:

| 優先度 | 時間 | 打席 |
|-------|------|------|
| 1 | 21:00 | 打席① |
| 2 | 21:00 | 打席③ |
| 3 | 21:00 | 打席② |
| 4 | 20:00 | 打席① |
| 5 | 20:00 | 打席③ |
| 6 | 20:00 | 打席② |

探索範囲: 今日〜10日後（`offset 0〜10`）

### 3-2. スロットの状態

カレンダーページの DOM 要素から CSS クラスで判定:

| 状態 | クラス | 意味 |
|------|-------|------|
| `available` | `js_can_reserve` | 予約可能 |
| `cancel` | `js_waiting_cancellation` | 予約不可・キャンセル待ち可 |
| `other` | その他 | 満席等 |
| `missing` | 要素なし | 表示期間外または過去スロット |

### 3-3. メインロジックフロー（`run_reservation_logic`）

```
① 予約履歴チェック
   └─ 確定済み未来予約あり → 最も遅い日付を secured_date とする
                              探索フローをスキップ
   └─ 確定済みなし → ② へ

② 新規予約探索（today〜today+10日）
   各日: PRIORITY_SLOTS 順に available を探す
         └─ available 発見 → make_reservation() → 成功で secured_date = その日
         └─ 全スロット missing かつ today でない → 探索終了
         └─ 全スロット missing かつ today → 今日は過去スロットとして次へ

③ 明日チェック（翌日の 6 スロットを確認）
   secured_date == tomorrow → スキップ（明日はすでに確保済み）

   ③-a: available があり、かつ tomorrow < secured_date（明日の方が近い）
         └─ secured_date をキャンセル
              └─ キャンセル成功 → 明日を予約
                   └─ 予約成功 → 完了
                   └─ 予約失敗 → search_and_reserve() で再探索
              └─ キャンセル失敗 → 既存予約を維持

   ③-b: ③-a が成功しなかった場合のみ
         cancel スロットがあれば全件キャンセル待ち登録
         なければ何もしない
```

### 3-4. 予約実行（`make_reservation`）

1. カレンダーページへ遷移（`data-event-id` と `data-usage-timestamp` で要素特定）
2. 要素の `data-url` から予約フォームへ遷移
3. チェックボックスにチェック → 「内容確認」ボタンをクリック
4. 「予約を登録する」ボタンをクリック
5. ページ本文に「予約を受け付けました」または「予約ID」が含まれるかで成否判定
6. 失敗時はスクリーンショットを `/tmp/swing24_*.png` に保存

### 3-5. キャンセル待ち登録（`register_cancel_wait`）

1. カレンダーページへ遷移
2. `cancel` 状態の要素をクリック
3. 「登録する」ボタンをクリックして完了

### 3-6. 既存予約キャンセル（`cancel_reservation`）

1. 予約履歴ページへ遷移
2. 対象日付 + 「確定」を含む行の「詳細」リンクをクリック
3. ダイアログを自動承認して「キャンセル」ボタンをクリック
4. 「はい」確認ボタンがあればクリック

### 3-7. Google Calendar 同期（`sync_calendar.py`）

`reserve.py` 実行後に `sync_calendar.py` が常に実行される（`if: always()`）。

1. **Step A:** 予約サイトにログインし、今後4日以内の確定予約を取得
2. **Step B:** Google Calendar から同タイトル（`SWING24/7 reservation`）のイベントを取得
3. **Step C:** 差分同期
   - サイトにあってカレンダーにない → イベント作成（1時間枠、5分前リマインダー）
   - カレンダーにあってサイトにない → イベント削除（キャンセル扱い）

### 3-8. 手動キャンセル＆再予約（`golf_cancel.py`）

`workflow_dispatch` でトリガー（iPhone ショートカット等からの手動実行）。

```
① ログイン
② 確定予約のうち最も近い日付 D を特定
   └─ 予約なし → エラーログ → exit(1)

③ D をキャンセル
   └─ 失敗 → エラーログ → exit(1)（不整合防止）

④ 再予約探索（D+1 〜 D+7 の7日間）
   PRIORITY_SLOTS順で各日をチェック:
   └─ available → 予約実行（成功で ⑤ へ）
   └─ 全スロット missing → 探索終了
   └─ 7日間で見つからず → カレンダーの D イベント削除 → exit(1)

⑤ Google Calendar 更新
   └─ D のイベント削除 → 新日時のイベント作成（1時間枠・5分前リマインダー）
```

---

## 4. 実行スケジュール

| 項目 | 設定値 |
|------|-------|
| cron | `53 1 * * *`（UTC） |
| 実行時刻 | 毎日 10:53 JST |
| タイムアウト | 15分 |
| 実行環境 | ubuntu-latest |

---

## 5. 設定値一覧

| 変数名 | 値 | 説明 |
|-------|-----|------|
| `BASE_URL` | `https://swing24-kayabacho.revn.jp` | サイトのベース URL |
| `MAX_DAYS_SEARCH` | 30（コード定義あり、探索では 11 日使用） | 最大探索日数 |
| `SYNC_DAYS` | 4 | カレンダー同期の先読み日数 |
| `JST` | UTC+9 | タイムゾーン |

---

## 6. 開発経緯

| フェーズ | 内容 |
|---------|------|
| 初期実装 | GitHub Actions ワークフローの追加。基本的な予約ロジックの実装 |
| メール通知 | キャンセル待ち・確定予約時のメール通知を追加（後に削除） |
| ロジック安定化 | 既存予約チェック・日時比較・キャンセル待ち条件の修正を繰り返す |
| JST 対応 | 海外サーバー実行での日付ズレ問題を解消するため、全処理を JST 明示に変更 |
| ログイン修正 | フィールド ID 指定（`#auth-login-login-id`）と Enter サブミットに変更 |
| カレンダー同期 | Google Calendar API によるイベント自動作成・削除を追加 |
| Secrets 対応 | base64 エンコード済み認証情報のデコードに対応 |
| スケジュール整理 | 1日6回 → 1回（10:53 JST）に統合 |
| ③-a ロジック修正 | 既存予約キャンセル後に明日を予約、失敗時は再探索するフローに確定 |
| 手動キャンセル機能追加 | `golf_cancel.py` と `cancel_and_rebook.yml` を新規追加。直近予約をキャンセルし D+1〜D+7 で再予約 |

---

## 7. 変更履歴

<!-- この以下は git commit 時に自動追記されます -->
- 2026-05-17: プロジェクト初版作成
- 2026-05-19: golf_cancel.py・cancel_and_rebook.yml を追加（手動キャンセル＆再予約機能）
