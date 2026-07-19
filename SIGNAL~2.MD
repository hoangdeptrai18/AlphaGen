# WorldQuant BRAIN — Thư Viện Thành Phần Tín Hiệu

## Cách dùng tài liệu này

Đây **KHÔNG** phải danh sách alpha để sao chép. Đây là **thư viện thành phần** để
bạn tự tổ hợp. Nếu bạn copy nguyên một biểu thức từ đây, bạn đã dùng sai tài liệu
và đang đi vào lối mòn mà chính sách tìm kiếm cấm.

Một alpha = **Hypothesis × Component × Mechanism × Structure**.
Tài liệu này cho bạn bốn thành phần đó **riêng biệt**. Việc của bạn là *ghép*.
Số tổ hợp khả dĩ là hàng nghìn; số biểu thức viết sẵn ở đây là **không** —
cố ý như vậy.

### Ba quy tắc bắt buộc

1. **Mỗi hypothesis phải cam kết MỘT dấu.** Nếu bạn viết được "LONG nếu X, SHORT
   nếu Y" thì đó không phải giả thuyết — đó là mô tả, không test được. Chọn một
   chiều, ghi rõ điều kiện gì sẽ chứng minh bạn SAI.
2. **Không có window mặc định.** Tài liệu này cố ý KHÔNG ghi con số cụ thể. Mọi
   window viết là `d_slow`, `d_fast`, `d_corr`. Bạn phải chọn theo *bản chất kinh
   tế* của tín hiệu (xem §2), không phải copy con số của người khác.
3. **Đa dạng cơ chế, không chỉ đa dạng field.** Đổi datafield mà vẫn dùng
   `rank(A)*rank(B)` là **cùng một alpha**. Cơ chế kết hợp mới có giá trị hơn field
   mới.

---

## 1. BỐN TRỤC ĐỘC LẬP — sinh tổ hợp bằng cách chọn mỗi trục một lần

Đừng nghĩ theo kiểu "cặp field nào hay". Nghĩ theo toạ độ 4 chiều:

```
Alpha = HYPOTHESIS_TYPE × COMPONENT_A × COMPONENT_B × COMBINATION_MECHANISM
```

Mỗi iteration: **thay đổi ít nhất một trục HOÀN TOÀN** so với iteration trước.
Nếu chỉ đổi window → không tính là thay đổi.

### Trục 1 — HYPOTHESIS_TYPE (bạn đang đặt cược vào cái gì?)

| Loại | Cơ chế kinh tế | Cam kết dấu |
|---|---|---|
| **Underreaction** | Thông tin có thật chưa vào giá hết → giá sẽ drift theo thông tin | Cùng chiều thông tin |
| **Overreaction** | Giá đã phản ứng quá đà → sẽ hồi | Ngược chiều price move |
| **Crowding** | Quá nhiều người cùng một phía → hết người mua | Ngược chiều consensus |
| **Attention gap** | Thông tin tốt nhưng chưa ai chú ý → sẽ được phát hiện | Cùng chiều thông tin, điều kiện attention THẤP |
| **Expectation mismatch** | Kỳ vọng ≠ thực tế → hội tụ về thực tế | Cùng chiều thực tế |
| **Risk mispricing** | Rủi ro bị định giá sai | Tuỳ chiều sai lệch, phải nêu rõ |
| **Regime conditioning** | Signal chỉ hoạt động trong một số điều kiện | Signal gốc, gated |
| **Information timing** | Nguồn nhanh biết trước nguồn chậm | Cùng chiều nguồn nhanh |
| **Stability-as-signal** | Tần suất/độ ổn định của thay đổi mang thông tin | Phải nêu rõ |

⚠️ Overreaction và Underreaction **mâu thuẫn nhau**. Cùng một cặp field không thể
đồng thời cả hai. Nếu bạn không biết chọn cái nào → bạn chưa có giả thuyết.
Chọn một, và ghi: *"Nếu Sharpe âm ổn định, hypothesis ngược mới đúng."*

