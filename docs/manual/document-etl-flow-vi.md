# Luồng trích xuất câu hỏi từ tài liệu

### Các bảng liên quan

users

```jsx
+ id: uuid
+ name: varchar(255)
+ email: varchar(255)
+ hash_password: varchar(255)
+ role: teacher | student
+ reset_password_token: varchar(50)
+ last_login_at: date
+ created_at: timestamp
+ updated_at: timestamp
```

file_metadatas

```jsx
+ id: uuid
+ name: varchar(255)
+ path: varchar(1024)
+ size: bigint
+ mime_type: varchar(255)
+ object_key: varchar(255)
```

tasks

```jsx
+ id: uuid
+ name: varchar(255)
+ type: varchar(50)
+ entity_id: uuid
+ entity_type: varchar(50)
+ logs: jsonb
+ status: smallint
+ progress: real
```

subjects

```jsx
+ id: uuid
+ name: varchar(255)
+ code: varchar(255)
+ created_at: timestamp
+ updated_at: timestamp
```

topics

```jsx
+ id: uuid
+ name: varchar(255)
+ code: varchar(255)
+ created_at: timestamp
+ updated_at: timestamp
```

documents

```jsx
+ id: uuid
+ file_id: uuid
+ uploaded_by: uuid
+ name: varchar(255)
+ status: smallint
+ progress: real
+ created_at: timestamp
+ updated_at: timestamp
```

pages

```jsx
+ id: uuid
+ document_id: uuid
+ page_image_id: uuid
+ page_number: int
+ content: text
+ image_list: jsonb
+ created_at: timestamp
+ updated_at: timestamp
```

questions_groups

```json
+ id: uuid
+ subject: varchar(255)
+ topic: varchar(255)
+ difficulty: varchar(50)
+ existence_count: bigint
+ vector_embedding: vector(768)
+ created_at: timestamp
+ updated_at: timestamp
```

questions

```jsx
+ id: uuid
+ page_id: uuid | null //null for manual created
+ parent_question_id: uuid | null // for composite question_type
+ questions_group_id: uuid
+ question_text: text
+ question_type: varchar(50)
+ difficulty: varchar(50) | null //null for sub_question (parent_question_id != null)
+ subject: varchar(255) | null // null for sub_question (parent_question_id != null)
+ topic: varchar(255) // null for sub_question (parent_question_id != null)
// null for sub_question (parent_question_id != null)
+ image_list: jsonb // null for sub_question (parent_question_id != null)
+ variant_existence_count: bigint
+ vector_embedding: vector(768)
+ status: smallint
+ created_at: timestamp
+ updated_at: timestamp
```

answers

```jsx
+ id: uuid
+ question_id: uuid
+ value: varchar(512)
+ is_correct: boolean
+ explaination: text
+ created_at: timestamp
+ updated_at: timestamp
```

### Flow:

- Người dùng upload file PDF ⇒ lưu file pdf vào s3 và tạo record document
- Người dùng send request extract-document ⇒ hệ thống send event queue
- Backend xử lý với các workers:
  - OCR + Validate Worker: Lấy event Xử lý trích xuất nội dung từng trang + validate ⇒ pass page_id qua event
  - Question Extraction + Embed Worker: Nhận event ⇒ Truy xuất page id ⇒ load nội dung page ra ⇒ xử lý trích xuất nội dung câu hỏi và embed nội dung câu hỏi và persist trong db
- Người dùng duyệt câu hỏi cần thêm vào ngân hàng đề thi

### Bài toán cần giải quyết

- Trích xuất nội dung câu hỏi
- Persist nội dung câu hỏi như thế nào
- Duyệt câu hỏi: duyệt theo trang sau khi đã hoàn thành xong luồng 1 cách manual

### Trích xuất nội dung câu hỏi

1. Người dùng upload file PDF ⇒ các page_image
2. OCR Xử lý trích xuất theo trang ⇒ các content_block
3. LLM Đối chiều page_image với các content_block ⇒ validated content
4. LLM dùng validated content để trích xuất câu hỏi ⇒ questions
5. Với mỗi câu hỏi, embed nội dung câu hỏi: embed question_text và answers nếu có

### Persist câu hỏi

Với từng câu hỏi cần persist

1. Embed trước nội dung câu hỏi
2. Query hết question_group theo các metadata của câu hỏi: `subject`, `topic`, `difficulty`
3. Tiến hành cosine search với embedded vector của `question` cần insert với embedded vector của `questions_group` để filter các group có độ tương quan đạt threshold cụ thể. Nếu có question_group record, lưu câu hỏi đó vào group có similarity cao nhất tương ứng. Nếu không, tạo `questions_group` mới với vector_embedding là vector của câu hỏi đó
4. Khi lưu các câu hỏi.
   - question_type ≠ composite: lưu bình thường
   - question_type == composite, lưu thêm question với parent_question_id là question composite đó
   - Đối với các câu trả lời:
     - Prompt nên chỉnh về là chỉ trả mảng `answers` là đủ, không cần correct_answer vì answer có structure như sau:

     ```json
     {
     	"value": "answer value"
     	"is_correct": "boolean"
     }
     ```

     - Đối với question_type dạng non-choice, vẫn trả về tương tự kiểu này, nhưng chỉ có 1 record và nó có `is_correct` == true

**Note** :

- Xử lý job phải có quá trình update tiến độ + log task theo document_id, với mỗi page, đều có nhiều trang. Nên có cờ mark is_final_page để hỗ trợ cập nhật tiến độ hoàn thành
- Flow cũ hiện tại của hệ thống cũng cơ bản OK, tuy nhiên cần tách luồng ra để làm 1 tí kiến trúc event-driven, cụ thể là quá trình ingest tài liệu này
