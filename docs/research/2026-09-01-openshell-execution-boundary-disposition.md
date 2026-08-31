# OpenShell 作為 cook 執行邊界：接縫評估與處置

日期：2026-09-01（Asia/Taipei）
主題 Issue：`ed3c/noodles#175`
評估基準：`ed3c/noodles@9a94ec44080e6018644090d9fc2e3cb0121226d1`、pinned `poteto/noodle@eaa1d5cce36f73e33e81d4855bb2fc47e33d0b24`（release `v0.1.5`）、`github.com/superfly/sprites-go@951bb2e6b07d`、`openshell 0.0.59`。
量測宿主：darwin/arm64，Docker server `29.4.0 OrbStack`，OpenShell gateway `openshell` = `https://127.0.0.1:8080`（`openshell status` → `Connected`，量測前後皆為既有常駐服務，本次沒有啟動或重啟任何 daemon）。
資料邊界：pinned runtime 的 release asset 與原始碼（雜湊比對）、sprites SDK 原始碼、本機 OpenShell gateway 真跑。本文沒有啟動 Noodle、沒有寫入 `.noodle` orders 晉升接縫、沒有改動任何 `.noodle.toml` 設定。

## 處置：HOLD

OpenShell 的沙盒**確實提供 `codex_isolation` 目前拿不到的物理能力**（下方 §2 有紅→綠受控實驗），但 `#175` 所列的三條接縫在目前 pin 上**沒有任何一條能以「最多一個 adapter」達成**（§1）。因此本原子的產出是處置本身，不是整合。

依 `AGENTS.md` 的 migration disposition 詞彙，這是 **HOLD**，不是 `DROP`：能力面通過，接縫面未通過，且解封條件是可證偽的（§4）。

`#175` 的 Physical acceptance 第一條就是「Evaluation first：先以 receipts 記錄接縫結論，再讓任何程式碼落地」。接縫結論為否，因此後續的雙 cook PoC、`writable_roots` 撤除、skill economics 量測**依該條的順序被正確地未執行**，而不是被跳過；每一項未量測都在 §3 具名列出。

## 1. 接縫評估（`#175` 指定的優先順序）

### 接縫 (1)：在 poteto/noodle 上游實作 `runtime.Runtime` — 不可用（需 fork + 自建 + 換保管模型）

`runtime.Runtime` 介面本身存在且乾淨（`runtime/runtime.go:48-53`：`Dispatch`／`Terminate`／`ForceKill`／`Recover`）。但**它沒有註冊接縫**：runtime 對照表是在 `loop/defaults.go` 內硬寫死的兩個字面鍵。

```
loop/defaults.go:47   runtimes := map[string]loopruntime.Runtime{
loop/defaults.go:48       "process": loopruntime.NewProcessRuntime(...),
loop/defaults.go:51   if runtimeEnabled(cfg.AvailableRuntimes(), "sprites") {
loop/defaults.go:68           runtimes["sprites"] = r
config/types_defaults.go:218  func (c Config) AvailableRuntimes() []string   // 回傳 process[, sprites][, cursor]，同樣硬編
```

沒有 plugin 註冊、沒有 `RegisterRuntime`、沒有 out-of-tree 載入路徑。新增 `"openshell"` 一定要改 `loop/defaults.go` 與 `config`，也就是 fork 上游。

更貴的是保管模型會被換掉。`policy/runtime.lock.json` 現在鎖的是**上游發佈的預建二進位**，且兩層雜湊都對得上：

```
asset  sha256 d83f367b0afd933a6322b7fcf01888ff098f4df3c2c6ac058355cb652c078765  （= lock.asset_sha256）
binary sha256 56dfc5bbc05a45c41783715d01c24edab79a8e94f0ba777066325b9302a3f375  （= lock.binary_sha256）
```

採接縫 (1) 等於把「驗證上游發佈物的位元組」換成「驗證我們自建的位元組」。這不是一個 adapter，是換掉整條 runtime 供應鏈的信任根。

