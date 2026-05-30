# Nghiệp vụ: Tạo đề thi gốc (Base Exam Generation)

**Service**: `src/services/core/base_exam_generation_service.py`  
**Class**: `BaseExamGenerationService`

---

## Tổng quan

Đây là lõi thuật toán tạo **đề thi gốc** (`is_base=True`). Đề thi gốc là đề dùng để sinh ra các phiên bản (versions) đề thi sau này. Service này chỉ xử lý thuần tuý việc chọn câu hỏi và tạo cấu trúc đề — không quản lý template lifecycle hay trạng thái đề thi (những việc đó thuộc về `ExamService`).

---

## Hai chế độ tạo đề

### Chế độ 1 — Tái sinh từ template (`template_id` được cung cấp)
- Tải template từ DB theo `template_id`.
- Nếu `sections` truyền vào rỗng: dùng `generation_config` mặc định của template (JSON).
- Nếu `sections` truyền vào có dữ liệu: **override** config của template.

### Chế độ 2 — Tạo đề một lần (`template_id = null`)
- Yêu cầu bắt buộc: `subject` và `sections`.
- Không lưu template; chỉ tạo một `ExamInstance` độc lập.

---

## Luồng tạo đề chi tiết

```
GenerateBaseExamRequest
        │
        ▼
_resolve_sections()
  ├─ [Mode 1] Load template → dùng/override generation_config
  └─ [Mode 2] Dùng sections trực tiếp
        │
        ▼
_create_exam_instance()
  ├─ Tạo ExamInstance (status=PENDING)
  ├─ Duyệt từng SectionConfig
  │     ├─ Tạo ExamTestSection
  │     ├─ [skip_group_filtering=true]  → _pick_questions_directly()
  │     └─ [skip_group_filtering=false] → _retrieve_candidate_groups()
  │                                          → select_groups_greedy()
  │                                          → _distribute_slots()
  │                                          → _pick_variants()
  ├─ Mỗi câu hỏi: _shuffle_answers() → tạo QuestionExamTest
  └─ increment_exam_counts() (cập nhật usage counter)
        │
        ▼
      ExamInstance
```

---

## Hai chiến lược chọn câu hỏi

### Chiến lược A — Chọn thẳng câu hỏi (`skip_group_filtering = true`)

Dùng khi muốn kiểm soát chính xác câu hỏi, bỏ qua tầng nhóm ngữ nghĩa.

**Các bước:**

1. **Truy vấn câu hỏi** theo `subject`, `topic[]`, `difficulty`, chỉ lấy câu hỏi gốc (`parent_question IS NULL`) và đã được duyệt (`status = APPROVED`).

2. **Fallback độ khó**: Nếu không tìm được câu nào với độ khó yêu cầu, thử theo thứ tự:
   - `easy` → `medium` → `hard`
   - `medium` → `easy` → `hard`
   - `hard` → `medium` → `easy`

3. **Lọc loại câu hỏi** (`question_type`): Nếu config có chỉ định, lọc bỏ câu không khớp.

4. **Xếp hạng theo ngữ nghĩa** (tùy chọn): Nếu `custom_text` được cung cấp, embed văn bản này thành vector rồi sort câu hỏi theo cosine similarity giảm dần. Lấy pool `5 × top_k` câu hàng đầu để giảm phạm vi sampling.

5. **Weighted sampling không hoàn lại**: Chọn `top_k` câu từ pool. Trọng số của mỗi câu = `1 / (variant_existence_count + 1)` — câu ít được dùng có xác suất chọn cao hơn.

---

### Chiến lược B — Chọn qua nhóm ngữ nghĩa (`skip_group_filtering = false`) *(mặc định)*

Dùng khi muốn đề thi đa dạng về nội dung, tránh lặp câu hỏi cùng chủ đề.

**Các bước:**

#### Bước 1 — Tìm nhóm câu hỏi ứng viên (`_retrieve_candidate_groups`)
- Query `QuestionGroup` theo `subject`, `topic[]`, `difficulty`.
- Fallback độ khó tương tự chiến lược A.
- Lọc theo `question_type` nếu có: kiểm tra ít nhất một câu hỏi trong nhóm có đúng loại.
- **Nếu có `custom_text`**: embed → cosine search không ngưỡng → lấy top `5 × top_k` nhóm gần nhất về ngữ nghĩa.
- **Nếu không có `custom_text`**: random sample `5 × top_k` nhóm từ danh sách (tránh quét toàn bộ).