### Trục 2 & 3 — COMPONENT (xem §3 — chọn 2 thành phần từ 2 **họ khác nhau**)

### Trục 4 — COMBINATION_MECHANISM (xem §4 — đây là trục bị bỏ quên nhiều nhất)

---

## 2. TỐC ĐỘ TÍN HIỆU — chọn window từ bản chất, không copy số

**Không** copy window của người khác. Suy ra window từ **nhịp cập nhật thật** của
dữ liệu:

| Nhịp dữ liệu | Ví dụ nguồn | Window hợp lý | Lý do |
|---|---|---|---|
| Theo quý | Fundamental (`fnd6_*`) | Vài quý | Ngắn hơn 1 quý = đo nhiễu restatement, không phải kinh tế |
| Theo sự kiện | Analyst revision, guidance | Bao trọn vài chu kỳ sự kiện | Quá ngắn → sparse, quá dài → pha loãng |
| Hàng ngày | Price, volume, news | Ngắn đến trung bình | Đủ dài để lọc nhiễu, đủ ngắn để còn kịp |
| Liên tục | Social, buzz | Rất ngắn | Decay nhanh, dài = mất tín hiệu |

**Nguyên tắc mismatch:** khi kết hợp hai nguồn khác nhịp, window phải khác nhau —
dùng cùng một window cho fundamental và social là sai về bản chất.

**Nguyên tắc chọn window có kỷ luật:** nếu bạn phải thử window, thử theo **bậc độ
lớn** (ví dụ: ~1 tháng vs ~1 quý vs ~1 năm), không phải ±10%. Chênh lệch ±10% là
noise sampling — bị cấm. Chênh lệch một bậc là giả thuyết về horizon — hợp lệ.

---

## 3. THÀNH PHẦN THEO CHỨC NĂNG (không phải theo dataset)

Phân loại theo **vai trò kinh tế**, để bạn ghép chéo. Cột "Tốc độ" cho biết
component thuộc lớp nhanh hay chậm.

### 3.1 Đo CHẤT LƯỢNG / SỨC KHOẺ (chậm)
| Thành phần | Field gợi ý | Cảnh báo |
|---|---|---|
| Chất lượng lợi nhuận | `fnd6_oancf` vs `fnd6_ni` / `fnd6_ib` | Dùng **hiệu** hoặc scale theo assets, **KHÔNG chia** — net income âm sẽ đảo dấu ratio |
| Sinh lời | `fnd6_oibdp`, `fnd6_gp` scale theo `fnd6_at` / `fnd6_icapt` | Mẫu số assets an toàn (luôn dương) |
| Đòn bẩy | `fnd6_dltt`, `fnd6_che` scale theo `fnd6_at` | Chia cho `fnd6_che` **nguy hiểm** — cash có thể ≈ 0 |
| Thanh khoản DN | `working_capital` scale theo `assets` | WC có thể âm — dùng zscore, không rank thô |
| Điểm tổng hợp | `fscore_quality`, `fscore_total`, `fscore_surface` | Đã là score chuẩn hoá — **đừng rank lại rồi rank nữa** |

### 3.2 Đo KỲ VỌNG (trung bình, theo sự kiện)
| Thành phần | Field gợi ý | Cảnh báo |
|---|---|---|
| Consensus level | `anl4_afv4_eps_mean` | Level thô ít nghĩa — cần scale theo giá hoặc so với chính nó |
| Revision momentum | `anl4_adxqf_pu`, `anl4_adxqf_down` | Hiệu (`pu - down`) mạnh hơn từng cái riêng |
| Bất đồng | `anl4_afv4_dts_spe` | Tương quan mạnh với size & volatility — cân nhắc neutralize |
| Guidance uncertainty | `anl4_afv4_maxguidance`, `anl4_afv4_minguidance` | Sparse — cần `ts_backfill` |
| Growth forecast | `star_val_fwd5_eps_cagr` | Kỳ vọng dài hạn, decay chậm |
| Actual vs consensus | `anl4_bac1actualqfv110_actual` | ⚠️ **Point-in-time risk** — actual earnings có timing hiểm. Kiểm tra kỹ trước khi dùng |