### 接縫 (2)：本地 shim 講既有 sprites exec HTTP API — 物理上關閉（設定旋鈕存在，生產端不讀）

這條接縫**在設定面看起來是開的**：`SpritesConfig` 有 `base_url` 欄位，型別與 toml tag 都在，pinned 二進位裡也找得到 `toml:"base_url"` 字串。

```
config/types_defaults.go:88-93   type SpritesConfig struct { TokenEnv; BaseURL `toml:"base_url"`; SpriteName; GitTokenEnv; MaxConcurrent }
```

但**沒有任何生產碼讀它**。整個 pinned 樹裡 `BaseURL` 只出現在兩處結構宣告（`SpritesConfig`、`CursorConfig`），零消費端：

```
$ grep -rn "BaseURL" noodle-src | grep -v _test
config/types_defaults.go:90:	BaseURL       string `toml:"base_url"`
config/types_defaults.go:98:	BaseURL       string `toml:"base_url"`
```

實際建立 client 的那一行完全忽略設定：

```
dispatcher/sprites_dispatcher.go:56:	client := sprites.New(config.Token)
```

而 SDK 的預設是寫死的常數，`WithBaseURL` 這個 option 存在但 noodle 從不傳：

```
sprites-go/client.go:42:		baseURL: "https://api.sprites.dev",
sprites-go/client.go:78:	func WithBaseURL(url string) Option
sprites-go/client.go:165:	url := fmt.Sprintf("%s/v1/sprites/%s/exec", c.baseURL, spriteName)
```

SDK 也沒有任何 base-URL 環境變數（`grep -rn "os.Getenv" sprites-go` 只有 `SPRITES_SDK_DEBUG` 與 examples 的 `SPRITE_TOKEN`／`SPRITE_NAME`）。

二進位層獨立覆核：`strings -a noodle | grep -c "api.sprites.dev"` = **1**，且沒有第二個 sprites 主機字串。

結論（範圍限定）：**在設定面／字串表這一層**，pinned 二進位的 sprites runtime 只宣告 `https://api.sprites.dev`，沒有第二個可設定的目的地。要把它指向本地 OpenShell shim，設定面看到的手段是 DNS 劫持 + 讓 Go 二進位信任自簽憑證 + 還要先設非空 `SPRITES_TOKEN` 才會註冊該 runtime——那是三個外部改動，不是一個 adapter。

這個結論**沒有**檢查撥號路徑：`sprites-go/client.go:42-56` 的 `http.Client` 沒有設 `Transport`，因此走 `http.DefaultTransport`，其 `Proxy: http.ProxyFromEnvironment` 預設就會遵守 `HTTPS_PROXY`。更關鍵的是，本文 §2.4／§2.6a 自己已經證明 OpenShell gateway 對沙盒內任意 HTTPS 目的地做的正是同一種攔截（TLS 終結 + L7 規則），且沙盒內的系統信任庫已經預裝該 gateway 的 CA（§2.6a）。如果 noodle 二進位本身在沙盒內執行，它撥往 `api.sprites.dev` 的連線是否會被同一個攔截機制接住——完全不需要碰 Go 原始碼、不需要額外的 DNS 劫持步驟——這件事本文沒有測。見 §3 non-claim 10。

這一條同時是一個一般教訓：**`base_url` 是一個宣告了卻沒有發射者的狀態**。只看設定 schema 會判「接縫是開的」，只有問「哪一行生產碼讀它」才會看到塌陷。

### 接縫 (3)：只包 carrier 命令 — 物理上關閉（沒有 bind mount，且沒有回寫路徑）

現況的 carrier 包裝（`.agents/bin/codex` + `.noodle.toml [agents.codex]`）之所以能成立，是因為 codex 與 daemon 共用同一個宿主檔案系統：Noodle 建立宿主 worktree，把路徑交給 process dispatcher，cook 就地寫，daemon 事後在本地 merge 那個 worktree。