#### Bước 2 — Xếp hạng nhóm theo diversity + semantic (`select_groups_greedy`)
Thuật toán **greedy** chọn lần lượt nhóm có điểm cao nhất, tính theo công thức:

```
final_score = compute_score(embedding, query_vec, existence_count, random_level)
            - diversity_penalty × 0.3
```

- `compute_score`: Kết hợp độ phổ biến thấp (nhóm ít dùng được ưu tiên) + độ tương đồng với `query_vec` (nếu có) + nhiễu ngẫu nhiên theo `random_level`.
- `diversity_penalty`: Cosine similarity cao nhất với các nhóm đã chọn trước — nhóm quá giống nhóm đã chọn bị phạt.
- Kết quả: Danh sách nhóm được xếp hạng theo thứ tự tốt nhất → kém nhất.

#### Bước 3 — Phân bổ slot câu hỏi (`_distribute_slots`)
Chia đều `top_k` câu cho các nhóm đã xếp hạng. Phần dư được cộng vào các nhóm đầu.

```
Ví dụ: 4 nhóm, top_k=15
→ {nhóm0: 4, nhóm1: 4, nhóm2: 4, nhóm3: 3}
```

#### Bước 4 — Chọn câu hỏi từ mỗi nhóm (`_pick_variants`)
Trong mỗi nhóm, chọn câu theo weighted sampling không hoàn lại giống chiến lược A.  
Trọng số = `1 / (variant_existence_count + 1)`.

---

## Xử lý đáp án (`_shuffle_answers`)

Sau khi chọn câu hỏi, đáp án được **shuffle ngẫu nhiên** thứ tự. Kết quả là một mảng index `[2, 0, 3, 1]` lưu vào `answer_order` của `QuestionExamTest` — dùng để render đề thi với thứ tự đáp án khác nhau giữa các phiên bản.

---

## Cập nhật thống kê (`increment_exam_counts`)

Sau khi tạo xong toàn bộ đề, hệ thống tăng bộ đếm:
- `QuestionGroup.existence_count` cho tất cả nhóm được dùng
- `Question.variant_existence_count` cho tất cả câu hỏi được chọn

Điều này ảnh hưởng trực tiếp đến xác suất chọn trong lần tạo tiếp theo (câu/nhóm đã dùng nhiều sẽ ít được ưu tiên hơn).

---

## Cấu hình đầu vào — `SectionConfig`

| Trường | Kiểu | Bắt buộc | Mô tả |
|--------|------|----------|-------|
| `name` | `str` | ✓ | Tên phần (ví dụ: "Phần 1 - Trắc nghiệm") |
| `subject` | `str` | ✓ | Mã môn học |
| `topic` | `str \| List[str]` | ✓ | Mã chủ đề (một hoặc nhiều) |
| `difficulty` | `str` | ✓ | Độ khó: `easy`, `medium`, `hard` |
| `question_type` | `str \| List[str] \| null` | | Loại câu hỏi; `null` = tất cả loại |
| `top_k` | `int` | ✓ | Số câu hỏi cần chọn cho phần này |
| `random_level` | `str` | | Mức ngẫu nhiên: `low`, `medium`, `high` (mặc định: `medium`) |
| `custom_text` | `str \| null` | | Văn bản gợi ý ngữ nghĩa để tìm câu hỏi liên quan |
| `skip_group_filtering` | `bool` | | `true` = chọn thẳng câu hỏi, bỏ qua tầng nhóm (mặc định: `false`) |

---

## Sơ đồ quyết định chọn chiến lược

```
skip_group_filtering?
    ├─ true  → Chiến lược A (trực tiếp)
    │           └─ Nhanh hơn, kiểm soát chặt hơn
    │              Phù hợp: đề nhỏ, topic hẹp, cần lấy đúng loại câu
    └─ false → Chiến lược B (qua nhóm)  ← mặc định
                └─ Đa dạng nội dung hơn, tránh trùng lặp ngữ nghĩa
                   Phù hợp: đề lớn, cần phân bổ chủ đề đồng đều
```

---

