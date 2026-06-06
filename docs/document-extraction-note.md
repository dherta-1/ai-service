# Document Extraction Pipeline - Tìm/Tạo Question Groups

## Tổng Quan

Khi trích xuất câu hỏi từ tài liệu, mỗi câu hỏi cần được gán vào một QuestionGroup. Hệ thống sử dụng **two-step matching approach** để tìm hoặc tạo nhóm phù hợp:

1. **Bước 1**: Lọc ứng viên theo taxonomy (subject, topic, difficulty) và user
2. **Bước 2**: Tìm vector match hoặc tạo nhóm mới

---

## Bước 1: Lọc Question Groups Theo Taxonomy

**Mục Đích**: 
- Giới hạn không gian tìm kiếm tới các groups có cùng metadata cơ bản
- Đảm bảo groups chỉ được tái sử dụng cho câu hỏi cùng subject/topic/difficulty
- Scope theo user để multi-tenancy (không mix questions giữa các users)

**Pseudo Code**:

```
FUNCTION filter_candidates_by_taxonomy(subject, topic, difficulty, uploaded_by_id):
    candidates ← DB.SELECT(QuestionGroup)
    
    candidates ← candidates.WHERE(
        (QuestionGroup.subject == subject)
        AND (QuestionGroup.topic == topic)
        AND (QuestionGroup.difficulty == difficulty)
    )
    
    IF uploaded_by_id NOT NULL:
        candidates ← candidates.WHERE(QuestionGroup.from_user_id == uploaded_by_id)
    
    RETURN candidates.execute()
```

**Ý nghĩa**:
- Tìm tất cả groups với subject, topic, difficulty khớp
- Tùy chọn scope theo user (nếu có uploaded_by_id)
- Kết quả: danh sách candidate groups cùng taxonomy

**Output**: List[QuestionGroup] hoặc empty list (nếu không có groups)

---

## Bước 2: Tìm Vector Match Hoặc Tạo Nhóm Mới

**Mục Đích**:
- Tìm group có vector embedding tương tự (reuse group)
- Hoặc tạo group mới nếu không có match
- Đảm bảo semantic similarity giữa các câu hỏi trong cùng group

**Pseudo Code**:

```
FUNCTION find_or_create_group(subject, topic, difficulty, question_vector, threshold, uploaded_by_id):
    // Step 2.1: Lấy candidate groups từ bước 1
    candidates ← filter_candidates_by_taxonomy(subject, topic, difficulty, uploaded_by_id)
    
    // Step 2.2: Tìm vector match từ candidates
    IF candidates NOT EMPTY AND question_vector NOT NULL:
        matches ← cosine_search(candidates, question_vector, threshold)
        
        IF matches NOT EMPTY:
            best_group ← matches[0]  // Get group với similarity cao nhất
            LOG: "Reused QuestionGroup: " + best_group.id
            RETURN best_group
    
    // Step 2.3: Không có match → tạo group mới
    new_group ← DB.CREATE(QuestionGroup,
        subject = subject,
        topic = topic,
        difficulty = difficulty,
        vector_embedding = question_vector OR [],
        from_user_id = uploaded_by_id
    )
    
    LOG: "Created new QuestionGroup: " + new_group.id
    RETURN new_group
```

**Chi Tiết từng Sub-step**:

### **Step 2.1: Lấy Candidates**
- Gọi kết quả từ Bước 1 (filter_candidates_by_taxonomy)
- Danh sách groups có cùng taxonomy

### **Step 2.2: Cosine Search**
```
FUNCTION cosine_search(candidates, question_vector, threshold):
    results ← []
    
    FOR EACH group IN candidates:
        IF group.vector_embedding IS NULL:
            CONTINUE
        
        similarity ← cosine_similarity(group.vector_embedding, question_vector)
        
        IF similarity >= threshold:
            results.append((similarity, group))
    
    // Sort by similarity DESC
    results.sort(BY similarity DESC)
    
    RETURN [group FOR (_, group) IN results]
```

**Output**: Sorted list of groups với similarity >= threshold (best first)

### **Step 2.3: Create or Reuse Decision**
```
IF matches FOUND:
    // Reuse best match (highest similarity)
    RETURN matches[0]
ELSE:
    // Create new group
    RETURN DB.CREATE(QuestionGroup, ...)
```

---

## Thông Số Quan Trọng

| Thông Số | Mặc định | Ý nghĩa |
|----------|---------|---------|
| `similarity_threshold` | 0.5 (có thể 0.75) | Similarity tối thiểu để reuse group |
| `uploaded_by_id` | NULL | Scope user (multi-tenancy) |
| `vector_embedding` | [] (empty) | Vector embedding nếu không có |

---

## Workflow Đầy Đủ

```
FOR EACH question IN extracted_questions:
    subject ← question.subject
    topic ← question.topic
    difficulty ← question.difficulty
    vector ← question.vector_embedding
    
    // Bước 1: Filter by taxonomy
    candidates ← find_candidates(subject, topic, difficulty, uploaded_by_id)
    
    // Bước 2.1: Cosine search
    IF candidates NOT EMPTY:
        matches ← cosine_search(candidates, vector, threshold)
        
        IF matches NOT EMPTY:
            group ← matches[0]  // Reuse
        ELSE:
            group ← create_new_group(...)  // Create
    ELSE:
        group ← create_new_group(...)  // Create
    
    // Gán group_id cho question
    question.group_id ← group.id
```

---

## Ví Dụ Thực Tế

**Scenario 1: Reuse Group**
```
Input:
  - subject = "TOÁN"
  - topic = "ĐẠI SỐ"
  - difficulty = "MEDIUM"
  - question_vector = [0.1, 0.2, 0.3, ...]
  - threshold = 0.75

Step 1 (Taxonomy):
  - candidates = [Group-A, Group-B, Group-C]  // 3 groups cùng TOÁN/ĐẠI SỐ/MEDIUM

Step 2 (Vector search):
  - Group-A similarity = 0.92 ≥ 0.75 ✓
  - Group-B similarity = 0.88 ≥ 0.75 ✓
  - Group-C similarity = 0.50 < 0.75 ✗
  - matches = [Group-A (0.92), Group-B (0.88)]
  - best = Group-A

Output:
  - Reuse Group-A
  - question.group_id = Group-A.id
```

**Scenario 2: Create New Group**
```
Input:
  - subject = "VẬT LÝ"
  - topic = "ĐIỆN"
  - difficulty = "HARD"
  - question_vector = [0.5, 0.6, 0.7, ...]
  - threshold = 0.75

Step 1 (Taxonomy):
  - candidates = []  // Không có groups VẬT LÝ/ĐIỆN/HARD

Step 2 (Vector search):
  - Skip (không có candidates)

Output:
  - Create new group: Group-D
  - question.group_id = Group-D.id
```

---

## Multi-Tenancy & User Scope

Groups được tạo với `from_user_id` để isolate data per user:

```
FUNCTION find_or_create_group(subject, topic, difficulty, vector, threshold, uploaded_by_id):
    // Lấy groups của user này thôi
    candidates ← find_by_metadata(subject, topic, difficulty, from_user_id=uploaded_by_id)
    
    // Search in user's groups only
    matches ← cosine_search(candidates, vector, threshold)
    
    IF matches:
        RETURN matches[0]
    
    // Tạo new group cho user này
    RETURN create_with_vector(subject, topic, difficulty, vector, from_user_id=uploaded_by_id)
```

**Lợi ích**:
- Không mix questions giữa users
- Mỗi user có taxonomy riêng
- Flexibility: user A có Group-X với 10 questions, user B có Group-X khác với 5 questions