OpenShell 沙盒**看不到宿主檔案系統**，而且 CLI 沒有提供 bind mount：

```
$ openshell sandbox create --help   # 全部 flag 中沒有任何 mount/volume/bind 選項
UPLOAD FLAGS:
      --upload <LOCAL_PATH[:SANDBOX_PATH]>   # 複製進去，不是掛載
（取回只有 openshell sandbox download）
```

沙盒內實測：

```
$ openshell sandbox exec -n n175-a -- sh -c 'ls /Users; ls -d /private/tmp/claude-501; pwd'
ls: cannot access '/Users': No such file or directory
ls: cannot access '/private/tmp/claude-501': No such file or directory
/sandbox
$ openshell sandbox exec -n n175-a -- sh -c 'id; uname -a'
uid=998(sandbox) gid=998(sandbox) groups=998(sandbox)
Linux ... aarch64 GNU/Linux   /   PRETTY_NAME="Ubuntu 24.04.3 LTS"
```

所以「只包 carrier」會讓 cook 在容器內對著一份**不存在於宿主的**工作樹寫，Noodle 事後在宿主 merge 的還是那個空的 worktree。要補上就得複製進去、跑完再複製回來、還要接上 session lifecycle——那是一整個 dispatcher，不是包一個命令。

sprites runtime 之所以能繞過這點，是因為它根本不用宿主 worktree：它在遠端 clone 再靠 git remote 同步（`dispatcher/sprites_dispatcher.go:183-205 prepareRemoteRepo` / `:311 cloneOnSprite`）。任何 OpenShell 方案要能用，必須複製這個模式，而複製它就回到接縫 (1)。

### 接縫評估總結

| 接縫 | 判定 | 決定性 receipt |
|---|---|---|
| (1) 上游 `runtime.Runtime` 實作 | 需 fork＋自建，換掉二進位保管模型 | `loop/defaults.go:47-68` 硬編 map；`runtime.lock.json` 只鎖上游 asset/binary sha256 |
| (2) 本地 shim 講 sprites exec HTTP API | 設定面物理關閉（撥號路徑未測，見非量測 10） | `BaseURL` 零消費端；`sprites.New(config.Token)`；二進位內 `api.sprites.dev` 出現 1 次 |
| (3) 只包 carrier 命令 | 物理關閉 | 無 bind mount flag；沙盒內 `/Users` 不存在；宿主 worktree 無回寫路徑 |

沒有一條符合 `#175` 自己下的門檻「最多一個 adapter，不得有 interface／factory／registry」。

## 2. 沙盒實際提供什麼（本機真跑，含反向控制）

以下每一條都是同一台宿主上的受控實驗：紅、綠只差一個變因，且每個「拒絕」都確認過發射者。

### 2.1 檔案面：預設可寫集就是宣告的那一個

```
/sandbox 寫入 rc=0      /tmp 寫入 rc=0
/etc     rc=2  sh: cannot create /etc/w.txt: Permission denied
/usr     rc=2  sh: cannot create /usr/w.txt: Permission denied
```

effective policy 的 `filesystem_policy` 與觀察到的行為一致：`read_write: [/sandbox, /tmp, /dev/null]`，其餘 `read_only`。

### 2.2 跨沙盒：植入的寫入不會外溢（附正向控制）

```
w1: echo W1-WROTE-THIS > /sandbox/CROSS ; > /tmp/CROSS   → 兩個檔案都真的建立（-rw-r--r-- 14 bytes）
w1 readback                                              → W1-WROTE-THIS（正向控制：寫入確實發生）
w2: cat /sandbox/CROSS ; cat /tmp/CROSS                  → No such file or directory（兩者皆是）
w1: > /usr/CROSS rc=2 ; > /etc/CROSS rc=2 ; > /app/CROSS rc=2
```