## Ghi chú quan trọng

- **Câu hỏi hợp lệ**: Chỉ lấy câu gốc (`parent_question IS NULL`) và đã được duyệt (`status = APPROVED`). Câu hỏi con (sub-questions) không bao giờ được chọn trực tiếp.
- **Vector embedding**: Cả `QuestionGroup` và `Question` đều có embedding 768 chiều. Nếu thiếu embedding, câu/nhóm đó bị bỏ qua khi tính cosine.
- **`custom_text`**: Cần `llm_client` khởi tạo mới hoạt động. Nếu không có client hoặc embed thất bại, sẽ dùng random sampling thay thế.
- **Trạng thái ban đầu**: Mọi `ExamInstance` mới tạo đều có `status = PENDING`.

---

## Logic tạo Template

**Route**: `POST /templates`  
**Request DTO**: `SaveExamTemplateRequest`

### Luồng xử lý

```
SaveExamTemplateRequest
        │
        ▼
ExamService.save_template()
  ├─ Kiểm tra: template_id có → UPDATE; null → CREATE
  ├─ Validate generation_config (JSON)
  ├─ Lưu template: name, subject, generation_config, created_by_id
  └─ Return: ExamTemplate
        │
        ▼
Log audit: ACTION=CREATE/UPDATE
  └─ before_data: {name, subject} (nếu update)
  └─ after_data: {name, subject}
        │
        ▼
Response:
  ├─ template.id, name, subject
  ├─ generation_config (parsed JSON từ DB)
  └─ HTTP 200
```

### Điều kiện

- **CREATE** (`template_id = null`): Tạo template mới, lưu `generation_config` dạng JSON string.
- **UPDATE** (`template_id != null`): Cập nhật template hiện có, có thể đổi `name`, `subject`, hoặc `generation_config`.
- **Quyền**: `created_by_id` = user hiện tại.
- **Audit**: Log hành động tạo/cập nhật cùng IP address.

---

## Ví dụ JSON Tạo Template

### Request: Tạo template mới

```json
{
  "name": "Đề Toán lớp 10 - Học kỳ 1",
  "subject": "math",
  "generation_config": [
    {
      "name": "Phần 1: Trắc nghiệm",
      "subject": "math",
      "topic": ["algebra", "geometry"],
      "difficulty": "medium",
      "question_type": "multiple_choice",
      "top_k": 10,
      "random_level": "medium",
      "skip_group_filtering": false
    },
    {
      "name": "Phần 2: Tự luận",
      "subject": "math",
      "topic": "algebra",
      "difficulty": "hard",
      "question_type": "essay",
      "top_k": 2,
      "random_level": "low",
      "custom_text": "Giải phương trình bậc hai, bất phương trình",
      "skip_group_filtering": false
    }
  ]
}
```

### Response: Template tạo thành công

```json
{
  "code": 200,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Đề Toán lớp 10 - Học kỳ 1",
    "subject": "math",
    "generation_config": [
      {
        "name": "Phần 1: Trắc nghiệm",
        "subject": "math",
        "topic": ["algebra", "geometry"],
        "difficulty": "medium",
        "question_type": "multiple_choice",
        "top_k": 10,
        "random_level": "medium",
        "skip_group_filtering": false
      },
      {
        "name": "Phần 2: Tự luận",
        "subject": "math",
        "topic": "algebra",
        "difficulty": "hard",
        "question_type": "essay",
        "top_k": 2,
        "random_level": "low",
        "custom_text": "Giải phương trình bậc hai, bất phương trình",
        "skip_group_filtering": false
      }
    ],
    "created_by_id": "user-123",
    "created_at": "2026-05-26T10:30:00Z"
  },
  "message": "Template saved successfully"
}
```

### Request: Cập nhật template hiện có

```json
{
  "template_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Đề Toán lớp 10 - Học kỳ 1 (Bản cập nhật)",
  "subject": "math",
  "generation_config": [
    {
      "name": "Phần 1: Trắc nghiệm",
      "subject": "math",
      "topic": ["algebra"],
      "difficulty": "easy",
      "question_type": "true_false",
      "top_k": 15,
      "random_level": "high",
      "skip_group_filtering": false
    }
  ]
}
```

---

## Ví dụ JSON Tạo Đề Thi

