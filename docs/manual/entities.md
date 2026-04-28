## DB

### 1. Nhóm bảng chung

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

### 2. Nhóm bảng Document

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

### 3. Nhóm bảng exam test

user_test_attempts

```jsx
+ id: uuid
+ user_id: uuid
+ exam_test_id: uuid
+ attempt_records: jsonb
+ score: decimal(3, 2)
+ created_at: timestamp
+ updated_at: timestamp
```

user_test_attempt_answers

```json
+ id: uuid
+ attempt_id: uuid
+ question_id: uuid
+ selected_answer_id: uuid
+ is_correct: boolean
+ time_spent: bigint
+ created_at: timestamp
+ updated_at: timestamp
```

exam_templates

```jsx
+ id: uuid
+ name: varchar(255)
+ subject: varchar(50)
+ generation_config: jsonb
+ created_at: timestamp
+ updated_at: timestamp
```

exam_instances

```jsx
+ id: uuid
+ exam_template_id: uuid
+ parent_exam_instance_id: uuid | null // other exam instance variant
+ exported_file_id: uuid | null
+ exam_test_code: varchar(255)
+ is_exported: boolean
+ created_at: timestamp
+ updated_at: timestamp
```

exam_test_sections

```jsx
+ id: uuid
+ exam_instance_id: uuid
+ name: varchar(255)
+ order_index: int
```

question_exam_tests

```jsx
+ id: uuid
+ question_group_id: uuid
+ question_id: uuid
+ exam_test_section_id: uuid
+ order_count: int
+ created_at: timestamp
+ updated_at: timestamp
```