正向控制是必要的：沒有它，「sibling 讀不到」也可能只是因為寫入根本沒成功。

### 2.3 egress：預設拒絕，且以「二進位身分」為單位

```
curl → example.com        : CONNECT tunnel failed, response 403   (curl rc=56)
curl → api.github.com     : CONNECT tunnel failed, response 403   (curl rc=56)
getent hosts example.com  : rc=2                                   (DNS 也擋)
```

`api.github.com` 在預設 policy 裡是存在的，但只綁在 `github_rest_api`（binaries `/usr/local/bin/claude`、`/usr/bin/gh`）與 `copilot` 之下，因此 `curl` 仍被拒。這與 codex `network.enabled=true` 的全有全無不同——**主體是 (binary, host, port)**。

### 2.4 L7：方法與路徑真的會擋，而且會具名指出缺哪一條規則

這是最重要的一條，因為它直接對應 `#132/#134/#170/#172` 想擋的東西——cook physically 碰得到 `refs/heads/main`。

沙盒 `n175-d` 以 create-time policy 起，只允許 git 的**取回**動詞：

```yaml
network_policies:
  cook_git:
    binaries: [{path: /usr/bin/git}, {path: /usr/bin/curl}]
    endpoints:
      - host: github.com, port: 443, protocol: rest, enforcement: enforce, tls: terminate
        rules:
          - allow: {method: GET,  path: "/**/info/refs*"}
          - allow: {method: POST, path: "/**/git-upload-pack"}
```

同沙盒、同二進位、同主機，只變動 method/path：

```
GET  /ed3c/noodles.git/info/refs?service=git-upload-pack   → http=200      （綠）
POST /ed3c/noodles.git/git-upload-pack                     → http=200      （綠）
POST /ed3c/noodles.git/git-receive-pack                    → HTTP/1.1 403  （紅）
     X-OpenShell-Policy: cook_git
     {"binary":"/usr/bin/curl","detail":"POST /ed3c/noodles.git/git-receive-pack not permitted by policy",
      "error":"policy_denied","host":"github.com","layer":"l7","method":"POST",
      "rule_missing":{"binary":"/usr/bin/curl","host":"github.com","layer":"l7","method":"POST",
                      "path":"/ed3c/noodles.git/git-receive-pack","port":443,"type":"rest_allow"}}
DELETE /ed3c/noodles.git/git-upload-pack （已允許的路徑、未允許的動詞）→ 403（紅）
```

拒絕的發射者是被指名的：`X-OpenShell-Policy` header + `layer: l7` + `policy_denied`。這不是推論出來的。

**同一件事我第一次沒問對，記在這裡當反例**：先用 `git push` 測，得到 `fatal: could not read Username`——那是 git 自己的憑證提示，push 根本沒送出 receive-pack 請求；補上假憑證後看到的是 `HTTP/1.1 401 Unauthorized`，那是 GitHub 的回應，不是 policy。兩次都不能拿來宣稱「policy 擋住了 push」。只有把二進位換成可控的 `curl` 直接打那個路徑，才拿到上面這張 receipt。

### 2.5 憑證：placeholder 注入是真的（附可以變紅的反向控制）

註冊一個只含 canary 值的 provider，掛上沙盒後在沙盒內找那個字面值：

```
provider n175-fake  type github  credential GITHUB_TOKEN=<24 字元 canary>
sandbox env | grep -c <canary>                              → 0
printenv GITHUB_TOKEN                                        → 55 字元，prefix "openshell:resolve:"
grep -rIl <canary> /sandbox /tmp /etc /home /root /var       → 無命中
正向控制：printf <canary> > /tmp/canary.txt 後同一條 grep    → /tmp/canary.txt（掃描器確實找得到）
```

兩個沙盒各掛不同 provider，**拿到的 placeholder 參照**互不相同也互不可見：

