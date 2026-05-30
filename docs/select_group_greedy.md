# Thuật toán Greedy Search cho Lọc Nhóm Câu Hỏi

## Tổng quan

Khi tạo đề thi, hệ thống cần lựa chọn `top_k` nhóm câu hỏi (QuestionGroup) từ danh sách các ứng cử viên. Việc lựa chọn không phải ngẫu nhiên mà dựa trên **thuật toán greedy** kết hợp ba yếu tố:

1. **Semantic Similarity** — độ tương đồng với yêu cầu custom_text
2. **Novelty/Freshness** — ưu tiên nhóm chưa được dùng nhiều
3. **Diversity** — tránh chọn những nhóm quá giống nhau

---

## Quy trình Greedy Selection

### Input
- `candidates` — danh sách QuestionGroup có thể chọn
- `top_k` — số lượng nhóm tối đa cần chọn
- `query_embedding` — vector embedding từ custom_text (nếu có)
- `random_level` — mức độ ngẫu nhiên: "low", "medium", "high"
- `diversity_weight` — trọng số penalty đa dạng (mặc định 0.3)

### Output
- Danh sách nhóm được chọn (độ dài ≤ top_k)

### Thuật toán (Pseudo-code)

```
selected = []
selected_embeddings = []

for i in range(1 to top_k):
    best_group = None
    best_score = -∞
    
    for each group in candidates (chưa được chọn):
        score = compute_score(group, query_embedding, random_level)
        penalty = diversity_penalty(group, selected_embeddings)
        final_score = score - penalty * diversity_weight
        
        if final_score > best_score:
            best_group = group
            best_score = final_score
    
    if best_group is None:
        break
    
    selected.append(best_group)
    selected_embeddings.append(best_group.vector_embedding)

return selected
```

### Đặc điểm
- **Greedy** — mỗi bước chọn nhóm có điểm cao nhất (không tối ưu toàn cục)
- **Iterative** — mỗi lần chọn, `selected_embeddings` được cập nhật để tính diversity penalty cho lần tiếp theo
- **Dừng sớm** — nếu không tìm được nhóm nào phù hợp, dừng trước khi đạt `top_k`

---

## Các Công Thức Tính Toán

### 1. Compute Score — Điểm cơ sở của một nhóm

**Ý nghĩa cơ bản:**

Điểm cơ sở của một nhóm phản ánh **độ phù hợp tổng thể** của nhóm đó để được chọn vào đề thi. Nó cân bằng giữa hai tiêu chí:

- **Semantic Relevance (70%)** — Nhóm này có nội dung phù hợp với chủ đề yêu cầu không? Nó gần với yêu cầu custom_text bao nhiêu?
- **Novelty (30%)** — Nhóm này còn "tươi" (chưa dùng nhiều) không? Hay đã lặp lại quá nhiều lần?

Tỉ lệ 70-30 thể hiện **ưu tiên nội dung hơn tính mới lạ**: Một nhóm phù hợp về nội dung nhưng dùng nhiều lần vẫn tốt hơn một nhóm mới nhưng không phù hợp.

**Công thức:**
```
score = sim × 0.7 + exist_score × 0.3
```

Trong đó:

#### `sim` — Semantic Similarity (70% trọng số)

```
sim = cosine_similarity(query_embedding, group_embedding) ∈ [0.0, 1.0]
```

**Ý nghĩa**:
- Đo độ tương đồng giữa yêu cầu custom_text và nội dung nhóm câu hỏi
- **sim = 0.0** → nhóm hoàn toàn không liên quan (trực giao)
- **sim ≈ 0.5** → nhóm có liên quan vừa phải
- **sim ≈ 1.0** → nhóm cực kỳ phù hợp (cùng hướng)

**Các trường hợp áp dụng**:
- Nếu **không có query_embedding** (không có custom_text) → sim = 0.0 (không ảnh hưởng)
- Nếu **nhóm không có vector_embedding** → sim = 0.0 (bỏ qua semantic match)
- Nếu **có cả query_embedding lẫn group_embedding** → tính cosine similarity bình thường

**Tại sao 70% trọng số cho semantic?**
- Mục tiêu chính của đề thi là có **nội dung phù hợp** với yêu cầu
- Nội dung tốt nhưng dùng nhiều lần (exist_score thấp) vẫn được ưu tiên hơn nội dung kém nhưng mới
- Nếu yêu cầu custom_text = "Động vật có xương sống", một nhóm về "Cá" (sim=0.95) sẽ được chọn trước "Thực vật" (sim=0.1), dù "Thực vật" chưa dùng bao giờ

#### `exist_score` — Novelty Score (30% trọng số)

```
exist_score = 1.0 / (existence_count + 1) ^ alpha
            ∈ (0.0, 1.0]
```

