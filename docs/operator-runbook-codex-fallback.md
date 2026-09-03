# Operator runbook — running noodles without a Claude dispatcher

**Class: N — operating manual. Never gate-bearing. Nothing in this file may be
cited as verification authority, evidence of closure, or admission for anything
it describes. Every mechanism named here is owned by an executable contract, a
gate, or a provider readback that exists independently of this document; when
they disagree, they are right and this file is stale.**

Subject: `ed3c/noodles#411`. Authored 2026-09-03. Every provider state quoted
below (issue numbers, states, blockers, pool membership) was read back from
GitHub on 2026-09-03 with `gh issue view` / `gh issue list`; each section names
the command that reconstructs it. A row that disagrees with a live readback is
stale, not authoritative.

## 0. Why this file exists

The knowledge required to run this machine has been living in two carriers that
do not survive a session: a per-user memory file outside the repository (the
standing dispatch formula) and a scratchpad ledger in a tmpdir (the wave-by-wave
adjudications — ratified topology, landing-train failure cures, throttle rules,
residency taxonomy, closure criteria). The pure-Codex fallback is ratified as
*provider degradation, never governance degradation*; a fallback whose operating
manual dies with the dispatcher's subscription is governance degradation by
another name.

This file is the survivor. It distills, it does not duplicate: each of the seven
fallback atoms keeps its acceptance in its own issue body, each gate keeps its
semantics in its own code, and this document says what to run, in what order,
and what a failure means.

Read in order the first time: §1 the formula → §2 the topology and mode machine
→ §3 running a wave → §4 landing → §5 what is unbuilt → §6 what is open → §7
why things are the way they are.

---

## 1. The standing dispatch formula, v-next.4 (verbatim)

**SSOT.** The authoritative copy is the operator's own memory file,
`~/.claude/projects/-Users-neon-noodles/memory/noodles-dispatch-formula.md`
(sha256 of the whole file at copy time:
`7a4dfcfe2e56ee268a31a6e2b1b5d7477062920895c9f96995a741f03d00b0eb`). That file
is outside this repository and dies with the machine it lives on; the block
below is a byte copy of its formula body (its lines 19–126) taken 2026-09-03.
**If the two ever disagree, the memory file wins while it exists, and this copy
wins after it does not.** Amendments are operator diffs against the SSOT, and a
diff that lands there must be copied here in the same motion or this section is
lying by omission.

The formula is quoted in the operator's own language deliberately: it is a
standing directive, and paraphrase is how standing directives drift. §2–§7 below
are the English operating consequences of it.

### Verbatim block (do not edit except to re-copy from the SSOT)

```text
# BEGIN dispatch-formula-v-next.4
用 noodles 全自動處理,持續到 all issues 解決:

1) 入帳(gate 優先):問題收斂成機器 issues 前,先用機器閘門乾跑准入
   (issue_contract 讀回;requirement 綁既有規格標題,鑄新 id 標記 wave 直取;
   依賴只寫 marker;filing 前先跑 failure-fingerprint 查重;失敗類單的
   觀察者先示範雙向——red-team finding 的實驗塊直接充當示範段;
   observer/capability-probe 雙 marker 已為機器閘;示範章=GREEN/RED
   各含逐字 invocation+其下相異真輸出;
   未驗證的架構寫作先落 /docs N-class 自宣告,物理驗證後才進規格書)。
   能下沉為 inline 閘門的,不開監督、不寫清單(availability→gate)。

2) 分派(單分派器分區,依依賴鏈+錯誤類分 lane,預留下一波並行空間):
   daemon 持有的 pool 不派 wave;操作者拓撲線(issue-NNN-*)=落地面
   單一寫入者,永不觸碰,寫界衝突我方後落。
   派發密度=回授兩訊號(swap 餘裕+落地隊深),重波不並行(1重+1輕);
   全量濾網只在推前與 rebase 後,中間輪差分。
   地端線=實作+初驗:Opus implement 並行→L 級濾網必跑
   (「雲端會抓」列為違規)→單棒 reconcile 套 findings→
   儀軌三件+state flip 即收工;
   雲端線=終驗+落地:landing train/並行拓撲鏈式消化(零 agent),
   單棒 Sonnet sweeper 對帳終態;機器類只認 land.yml 五連動合併,
   雲端 merge 只合 issue-NNN-* 類+merged-via 標記
   (無標記自動合併=切專屬 App 身份的觸發器);
   execution provider 可替換(Claude/Codex 依 #70 路由;Hybrid=品質主路徑
   =Codex implement+Claude monitors/judge;純 Codex=fallback,
   SUPERVISION_DIVERSITY 誠實標 provider-diverse 或 config-diverse-only),
   workflow semantics 與 landing authority 不可替換
   (agent proposes/machine verifies/landing identity lands);
   noodles 唯讀+釘定接 cursor/plugins pstack(正典唯讀);
   skill 出生/維護走雙規格標準:pstack create/maintain-verification-skill
   (Launch/Doctor/Drive/Evidence/Cleanup/Feature Map+prove-once 端到端)
   × skill-concerns 八閘機械准入(出生三件=feature map/refusing doctor/
   prove-once receipt;validator wiring、test discovery、count tie、
   admission stamp、campaign 種植陰性臂、Roles 掃描、AGENTS.md 列、
   conformance 皆 repo 級 gate)——雙規格於出生時物理化自動符合,
   不靠事後補課;兩標準缺一不落 main;
   noodle(daemon)世代由操作者在自己終端啟停。

3) 監督(複數 supervisor,全 reader-only,收據引用+提問,階段邊界對齊,
   絕不中途注入;red-team 訊號只上派發者;
   residency=掛載點×讀面×發聲節奏三元組,resident≠always executing):
   - wave 路線:四角度邊界 monitors 各讀全部 lanes、digest 釘定——
     spatial-loop-grounded(全條文@釘定 SHA,現行至 C12;條數不硬編碼;
     stage/generation boundary 裁決)/
     Shadow architect(形狀;讀釘定 skill;stage-aware:可讀 material
     delta,bounded output)/
     control-noodle(儀軌誠實;ceremony boundary)/
     red-team(boundary-resident falsifier,mid-generation 否;
     讀 skills/red-team@釘定 SHA:目錄比對+抽樣否證+run 記錄,
     無命中回無發現;N 渲染 findings=N schema 記錄、
     render_demonstration 塊逐字入案、未跑配方的 discard 列
     ABSENT-triaged 附理由;run 記錄經 producer 落帳——
     monitor 只交棒,落地 lane 代寫);
     收官 judge 讀同一份 red-team 位元組當規則源。
     semantic-decompression-shadow(sc#147,雙規格出生)通過八閘+三陰性臂
     後加入為第五讀者:session-resident passive——mid-generation
     presence, closed-boundary authority(邏輯常駐=anchor state+
     checkpoint 契約,非物理進程;attach early, observe continuously,
     speak late;emit 只在 semantic commitment boundary,早於 PR
     boundary;UNKNOWN_BLOCKING 例外直上派發者)。
     急迫類唯一提前路徑=sensor-falsifier 拆分:catalogue class→
     最小可觀察前驅→常駐機械 sensor→bounded 訊號→派發者;
     前驅全機械化即 sensor→gate,class 依 R6 退出抽樣——
     絕不讓紅隊 mid-generation 跟著 agent 思考。
   - daemon 路線:常駐三層(dynamic-workflow 活性 / control-noodle 儀軌 /
     arrival-engineering 抵達)+世代收官雙 pass(slg 裁決+red-team 否證);
     世代中零注入,回饋只落 issue/ledger,下一世代消費。
   - findings → 派發者:指紋查重→聚類→開類原子(自帶存量清掃)或 enrich;
     緊急類走訊號,立案永遠走裁決;類閘門化即退出抽樣。

4) 落帳與抵達(落地≠使用;詞彙=DECLARED/EXERCISED/PRODUCTION):
   每波 judge verdict 經 gen_ledger 併批進 slg ledger(judge 讀
   evidence manifest,原始件存 artifact 按引取,不做巨型 prompt 拼接);
   red-team run ledger 記每次運行(含 subject kind:wave 邊界/世代收官),
   三曲線(已知類再犯/judge gaps/指紋阻擋)帶分母
   (再犯/合格變更、gaps/受裁波、阻擋/准入候選)+issue-class mix,
   三波不降=INSTRUMENT_SUSPECTED→有界診斷(儀器壞或分布變,雙假說),
   不立即宣告儀器失敗;
   **「持續到 all issues 解決」=世代收束謂詞**:所有 admitted issues 落入
   terminal 類(RESOLVED/DUPLICATE_ENRICHED/GATED_OUT/N_CLASS_DECLARED/
   BLOCKED_EXTERNAL/DEFERRED_BUDGET/QUARANTINED/SUPERSEDED)
   ∧ no_active_lanes ∧ landing_train_empty ∧ findings_accounted
   ∧ ledgers_committed;BLOCKED_EXTERNAL 永不冒充 resolved;
   雲端 advisory check 與 trusted verify 的一致率入 ledger,
   達標才棘輪晉升 required;對話新裁定追加 arrival topology 列
   (無收據路徑拒收);digest preimage=provider 原始位元組
   (--body-file 發布);二次抵達 cell 附存取路徑,sc#102 天花板引用
   不重推導;PRODUCTION 只憑 session/run 收據升級;
   二次抵達用 GraphQL userContentEdits;
   下個 daemon 驗證批的跨 repo intel=coverage obligation:至少一顆
   eligible 跨 repo atom 被 exercised;無合格候選記 COVERAGE_ABSENT+reason,
   不為湊數造 issue。

配額走預算載體 fail-soft(模式機:NORMAL_HYBRID/CODEX_ONLY/READ_ONLY_DRAIN/
ADMISSION_ONLY/PAUSED_BUDGET/PAUSED_AUTHORITY;模式轉換帶收據),
絕不換身份=硬閘;不過度設計、side effect 以收據可控。

---

版本沿革:v-next(2026-09-03 六 diff:雙 marker 機器閘/密度回授/slg 全條文@SHA/
第五讀者/紅隊 producer 落帳/preimage+存取路徑)→ v-next.1(同日補雙規格標準)
→ v-next.2(同日,第五讀者行改治理句 mid-generation presence, closed-boundary
authority+邏輯常駐形;物理形細節在 sc#147 契約)→ v-next.3(同日,§3 摺入
五角 residency 座標、紅隊形式義務 N=N+逐字塊+ABSENT-triaged、
sensor-falsifier 唯一提前路徑)→ v-next.4(同日,Codex 總裁定:§2 provider
可替換/semantics 不可替換、§4 judge manifest+三曲線分母與
INSTRUMENT_SUSPECTED+世代收束謂詞+coverage obligation+fail-soft 模式機)。
相關:[[machine-load-throttle]]、[[landing-train-mechanics]]、[[noodles-ops-preauthorized]]、[[pstack-canonical]]。
# END dispatch-formula-v-next.4
```