```
w1 placeholder sha256[:12] 56421f381395  len 55
w2 placeholder sha256[:12] 9245489b4a81  len 56
placeholders_differ: True     w2_can_see_w1_canary: False
```

沙盒手上只有一個 `openshell:resolve:` 參照，真值由 gateway 在出口解析。**這證到的是「兩個參照字面不同」，不是「兩個參照解析出的真實憑證不同」**——後者才是 `#175` 要的 distinct token identity by per-bucket readback；gateway 理論上可能把兩個不同參照解回同一把金鑰。這道差距沒有補上，見 §3 non-claim 6。

### 2.6 兩個必須寫下來的代價

**(a) gateway 看得到全部明文。** 沙盒內看到的憑證簽發者是 OpenShell 自己：

```
== Info: found 148 certificates in /etc/openshell-tls/ca-bundle.pem
== Info:   issuer: CN=OpenShell Sandbox CA,O=OpenShell
```

L7 規則能生效的前提就是 TLS 被終結。placeholder 注入把秘密移出沙盒，但同時把 gateway 變成新的單一保管點。

**(b) 增量 policy 指令是「放寬」語意，宣告的窄授權不等於生效的授權。** 我下的是一條看起來很窄的指令：

```
openshell policy update n175-a --add-endpoint 'api.github.com:443:read-only:rest:enforce' \
                               --binary /usr/bin/curl --rule-name n175_curl_github
```

實際落點不是新規則，而是**併進既有的 `copilot` 群組**——`/usr/bin/curl` 因此同時獲得該群組的 `github.com:443` 與六個 `*.githubcopilot.com` 的 **read-write** endpoint：

```
policy v5 → network_policies.copilot.binaries = [/usr/bin/copilot, .../@github/**/copilot, /usr/bin/curl]
```

同一類：`--add-allow 'api.github.com:443:GET:/repos/**'` 沒有收窄任何東西，因為 `read-only` preset 早已展開成 `GET **`／`HEAD **`／`OPTIONS **`，而 `--add-allow` 只會再加一條。實測 `GET /zen` 在「只允許 `/repos/**`」的狀態下仍然 200。

安全用法是 create-time 的整檔宣告：`sandbox create --policy <file>`。沙盒 `n175-c` 這樣起之後，effective network groups 剛好只有 `['cook_git']`，其餘十個預設群組全部不存在。

而且**收窄只能在建立時做**——對已存在的沙盒下整檔 policy 會被拒絕：

```
status: InvalidArgument, message: "filesystem read_only path '/dev/urandom' cannot be removed on a live sandbox"
```

`openshell policy prove --policy cook-policy-d.yaml --credentials creds.yaml --compact` 對這份 cook policy 回 `PASS no findings`（rc=0）；但本次沒有做植入缺陷的反向對照，所以 prove 的檢出能力在本文不算已驗證（見 §3）。

### 2.7 成本量測（單次實現，不是通則）

```
sandbox 建立：4.12s（首次）/ 1.55s / 1.28s（映像已在本機）
沙盒內 git clone --depth 50 ed3c/noodles：1s
沙盒基底映像已含：Python 3.14.3、git 2.43.0、/usr/bin/gh、/usr/bin/codex；nproc=10、8004 MB
```

同一個 commit 的測試面：

| 執行面 | 結果 | 秒數 |
|---|---|---:|
| 沙盒 n175-d（linux/aarch64） | `Ran 572 tests` — FAILED (failures=8, errors=7) | 84 |
| 宿主 worktree（darwin/arm64） | `Ran 572 tests` — OK | 313 |

沙盒側 15 個失敗**全部是同一個原因**：`required noodle runtime command not found: noodle`（`runtime_contract.py:502`）。這不是偶發，是本 repo 的鎖檔決定的——`policy/runtime.lock.json` 的 `platforms` 只有 `darwin_arm64`，Linux 沙盒拿不到任何通過雜湊驗證的 noodle 二進位。