### 3.3 Đo GIÁ / DÒNG TIỀN (nhanh)
| Thành phần | Field gợi ý | Cảnh báo |
|---|---|---|
| Momentum | `returns`, `close` | Load nặng vào market factor — luôn cần neutralize |
| Attention / flow | `volume` so với chính nó | Skew rất mạnh — cân nhắc `log` trước khi rank |
| Thanh khoản | `adv20`, `cap` | Proxy của size — dễ tạo size bias |
| Institutional | `vwap` vs `close` | Intraday info, decay nhanh |
| Định giá | `star_val_pe`, `star_val_pb`, `star_val_piv_ratio` | Đã là rank 1–100 — **không rank lại** |

### 3.4 Đo THÔNG TIN / SENTIMENT (nhanh)
| Thành phần | Field gợi ý | Cảnh báo |
|---|---|---|
| News sentiment | `nws18_ssc`, `nws18_qep`, `nws18_ber` | Sparse — coverage thấp, **bắt buộc** `ts_backfill` |
| News importance | `nws18_nip`, `nws18_relevance` | Là **điều kiện gating** tốt hơn là signal độc lập |
| Credit/legal | `rp_css_credit`, `rp_css_legal` | Rất sparse, event-driven |
| Retail sentiment | `snt_social_value`, `snt_social_volume` | Coverage lệch về large-cap → size bias ngầm |
| Buzz | `scl12_buzz`, `scl12_sentiment` | Buzz mạnh nhất khi dùng làm **gate/condition** |
| Target/expectation | `snt1_d1_uptargetpercent` và họ `snt1_*` | Ít khai phá — xem §6 |

### 3.5 Đo RỦI RO (trung bình)
| Thành phần | Field gợi ý | Cảnh báo |
|---|---|---|
| Systematic | `beta_last_90_days_spy`, `systematic_risk_last_*` | Nhiều horizon → so sánh giữa các horizon là ý tưởng chưa khai phá |
| Idiosyncratic | `unsystematic_risk_last_90_days` | Tương quan nghịch với size |
| Realized vol | `ts_std_dev(returns, d)` | Là **conditioning variable** rất tốt, ít ai dùng làm gate |

---

## 4. CƠ CHẾ KẾT HỢP — TRỤC QUAN TRỌNG NHẤT VÀ BỊ BỎ QUÊN NHẤT

Đây là nơi tạo ra sự đa dạng thật. Đổi field mà giữ cơ chế = alpha cũ.
**Mỗi cơ chế mã hoá một giả thuyết kinh tế KHÁC NHAU** — chọn cơ chế khớp với
hypothesis, đừng mặc định nhân.

### M1 — Nhân (AND cứng)
```
rank(A) * rank(B)
```
- **Nghĩa:** "cần CẢ HAI cùng mạnh"
- **⚠️ Cảnh báo nặng:** đây là cơ chế bị lạm dụng nhất. Nhân ≥3 rank chọn ra góc
  cực của hypercube → rất ít cổ phiếu sống sót → **weight concentration cao** →
  HARD REJECT ở ngưỡng 20%.
- **Chỉ dùng khi:** hypothesis thực sự là hội tụ (conjunction), và **không quá 2 thành phần**.
- **Nếu đã có peer dùng M1 trong iteration này → bạn dùng cơ chế khác.**

### M2 — Cộng z-score (OR mềm)
```
zscore(A) + zscore(B)
```
- **Nghĩa:** "một trong hai mạnh là đủ, cả hai thì tốt hơn"
- **Ưu điểm:** phân phối weight mượt hơn M1 rất nhiều → ít fail weight check
- **Dùng khi:** hai nguồn độc lập cùng đo một khái niệm (diversification)
- **Chưa được khai phá đủ** — ưu tiên thử

### M3 — Trực giao hoá (residual)
```
vector_neut(A, B)     hoặc     group_neutralize(A, group)
```
- **Nghĩa:** "phần của A mà B **không** giải thích được" — đây là *alpha thật* sau
  khi loại bỏ cái đã biết
