Luồng ổn nên tách **template / instance / delivery token** rõ ràng:

```txt
Exam Template
  └─ chứa cấu trúc đề: môn, thời gian, số câu, rule chọn câu hỏi, điểm, taxonomy...

Exam Instance
  └─ một mã đề đã random từ template
  └─ chứa danh sách question_id đã chọn + thứ tự câu + thứ tự đáp án
  └─ KHÔNG expose trực tiếp instance_id ra FE

Exam Session / Attempt
  └─ phiên làm bài của user
  └─ FE chỉ nhận delivery_token / attempt_token dạng opaque
```

## Luồng tạo đề nên như sau

```txt
1. Admin tạo Exam Template
   - cấu hình rule chọn câu hỏi
   - ví dụ: 10 câu dễ, 15 câu trung bình, 5 câu khó
   - theo chapter, taxonomy, skill, question type...

2. Khi user bắt đầu thi:
   BE nhận: template_id + user_id

3. BE random ra Exam Instance
   - chọn câu hỏi theo rule
   - shuffle thứ tự câu
   - shuffle đáp án nếu cần
   - lưu snapshot lại DB

4. BE tạo Exam Attempt
   - attempt_id internal
   - exam_instance_id internal
   - user_id
   - started_at, expires_at, status

5. BE trả về FE:
   - attempt_token
   - danh sách câu hỏi đã được sanitize
   - KHÔNG trả exam_instance_id
   - KHÔNG trả answer_key
   - KHÔNG trả question bank metadata nhạy cảm

6. User submit:
   FE gửi attempt_token + answers

7. BE decode/lookup attempt_token
   - lấy attempt_id
   - lấy exam_instance_id internal
   - chấm điểm bằng answer_key trong server
```

## Điểm quan trọng về bảo mật

Không nên để FE thấy:

```txt
exam_template_id thật nếu không cần
exam_instance_id
question_bank_id
question_id gốc nếu có thể tránh
correct_answer
difficulty nội bộ
taxonomy/path nếu có thể suy ra đáp án hoặc nguồn đề
identity value của mã đề
```

FE chỉ nên thấy:

```txt
attempt_token
display_question_no
question_content
answer_options đã shuffle
option_token hoặc option_key dạng opaque
```

Ví dụ thay vì trả:

```json
{
  "exam_instance_id": "einst_123",
  "question_id": "q_999",
  "options": [{ "id": "A", "is_correct": false }]
}
```

nên trả:

```json
{
  "attempt_token": "opaque_token_here",
  "questions": [
    {
      "question_no": 1,
      "question_token": "opaque_question_token",
      "content": "...",
      "options": [
        {
          "option_token": "opaque_option_token",
          "content": "..."
        }
      ]
    }
  ]
}
```

## Cách random instance

Nên lưu snapshot, không random lại mỗi lần gọi API:

```txt
exam_instance_questions
- exam_instance_id
- question_id
- display_order
- points

exam_instance_options
- exam_instance_id
- question_id
- option_id
- display_order
```

Lý do: nếu user reload trang, thứ tự câu/đáp án vẫn giữ nguyên.

## Token nên làm kiểu nào?

Có 2 cách tốt:

### Cách 1: Opaque token + DB lookup

```txt
attempt_token = random 256-bit string
```

DB lưu hash của token:

```txt
attempt_token_hash -> attempt_id
```

Ưu điểm: bảo mật tốt, revoke được, không lộ metadata.

Đây là cách mình khuyên dùng cho thi cử.

### Cách 2: JWT/JWE

Có thể dùng, nhưng không nên chứa `exam_instance_id` plain trong JWT. Nếu dùng thì nên dùng **JWE encrypted token** , hoặc JWT chỉ chứa `attempt_id` dạng public-safe.

## Luồng API gợi ý

```txt
POST /exam-templates/{template_id}/attempts
→ tạo attempt + random instance
→ trả đề đã sanitize

GET /exam-attempts/current
→ lấy lại attempt đang làm bằng token/session

POST /exam-attempts/{attempt_token}/submit
→ nộp bài

GET /exam-attempts/{attempt_token}/result
→ xem kết quả nếu được phép
```

## Kết luận

Thiết kế ok nhất là:

```txt
Template dùng để cấu hình đề
Instance dùng để snapshot mã đề đã random
Attempt dùng để user làm bài
FE chỉ cầm opaque token
BE giữ toàn bộ identity thật + answer key
```

Không expose `exam_instance_id` là đúng. Nên dùng `attempt_token` opaque random, lưu mapping ở server, và mọi thao tác làm bài/chấm bài đều đi qua token đó.