**Ý nghĩa**:
- Đo mức độ "tươi mới" của nhóm — có bao nhiêu nhóm lặp lại?
- **existence_count** — số lần nhóm đã được dùng trong các đề thi trước
  - = 0 → nhóm chưa dùng bao giờ (hoàn toàn mới) → exist_score = 1.0 (tối đa)
  - = 4 → nhóm dùng 4 lần trước (hơi cũ) → exist_score < 0.5 (bị phạt)
  
- **alpha** — hệ số điều chỉnh phụ thuộc `random_level`
  - Kiểm soát **độ "mạnh" của phạt lặp lại**
  - alpha cao → lặp lại bị phạt nặng
  - alpha thấp → lặp lại bị phạt nhẹ

**Bảng alpha theo random_level:**
| random_level | alpha | Ý nghĩa | Hành vi |
|--------------|-------|---------|---------|
| "low"        | 0.1   | Yếu | Lặp lại bị phạt nhẹ, có thể chọn nhóm cũ nếu semantic tốt |
| "medium"     | 0.5   | Vừa phải | Cân bằng giữa mới và cũ |
| "high"       | 1.0   | Mạnh | Lặp lại bị phạt nặng, ưu tiên nhóm mới |

**Ví dụ tính exist_score:**

Nhóm dùng 4 lần trước (existence_count = 4):
```
Với alpha=0.1 (low): exist_score = 1.0 / (4+1)^0.1 = 1.0 / 1.175 ≈ 0.851
→ Bị phạt ít, vẫn có điểm cao

Với alpha=0.5 (medium): exist_score = 1.0 / (4+1)^0.5 = 1.0 / 2.236 ≈ 0.447
→ Bị phạt vừa phải, giảm 50% điểm

Với alpha=1.0 (high): exist_score = 1.0 / (4+1)^1.0 = 1.0 / 5 = 0.2
→ Bị phạt nặng, giảm 80% điểm
```

**Tại sao 30% trọng số cho novelty?**
- Muốn **tránh lặp lại quá nhiều**, nhưng không quá cứng nhắc
- Ưu tiên **nội dung tốt hơn tính mới lạ**: Một nhóm phù hợp dùng 5 lần vẫn tốt hơn nhóm không phù hợp chưa dùng
- Cân bằng **chất lượng** vs **tính tươi mới** của đề thi

### 2. Diversity Penalty — Phạt nhóm trùng lặp

**Công thức:**
```
penalty = max(cosine_similarity(group_embedding, selected_emb_i))
        ∈ [0.0, 1.0]
```

**Ý nghĩa chi tiết:**

Đây là **phạt dựa trên sự giống nhau** với các nhóm đã chọn trước đó.

- **Mục đích**: Đảm bảo **đề thi không trùng lặp nội dung**, không quá tập trung vào một lĩnh vực

- **Cách tính**:
  1. So sánh nhóm hiện tại với **tất cả** các nhóm đã chọn rồi
  2. Tính cosine similarity với mỗi nhóm cũ
  3. Lấy giá trị **cao nhất** (nếu quá giống bất cứ nhóm nào = penalty cao)

- **Kết quả**:
  - **penalty = 0.0** → nhóm hiện tại hoàn toàn khác biệt với các nhóm đã chọn (tốt!)
  - **penalty = 0.5** → nhóm hiện tại khá giống một nhóm cũ (trung bình)
  - **penalty = 0.95** → nhóm hiện tại gần giống một nhóm cũ (xấu, nên tránh)

**Ví dụ:**

Đã chọn 2 nhóm: A (embedding_A) và B (embedding_B)
Đánh giá nhóm C (embedding_C):
```
sim(C, A) = 0.85 (C giống A 85%)
sim(C, B) = 0.60 (C giống B 60%)
penalty(C) = max(0.85, 0.60) = 0.85

→ Nhóm C bị phạt nặng vì quá giống A (thậm chí nếu C khác B, vẫn bị phạt)
```

**Tại sao là "max" chứ không phải trung bình?**
- Nếu C giống **bất kỳ** nhóm nào → cần tránh (dù chỉ giống 1)
- Lấy max = lấy "mối nguy hiểm" cao nhất → an toàn hơn

### 3. Final Score — Điểm cuối cùng sau penalty

**Công thức:**
```
final_score = score - penalty × diversity_weight
            = (sim × 0.7 + exist_score × 0.3) - penalty × diversity_weight
```

**Ý nghĩa:**

Đây là **điểm cuối cùng** dùng để so sánh và chọn nhóm.

- **score** (0 đến 1.0) — "goodness" cơ sở của nhóm (semantic + novelty)
- **penalty × diversity_weight** — "trừ điểm" vì quá giống các nhóm cũ
- **Công thức trừ** → prioritize **diversity** (tránh trùng lặp)

**Ví dụ:**

Scenario: Lựa chọn lần 2 (đã chọn nhóm A)