### Mode 1: Tạo từ Template (Regenerate)

```json
{
  "template_id": "550e8400-e29b-41d4-a716-446655440000",
  "sections": []
}
```

**Hành động**: Lấy `generation_config` từ template, không override.

---

### Mode 2: Tạo từ Template với Override Sections

```json
{
  "template_id": "550e8400-e29b-41d4-a716-446655440000",
  "sections": [
    {
      "name": "Phần 1: Trắc nghiệm (Override)",
      "subject": "math",
      "topic": "trigonometry",
      "difficulty": "hard",
      "question_type": "multiple_choice",
      "top_k": 20,
      "random_level": "medium",
      "skip_group_filtering": false
    }
  ]
}
```

**Hành động**: Override template config với `sections` được truyền vào.

---

### Mode 3: Tạo đề một lần (không dùng template)

```json
{
  "template_id": null,
  "subject": "physics",
  "sections": [
    {
      "name": "Phần 1: Cơ học",
      "subject": "physics",
      "topic": ["kinematics", "dynamics"],
      "difficulty": "medium",
      "question_type": null,
      "top_k": 8,
      "random_level": "medium",
      "custom_text": "Chuyển động, lực, gia tốc",
      "skip_group_filtering": false
    },
    {
      "name": "Phần 2: Điện từ",
      "subject": "physics",
      "topic": "electromagnetic",
      "difficulty": "hard",
      "question_type": "selection",
      "top_k": 5,
      "random_level": "low",
      "skip_group_filtering": true
    }
  ]
}
```

**Hành động**: Tạo exam standalone không liên kết template.

---

### Response: Đề thi tạo thành công

```json
{
  "code": 200,
  "data": {
    "exam_instance": {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "exam_test_code": "MT20260526001",
      "is_base": true,
      "status": 0,
      "exam_template_id": "550e8400-e29b-41d4-a716-446655440000",
      "parent_exam_instance": null,
      "created_by_id": "user-123",
      "sections": [
        {
          "id": "770e8400-e29b-41d4-a716-446655440001",
          "name": "Phần 1: Trắc nghiệm",
          "order_index": 0,
          "questions": [
            {
              "question_id": "880e8400-e29b-41d4-a716-446655440001",
              "question_text": "1 + 1 = ?",
              "question_type": "multiple_choice",
              "subject": "math",
              "topic": "algebra",
              "difficulty": "easy",
              "answers": [
                {
                  "id": "990e8400-e29b-41d4-a716-446655440001",
                  "value": "2",
                  "is_correct": true
                },
                {
                  "id": "990e8400-e29b-41d4-a716-446655440002",
                  "value": "3",
                  "is_correct": false
                }
              ],
              "answer_order": [1, 0],
              "order_count": 0
            }
          ]
        }
      ]
    },
    "total_questions": 10
  },
  "message": "Base exam generated successfully"
}
```

---

## Cấu hình chi tiết — `SectionConfig` (JSON)

| Trường | Kiểu | Yêu cầu | Ví dụ | Mô tả |
|--------|------|--------|--------|--------|
| `name` | string | ✓ | `"Phần 1: Trắc nghiệm"` | Tên phần hiển thị |
| `subject` | string | ✓ | `"math"` | Mã môn học |
| `topic` | string \| string[] | ✓ | `"algebra"` hoặc `["algebra", "geometry"]` | Chủ đề (đơn hoặc danh sách) |
| `difficulty` | string | ✓ | `"easy"`, `"medium"`, `"hard"` | Độ khó, fallback tự động nếu thiếu |
| `question_type` | string \| string[] \| null | | `"multiple_choice"`, `["true_false", "selection"]`, hoặc `null` | Loại câu; `null` = lấy tất cả loại |
| `top_k` | int | ✓ | `10`, `15`, `20` | Số câu hỏi cần chọn |
| `random_level` | string | | `"low"`, `"medium"`, `"high"` | Mức ngẫu nhiên (mặc định: `"medium"`) |
| `custom_text` | string \| null | | `"Phương trình bậc hai, bất phương trình"` | Gợi ý ngữ nghĩa (embedding) |
| `skip_group_filtering` | bool | | `true` hoặc `false` | Bỏ qua tầng nhóm, chọn thẳng (mặc định: `false`) |
