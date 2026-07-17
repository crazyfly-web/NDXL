# NDXL v2 — Nasdaq-100 追蹤儀表板

乾淨版架構，只使用：

- 靜態 HTML / CSS / JavaScript
- GitHub Actions 每日抓取資料
- `data/tracking.json` 保存計算結果
- Cloudflare Pages 隨 GitHub commit 自動部署

不使用 D1、Worker、Wrangler、npm 或任何 Secret。

## 上傳到空白 GitHub 儲存庫

請把本專案根目錄的所有內容上傳到儲存庫根目錄。必須包含隱藏資料夾：

```text
.github/workflows/update-tracking.yml
```

Mac Finder 按 `Command + Shift + .` 顯示隱藏檔案。

GitHub 根目錄應看到：

```text
.github/
data/
scripts/
index.html
app.js
styles.css
README.md
```

## 第一次執行

1. Repository → **Actions**。
2. 左側選 **Update Nasdaq-100 tracking data**。
3. 按 **Run workflow**，分支選 `main`。
4. 等待綠色勾勾。
5. 成功後 `data/tracking.json` 會更新，並產生 commit：
   `data: update Nasdaq-100 tracking snapshot`
6. Cloudflare Pages 會因新 commit 自動重新部署。

## GitHub Actions 權限

Repository → Settings → Actions → General → Workflow permissions：

- 選 `Read and write permissions`
- 儲存

Workflow 本身也只要求 `contents: write`。

## 自動更新時間

週一至週五 UTC 23:40，約為台灣時間隔日上午 07:40。排程可能因 GitHub Actions 負載稍有延遲。

## 資料口徑

- `^XNDX`：Nasdaq-100 Total Return Index 的延遲資料代理。
- `QQQ`、`00662.TW`、`009800.TW`：Adjusted Close 作為含息報酬代理。
- `TWD=X`：美元兌新台幣，用於建立新台幣口徑的 Nasdaq-100 基準。
- QQQ 與美元基準比較；00662、009800 與新台幣基準比較。

Yahoo Finance chart endpoint 為非官方資料來源。正式研究仍需與 Nasdaq、基金公司及交易所官方資料交叉核對。