- **Mạnh hơn nhân về mặt khái niệm:** thay vì đòi hỏi trùng khớp, nó cô lập phần mới
- **Dùng khi:** hypothesis là "thông tin trong A vượt ngoài cái B đã nói"
- **Rất ít được dùng** → giá trị exploration cao

### M4 — Gating có điều kiện
```
trade_when(condition, signal, -1)
```
- **Nghĩa:** "signal chỉ đúng trong regime này"
- **Ưu điểm:** giảm turnover, tách bạch WHAT (signal) và WHEN (condition)
- **⚠️ Bẫy tập thể:** gating theo liquidity (`volume`/`adv20`) là thứ **mọi agent
  đều nghĩ tới đầu tiên**. Nếu peer đã gate theo liquidity → bạn gate theo cái khác:
  volatility regime, dispersion, sentiment state, beta regime, news relevance.
- **Chỉ MỘT agent/iteration được gate theo liquidity.**

### M5 — Đo đồng vận theo thời gian
```
ts_corr(A, B, d_corr)          — không quan tâm magnitude
ts_covariance(A, B, d_corr)    — có quan tâm magnitude
ts_regression(A, B, d)         — tách slope/residual
```
- **Nghĩa:** "mối *quan hệ* giữa A và B mang thông tin, không phải level của chúng"
- **Khác biệt căn bản với M1:** M1 hỏi "cả hai có cao không", M5 hỏi "chúng có
  di chuyển cùng nhau không"
- `ts_regression` gần như **chưa được dùng** → giá trị exploration rất cao

### M6 — Bucket / conditioning
```
bucket(rank(A), range="0,1,0.1")  → dùng làm group cho B
```
- **Nghĩa:** "so sánh B *trong nhóm* có cùng đặc tính A"
- Đây là dạng conditioning tinh vi, khác hẳn nhân
- **Chưa khai phá**

### M7 — Reshaping phi tuyến
```
signed_power(x, p)  |  winsorize(x, std)  |  quantile(x)
```
- **Nghĩa:** "quan hệ signal→return là phi tuyến"
- ⚠️ `signed_power` khuếch đại đuôi → **theo dõi weight concentration**. Ghép với
  lớp chuẩn hoá thay vì tinh chỉnh số mũ.
- Ba cái này test **cùng một giả thuyết** theo ba cách → nếu peer dùng `signed_power`,
  bạn dùng `bucket` hoặc `quantile`.

### M8 — Sự kiện / timing
```
days_from_last_change(x)  |  ts_arg_max(x, d)  |  hump(x, h)  |  ts_step(d)
```
- **Nghĩa:** "*khi nào* thay đổi xảy ra quan trọng hơn *bao nhiêu*"
- Họ operator này gần như vắng bóng trong hầu hết alpha → **giá trị exploration cao nhất**

### M9 — So sánh đa horizon
```
zscore(A_short_window) - zscore(A_long_window)
```
- **Nghĩa:** "tốc độ ngắn hạn lệch khỏi chuẩn dài hạn"
- Dùng **một** field nhưng **hai** thang thời gian → không cần field thứ hai
- Đặc biệt hợp với họ `systematic_risk_last_*` (có sẵn nhiều horizon) — **chưa ai dùng**

### Bảng ánh xạ Hypothesis → Mechanism

| Hypothesis | Cơ chế tự nhiên | Cơ chế SAI |
|---|---|---|
| Underreaction | M3 (residual), M9 | M1 |
| Overreaction | M7, M4 (gate theo extreme) | M2 |
| Crowding | M5 (co-movement kéo dài) | M3 |
| Attention gap | M4 (gate attention thấp) | M1 |
| Expectation mismatch | M2, M3 | M5 |
| Regime conditioning | M4, M6 | M1 |
| Information timing | M9, M5 | M2 |
| Stability-as-signal | M8 | M1 |

Nếu bạn đang dùng M1 cho một hypothesis không phải conjunction → bạn chọn sai cơ chế.