### Verbatim control (runnable from the merged tree)

Positive direction — recompute the block's digest:

```bash
sed -n '/^# BEGIN dispatch-formula-v-next\.4$/,/^# END dispatch-formula-v-next\.4$/p' \
  docs/operator-runbook-codex-fallback.md | shasum -a 256
```

Recorded value (this landing): `8e6c8af5f9f987701fb76ef6a005ee79dbc24b192533c21d4633f22d487cefeb`

Planted-negative direction — change one byte inside the block and rerun the same
command; the digest differs. Both directions were run at authoring time with
their exit status recorded in the atom's landing receipt. This control proves
only that the block was not silently edited after landing; it cannot prove the
block matched the SSOT at copy time, which is what the SSOT digest above is for.

### Amendments made after this copy: v-next.5 and v-next.6

The SSOT moved twice more on the day this file was written, both after the block
above was copied. The block is a pin of **v-next.4** and stays one; the two later
clauses are recorded here in English so a cold reader is not surprised to find a
formula with more text in it than the pin has:

- **v-next.5 — the trusted-policy invariant (into the formula's §2).** A lint or
  type policy belongs to the *trusted verifier*, not to the candidate: **a pull
  request may not amend the policy that approves it.** A candidate shipping
  `ignore = ALL` still goes red against the policy on `main`, and a policy change
  takes effect from PR N+1 onward. Same shape as the exact-head lander. Carriers:
  `#413`, `#415`, `#418`, `#417`.
- **v-next.6 — collision granularity (into the formula's §2).** Overlapping write
  boundaries constrain **co-landing, never co-implementation**, and shared files
  that are regenerated by a producer do not count as overlap at all. Full
  reasoning in §7.7.

### The one-line reading, for an operator who cannot read the block

Admission is a gate, not a review (§1 of the formula). Dispatch is one
partitioned dispatcher with density feedback and a never-touched operator lane
(§2). Supervision is plural, reader-only, boundary-aligned, and never injected
mid-generation (§3). Accounting is arrival-typed — DECLARED / EXERCISED /
PRODUCTION — and "keep going until all issues are solved" means the
generation-closure predicate, not `while open_issues > 0` (§4). Quota pressure
moves the fail-soft mode machine; **substituting an identity is a hard gate
refusal, never a fallback.**

---

## 2. Ratified fallback topology, modes, and transitions

Source: operator adjudication 2026-09-03, recorded verbatim in the body of
`ed3c/noodles#407` under *Ratified fallback topology*. That issue body is the
contract; this section is its operating summary.

### 2.1 The canonical sentence

Hybrid is the quality mainline (Codex implement lanes + Claude monitors and
judge, provider-diverse supervision). Codex-only is a **full-function fallback
with reduced supervision diversity** — provider degradation, never governance
degradation. Both share **one** control plane, issue contract, gate set, ledger
set, and machine landing authority, so the fallback can never become a second
workflow that drifts.

### 2.2 Control-plane exclusivity (only noodles may do these)

Advance workflow state · assign lanes · declare a lane stalled or dead ·
receive monitor findings · create or enrich issues · submit to the landing
train · decide queue-terminal.

Codex agents produce **typed proposals and receipts only**. An agent that closes
an issue, merges a PR, or advances a state marker is out of contract regardless
of how good its work was.

### 2.3 Landing-authority separation (the credential-separation pattern)

| Job | Holds | Does |
|---|---|---|
| agent job | repository **read** + model-provider credential | emits a patch artifact |
| landing job | repository **write**, *no* model-provider credential | applies the patch, opens the PR |
| App identity | machine triggers only | exact-head merge, closure, anchor, train |

No agent touches a merge endpoint. Full local filters re-run after every rebase.
Branch/worktree residue is checked after every merge. GraphQL
`userContentEdits` is executed only by the arrival writer.

### 2.4 The topology, in dispatch order

```text
admission gate
   -> dispatcher (single, partitioned)
      -> heavy / light Codex lanes
         -> L-grade local filter (mandatory; "the cloud will catch it" is a violation)
            -> generation boundary
               -> five reader-only monitors
                  -> single-baton Codex reconcile
                     -> pinned Codex judge
                        -> machine landing train
                           -> Codex sweeper
                              -> generation ledger
                                 -> dispatcher (next generation)
```

### 2.5 Mode table

| Mode | What is permitted | Honest supervision label |
|---|---|---|
| `NORMAL_HYBRID` | everything; Codex implements, Claude supervises | `SUPERVISION_DIVERSITY=provider-diverse` |
| `CODEX_ONLY` | everything; one provider on both sides | `SUPERVISION_DIVERSITY=config-diverse-only` |
| `READ_ONLY_DRAIN` | dedupe, admission dry-run, classification, reader-only monitoring, ledger reconciliation, next-wave preparation — **execution verbs refused with the mode named** | inherited |
| `ADMISSION_ONLY` | admission and classification; no execution lanes | inherited |
| `PAUSED_BUDGET` | nothing new; affected admitted issues classified `DEFERRED_BUDGET` with the budget reading and retry condition | inherited |
| `PAUSED_AUTHORITY` | nothing that needs landing authority | inherited |

`config-diverse-only` is a label the machine must carry, not a euphemism to
drop: presenting it as provider diversity is the dishonesty this mode exists to
prevent.

### 2.6 Transition table (verbatim triggers from `#407`)

| Trigger reading | Transition |
|---|---|
| Claude unavailable | → `CODEX_ONLY` |
| Codex write-quota pressure | → `READ_ONLY_DRAIN` |
| all execution providers unavailable | → `ADMISSION_ONLY` |
| total budget exhausted | → `PAUSED_BUDGET` |
| GitHub App / landing authority lost | → `PAUSED_AUTHORITY` |
| recovery reading | reverses each transition, **with its own receipt** |

Three invariants ride on this table:

1. Every transition emits a receipt naming the **trigger reading**. A transition
   without a receipt is a validator error, not a silent mode change.
2. **Identity substitution under any mode is a validator error.** No mode
   reachable by any transition admits swapping credentials or identities to get
   past a quota. This is the hardest invariant in the design.
3. Entering `PAUSED_BUDGET` (or deferring on budget in any mode) carries a
   terminal-classification duty: each affected admitted issue becomes
   `DEFERRED_BUDGET` with the budget reading and the retry condition. A budget
   deferral that classifies nothing is a validator error.

Readings are **consumed**, never produced, by the mode machine: the event
adapter (`#170`) owns provider availability sensing for both dialects.

### 2.7 Branch-naming gate (operator-resolved 2026-09-03)

Fallback mode **only**: Codex lane branches use machine-minted naming (the
wave-id mint's natural extension, `#410`), and the train admits only
machine-recognized branches. Normal-mode wave branch naming (`b<N>-*`) is
unchanged — the earlier reading that "only `issue-NNN-*` may enter the train"
would have rejected every existing wave branch and was retired.

The gate **composes** with the accelerator model rather than replacing it: cloud
parallel-acceleration merges and re-acceptance stay legal in fallback for
machine-named branches carrying the `merged-via` marker, with the
bundle-completion duty unchanged. The naming gate binds **admission** on both
routes (train and accelerator); it never touches the merge-authority split.

### 2.8 Supervision isolation — the four layers

Recorded in `#407` so the contract survives until the Codex reader-fleet atom is
filed (deliberately post-canary):

1. **Thread** — a monitor never resumes an implementation thread and never
   inherits implementer reasoning. It reads: pinned snapshot, lane receipt,
   diff, test evidence, referenced skill bytes, journal/digest. An implementer's
   summary is never the sole source of any finding.
2. **Role** — project-scoped read-only agents; no GitHub write tool, no
   issue-creation authority, no landing authority; fixed findings schema;
   independent threads; no monitor receives another monitor's conclusions.
3. **Evidence** — each monitor reads raw material itself. (Red-team input =
   subject digest + pinned skill bytes + directory inventory + sample targets +
   raw command receipts + discard/ABSENT records.)
4. **Config** — bounded inference differences per role (implementer
   high-reasoning workspace-write; monitors read-heavy; judge high-reasoning
   with a fixed config digest; sweeper low-reasoning strict schema), labeled
   `SUPERVISION_DIVERSITY=config-diverse-only`.

---

## 3. Running one wave on `codex exec --json`

Host surface verified 2026-09-03 by direct probe: `codex --version` →
`codex-cli 0.149.0`; `codex exec --help` carries `--json`, `--output-schema`,
`-o/--output-last-message`, `-C/--cd`, `--add-dir`, `-m/--model`,
`-s/--sandbox`, `-p/--profile`, and the `resume` / `fork` subcommands. Re-probe
before trusting this paragraph on a different host or a newer CLI.

### 3.0 Model routing

`policy/fitness.json` owns the admitted Codex task profiles — one model and one
reasoning effort per task type — and is the only place to read them:

```bash
python3 -c "import json;print(json.load(open('policy/fitness.json'))['required_codex_task_profiles'])"
```

**This document deliberately does not reproduce the values.** Writing them here
would create a second copy that drifts, and the repository refuses it
mechanically: `validate_task_profile_single_source` fails `./noodles verify`
with *"pins task model '<name>'; derive it from policy/fitness.json via
`skill_contract.task_profiles`"* for any tracked file outside the declared
exempt set. That refusal fired on the first draft of this very section, which is
the cheapest possible demonstration that the rule is a gate and not advice. Read
the values; never quote them.

### 3.1 Pick the pool and prove admission before spending anything

```bash
./noodles verify                                   # local gate must be green first
./noodles issue completeness                       # which open issues are schedulable, and why not
./noodles issue validate ed3c/noodles#<N>          # per-atom contract readback
```

`completeness` is the dry-run of admission. An issue that is not schedulable is
not a lane; fix the marker, do not dispatch around it. Before filing anything
new, run the failure-fingerprint dedupe (§7.3) — a duplicate filing costs a
whole lane.

### 3.2 Mint the wave id

Today the wave label is dispatcher-authored free text. That is exactly the hole
`#410` closes: once it lands, the scheduler mints the id and an unminted id
presented to any machine-side consumer is a validator error. **Until `#410`
lands, treat the wave label as untrusted input and never use it as a join key
for anything that matters.**

### 3.3 One lane = one fresh clone

Never run a lane in a working tree someone else owns. Per lane:

```bash
LANE=$SCRATCH/wave<N>/<lane>
mkdir -p "$LANE" && git clone https://github.com/ed3c/noodles.git "$LANE/repo"
git -C "$LANE/repo" checkout -b b<issue>-<slug> origin/main
```

For a wave of many lanes, share objects instead of re-downloading — keep one
mirror per wave and clone with `--reference` (a content-addressed share; byte
equality is preserved, and the mirror needs `gc.auto=0` plus between-wave
maintenance).

### 3.4 Build the lane prompt

The prompt is three concatenated parts, in this order:

1. the issue body **in full**, read from the provider
   (`gh issue view <N> --repo ed3c/noodles --json body -q .body`) — the
   acceptance clauses in the body *are* the acceptance;
2. the HARD rules block, scoped to that lane's directory (write boundary, local
   filter, suite mutex, git identity, "never merge", digest discipline);
3. the deliverable contract: push the branch, no PR, write a full lane report to
   a named path, return a short summary.

### 3.5 Run the lane

```bash
# derive the model from the SSOT; never paste it into a script or a document
MODEL=$(python3 -c "import json;print(json.load(open('policy/fitness.json'))['required_codex_task_profiles']['execute']['model'])")

codex exec --json \
  -C "$LANE/repo" \
  -m "$MODEL" \
  -s workspace-write \
  --output-schema "$WAVE/lane-report.schema.json" \
  -o "$LANE/last-message.txt" \
  - < "$LANE/prompt.md" | tee "$LANE/events.jsonl"
```

Rules that make this run auditable rather than merely finished:

- **Capture the full JSONL stream.** `events.jsonl` is the lane's primary
  receipt: token usage comes off `turn.completed`, and terminal state comes off
  typed events only.
- **Terminal state is typed, never textual.** Process exit status,
  `turn.completed`, `turn.failed`, `error` (and App Server thread/turn events)
  decide whether a lane finished. The strings `truncated` / `failed` /
  `completed` appearing *inside* output text are payload and must never be read
  as control signals. (This is the class `#260` deletes; until it lands, the
  substring landmine is live.)
- **Absence of a terminal event does not mean death.** Combine a quiet budget
  with side evidence (process runtime, noodles journal, repository movement)
  before calling a lane stalled. Competing with a lane that is merely quiet is
  how two writers end up on one branch.
- **`--output-schema` proves shape, never eligibility.** A schema-valid final
  message is not an issue contract, not a `Refs` body, not test evidence, and
  not landing eligibility. noodles admission and landing validation run
  unchanged on top of it.
- **One bounded retry per lane, with the failure class named** (turn failure /
  context exhaustion / tool failure / interrupted output / process termination /
  protocol drift / schema-valid-but-semantically-refused). A second failure is
  recorded, never retried.

Resume rather than restart when a lane dies mid-work:
`codex exec resume <session-id>` (or `--last`).

### 3.6 The local filter — mandatory, exit codes captured

Before every push, in the lane's own clone:

```bash
flock -x "$WAVE/suite.lock" tests/run.sh;              echo "TESTS_EXIT=$?"
flock -x "$WAVE/suite.lock" ./noodles verify;          echo "VERIFY_EXIT=$?"
flock -x "$WAVE/suite.lock" ./noodles verify --trusted-preview; echo "PREVIEW_EXIT=$?"
git fetch origin
git diff origin/main...HEAD --name-only              # must be a subset of the declared write boundary
```

Non-negotiables learned the expensive way:

- **Capture exit codes; never pipe them away.** `cmd | tee log` reports `tee`'s
  status. Use `&& echo RESULT_EXIT_0 || echo RESULT_NONZERO` when a shell guard
  rejects `$?` capture.
- **Grep failures on the runner's verdict lines** (`FAILED`, `OK`, `Ran N`),
  never on the substring `FAIL:` — two green tests print `FAIL:` in diagnostic
  output, and the false red costs a rerun.
- **Three-dot diff against a freshly fetched `origin/main`.** A stale local
  `main` makes GitHub's `update-branch` (which carries landed peers' bytes onto
  your branch) look like cross-contamination. This exact false alarm consumed a
  repair agent's session.
- **The full triple runs at final pre-push and after every rebase.**
  Intermediate iterations may run targeted subsets. The claim points are the
  ones that must be complete; the middle of the loop may be cheap.
- **Take the suite mutex.** Concurrent full suites across lanes both exhaust the
  machine and manufacture load-induced flakes; serializing them raises signal
  quality as a side effect.
- "The cloud will catch it" is a rule violation, not a plan. Local is L-grade
  (implement + first verification); cloud is R-grade (final verification and
  landing). Both are required and neither substitutes.

### 3.7 Push, PR, flip

```bash
git -c user.name=ed3c -c user.email=ed3c@users.noreply.github.com commit ...
git push -u origin b<issue>-<slug>                    # --force-with-lease only, never plain --force
gh pr create --repo ed3c/noodles --head b<issue>-<slug> \
  --title "<subject>" --body "Refs ed3c/noodles#<N>"
```

The PR body must be **exactly** `Refs ed3c/noodles#<N>` — `land` parses it and
compares it against the verify receipt. Then flip the issue's state marker to
`awaiting_land`; that marker is what the machine reads as "mechanically
landable". Do not flip it for a PR that is red for a reason a rebase cannot fix
— that state belongs to `blocked` (see §4.4).

Never merge by hand. Machine merges only.

---

## 4. Daemon generations and the landing train

### 4.1 Starting and stopping a generation (operator's terminal)

Daemon generations are started **by the operator, in the operator's own
terminal**, never by a lane agent and never by a wave. The bootstrap call order
is owned by `README.md`; this is the operating subset:

```bash
./noodles verify                 # local gate
./noodles runtime check          # pinned upstream Noodle binary readback
./noodles providers sync         # pinned provider commits
./noodles github protect apply   # one-time, admin-capable token
./noodles start                  # ONE daemon generation
./noodles supervise              # unattended: heal, restart, rotate, cool down
```

- `./noodles start` runs one generation and fails closed unless local fitness,
  pinned providers, and GitHub protection readback all pass.
- `./noodles supervise --generations N` stops after N generations;
  `--heal-only` prints the heal receipt **without spawning a daemon** — that is
  the safe way to inspect daemon health.
- `./noodles reconcile` fast-forwards local `main` after the machine landed
  something and releases the Noodle review. `--watch` polls.
- Noodle stays in `supervised` mode on purpose: `auto` merges a completed
  worktree into local `main`, which is orchestration, not GitHub exact-head
  enforcement. `supervised` is the containment point.
- **Stopping** is stopping the process the operator started. There is no
  "stop generation" verb, and a lane agent must never start one: no `.noodle`
  runtime state outside a test's own temporary directory.

Partition rule that keeps daemon and waves from fighting: **the daemon owns the
ready pool; waves own their explicitly dispatched issues.** An issue the daemon
holds is not a wave lane.

### 4.2 What actually triggers landing

`.github/workflows/land.yml` is triggered by
`workflow_run: [verify] completed` with `conclusion == 'success'` — **not by a
merge, not by a push, not by a comment.**

The operating consequence: to restart a stalled cascade you do not need to
merge anything. You need **one PR to produce one verify-success**. Rebasing any
eligible PR onto the current tip is enough.

### 4.3 The five-action bundle

One successful `verify` run drives `noodles.py github land` followed by
`noodles.py github train`, and together they perform five actions. All five
belong to one ceremony; a merge that skips four of them leaves *bundle debt*.

| # | Action | Mechanism | Failure meaning |
|---|---|---|---|
| 1 | **exact-head merge** | `PUT /pulls/N/merge` with `sha=head_sha`, `merge_method=merge`; merge-commit parent readback; default-branch advance readback | the receipt, the event, the PR head and the tree must all agree — any disagreement refuses before merging |
| 2 | **marker write** | `PATCH` issue body: `state=landed`, `landed_pr`, `head`, `merge` | the durable record of which bytes landed |
| 3 | **issue closure** | `PATCH state=closed, state_reason=completed`, then a closure readback that re-parses the contract | a closed issue whose body does not read `landed` is a failed land |
| 4 | **receipt anchor** | one idempotent N-class comment carrying merge sha, `merged_at`, and the sha256 of the PR body **as merged** | additive and non-fatal by construction (see 4.4) |
| 5 | **train pump** | `noodles.py github train`: mechanical rebase of the next candidate + the predecessor-closure nudge | keeps the queue moving with zero agents |

Action 4 is deliberately inside a `try` that cannot fail the land: by the time
it runs, the merge and closure are already durable provider state, so a failed
comment POST must never report a successful land as failed. It returns
`"failed"` and the anchor is completed later.

### 4.4 Train selection, and the starvation it can cause

`train_select` picks **the oldest open PR that is `awaiting_land`, behind the
default branch, and carries no fail-back marker.**

The failure mode this produces: a PR that rebases cleanly (so it never earns a
fail-back marker) but whose `verify` stays red for a reason a rebase cannot fix
gets re-selected forever and **starves every newer PR**. The mechanical cure
landed as a stateless guard — a head with a *completed* failed trusted `verify`
run at that exact sha is skipped (a success, an in-progress run, or no run at
all never skips). The operator cure, when it happens anyway: **flip the issue's
state from `awaiting_land` to `blocked`.** `awaiting_land` means "mechanically
landable"; a verify-blocked PR is `blocked`, and the train skips it.

The train also nudges **declared dependents** on closure: when a land closes
subject `X`, every open `awaiting_land` PR whose issue declares `depends-on: X`
is rebased once. It is bounded with no state file — a dependent is nudgeable
only while genuinely behind, so replaying the same closure finds
`behind_by == 0` and pushes nothing.

### 4.5 Known failure classes and their cures

| Class | Symptom | Cure |
|---|---|---|
| **lost PR association** | land refuses with `expected one PR on workflow run, got 0`; a double-green PR is stranded | close and reopen the PR to re-associate it with its workflow run, then trigger a fresh verify (rebase to tip). `#386`/`#376` are the mechanical cures, both operator-owned |
| **land race (benign)** | a second land run refuses with `PR must be open, unmerged, and non-draft` or `issue drifted before landing` | **benign** — it means the first run already landed it. Read back the merge and closure; do not retry, do not "fix" anything |
| **anchor absence** | the merge and closure are durable but no anchor comment exists (`receipt_anchor: "failed"`), or a `422` on the marker `PATCH` skipped the anchor step | re-post the anchor from the merged PR's own bytes; it is idempotent. The anchor is N-class, so its absence never invalidates the land — but bundle-completion duty says somebody must finish it |
| **bundle debt from an accelerator merge** | a human or cloud merge completed action 1 and skipped 2–5 | the merger inherits the completion duty: markers + anchor + train pump. `#386` is the reconciler that would do this by machine |
| **merge outran its own red self-tests** | branch protection requires `verify` but not `candidate-self-tests`, so a merge can win the race against its own red tests and redden `main` | `#389` (add it to the required-check set) — operator-owned. Until then: never accelerate a merge whose self-tests have not concluded |
| **starved train head** | one old PR re-selected forever, newer PRs never move | §4.4: flip `awaiting_land` → `blocked` |
| **orphan workflow** | a dispatch pushed a branch, the issue sits `in_progress`, no PR | **do not assume a crash.** No terminal event ≠ death. Wait for the completion notification; intervening competes with a live land agent for the same PRs |

### 4.6 Manual recovery, when a lane genuinely crashed

Only after a terminal signal (notification arrived, result shows error/empty):

```bash
gh api repos/ed3c/noodles/compare/main...<branch>          # confirm ahead >= 1
gh pr create --body "Refs ed3c/noodles#<N>"                 # exact body
# flip the issue state marker to awaiting_land
```

If the PR is behind, reproduce what the train does: a scratch `git init`, fetch,
rebase onto `origin/main` under the train identity
(`-c user.name=noodles-train -c user.email=noodles-train@users.noreply.github.com`),
then `--force-with-lease`. That triggers a fresh verify, which triggers land.
Conflicts abort and are resolved by hand. **The merge itself is always the
App's.**

### 4.7 Merge topology (operator adjudication v2, 2026-09-03)

- The machine route (`land.yml`'s five-action bundle) is the **mandatory** route
  for every class, including `issue-NNN-*`. No PR depends on a cloud action.
- Cloud merges are an **accelerator** or a re-acceptance path, never a route
  dependency.
- Three reins: (1) red cannot merge — `enforce_admins: true`, `verify` required,
  `strict: true`; (2) an automated cloud merge must carry the `merged-via`
  marker (a hand merge is attributable anyway); (3) **an accelerated merge that
  bypasses the land run owes the remaining four actions** — the merger completes
  them, or the machine's bundle-completion reconciler does.
- One unmarked automated merge is the falsifiable trigger for minting a
  dedicated App identity.

---

## 5. The seven fallback atoms, their closure criteria, and the drill

Provider readback 2026-09-03. Reconstruct with:
`gh issue view <N> --repo ed3c/noodles --json state,body`

| Atom | Component | State | What it owns | Closed when (from its own body) |
|---|---|---|---|---|
| `#260` | carrier | `awaiting_land` | typed terminal-state migration | terminal state derives **only** from process exit / `turn.completed` / `turn.failed` / `error` / App Server lifecycle events; the `TRUNCATION_RE` substring input is a named planted negative, red under the old match and green under the fix; zero remaining bare-substring match for that token |
| `#170` | carrier | `blocked` (intake-normalizer: `blocked` needs an explicit blocker owner) | dual-dialect lane-event adapter **and** owner of provider-availability sensing | both dialects (Codex JSONL/App Server, Claude harness events) normalize into one lane-health receipt form feeding four evidence lanes and six health states; **no provider-specific branch leaks past the adapter's output boundary**; availability/quota/error readings are published here, not invented downstream |
| `#406` | docs | `ready` | the Codex/Claude differential canary | `docs/codex-claude-differential-canary.md` carries all six axes **with denominators** (tokens, wall-clock, filter pass rate, findings as confirmed/total, rework distance, correlated miss rate); the discrimination fixture ran **before** the live lanes; no cross-merge between worktrees, asserted by a diff-provenance table; per-lane `SUPERVISION_DIVERSITY` labels; one bounded retry with the failure class named |
| `#407` | scheduler | `ready` | the six-mode fail-soft machine | one fixture per transition class (planted reading → exactly the adjudicated transition with a receipt naming the reading; a clear reading → no transition — **both directions**); `READ_ONLY_DRAIN` refuses an execution verb naming the mode and admits a classification verb; identity substitution under any mode is a validator error with a planted control; a receipt-less transition is a validator error; the `DEFERRED_BUDGET` classification duty is asserted by the closure predicate's consumer fixture |
| `#408` | scheduler | `ready` | the generation-closure predicate | eight terminal classes each with a receipt (removing any one flips the predicate open **naming that issue**); `BLOCKED_EXTERNAL` presented as `RESOLVED` is a validator error; **seven** liveness conjuncts each with its own fixture — no active lanes, no completed-unreconciled lanes, empty train, findings accounted, **sweeper balance zero**, ledgers committed; the predicate performs zero writes, asserted |
| `#409` | verify | `ready` | exit-status in the evidence gate | each demonstration half carries one recognizable status line, with the accepted form stated **in the gate's own refusal message** (planted-absence fixture asserts the message names it); **the same atom migrates the live backlog** and the completeness report is clean at landing (honest recorded values only — an unknown status is marked unknown, never invented) |
| `#410` | scheduler | `ready` | machine-minted wave/generation ids | successive mints unique and monotonic, each with a receipt naming the generation context; a never-minted id presented to a machine-side consumer is a validator error naming the id (a minted id passes the same consumer); validating an id performs zero writes |

Plus one mapping, not a new atom: the `QUARANTINED` terminal class's producer is
`#360` (the operator-owned starvation-flip atom), not a new mechanism. And one
dispatcher-side item with no issue at all: `SupervisionDiversity` becomes a
column in the `gen_ledger` entry schema at the next batch append. (`gen_ledger`
is the slg ledger's producer and lives in `ed3c/skill-concerns`, not here — every
identifier this document cites resolves in this repository except that one and the
judge verdict field in §6.4, and both are named as foreign on purpose.)

### 5.1 The closure ladder for the group

- **Already closed (`PRODUCTION`)**: the admission layer itself — it is pure
  code with no prompt surface, so it is provider-neutral by construction;
  `codex_isolation` sandboxing is `SANDBOX-EXERCISED`; contract auditability and
  the CLI surface probe are closed; the semantic-shadow design is portable by
  construction.
- **`DECLARED` today**: `#260`, `#170`, `#407`, `#408`, `#409`, `#410` — their
  fixtures exist as acceptance text, and acceptance text is a design, not an
  arrival. `#406` is declared and **not yet run**.
- **`EXERCISED`**: reached when those **six** atoms have all landed.
- **`PRODUCTION`**: reached only by passing the drill below.

Order: this wave (scheduler chain serial + verify + isolation lanes) → the
`#406` canary → then, and only then, unfreeze the Codex reader fleet
(`.codex/agents/*.toml`) and the provider-neutral dynamic-workflow upgrade.
Measurement precedes fleet-building, deliberately.

### 5.2 The PRODUCTION drill (the named terminal criterion)

> **Fallback drill** — simulate Claude unavailable → the machine emits a
> `CODEX_ONLY` transition receipt naming the trigger reading → one full
> generation runs pure-Codex through the unchanged control plane, gates, and
> landing authority → the generation-closure predicate (`#408`) judges that
> generation **closed**.

Rules the drill inherits and must not relax:

- The drill hangs off a daemon generation's verification batch as a **coverage
  obligation**. It never precedes the machine's own filing: if there is no
  eligible candidate, record `COVERAGE_ABSENT` with a reason. **Do not
  manufacture an issue to make the drill runnable.**
- Simulating unavailability means simulating the *reading*, not disabling a
  credential and certainly not substituting one.
- `BLOCKED_EXTERNAL` may never satisfy the `RESOLVED` arm. A drill that closes a
  generation by reclassifying its blockers has proved nothing.
- The supervision label for the whole drill is `config-diverse-only`. A drill
  that reports `provider-diverse` is a failed drill regardless of its outcome.
- Six landed = `EXERCISED`. Drill passed = `PRODUCTION`. Neither implies the
  other and neither may be inferred from a report.

### 5.3 What is deliberately *not* built yet

Codex read-only supervision roles (`.codex/agents/*.toml`) and the
provider-neutral dynamic-workflow upgrade are **post-canary on purpose**:
measure before building a fleet. When they do land, one question must be
answered in the same atom — whether `.codex/agents/*.toml` or `.noodle.toml`'s
`[agents.codex]` is the single source of truth for agent configuration. Two
coexisting configuration surfaces is a drift window; one SSOT plus a pointer is
the only admitted shape.

The core sentence to keep: native subagents can reproduce the wave's parallel
*shape*. What cannot be handed to a provider runtime is **durable phase
semantics, zero-injection health policy, cross-model supervision, and landing
authority.**

---

## 6. The open pool at landing time

Snapshot re-read 2026-09-03 19:2x CST, immediately before this branch's final
filter: **49** open issues in `ed3c/noodles` — 38 when this atom's own issue was
filed about four hours earlier — plus 5 in `ed3c/ai-content-notes`. The pool grew
by eleven inside one session, and that growth is the fallback queue, not noise:
filing froze at the end of the session precisely so the queue would stop growing
before anyone had to consume it cold. This is a **snapshot, not a live view.**
Reconstruct at any time with:

```bash
gh issue list --repo ed3c/noodles --state open --limit 200 \
  --json number,title -q '.[] | "\(.number)\t\(.title)"'
gh issue list --repo ed3c/ai-content-notes --state open --limit 50 \
  --json number,title -q '.[] | "\(.number)\t\(.title)"'
./noodles issue completeness      # which of them are actually schedulable, and why not
```

### 6.1 The landing-surface six — the operator's parallel-topology line

**The landing surface has one writer: the operator's parallel-topology line.**
These six are its backlog. A wave lane must never implement one, and must never
touch an `issue-NNN-*` branch or PR.

Read their state markers before assuming anything: at the first snapshot (15:30)
the five that existed then all read `noodles-state: blocked` with a
`noodles-blocker: operator: ...`; at the second (19:2x) five of the six read
`ready` and only `#394` still reads `blocked` (`#423` was filed between the two
snapshots and has been `ready` since it was filed).
**A flip to `ready` here is a hand-off signal to go read the issue body, not an
invitation to take the ticket** — `#389`'s widen half had already landed on `main`
by then (`widen(protection): stage candidate self-tests requirement`, PR #425),
i.e. the operator was working the list live. `#394` is the explicit exception: its
body carries an `## Ownership transfer (operator, 2026-09-03)` section moving the
train half to the dispatcher line, scoped to that one atom, with the five-action
bundle and the App identity unchanged and its landing ordered behind the running
waves — a lander is never swapped under a live queue.

| # | Requirement | What it would cure |
|---|---|---|
| `#360` | `DELIVERY.LANDING_TRAIN.001` | a permanently failing head is never parked by the machine — the starvation clause's flip half needs a mechanical owner (also the `QUARANTINED` producer for `#408`) |
| `#376` | `DELIVERY.LANDING_TRAIN.001` | the land job trusts a lossy payload: empty `pull_requests` strands double-green PRs; resolve by exact head as fallback |
| `#386` | `DELIVERY.LANDING_TRAIN.001` | accelerator merges leave bundle debt and misnamed noise: one reconciler completes the ceremony regardless of who won |
| `#389` | `DELIVERY.LANDING_TRAIN.001` | a merge can outrun its own red self-tests — `candidate-self-tests` is not in the required-check set |
| `#394` | `DELIVERY.LANDING_TRAIN.001` | the strict treadmill taxes a depth-`n` queue `n²` verify runs: wire verified-batch into the train's clear-queue path (ownership transferred; see §7.7) |
| `#423` | `DELIVERY.LANDING_TRAIN.001` | the train's auto-rebase discards the pre-rebase head, so digest-pinned citations rot on the landing surface's own rewrites |

`#393` (declared-capacity feedback gate, `CONCURRENCY.DECLARED_CAPACITY.001`,
state `ready`) is the **read-side** counterpart that is *not* operator-owned:
the scheduler only keeps the queue shallow; the real `n²` cure is `#394` on the
machine side. Their non-claims sections point at each other and do not overlap.

### 6.2 Governance-parked five — `ed3c/ai-content-notes`

Deliberately **zero-write**: no wave lane may edit, enrich, or implement them,
and a judge verifies the zero-write property (via `totalCount` / `lastEditedAt`)
each wave. They await operator adjudication, not engineering.

`#41` (is the Google Doc lane retired? define GitHub-backed persistence) ·
`#42` (authorized corpus and accuracy benchmark need a stated rights basis) ·
`#49` (bilingual documentation and open-source baseline) ·
`#55` (make Docs/Sheets a Git-canonical projection) ·
`#68` (resolve PARTIAL/UNBOUND sources to consumer DAG or no-implementation)

### 6.3 The rest of the `ed3c/noodles` pool, by class

- **This wave's fallback chain** — `#260`, `#170`, `#406`, `#407`, `#408`,
  `#409`, `#410`, plus `#393` and this runbook `#411`. Closure criteria in §5.
- **Legacy blocked / upstream** — `#14`, `#21`, `#22`, `#78`, `#85`, `#183`.
  Each waits on an upstream or on the operator; none is dispatchable.
- **Code-intel / retrieval chain** — `#293` → `#294` → `#295` → `#307`. This is
  the load-bearing capability gap the daemon's generation-verification batch
  needs.
- **Backbone** — `#325`, `#303`, `#309`, `#310` (a macOS admission-control flake
  on the untouched default branch), `#274`, `#267`, `#308`.
- **Unclaimed findings from previous waves' monitors and judges** — `#390`,
  `#391`, `#392`, `#395`, `#396`, `#397`, `#398`, `#399`. The honest backlog:
  filed, fingerprinted, unimplemented.
- **The Python-enforcement ladder** (filed late in the same session, none
  implemented) — `#413` a curated ruff behavioural subset with justified
  suppressions, then `#415` basedpyright (depends on `#413`), then `#419` branch
  coverage as a report-first surface with **no percentage target** (depends on
  `#415`); `#416` CodeQL as an advisory-first dataflow gate; `#418`
  forbidden-import and cycle rules on the existing structural verifier; `#417`
  the ABI contract that keeps the ladder from making Python the architectural
  boundary. `#413` and `#415` are the two named cold-start candidates: they are
  the largest enforcement gap and neither depends on anything unlanded.
- **Admission and worktree hardening** — `#420` (a worktree may not exist before
  its work is admissible), `#421` (an out-of-repo dependency crashes the
  dependency parser instead of naming a reason — a crash *in the reason-producing
  path*, which poisons every issue that depends on the unparseable one), `#422`
  (the capability contract has neither producer nor consumer), `#414` (three
  issues are refused by a completeness gate whose defects only their authors may
  cure).
- **In flight at this snapshot** — `#427` and `#429` read `awaiting_land`; treat
  them as landing, not as available.

### 6.4 Anything unmerged from this wave

This document was authored inside the wave it describes, so it cannot record the
wave's own outcome. The rule is what survives:

> Anything unimplemented at the deadline is recorded **UNMERGED** with
> `RULE-1/3 SCOPE: UNMERGED @ <sha> — reason: <gate + refusal>` plus a
> **NEXT-ACTOR note precise enough for a cold Codex lane to resume from** — the
> branch and sha, the exact gate that refused, its verbatim refusal text, what
> was already proven, and the single next action.

Where to look for the actual list, in order of authority:

1. each atom's own issue state marker (`gh issue view <N>` — `landed` and closed
   means it landed; anything else did not);
2. the wave's judge verdict JSON (`unmerged_handoff_verdict`) — a dispatcher
   artifact, not a file in this repository;
3. the lane reports.

A wave summary that says "landed" while the issue body does not read `landed` is
wrong; the provider is the authority.

---

## 7. Session adjudications index

The reasoning behind the rules above, so a cold reader can tell a law from a
convenience. Each entry names where the full contract lives.

### 7.1 Residency taxonomy (operator-ratified; contract text in `ed3c/skill-concerns#147`)

Canonical law: **unknown semantics get looked at early; known defects get
verified late; urgent risk sinks into a sensor — never make the whole red team
follow an agent's thinking.**

`Resident ≠ always executing.` Each supervisor is a triple of *(attachment
point, what it reads mid-generation, cadence of speech)*, and the three axes are
orthogonal:

| Supervisor | Attachment | Mid-generation read |
|---|---|---|
| Semantic Shadow | session-resident observer | yes, passive |
| Shadow Architect | stage-aware observer | may read material delta, bounded output |
| Red Team | boundary-resident falsifier | **no** |
| Control Noodle | ceremony observer | ceremony boundary |
| SLG judge | grounded supervisory verdict | stage / generation boundary |

The mixed mode is *mid-generation presence, closed-boundary authority*. Its v1
physical form is **logical** residency: a fixed shadow role whose anchor state
initializes at session start and is fed the observable delta at each material
checkpoint — zero daemon, zero event bus, zero persistent store, because an
unproven long-lived process is itself over-design. Authoritative intents are not
overwritten by recency (anchor authority, not recency), and inference may
produce a **candidate obligation, never a requirement**; promotion needs a
source, an owner decision, or runtime evidence.

The red team stays closed-boundary and is **not** changed mid-generation (it
would manufacture half-built false positives, amplify experiment cost, anchor
the worker, and overlap other monitors). The only admitted early path for an
urgent class is the **sensor/falsifier split**: catalogue the class → find its
minimal observable precursor → make a resident mechanical sensor → emit a
bounded signal → dispatcher. When the precursor is fully mechanized, the sensor
becomes a gate and the class exits sampling.

### 7.2 Refactor and mutation contracts

- **`docs/slop-safe-refactor-contract.md`** (N-class, in this repository) — the
  six clauses `R1`–`R6`. A refactor atom's physical acceptance instantiates every
  applicable clause as a runnable control, and declares by name any clause it
  considers inapplicable. Clauses graduate individually when an atom lands one as
  executable acceptance; the file retires when nothing unpromoted remains.
- **`docs/parallel-topology-tail-contract.md`** (N-class) — the three
  serial-era stall classes, each to be adjudicated as *impossible by
  construction* or *owned recovery*, with the planted control **run**, not
  argued.
- **Mutation adjudication (2026-09-03)**: sensitivity is an independent claim,
  never folded into behavioral equivalence — the six clauses prove equivalence,
  mutation proves the oracle's discriminating power. Confidence ladder, strictly
  cumulative with no substitutions: regression green → red-then-green → planted
  negative → differential mutation. Mandatory only on triggers `T1`–`T3`
  (semantically-editing refactor / new oracle or gate / first build of a class
  guard); pure relocation does not trigger. A surviving mutant is dispositioned
  `KILLED` / `EQUIVALENT` / `NON_OBSERVABLE_BY_CONTRACT` / `OUT_OF_SCOPE` (the
  last two with a bounded machine-readable reason). **Never a global mutation
  score as a gate.** `RefactorSafe = Observable equivalence + sensitivity not
  reduced + architecture invariants pass`; differential mutation is a cost
  optimization only and never changes semantics.

### 7.3 Admission mechanization list

The admission layer is provider-neutral by construction: `issue_contract.py` is
pure code with zero prompt surface, so there is no place for a provider branch
to hide. Six mechanizations are landed and were each enforced against this
session's own work:

1. requirement markers must bind an existing `### ID` heading in
   `contracts/system-v1.md`;
2. dependencies are declared by marker only — dependency **prose** is refused;
3. defect fingerprints may only *enrich*, never block a distinct atom;
4. demonstration halves must produce **different** outputs (anti-blind control);
5. `noodles-observer` and `noodles-capability-probe` are validator-judged, both
   markers being machine gates;
6. a class that becomes gated exits sampling (the red team's `R6` lifecycle).

Two gaps are filed and unimplemented: `#409` (exit status in the demonstration —
"narrative can be edited, a status code cannot") and `#410` (machine-minted wave
ids — in fallback mode the only free-text admission input with nobody watching).
One item stays discipline rather than mechanism and is recorded honestly as
such: *unverified architecture writing goes into `/docs` as N-class first* — the
receipt precondition for spec edits is not fully mechanizable today and is held
by the judge and authoring discipline. **If it is violated once more, promote it
to a register or a gate.**

Marker honesty, quoted from the parser's own refusal text, because "none" is
routinely misused:

- `observer: none` is admissible **only** when the issue makes no
  absence-or-failure observation claim;
- `capability-probe: none` is admissible **only** when the acceptance specifies
  no external tool behavior;
- otherwise each marker carries an exact invocation plus its
  `## Observer demonstration` / `## Capability probe` section, and the
  demonstration shows both a GREEN and a RED direction with real, differing
  output.

**Dedupe before filing.** The mechanical fingerprint is a digest over the exact
set of snake_case tokens the rationale section quotes in backticks; identity is
*set equality*, deliberately, because two atoms sharing one token are routinely
unrelated and a false block has no honest exit. Its stated ceiling: it catches
the twin filing and does **not** catch partial overlap, which stays a monitor or
judge finding. A rationale that quotes no mechanical token has no fingerprint at
all — the check still runs, and its honest result is "no elder", which is a
different thing from "checked and clean". Pair it with a title scan of the open
pool.

### 7.4 Density, throttling, and the shape of scheduling

Measured 2026-09-03 during a three-wave overlap: swap 2.4 GB of 4 GB, six or
more concurrent unittest runs, each spawning daemon and listener children. The
diagnosis was the clone/test storm from parallel heavy waves; file-system
indexing daemons were amplifiers, not the cause.

Standing rules that came out of it:

- **A heavy-suite repository wave never runs beside another heavy wave.** At
  most one heavy plus one light concurrently.
- Four standing adjustable knobs, none of which touch a claim point: (1) a
  scratchpad mirror plus `git clone --reference`; (2) the filter ladder — full
  triple only at pre-push and after every rebase, targeted subsets in between;
  (3) implement width 5 → 3 when waves share the machine; (4) a `flock` mutex
  over full suites. Knob 4 has a reverse dividend: serializing suites *reduces*
  load-induced false reds, so signal quality goes up.
- The invariant across all four: **the claim points and gate predicates do not
  move by one byte; only execution density and object transport change.**
- Scheduling shape is **feedback with a WIP cap** (kanban/TCP-like), not dynamic
  programming: two signals (swap headroom, landing queue depth), three valves
  (lane admission, flock permits, wave co-running), one ordering key
  (topological depth — deep chain tails dispatch late). Rationale: landing is
  serial and `strict`, so clearing a queue of depth `n` costs about `O(n²)`
  verify runs, and implement width beyond "queue depth 1–2" has negative
  marginal value. Lane cost is near-constant, so measurement beats prediction and
  a model's maintenance cost buys no better decision. `#393` carries the read
  side; `#394` carries the real cure.

### 7.5 Evidence and receipt discipline

- **Arrival vocabulary**: `DECLARED` / `EXERCISED` / `PRODUCTION`. They do not
  imply one another. A load-bearing invariant whose misjudgment is costly needs
  at least two *independent* arrivals — independent meaning one bug cannot fool
  both.
- **Digest preimage is the provider's raw bytes.** Publish comments with
  `--body-file`: POSIX `$(...)` strips trailing newlines, and a digest taken over
  a shell-captured body measures what was *sent*, not what is *stored*. A byte
  claim must name which side of the wire it describes. Record a pre-land and a
  post-land digest row for every landed issue.
- **Second-arrival probing uses GraphQL `userContentEdits`** — the REST
  `issues/N/events` endpoint is blind to body edits (measured: 0 vs 2–5). A
  second-arrival cell carries its access path, and the known ceiling is cited by
  reference rather than re-derived each time.
- **Concurrent-edit discipline**: never edit an issue body inside the window
  after its land has begun — a concurrent body edit can erase landing markers.
  Measured counter-evidence worth keeping: the **anchor comment survived** the
  same concurrent edit that wiped body markers, which is the first direct
  evidence that the comment surface is more durable than the body-marker surface.
- **`FIXED` means the named defect's bytes changed.** Anything else is
  `ANSWERED` (with a runnable receipt) or `DEFERRED` (with an open-issue
  destination whose `state=open` was read back). A disposition table that dies
  with its report is not a filing.
- **Three curves, each with a denominator**: known-class recurrence /
  qualifying changes; judge gaps / waves judged; fingerprint blocks / admission
  candidates — reported with the issue-class mix. Three waves without a decline
  is `INSTRUMENT_SUSPECTED` → a bounded diagnosis under two hypotheses (the
  instrument is broken, or the workload distribution moved), **not** an immediate
  verdict of instrument failure. Do not count bare issue volume: a healthy
  machine keeps filing real defects.
- **Cross-repository work is a coverage obligation**, not a quota: if there is no
  qualifying candidate, record `COVERAGE_ABSENT` with a reason. A cross-repo atom
  carries eight items (both SHAs, contract, compatible oracle, independent
  worktree, rollback boundary, landing order, post-landing verification).
- **The judge reads an evidence manifest** — structured references with raw
  material stored as artifacts and retrieved by reference — not a hundred-thousand
  word concatenated prompt. Better caching, stability, replay, provenance, and
  truncation diagnosis, and it applies to a Claude judge exactly as much as a
  Codex one.

### 7.6 Shared-tree rules

Never switch branches in a shared working tree — another session's `HEAD` and
files drift and commits land on the wrong branch. On a shared tree the git index
is **public state**: a hook-rejected commit does **not** roll back `git add`, so
the staged files get swept into the next session's commit with the wrong
message. Bind staging and committing into one command; on rejection the first
action is to unstage, not to retry the gate. Unstaging protects only that one
occurrence, which is why the binding matters more than the reflex.

### 7.7 Late-session adjudications (after this document's first draft)

The dispatcher ledger these sections distil kept moving for hours after §1–§6
were written. What follows is from that tail and has no other survivor.

- **Write-boundary collisions bind landing, not implementation.** The first form
  of the rule — "atoms with overlapping boundaries are not dispatched together" —
  was over-broad, because worktrees already dissolve the implementation-layer
  collision. What actually collides is the shared `main`, the serial train, and
  the handful of files every atom is *forced* to touch. So overlapping atoms
  implement in parallel and **queue serially at landing**: the later one waits for
  the earlier one to land. Carrier: `#393`'s landing co-queueing gate, with
  two-way fixtures (a named overlap delays the second atom's entry; a non-overlap
  co-queues freely).
- **Producer-regenerated shared files are exempt from that rule.** The definition
  roster (`policy/definition-dispositions.json`) and the AGENTS.md disclosure row
  are measurement-derived: a conflict in them is resolved by taking either shape
  and re-running the measurement, never by hand-merging. Corollary, learned by
  walking into it: adding or removing a top-level definition in `noodles.py`
  mechanically forces **both** files, and both fall outside almost every declared
  write boundary (`#390`). Widen the boundary before you start, or the gate
  refuses at push time with a wall of red that is one missing row.
- **The train auto-rebases behind your back.** Every push to `main` makes
  `land.yml` rebase the most-behind mergeable candidate on its own. This is in no
  design document; it was found when a sweeper's two manual rebases were beaten to
  it. Two consequences. Never race it: re-read `headRefOid` immediately before
  pushing and **abandon rather than race**. And know that the rebase **discards
  the pre-rebase head**, so digest-pinned citations to a candidate's old head stop
  resolving — the landing automation is the one systematic violator of the
  digest-binding discipline. That is `#423` (bounded-namespace salvage refs with a
  retention window); until it lands, the lane-side rule is to push a salvage ref
  before any force-push.
- **Waves serialise at their tails, not at their heads.** Wave N+1 implements
  while wave N lands, and its ship stage polls until wave N's pull requests are
  drained before opening any of its own. With `#394`'s two halves — a
  dispatcher-side pre-stacked batch manifest (SANDBOX arrival) and the train's
  verified-batch clear-queue path (PROD arrival) — total landing wall-clock scales
  with the number of *waves*, not the number of heads. That is the whole point:
  it makes running more waves affordable on the landing surface. The two halves do
  not block each other; the dispatcher half alone already removes the stall term.
- **Records are persisted before any ship rebase.** A red-team or wave record
  built from diff heads is destroyed by the rebase that lands the wave, and the
  producer-only ledger then correctly refuses a hand-rebuilt substitute. That
  sequence recurred three times before it earned a phase of its own: persist
  through the producer between monitor completion and ship rebase, and anything
  that cannot be is recorded `UNPERSISTABLE` out loud.
- **Filing froze at the end of the session.** No new tickets for speculative work;
  only a newly *measured* defect earns one. The pool went from about 29 to 49 in
  a day — the dispatcher's own count, then §6's measurement —
  and a queue that grows faster than it drains is the failure mode a cold consumer
  inherits.

### 7.8 Landing strategy and salvage (pointer)

- **`docs/landing-strategy-and-salvage.md`** (N-class, `ed3c/noodles#438`) —
  three session-adjudicated bodies of landing knowledge that had no repository
  home: the three-beat async landing strategy (displacement-conservation law,
  accelerator-hold classes), the storm-salvage protocol (verified live during
  the 2026-09-03 provider incident), and model-tier degradation practice
  (distinct from and finer than `#407`'s provider-level fail-soft modes).

---

## 8. Ceiling of this document

- It is N-class. It gates nothing, admits nothing, and blocks no candidate. If
  it ever appears in an evidence or receipt allowlist, that is a defect in the
  allowlist.
- §6's pool map is a timestamped snapshot and goes stale by design; §6 carries
  its own reconstruction commands.
- §1's verbatim block is protected against post-landing edits by a recomputable
  digest, and against nothing else. It cannot prove the copy matched its SSOT at
  copy time; the SSOT file digest recorded in §1 is what a future reader compares
  against if that file still exists.
- §5's per-atom rows are *distillations* of acceptance owned by issue bodies. On
  any disagreement the issue body wins, and the row is the thing that is wrong.
- Nothing here asserts the fallback works. §5.2 defines the drill that would
  demonstrate it; the drill had not been run when this file landed.