**這本身是一個獨立 finding，不只是成本量測的附註**：同一棵樹裡 `./noodles verify --json` 在沙盒內正常通過（rc=0），因為 `verify` 的路徑不呼叫 `resolve_locked_runtime_binary`；它對「這個平台能不能拿到已鎖定的 noodle 二進位」是**盲的**。也就是說，`verify` 綠燈目前不能被讀成「這個環境可以跑 cook」——它只覆蓋了 runtime 鎖檔以外的檢查面。任何未來想用 `verify` 通過與否當 Linux 沙盒可用性判準的人都會被這個盲點誤導。

秒數差不可解讀為「沙盒比較快」：兩邊 CPU 配額、Python 版本（3.14.3 vs 宿主）與磁碟後端都不同，這是單次、單一配置的觀察。

## 3. 明確未量測（non-claims）

以下每一項都**沒有**證據，不得由本文的任何段落推導：

1. **雙 cook 並行 PoC 未執行。** 沒有兩個 cook 在兩個沙盒裡對 disjoint ready atoms 各自 land。接縫評估為否，依 `#175` 的順序不進入這一步。
2. **`writable_roots` 撤除未驗證。** 沒有任何 `.noodle.toml` 被改動；「cook 在沒有 `.git` 寫入授權下仍能完成 commit/push」這件事本文沒有量測。
3. **pstack／skill 載入經濟學未量測。** 沒有沙盒內的 pstack 載入時間，因此與已量測的 8.5–26.6% `skill_loading` 佔比**沒有**可比數字，`#174` 不能引用本文得到任何比較。
4. **`git-receive-pack` 的 policy 拒絕是用 `curl` 打出來的**，不是用 `/usr/bin/git` 走完整 push 交握打出來的。規則形狀相同，但「真實 push 在拿到有效憑證後會在同一條規則上被擋」屬於推論，未觀察。
5. **`policy prove` 的檢出能力未驗證。** 只看到它對一份乾淨 policy 回 PASS；沒有植入一個缺陷確認它會變紅。一個從沒拒絕過東西的檢查器不算已驗證。
6. **placeholder 的出口替換未驗證。** 證到的是「真值不在沙盒內」；沒有證到「gateway 在出口把參照換成真值後請求成功」——那需要一個真憑證。
7. **長時穩定性、checkpoint／restore、崩潰後 session 復原、資源上限行為全未測。** 每個沙盒生命週期都是分鐘級。
8. **本次只在一台宿主、一種 driver（OrbStack 上的 Docker）、`openshell 0.0.59` 的單一組合上量測。** 換 driver（VM／Kubernetes）、換 gateway 部署形態的行為不在本文範圍。
9. **`--approval-mode` 的 agent-authored policy proposal 流程未測。**
10. **sprites SDK 的撥號路徑（`HTTPS_PROXY` + `ProxyFromEnvironment` + gateway 既有的 TLS 終結能力組合起來能不能攔到 `api.sprites.dev`）未測。** §1 接縫 (2) 的「物理關閉」只驗證了設定面（`BaseURL` 零消費端、二進位內字串出現次數），沒有驗證撥號層；本文 §2.4／§2.6a 已經證明 gateway 對任意 HTTPS 目的地做同一種攔截，這條路徑是否真能繞過「新增 adapter」門檻，需要一次真跑才能判，本文沒有做。

## 4. 解封條件（可證偽，按成本排序）

HOLD 由下列條件解除；每一條都是一次可執行的實驗，不是一段論述。