---

## 5. VÍ DỤ TỔ HỢP — đọc để hiểu *phương pháp*, không để copy

Các ví dụ dưới đây cố ý viết ở dạng **schema**, không phải code chạy được, để bạn
không copy-paste. Mỗi cái minh hoạ việc chọn toạ độ 4 trục.

**Ví dụ A** — Hypothesis: *Expectation mismatch* · Component: chất lượng lợi nhuận (3.1) ×
kỳ vọng analyst (3.2) · Mechanism: **M3 residual**
```
core     = <đo accrual: hiệu oancf−ni, scale theo assets>
expected = <consensus EPS đã chuẩn hoá>
raw      = vector_neut(core, expected)   # phần chất lượng mà kỳ vọng chưa phản ánh
```
*Cam kết dấu:* LONG khi residual dương. *Sai nếu:* Sharpe âm ổn định → thị trường
đã pricing accrual, hypothesis chết.
*Lưu ý:* dùng **hiệu**, không chia — `ni` âm sẽ đảo dấu.

**Ví dụ B** — Hypothesis: *Attention gap* · Component: điểm chất lượng (3.1) ×
retail attention (3.4) · Mechanism: **M4 gating** (không phải liquidity!)
```
signal    = <fscore_quality>
condition = <social_volume thấp so với chính nó theo d_fast>
raw       = trade_when(condition, signal, -1)
```
*Cam kết dấu:* LONG. *Sai nếu:* hoạt động tốt cả khi attention cao → không phải
attention gap, chỉ là quality factor.

**Ví dụ C** — Hypothesis: *Information timing* · Component: rủi ro hệ thống (3.5)
**một field duy nhất, hai horizon** · Mechanism: **M9**
```
raw = zscore(<risk_short_horizon>) - zscore(<risk_long_horizon>)
```
*Cam kết dấu:* SHORT khi chênh lệch dương (rủi ro đang tăng nhanh hơn chuẩn).
*Điểm đáng chú ý:* không cần field thứ hai — đa dạng đến từ **cơ chế**, không từ field.

**Ví dụ D** — Hypothesis: *Stability-as-signal* · Component: bất kỳ field chậm nào ·
Mechanism: **M8**
```
raw = <days_from_last_change trên một field chưa ai thử>
```
*Cam kết dấu:* phải nêu rõ trước khi chạy. *Ghi chú:* đây là họ operator có
evidence thực nghiệm nhưng gần như không xuất hiện trong alpha nào.

Chú ý: bốn ví dụ dùng **bốn cơ chế khác nhau**. Đó là điểm mấu chốt. Nếu bốn alpha
của bạn đều là M1 với field khác nhau → bạn chỉ có **một** alpha.

---

## 6. VÙNG CHƯA KHAI PHÁ — ưu tiên đi vào đây

Bản đồ còn trống ở đâu thì thông tin nằm ở đó. Tính đến bản này:

**Cơ chế chưa khai phá (giá trị cao nhất):**
- M3 `vector_neut` — hầu như chưa dùng
- M9 so sánh đa horizon — chưa dùng, dù `systematic_risk_last_*` có sẵn nhiều horizon
- M6 `bucket` conditioning — chưa dùng
- M8 event/timing (`ts_arg_max`, `hump`, `ts_step`, `last_diff_value`) — chưa dùng
- `ts_regression` — chưa dùng

**Dữ liệu chưa khai phá:**
- Options / IV — gần như vắng mặt
- Họ `snt1_*` (bao gồm `snt1_d1_uptargetpercent`) — chưa có mục nào
- Vector fields + `vec_*` operators — chưa dùng
- CHN dataset — chưa dùng
- Group family áp lên fundamental scores — chưa có evidence

**Đã bão hoà (tránh trừ khi có lý do mạnh):**
- Liquidity gating (`volume`/`adv20` + `trade_when`) — cả colony đều nghĩ tới
- `rank(fnd6_*) * rank(anl4_*)` — mật độ cao nhất trong lịch sử tìm kiếm
- Multiply-three-ranks — nguyên nhân fail weight phổ biến nhất