Nhóm B: score=0.8, penalty=0.75 (B giống A 75%)
```
Với diversity_weight=0.3 (mặc định):
  final(B) = 0.8 - 0.75 × 0.3 = 0.8 - 0.225 = 0.575
  → B bị trừ 22.5%, vẫn còn điểm, nếu không có khiếu nại nó sẽ được chọn

Với diversity_weight=1.0 (mạnh):
  final(B) = 0.8 - 0.75 × 1.0 = 0.05
  → B bị trừ 75%, gần như loại bỏ, cần có nhóm khác khác biệt hơn
```

**Tại sao trừ chứ không chia?**
- **Trừ (subtraction)** → penalty tuyến tính, dễ tune
- Nếu dùng chia → penalty sẽ quá mạnh (exponential) → khó kiểm soát

**Khi nào chọn diversity_weight?**

Mặc định = 0.3 → **balance** giữa nội dung tốt và đa dạng
- Tăng lên 0.5–1.0 → **force diversity**, chấp nhận chọn nhóm kém hơn nếu để giữ đa dạng
- Giảm xuống 0.0–0.1 → **ignore diversity**, chỉ chọn dựa trên content quality

---

## Ảnh hưởng của Các Tham số

### A. Ảnh hưởng của `random_level` (alpha)

Kiểm soát mức độ ưu tiên nhóm mới so với nhóm cũ.

- **"low"** (alpha=0.1): Chọn nhóm tốt nhất bất kể dùng bao nhiêu lần → Có thể lặp lại
- **"medium"** (alpha=0.5): Ưu tiên nhóm mới nhưng vẫn chọn nhóm cũ nếu match tốt
- **"high"** (alpha=1.0): Ưu tiên nhóm chưa dùng → Tránh lặp lại

**Ví dụ:**
Input: 3 nhóm, cần chọn 2
- Nhóm A: existence_count=0, sim=0.8
- Nhóm B: existence_count=5, sim=0.85
- Nhóm C: existence_count=0, sim=0.5

Với "low" (alpha=0.1):
- Nhóm A: score = 0.8×0.7 + 1.0×0.3 = 0.86 ✓
- Nhóm B: score = 0.85×0.7 + 0.85×0.3 = 0.805

Với "high" (alpha=1.0):
- Nhóm A: score = 0.8×0.7 + 1.0×1.0 = 1.46 ✓
- Nhóm C: score = 0.5×0.7 + 1.0×1.0 = 1.20 ✓

### B. Ảnh hưởng của `diversity_weight`

Kiểm soát mức độ bắt buộc của tính đa dạng.

| diversity_weight | Kết quả |
|------------------|--------|
| **0.0** | Bỏ qua diversity penalty |
| **0.3** (mặc định) | Cân bằng |
| **0.5** | Mạnh hơn |
| **1.0+** | Rất mạnh |

**Ví dụ:**
- score(B) = 0.8, penalty = 0.75
- Với diversity_weight=0.3: final = 0.8 - 0.75×0.3 = 0.575
- Với diversity_weight=1.0: final = 0.8 - 0.75×1.0 = 0.05

### C. Ảnh hưởng của `query_embedding` (custom_text)

Nếu SectionConfig có custom_text:
- Được embed thành vector
- Truyền vào select_groups_greedy()
- Ảnh hưởng đến sim trong compute_score()

| Trường hợp | Kết quả |
|-----------|---------|
| **Không custom_text** | sim = 0.0, score phụ thuộc 100% vào exist_score |
| **Có custom_text** | sim ∈ [0, 1], score = sim×0.7 + exist_score×0.3 |

---

## Luồng Hoàn Chỉnh trong Base Exam Generation

### Quy trình:

1. **Rank candidates** → select_groups_greedy() sắp xếp tất cả nhóm theo final_score
2. **Distribute slots** → chia top_k câu hỏi giữa các nhóm đã rank
3. **Pick variants** → từ mỗi nhóm, chọn count câu hỏi bằng weighted sampling

---

## Tuning và Best Practices

### Điều chỉnh `diversity_weight`?

- **Tăng (0.5–1.0)**: Nếu đề thi có quá nhiều câu hỏi từ cùng một chủ đề
- **Giảm (0.0–0.2)**: Nếu cần match chặt chẽ với custom_text

### Điều chỉnh `random_level`?

- **"low"**: Đề thi tối ưu nhất (highest semantic relevance)
- **"medium"**: Cân bằng chất lượng và tính mới lạ (khuyến nghị)
- **"high"**: Đề thi đa dạng, tránh lặp lại

### Monitoring

Enable debug export:
```
LOG_RESULTS=true
```

Kiểm tra `/debug/` → danh sách nhóm được chọn + điểm số

---

## Tóm tắt Công Thức

| Thành phần | Công thức | Ảnh hưởng chính |
|-----------|----------|----------------|
| **score** | sim×0.7 + exist_score×0.3 | Cân bằng semantic + novelty |
| **sim** | cosine(query, group_emb) | 70% của score |
| **exist_score** | 1/(existence_count+1)^alpha | 30% của score |
| **penalty** | max cosine(group, selected_*) | Phạt nhóm giống nhau |
| **final_score** | score - penalty×weight | Điểm chọn |