1. **`runtime.lock.json` 能鎖到一個 `linux_arm64` 的 noodle 二進位。** 這是最便宜也最硬的一道：在它成立之前，沙盒內連本 repo 的 runtime contract 都過不了（§2.7 的 15 個失敗）。上游若沒發 Linux asset，這條就必須先變成獨立的上游原子。
2. **上游出現一個不用 fork 的 runtime 註冊接縫**，或 `SpritesConfig.BaseURL` 真的接上 `sprites.New(..., WithBaseURL(...))` 而有生產碼消費。判準是 `grep -rn "BaseURL" | grep -v _test` 出現**消費端**，不只是宣告。
3. **`policy prove` 通過一次植入缺陷測試**：把 cook policy 放寬一條（例如把 `git-receive-pack` 加進 allow），prove 必須變紅並具名該條。它不變紅，就不能拿它當閘。
4. **用真憑證觀察到 `/usr/bin/git` 的完整 push 在 `git-receive-pack` 上拿到 `policy_denied`**，補上 §3.4 的那一層。
5. **一個沙盒內的 cook 能完成 commit → push → PR 的實際路徑**，且過程中 `filesystem_policy` 不含任何宿主 `.git` 授權。

只要 (1) 不成立，(2)–(5) 都不必花。

## 5. 與現有機制的對照（右欄只列本次真的量到的維度）

左欄「現況」取自既有 `.noodle.toml`／`codex_isolation` 原始碼與既有測試套件（`tests/run.sh` 內既有的 `codex_surface_canary` 測試這次隨套件跑過一次，但左欄其餘各格是讀碼／讀設定得到，不是本次為了這張表另外量測）；只有右欄「OpenShell 沙盒」是本次在真宿主上量到的。

| 維度 | `codex_isolation` + worktree lane（現況） | OpenShell 沙盒（本次量測） |
|---|---|---|
| 寫入面主體 | 宿主路徑前綴（`workspace_roots` = `/Users/neon/noodles/.git`，`.agents/skills` 可寫） | 容器內路徑集合（`read_write: /sandbox, /tmp, /dev/null`），宿主檔案系統完全不可見 |
| 跨 cook 隔離 | 同一宿主樹上的不同 worktree，共用 `.git` 與宿主 FS | 不同 mount namespace，sibling 寫入互不可見（§2.2） |
| egress 主體 | `network.enabled=true`（全有全無） | (binary, host, port) + L7 (method, path)，預設拒絕（§2.3、§2.4） |
| 拒絕是否可歸因 | 無 | 有：`X-OpenShell-Policy` header + `rule_missing`（§2.4） |
| 憑證位置 | 宿主環境／`gh` 憑證存放 | 沙盒內只有 `openshell:resolve:` 參照，每沙盒不同（§2.5） |
| 設定的驗證面 | `codex_isolation.validate_codex_agent_config` 逐字比對 args tuple，`codex_surface_canary` 真跑 | `policy get` 讀回 effective policy；但增量指令是放寬語意（§2.6b） |
| 與本 repo runtime contract 相容 | 相容（darwin_arm64 已鎖） | 不相容：Linux 無鎖定二進位（§2.7） |

現況機制在**與本 repo 契約相容**這一格是唯一過關的，OpenShell 在**邊界強度**那幾格明顯較強。這正是 HOLD 而非 DROP 的理由：贏面是真的，只是還接不上。

## 6. 本文的權威層級

本文是 N-class 描述與研究輸出。它沒有新增任何 L gate、沒有改動任何 runtime／policy 設定、沒有宣稱上述任一能力已經在 `noodles` 的執行路徑上生效。所有沙盒與 provider 在量測後都已刪除，gateway 讀回 `No sandboxes found.` 且 provider 清單回到量測前的兩筆（`claude-code`、`codex-runtime-env`）。§2.6b 已記錄「增量 policy 指令會併進既有群組」這個風險，因此這裡額外核過內容、不只核過名字：兩筆 provider 的 `openshell provider get` 讀回 `Resource version: 1`（型別／憑證鍵數與量測前一致：`claude-code`=1 把 credential key、`codex-runtime-env`=4 把），OpenShell 的 resource version 是平台自己的樂觀併發計數器，量測期間若曾被寫入會遞增；停在 1 代表這兩筆自建立以來未被本次任何 probe 動過。