---

## 7. CẢNH BÁO KỸ THUẬT (đọc trước khi viết biểu thức)

### 7.1 Mẫu số — nguồn NaN và outlier lớn nhất
- **KHÔNG chia** cho đại lượng có thể ≈ 0 hoặc đổi dấu: `fnd6_ni`, `fnd6_ib`,
  `fnd6_che`, `fnd6_dvt`, `working_capital`.
  → Net income âm biến ratio "tốt" thành số âm lớn → phá hoàn toàn rank.
- **An toàn:** chia cho `fnd6_at`, `fnd6_icapt`, `cap` (luôn dương).
- **Thay thế:** dùng **hiệu của hai đại lượng đã scale** thay vì tỉ số:
  `(A - B) / assets` an toàn hơn `A / B`.

### 7.2 Chuẩn hoá hai lần
- `star_val_pe`, `star_val_pb` đã là **rank 1–100**. `fscore_*` đã là **score chuẩn hoá**.
  Rank lại = mất thông tin, không thêm gì.

### 7.3 Neutralization — settings vs expression
- Alpha settings **đã có** `neutralization` (ví dụ INDUSTRY). Thêm
  `group_neutralize` trong biểu thức = neutralize **hai lần** → có thể triệt tiêu
  chính signal của bạn.
- Chỉ neutralize trong biểu thức khi **chiều đó khác** với settings, và phải nêu lý do.

### 7.4 Coverage & sparse data
- Field sentiment/news/credit rất sparse → `ts_backfill` là **bắt buộc**, không tuỳ chọn.
- Coverage < 50% → backfill window ngắn; đừng backfill quá dài (tạo dữ liệu giả).

### 7.5 Timing / point-in-time
- Actual earnings, guidance, và bất kỳ field nào gắn với "sự kiện công bố" đều có
  rủi ro look-ahead. Nếu không chắc timing → **đừng dùng**.

### 7.6 Bias ngầm cần biết
- `volume`, `adv20`, `cap`, `snt_social_*` đều là **proxy của size** → dễ vô tình
  xây size factor thay vì alpha.
- Momentum (`returns`) load nặng vào market factor.
- Analyst dispersion tương quan mạnh với volatility & size.

### 7.7 Anomaly đã publish
Accrual (Sloan 1996), asset growth (Cooper-Gulen-Schill 2008), BAB
(Frazzini-Pedersen 2014) là các anomaly **nổi tiếng vì từng thành công** — và đã
decay đáng kể sau khi được công bố (McLean & Pontiff 2016). Trên universe bị
arbitrage nặng, dùng chúng **ở dạng thô** gần như chắc chắn crowded.
→ Nếu dùng, phải dùng ở dạng **residual (M3)** hoặc **conditioned (M4/M6)**, tức là
phần mà factor đã biết *không* giải thích được. Đừng lặp lại paper.

---

## 8. NGUYÊN TẮC CHUNG (giữ lại, có giá trị)

### 8.1 Slow + Fast
- Tín hiệu chậm (fundamental) xác định **HƯỚNG**; tín hiệu nhanh (news, volume)
  xác định **THỜI ĐIỂM**.
- Điều này ánh xạ tự nhiên sang **M4 gating**: slow = signal, fast = condition.

### 8.2 Cross-dataset independence
- Tín hiệu từ dataset khác nhau ít tương quan hơn tín hiệu cùng dataset →
  kết hợp cross-dataset cho diversification tốt hơn.
- **Hệ quả:** hai component nên đến từ **hai mục §3 khác nhau**. Ghép hai field
  `fnd6_*` với nhau thường chỉ tạo ra một biến thể của cùng một factor.

### 8.3 Confirmation vs Divergence — dùng có kỷ luật
- **Confirmation** (hai tín hiệu cùng chiều) → M1 hoặc M2.
- **Divergence** (trái chiều) → ⚠️ **không mặc định SHORT**. Divergence có hai cách
  đọc đối lập:
  - *Market sai:* fundamental đúng, giá sẽ hội tụ về fundamental
  - *Market dẫn trước:* giá đã biết điều fundamental chưa phản ánh
  Bạn **phải chọn một** và nêu rõ. Giả định "fundamental luôn đúng" là bias, không
  phải kiến thức.

