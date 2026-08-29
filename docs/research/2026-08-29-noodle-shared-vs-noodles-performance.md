# `noodle-shared` 與 `noodles`：執行／推論延遲、返工與 Agent-Friendly 稽核

日期：2026-08-29（Asia/Taipei）  
研究基準：`ed3c/noodles@2f6f60fe8323189379605fa651ff1206eb217472`、`ed3c/noodle-shared@02d8ccc18887e5b1b4e3ed95e57a0b0e048d25ad`、pinned `poteto/noodle@eaa1d5cce36f73e33e81d4855bb2fc47e33d0b24`。  
資料邊界：GitHub provider readback、目前 repo source/tests、shared runtime session logs 唯讀。本文沒有修改 GitHub Issues/orders、沒有啟動 Noodle，也沒有把 PR/Issue latency 冒充純 LLM decoding latency。

## 結論

1. 沒有證據顯示 `noodles` 的 `gpt-5.4` 本體 tokens/s 比 `noodle-shared` 慢。兩者使用同一 model slug，且沒有可比的同 fixture TTFT/tokens/s corpus。
2. `noodles` 最長的浪費是 **重複叫 LLM 判斷「沒有新工作」**。目前 206 個本機 carrier sessions 中有 170 個 schedule、36 個 execute；至少 113 個 schedule 明確回報空 proposal，耗掉 14,860 秒（4.13 小時）、49,986,571 input tokens（其中 46,413,824 cached）、667,493 output tokens、319,655 reasoning tokens。
3. no-op storm 不是單一 prompt 可修的偶發錯誤。Pinned Noodle 空輸出只 cooldown 五分鐘，又會在任何 `miseChanged` 時清掉 cooldown；`mise` change 包含 active summary、recent history/events 等 schedule 自己會改變的暫態狀態。這形成 scheduler 自己喚醒自己的迴圈。
4. `noodles` 的 carrier 沒有像 `noodle-shared` 使用 `--ignore-user-config`。205/206 sessions 都出現 skill descriptions 超過 context budget、被截短的警告。這增加 context、使 skill discovery 不可重現，也讓 Agent 反覆猜錯 skill 路徑。
5. Agent 收到的通用 Noodle schedule prompt 與 repo schedule skill 互相衝突：前者要求直接寫 `orders-next.json`、允許 ad-hoc/`schedule` stage、宣稱有 `todos.md` 與 isolated worktree；後者要求 candidate publish gate、禁止 self-schedule，而 schedule 實際在 primary checkout 執行。
6. 最常返工的根因不是「模型不夠聰明」，而是同一事實有多個可變 owner、first live/provider test 太晚、驗證器沒有 transition state，以及 Agent 指令與物理介面不一致。
7. 現在不該先做 model bake-off。應先停止 PR #80 的錯誤 landing lane、修 no-change scheduling gate／prompt ownership、收斂 #70/#74/#79 的 SSOT，再處理 #64/#65 與 #45/#46。

## 量測結果

### GitHub 端到端代理指標

| 指標 | `noodle-shared` | `noodles` | 可證明的範圍 |
|---|---:|---:|---|
| configured model | `gpt-5.4` | `gpt-5.4` | 不是不同 model slug 造成 |
| scheduler/process concurrency | 1 / 1 | 4 / 4 | 宣告容量，不是 tokens/s |
| successful verify median | 約 31 秒 | 約 30 秒 | CI deterministic gate 幾乎相同 |
| PR open→merge median | 57 秒（n=12） | 97 秒（n=25） | provider integration latency，不含開 PR 前 Agent 工作 |
| PR open→merge p90 | 280 秒 | 1,185 秒 | `noodles` 有明顯較差 tail |