### 8.4 Phân loại operator theo chức năng
- **Đo mức nền (cross-sectional):** `rank`, `zscore`, `quantile`
- **Đo xu hướng (theo thời gian):** `ts_delta`, `ts_rank`, `ts_zscore`
- **Đo quan hệ:** `ts_corr`, `ts_covariance`, `ts_regression`
- **Giảm nhiễu:** `ts_mean`, `ts_decay_linear`, `winsorize`
- **Xử lý missing:** `ts_backfill`, `group_backfill`
- **Kiểm soát giao dịch:** `trade_when`, `hump`
- **Trực giao hoá:** `vector_neut`, `group_neutralize`
- **Sự kiện:** `days_from_last_change`, `ts_arg_max`, `ts_step`, `last_diff_value`

---

## 9. KHUNG XÂY DỰNG (schema — không phải template để điền)

Đây **không** phải công thức cố định. Các bước 2, 5, 7 có nhiều lựa chọn — chọn
theo hypothesis, đừng mặc định.

```
Bước 1 — HYPOTHESIS: viết một câu, cam kết một dấu, nêu điều gì chứng minh là sai.

Bước 2 — COMPONENTS: chọn 1–2 thành phần từ HAI mục §3 KHÁC NHAU.
         (1 component + M9 đa horizon là hoàn toàn hợp lệ, và ít crowded hơn)

Bước 3 — MISSING DATA: ts_backfill nếu coverage thấp (bắt buộc với sentiment/news)

Bước 4 — SPEED: chọn window theo §2 từ nhịp dữ liệu, KHÔNG copy số từ đâu cả

Bước 5 — MECHANISM: chọn từ M1–M9 theo bảng ánh xạ §4.
         ❌ Mặc định M1 là lỗi. Kiểm tra: peer nào đang dùng cơ chế này?

Bước 6 — OUTLIER: winsorize / quantile nếu M7 hoặc mẫu số rủi ro

Bước 7 — NORMALIZE: zscore HOẶC rank HOẶC không cần (nếu đã chuẩn hoá ở bước 5)

Bước 8 — TURNOVER: ts_decay_linear / hump — CHỈ khi turnover thực sự > ngưỡng.
         Dưới ngưỡng, giảm thêm không có tác dụng lên Fitness.

Bước 9 — NEUTRALIZE: kiểm tra settings trước (§7.3). Có thể KHÔNG cần bước này.
```

---

## 10. TỰ KIỂM TRA TRƯỚC KHI XUẤT

1. Hypothesis của tôi có cam kết **một** dấu không? Điều gì chứng minh nó sai?
2. Tôi dùng cơ chế nào (M1–M9)? Nó có khớp bảng ánh xạ §4 không?
3. **Cơ chế** của tôi có khác iteration trước không? (đổi field mà giữ M1 = không đổi)
4. Peer nào đang dùng cùng cơ chế? Nếu có → đổi.
5. Tôi có đang mặc định nhân ranks không? Nếu có → tại sao không phải M2/M3/M4?
6. Có mẫu số nào có thể ≈ 0 hoặc đổi dấu không? (§7.1)
7. Tôi có rank lại thứ đã được chuẩn hoá không? (§7.2)
8. Window của tôi đến từ bản chất dữ liệu hay từ copy? (§2)
9. Tôi có neutralize hai lần không? (§7.3)
10. Tổ hợp này đã có ai thử chưa? Nếu rồi → tôi đang đóng góp gì mới?

**Nhắc lại:** mục tiêu không phải tìm alpha tốt ở iteration này, mà là **tối đa
thông tin trên mỗi lần simulation**. Một tổ hợp mới thất bại có giá trị hơn một
bản sao thành công — vì nó thu hẹp không gian tìm kiếm cho cả colony.