來源：[`noodle-shared/.noodle.toml`](https://github.com/ed3c/noodle-shared/blob/02d8ccc18887e5b1b4e3ed95e57a0b0e048d25ad/.noodle.toml)、[`noodles/.noodle.toml`](https://github.com/ed3c/noodles/blob/2f6f60fe8323189379605fa651ff1206eb217472/.noodle.toml)、兩 repo 的 GitHub PR/workflow timestamps。

這些數據只能說 `noodles` 的 provider/repair tail 較差，不能說模型 decoding 慢。兩 repo 沒有相同 fixture、相同 host/time window 的 TTFT/tokens/s receipt。

### `noodles` 本機 session 分桶

| session | n | wall time | input tokens | cached input | output | reasoning |
|---|---:|---:|---:|---:|---:|---:|
| schedule 全部 | 170 | 22,367 s | 68,389,158 | 63,529,984 | 915,275 | 437,205 |
| 明確空 proposal | 113 | 14,860 s | 49,986,571 | 46,413,824 | 667,493 | 319,655 |
| execute/其他非 schedule | 36 | 18,779 s | 93,584,508 | 90,953,216 | 567,905 | 237,331 |

Schedule duration median 128 秒、p90 189 秒；明確空 proposal median 128 秒、p90 171 秒。`loop-events.ndjson` 同期只有 16 次 `stage.completed`，卻有 145 次 `schedule.completed`。空 proposal 的辨識是保守下限：只算 final action 明說「空 proposal／沒有新增／orders=[]」者。

Token 數是 Codex `turn.completed.usage` 的累計欄位，絕大多數 input 是 cached；它能證明 carrier 做了大量重複 context processing，不能直接換算成未快取 token 成本。

本機 deterministic gate 不是長桿：`./noodles metrics --json` 與 `./noodles verify` 都是亞秒級。耗時集中在 Agent/tool loops、subprocess/provider wait、CI landing 與 repair。

## 為什麼 schedule 會一直空轉

### 1. cooldown 的 state key 錯了

Pinned Noodle 在空 promotion 後只設定五分鐘 cooldown：[`loop_cycle_pipeline.go#L54-L55`](https://github.com/poteto/noodle/blob/eaa1d5cce36f73e33e81d4855bb2fc47e33d0b24/loop/loop_cycle_pipeline.go#L54-L55)。同檔又在任何 `miseChanged` 時清空 cooldown：[`loop_cycle_pipeline.go#L233-L235`](https://github.com/poteto/noodle/blob/eaa1d5cce36f73e33e81d4855bb2fc47e33d0b24/loop/loop_cycle_pipeline.go#L233-L235)。

`mise.Builder` 的 change comparison 雖排除 `GeneratedAt`，仍包含 backlog、ActiveSummary、RecentHistory、RecentEvents、resources、routing、task types：[`mise/builder.go#L94-L123`](https://github.com/poteto/noodle/blob/eaa1d5cce36f73e33e81d4855bb2fc47e33d0b24/mise/builder.go#L94-L123)。Schedule 自己的 start/completion 會改 active summary/events，因此可清掉自己的 cooldown。這是從 source 與連續 session 間隔共同得到的推論。

正確的 gate 應以「會改變排程決策的狀態 digest」為 key：provider backlog subject/state/dependencies、active **non-schedule** orders、失敗/landing event。相同 digest 已得到空結果後，不再啟動 LLM；只有 digest 改變或明確 chef steer 才重跑。

### 2. backlog 幾乎全被 blocked 手動鏡像卡住

GitHub 唯讀 readback：27 個 open Issues 中 26 個 marker 是 `blocked`，唯一 `ready` 是 #74。#18、#44、#61 已 closed/landed，但依賴它們的 #19、#45、#64、#65 仍是 `blocked`。

這不是依賴 graph 的真相，而是另一份需要人工同步的 mutable state。更糟的是 `adapter_sync()` 只輸出 `id/title/status/url`；`parse_issue_contract()` 與 `issue validate` 不輸出 `depends-on`、claim、physical acceptance、non-claims。Schedule skill 卻要求用這些資料做 admission。

結果是：scheduler 看見 27 個 item，但只有一個 marker 可排；該 item 已有 active/open PR lane 時又只能發布空 proposal。依賴已滿足的工作也不會自動轉 ready。

### 3. generic prompt 與 project contract 相反

Pinned Noodle 的 prompt owner 在 [`loop/schedule.go#L278-L339`](https://github.com/poteto/noodle/blob/eaa1d5cce36f73e33e81d4855bb2fc47e33d0b24/loop/schedule.go#L278-L339)，而 schedule 明確在 primary checkout 執行：[`loop/schedule.go#L153-L165`](https://github.com/poteto/noodle/blob/eaa1d5cce36f73e33e81d4855bb2fc47e33d0b24/loop/schedule.go#L153-L165)。實際 session prompt 與 repo skill 有下列衝突：

| Noodle generic prompt | repo schedule skill／實際環境 | 觀察到的浪費 |
|---|---|---|
| 直接寫 `.noodle/orders-next.json` | 必須先寫 candidate，再經 `skill_contract.py publish` | Agent 需要自行覆蓋較高層指令；#65 已承認 gate 可繞 |
| 列出所有 task types，包含 `schedule` | 禁止 emit `schedule` order/stage | 曾造成 self-order supersede/cancel/respawn（#30） |
| 允許 prompt-only/ad-hoc stage與 generic pipeline | 僅允許一個 `execute` stage | schema/normalization 返工 |
| 說有 `todos.md` | GitHub adapter，檔案不存在 | 44 sessions、45 次 failed reads |
| Noodle context 說在 isolated worktree | schedule 實際 primary checkout | writer/路徑判斷錯誤 |
| file 被 loop 消費後沒有 receipt | Agent 以檔案存在性驗證 publish | 118 sessions、205 次讀不存在的 `orders-next.json` |
| 沒給 exact skill path | Agent 猜 global path | 151 sessions、153 次讀不存在的 `/Users/neon/.agents/skills/schedule/SKILL.md` |

## Agent-Friendly 違反清單與處置

以下「全部」限定在本次實際稽核面：`AGENTS.md`、README、system contract、schedule/execute skills、fitness/skill gates、Noodle config/prompt、Issue/PR provider state與 session logs。不是對所有未讀未執行 surface 的無限聲明。

| 違反 | 證據 | 處置 | 防再犯的機械 gate |
|---|---|---|---|
| handoff 順序互相矛盾 | `AGENTS.md` 要先 `awaiting_land` 再開 PR；execute skill 與 `execute_handoff()` 必須先有 exact PR | **DELETE** AGENTS 詳細步驟，指向 execute skill/CLI；保留唯一程序 SSOT | handoff integration test 從 commit→PR→state→blocking receipt 驗證順序 |
| 啟動順序重複且相反 | AGENTS 是 verify→providers→protect audit→start；README 加 runtime check 並寫 protect apply | **DELETE** AGENTS call-order 區塊；README 只保留 bootstrap 與 normal `./noodles start` | CLI `start --explain/--dry-run` 輸出實際 prereq graph；測試 CLI，不 grep prose |
| Issue role 自相矛盾 | schedule skill 允許 evidence-only audit；parser 只接受 repository-mutating-atom | **DELETE** evidence-only 例外；若未來需要，另做明確 role/schema atom | parser positive/negative controls |
| blocked/ready 是手動鏡像 | landed dependency 已真，dependent marker仍 blocked | **REMOVE** dependency-waiting 的手動 state；blocked 只留真實 blocker | parse exact dependency markers；provider readback後 deterministic eligibility derivation |
| backlog adapter 不給 scheduler 所需資料 | sync/validate 缺 deps/claim/acceptance/non-claims | **ADD** 唯讀 `issue contract --json`（或 adapter typed fields）與 body digest | schema test + live provider readback；禁止 scheduler另猜 `gh` 命令 |
| order 複製 mutable Issue 內容 | skill 要 verbatim claim/acceptance/nonclaims；execute又重讀 Issue | **REDUCE** order 為 subject + provider body digest；execute重讀並比 digest | stale digest 必須 fail closed，禁止靜默沿用 snapshot |
| 無變更也叫 LLM | 至少 113 空 schedule、4.13h | **REMOVE** timer-only no-op inference | upstream decision-state digest + empty-result memo；相同 digest 零 carrier spawn |
| generic prompt 與 skill 雙 owner | direct-write/schema/worktree/human規則互撞 | **DELETE** generic policy文字；runtime只提供 typed envelope，skill單獨擁有政策 | golden prompt fixture證明無矛盾、無 `schedule` task self-advertisement |
| ephemeral output 無 receipt | 205 次讀已消費 file | **ADD** promotion digest/event/ack；Agent不以 file existence 作 readback | publish command回傳 candidate digest，loop event回同 digest |
| user config/plugin 洩入 carrier | 205/206 context-budget warnings；`noodles` 缺 `--ignore-user-config` | **ADAPT** `noodle-shared` carrier isolation模式，仍保留 Noodle configured skill paths | live discovery test：只出現 admitted skills，無截短警告 |
| always-loaded AGENTS 重複系統契約 | guarantee/ownership/migration/Issue contract/completion 多處重複 | **MOVE/DELETE**：AGENTS只留 ownership、isolation、route與一個 procedure pointer | size不是 correctness；測 route pointer與唯一 section owner |
| README 硬編 provider SHA/digest | lock JSON才是 owner | **DELETE** prose copies，README link lock/readback command | doc test只驗 pointer；lock validator驗 bytes |
| exact phrase 被當語意 gate | `required_agent_phrases` 與 skill constants grep prose | **DELETE** phrase-lock；改 parse/behavior tests | planted mutation保留字串但破壞結構時必失敗 |
| workflow security 以關鍵字判定 | #64 已記錄 lexical bypass | **DO #64** semantic workflow AST/bounded parser | comment/wrong job/disabled step/permission scope negatives |
| schedule publish可直接繞過 | #65；skill instruction只是 P-class | **DO #65**，若 upstream無 seam則 HOLD/ADAPT_EXTERNAL | pinned runtime direct-write negative與 supported hook readback |
| execute skill列大量負面產品名 | unsupported list增加無關概念 activation | **DELETE**品牌/工具清單，改成「只允許解析成功的 allowlisted route」 | resolver對 unknown route fail closed |
| system non-claims帶入未觸發工具 | GrepAI/tree-sitter/Serena 在一般 system route中造成噪音 | **MOVE**到對應 migration ledger/Issue | system contract只保留跨任務 claim boundaries |
| concurrency 4 是設定而非證據 | 兩個 config 欄位重複 4；#45/#46 尚 blocked | **KEEP AS N-CLASS**，先做 #45/#46；不要宣稱安全並行 | daemon lease + unique session/worktree provenance canary |
| current #74 PR/Issue/open-order 三態漂移 | PR #80 open、verify成功、land因 issue drift失敗；Issue #74又回 ready | **STOP/REPAIR SAME LANE**，ready item若已有 exact open PR不得重排 | ready/open-PR correlation gate；handoff failure保留唯一 repair owner |

## 最常造成返工的具體模式

### 上游介面到 live runtime 才驗

- #25：schedule task frontmatter缺失，Noodle bootstrap改 shared main。
- #37：execute 未註冊，`do: execute` normalization後消失、沒有 worktree。
- #43：local publish 接受 top-level `rationale`，pinned runtime 拒絕並改成 `.bad`。
- #57：repair 使用錯誤 Noodle argv。
- #23：不存在的 `gpt-5.6-pro` slug回 400，terminal failure又被重排。

共同修法：每個 adapter/argv/schema atom在 merge前直接跑 exact pinned runtime positive + planted negative，不以 prose/schema猜測代替。

### trusted-main 與 candidate 缺 transition state

- #52：trusted main 測試要求 hosted runner沒有的 live Noodle，candidate無法自救。
- #58：trusted main仍接受舊 provider fixture，candidate換新 provider後必敗，最後要 two-state oracle。
- #70：candidate改 model default，但 trusted policy仍只允許舊 model；Issue已要求窄 transition atom，backlog沒有對應 ready atom。

共同修法：任何 SSOT replacement 先有 old+new exact two-state validator，再切 consumer，最後刪舊；每步獨立可 land。

### identity 與 mutable state多 owner

- #54：以 `__main__` 與 import 載入兩份 `GateError` class，retry catch不到。
- #60：clean-but-behind local main在 reconcile有權 fast-forward前先被拒絕。
- #30：scheduler重寫 active/self order，取消 active cook並重建 worktree。
- #74：只清 token env，未隔離 `gh` stored credentials，Agent實際 PATCH Issue body。
- #75/#76/#77：fixture bytes/root alias、harness-owned mutation、rubric denominator/attempt budget分別漂移。

共同修法：每個 durable value一個 owner；跨程序傳 stable ID/digest，不靠 class object、路徑字串或 Agent記憶；eval harness與candidate evidence分 owner。

## 現在應先解哪些 Issues

### Stop line：先停止正在製造返工的 lane

1. **PR #80 / Issue #74**：不要原樣 land。Verify成功但 land run因 `issue drifted before landing` 失敗；PR還硬編舊 #70 body，且缺 #74 要求的 provider before/after、真實 non-event、auth-status readback與 subprocess timeout。應在同一 repair lane補完整控制；Issue有 exact open PR 時不得回到一般 `ready` 排程。
2. **#70/#79 決策收斂**：current #70 owner decision不要求 5.4 vs 5.6 behavioral comparison；#79與 PR #80 fixture仍要求 eval。二選一，不得混合。依 current #70，建議採 direct transition。
3. **DROP/脫鉤 #75–#77、#79**：若 #70採 direct transition，這些不應再是 default update prerequisites；否則會建成 #70 non-claim 明確排除的 eval framework。若未來確需 benchmark，另立非 blocking、固定 fixture 的研究 atom。

### P0：先砍浪費與不一致

1. **新增 upstream-owned no-change schedule gate atom**：decision-state digest、empty memo、排除 schedule lifecycle events；相同 digest 必須零 LLM spawn。這是最大的直接速度收益，現有 noodles Issue沒有完整覆蓋。
2. **新增 carrier isolation atom**：以 live discovery/control證明 `--ignore-user-config` 或等價 allowlist不破壞 project/provider skills，並消除 context-budget truncation。
3. **新增 dependency/contract readback atom**：typed dependency markers、deterministic eligibility、readonly full contract+digest；移除手動 dependency-waiting state。
4. **#64**：其依賴 #61 已 landed，應由機械規則變 ready；把 workflow lexical checks換 semantic boundary controls。
5. **#65**：其依賴 #61 已 landed，應變 ready；確認 upstream non-bypassable promotion seam，沒有就 HOLD/ADAPT_EXTERNAL，不做 local watcher。

### P0：再證明並行是真實的

1. **#45 → #46**：先唯一 daemon lease，再綁 execute unique worktree/session provenance。完成前 `concurrency=4` 只是一個設定值。
2. 完成後才用 concurrency=1量單任務 latency，再用 concurrency=4量 throughput；不能把兩者混成 model speed。

### P1：跑通 Golden Path，再做擴張

1. **#19 → #20 → #4 → #21**。
2. 之後才做 #22/#66 等多 Issue automation。
3. #5–#13 code-intelligence 工作延後；它們不是目前 latency/rework root cause。
4. #78 是 supervision metadata，放在安全/吞吐 root cause之後。

## 真正可回答 model inference speed 的 benchmark

現有資料不足以嚴格比較 `noodle-shared` 與 `noodles` 的模型速度。需要一個不改 default 的 bounded benchmark，先固定：

- exact Codex CLI/provider/model/reasoning setting；
- exact fixture digest、同 host/time window；
- concurrency=1，避免吞吐混入 latency；
- process spawn→turn.started、first agent message/TTFT、turn wall、input/cached/output/reasoning tokens；
- tool/subprocess/GitHub wait另分桶；
- run前固定 trial count、timeout、scorer、denominator；
- raw observation與 verdict分離，禁止 trial中修改 harness/rubric；
- 先比較 single-task latency，再獨立比較 concurrency throughput。

在這個 benchmark存在前，最誠實的結論是：**`noodles` 慢在重複 schedule、context與工具工作、late boundary failure和 provider repair tail；尚未證明慢在模型 tokens/s。**

## 限制

- `noodle-shared` 沒有可比的本機 session log corpus，因此本機 token/wall-time分桶只描述 `noodles`。
- PR latency樣本任務大小不同，只是 provider integration proxy。
- shared runtime logs 是本機觀察，不是 GitHub provider truth；GitHub Issue/PR狀態另以 provider readback核對。
- 本報告是研究/設計輸出（N-class），不是已實作的 L/R gate。依本 repo Golden Path，沒有 exact Issue就不能宣稱上述刪除與機械防線已完成。

## Post-baseline addendum（2026-08-30）

本節記錄研究基準 `2f6f60f` 之後、直到本檔 land 為止的 provider 事實變動。上文的排序建議是以基準當時的 backlog 寫的；下列變動已使其中一部分過期。本節仍是 N-class 描述，不因為記錄了 landing 就成為 L/R 證據。

- **#64 已 landed**（PR #87）。上文「Agent-Friendly 違反清單」中 `workflow security 以關鍵字判定 → DO #64` 這一列的處置已由 semantic workflow boundary readback 取代 lexical phrase checks，不再是待辦。
- **#81–#86 已於基準後開立**，其中 **#86 已 landed**。這些 Issue 涵蓋基準當時尚未拆成 atom 的面向；上文 P0/P1 清單沒有它們，是基準時點的缺席，不是判斷它們不必要。
- **#75、#76、#77、#79 已 closed as superseded**。上文「DROP/脫鉤 #75–#77、#79」的建議與後續實際處置一致；`identity 與 mutable state多 owner` 一節仍引用 #75/#76/#77 作為歷史返工樣本，那是對已關閉 Issue 的事後描述，不是待辦。
- 未變動的部分：本檔的量測數字、session 分桶、cooldown/prompt 分析全部維持基準時點的觀察，沒有重新量測。任何要用它們支撐新決策的人必須重跑量測，不得直接沿用。
