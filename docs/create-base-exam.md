# Luồng Tạo Đề Thi (Generate Base Exam)

## Tổng Quan

Luồng tạo đề thi là quá trình tạo một thể hiện đề thi từ template hoặc từ cấu hình section trực tiếp. Hệ thống hỗ trợ hai chế độ:

- **Template Mode**: Tạo đề thi từ template được lưu trước
- **One-Off Mode**: Tạo đề thi độc lập với cấu hình trực tiếp

Xử lý bởi `BaseExamGenerationService` (thuật toán) và `ExamService` (quản lý vòng đời).

---

## Các Thành Phần Chính

### Route Handler (exam_route.py)

Tiếp nhận request POST /generate-base, xác thực người dùng, gọi BaseExamGenerationService để sinh đề thi, sau đó gọi ExamService để xây dựng dữ liệu response.

### Exam Service (exam_service.py)

Quản lý vòng đời của template và exam instance: CRUD template, cập nhật status exam, thay thế questions, xây dựng response data đầy đủ. Không chứa logic sinh đề thi.

### Base Exam Generation Service (base_exam_generation_service.py)

Chứa thuật toán sinh đề thi cơ bản. Phương thức chính là `generate_base_exam()` gọi qua các bước xử lý sections và chọn questions.

---

## 5 Bước Chính

### Bước 1: Resolve Sections

Xác định danh sách section config cuối cùng:

- Nếu template_id được cung cấp: Load từ template, có thể override bằng sections từ request
- Nếu template_id null: Sử dụng sections từ request, subject bắt buộc
- Validate: sections list không được trống

### Bước 2: Tạo Exam Instance Record

Tạo exam instance cơ sở dữ liệu với status PENDING. Khởi tạo tracking lists để theo dõi groups và questions được sử dụng (dùng cho việc cập nhật existence_count sau).

### Bước 3: Xử Lý Sections (Loop)

Với mỗi section, tạo ExamTestSection record và chọn questions dựa trên cấu hình section.

#### **Nhánh 3A: Direct Picking** (skip_group_filtering=true)

Chọn questions trực tiếp theo tiêu chí (subject, topic, difficulty, question_type):

1. Lấy questions từ DB với difficulty fallback
2. Nếu custom_text: Embed bằng LLM, rank theo cosine similarity, lấy top 5 * top_k
3. Weighted sampling: Chọn top_k questions với xác suất inversely proportional to variant_existence_count
4. Tạo QuestionExamTest records, shuffle answers, track groups/questions

**Pseudo Code**:

```
FUNCTION pick_questions_directly(section):
    topics ← section.topic AS LIST
    question_types ← section.question_type AS LIST OR NULL
  
    questions ← DB.get_by_criteria_with_fallback(
        subject = section.subject,
        topics = topics,
        difficulty = section.difficulty,
        fallback_difficulties = DIFFICULTY_FALLBACKS[section.difficulty],
        question_types = question_types
    )
  
    IF section.custom_text EXISTS:
        query_embedding ← LLM.embed(section.custom_text)
        questions ← rank_by_cosine_similarity(questions, query_embedding)
        questions ← questions[0 : 5 * section.top_k]
  
    selected ← weighted_sampling_without_replacement(questions, section.top_k)
  
    RETURN selected
```

**Thuật Toán Weighted Sampling (weighted_sampling_without_replacement)**:

```
FUNCTION weighted_sampling_without_replacement(questions, k):
    selected ← []
    pool ← COPY(questions)
    k ← MIN(k, len(pool))
  
    FOR _ FROM 1 TO k:
        weights ← [1 / (q.variant_existence_count + 1) FOR q IN pool]
        probabilities ← normalize(weights)  // probabilities ← weights / SUM(weights)
        idx ← random_choice(probabilities)
        selected.append(pool[idx])
        pool.remove(pool[idx])
  
    RETURN selected
```

**Ý nghĩa**:

- Tính weights inversely proportional to existence_count (ít dùng → weight cao)
- Normalize thành probabilities (tổng = 1.0)
- k iterations: mỗi lần chọn 1 question dựa trên probabilities
- Remove sau khi chọn để avoid duplicates (without replacement)
- Kết quả: k questions, ưu tiên những questions ít dùng

#### **Nhánh 3B: Group-based Filtering** (skip_group_filtering=false - default)

Chọn questions thông qua groups với diversity guarantee:

1. Lấy candidate groups theo metadata (subject, topic, difficulty) với difficulty fallback
2. Filter groups theo question_type nếu có
3. Nếu custom_text: Embed, rank groups by cosine similarity, lấy top 5*top_k
4. Diversity-based ranking: Gọi `select_groups_greedy()` để rank toàn bộ groups theo diversity + similarity + random level
5. Distribute slots: Chia proportionally top_k slots cho ranked groups
6. Từ mỗi group, chọn questions dùng weighted sampling (giống nhánh A)
7. Tạo QuestionExamTest records cho tất cả questions đã chọn

**Pseudo Code**:

```
FUNCTION retrieve_candidate_groups(section):
    candidates ← DB.find_by_metadata(
        subject = section.subject,
        topic = section.topic,
        difficulty = section.difficulty
    )
  
    IF candidates IS EMPTY:
        FOR fallback_difficulty IN DIFFICULTY_FALLBACKS[section.difficulty]:
            candidates ← DB.find_by_metadata(
                subject = section.subject,
                topic = section.topic,
                difficulty = fallback_difficulty
            )
            IF candidates NOT EMPTY:
                BREAK
  
    IF candidates IS EMPTY:
        RETURN []
  
    IF section.question_type NOT NULL:
        filtered ← []
        FOR EACH group IN candidates:
            group_questions ← DB.get_by_group(group.id)
            IF ANY(q.question_type IN section.question_type FOR q IN group_questions):
                filtered.append(group)
        candidates ← filtered
  
    IF section.custom_text EXISTS:
        query_embedding ← LLM.embed(section.custom_text)
        candidates ← cosine_search(candidates, query_embedding, threshold=0.0)
        RETURN candidates[0 : 5 * section.top_k]
  
    k ← MIN(len(candidates), 5 * section.top_k)
    RETURN random_sample(candidates, k)
```

### Bước 4: Cập Nhật Existence Counts

Tăng `existence_count` cho tất cả groups và `variant_existence_count` cho tất cả questions được sử dụng. Dùng để weighted sampling lần sau ưu tiên items ít được dùng (fairness).

**Pseudo Code**:

```
FUNCTION increment_exam_counts(group_ids, question_ids):
    IF group_ids NOT EMPTY:
        DB.UPDATE(QuestionGroup)
            SET existence_count = existence_count + 1
            WHERE id IN group_ids
            EXECUTE()
  
    IF question_ids NOT EMPTY:
        DB.UPDATE(Question)
            SET variant_existence_count = variant_existence_count + 1
            WHERE id IN question_ids
            EXECUTE()
```

**Ý nghĩa**:

- Cập nhật tất cả groups đã dùng: tăng existence_count lên 1
- Cập nhật tất cả questions đã dùng: tăng variant_existence_count lên 1
- Bulk update (batch operation) cho efficiency
- Counts này dùng cho weighted sampling lần sinh đề tiếp theo

**Workflow**:

1. Sau khi chọn xong tất cả questions/groups cho exam
2. Track danh sách group_ids và question_ids đã chọn
3. Gọi `increment_exam_counts()` một lần
4. Tất cả counts được updated atomically
5. Lần sinh đề tiếp theo: weighted sampling sẽ ưu tiên items ít dùng (fairness)

### Bước 5: Build Response

Return exam instance, sau đó ExamService fetch sections/questions/answers từ DB và xây dựng response data đầy đủ.

---

## Template Mode vs One-Off Mode

| Khía Cạch                | Template Mode                        | One-Off Mode                  |
| -------------------------- | ------------------------------------ | ----------------------------- |
| **Input**            | template_id + optional sections      | sections + subject (required) |
| **Config Source**    | Load từ template                    | Direct từ request            |
| **Reusability**      | Cao - sinh nhiều exams từ template | Thấp - standalone instance   |
| **exam_template_id** | Set                                  | Null                          |
| **Use Case**         | Template chuẩn reuse                | Quick one-time exam           |

---

## Thuật Toán Weighted Sampling

**Mục Đích**:

- Đảm bảo công bằng (fairness) khi tái sử dụng questions
- Ưu tiên questions ít được dùng, tránh overuse một số questions
- Tăng độ đa dạng của exams được sinh ra

**Công thức**:

$$
\text{weight}_i = \frac{1}{\text{variant\_existence\_count}_i + 1}
$$

$$
\text{probability}_i = \frac{\text{weight}_i}{\sum_j \text{weight}_j}
$$

**Ý nghĩa**: Questions ít được dùng (variant_existence_count thấp) → weight cao → xác suất chọn cao.

**Ví dụ**: 3 questions với existence_count = [5, 1, 0]

- Q1: weight = 1/6 ≈ 0.167
- Q2: weight = 1/2 = 0.5
- Q3: weight = 1/1 = 1.0
- Total = 1.667
- P(Q1) ≈ 10%, P(Q2) ≈ 30%, P(Q3) ≈ 60%

---

## Thuật Toán Difficulty Fallback

**Mục Đích**:

- Đảm bảo exam generation không bị gián đoạn do thiếu dữ liệu
- Cân bằng giữa chính xác yêu cầu và tính khả thi
- Giữ mức độ khó tương đương khi phải lựa chọn khác

**Quy tắc Fallback**:

```
easy      → [medium, hard]
medium    → [easy, hard]
hard      → [medium, easy]
```

**Ví dụ**: Nếu yêu cầu 10 questions "easy" nhưng DB chỉ có 5, hệ thống sẽ lấy thêm từ "medium" (fallback priority 1), nếu vẫn không đủ thì lấy từ "hard" (fallback priority 2).

---

## Thuật Toán Semantic Ranking (Custom Text)

**Mục Đích**:

- Tìm questions/groups liên quan ngữ nghĩa với custom_text
- Cải thiện độ liên quan của exams với yêu cầu cụ thể
- Giảm số lần full-scan bằng cách lấy top pool trước khi sampling/selection

Nếu section có custom_text: Embed text bằng LLM, tính cosine similarity với question/group embeddings, rank và lấy top 5*top_k để optimize.

### Vector Cosine Search & Similarity Ranking

**Quy trình**:

1. **Embedding**: LLM embed custom_text thành vector embedding (dimension=768)
2. **Batch Scoring**: Tính cosine similarity giữa query embedding và tất cả question/group embeddings
3. **Ranking**: Sắp xếp candidates theo similarity score giảm dần
4. **Sampling Pool**: Lấy top 5*top_k để đảm bảo diversity (không chỉ top_k để tránh overfitting vào semantic match)

**Công thức cosine similarity**:

```
similarity(query, candidate) = dot_product(query_vec, candidate_vec) 
                               / (||query_vec|| × ||candidate_vec||)
```

**Chi tiết toán học**:

- `dot_product`: Tích vô hướng = Σ(query[i] × candidate[i])
- `||vec||`: Norm L2 = sqrt(Σ(vec[i]²))
- Kết quả ∈ [0, 1] (1=identical, 0=orthogonal)

**Ví dụ số**:

```
query_vec = [0.1, 0.2, 0.3, ...]  (768 dimensions)
cand_vec  = [0.15, 0.21, 0.32, ...] 
dot = 0.1×0.15 + 0.2×0.21 + 0.3×0.32 + ... = 0.42
||query|| = sqrt(0.1² + 0.2² + 0.3² + ...) = 0.88
||cand||  = sqrt(0.15² + 0.21² + 0.32² + ...) = 0.95
similarity = 0.42 / (0.88 × 0.95) ≈ 0.50
```

**Áp dụng trong generate base exam**:

- **Direct Picking (nhánh 3A)**:

  - Rank questions by similarity → lấy top 5*top_k
  - Weighted sampling chọn final top_k từ pool này
  - Diversity tự nhiên từ weighted sampling (ít-dùng questions được ưu tiên)
- **Group-based Filtering (nhánh 3B)**:

  - Rank groups by similarity → lấy top 5*top_k candidates
  - Truyền query_embedding vào `select_groups_greedy()` để tính base_score
  - Base score kết hợp similarity (70%) + freshness (30%)
  - Greedy selection đảm bảo: similarity cao + không duplicate + freshness

**Threshold & Filtering**:

- **Direct Picking**: Không threshold — ranking by similarity, lấy top 5*top_k rồi sample
- **Group-based**: Cosine search với threshold=0.0 (no threshold) — sort by similarity, lấy top 5*top_k
- Không filter hứng strict vì semantic relevance là soft signal, không hard constraint

---

## Thuật Toán Xếp hạng theo Đa dạng Semantic (Diversity-based Ranking)

**Mục Đích**:

- Chọn groups vừa phù hợp semantic (relevant), vừa đa dạng (non-redundant)
- Tránh duplicate questions trong cùng một exam
- Cân bằng giữa relevance (từ custom_text), freshness (ít dùng), và diversity
- Đảm bảo exam coverage rộng hơn thay vì tập trung vào top matches

Khi chọn groups (nhánh 3B), hệ thống dùng `select_groups_greedy()` để xếp hạng tất cả candidate groups theo ba tiêu chí: độ tương tự semantic, độ đa dạng, và độ mới (freshness).

### Công thức Toán học

**1. Điểm số cơ sở (Base Score)**:

$$
\text{score}(g) = 0.7 \times \text{similarity}(g) + 0.3 \times \text{exist\_score}(g)
$$

Với:

- $\text{similarity}(g) = \text{cosine\_sim}(g.\text{embedding}, q.\text{embedding})$ (hoặc 0 nếu không có query embedding từ custom_text)
- $\text{exist\_score}(g) = \frac{1}{(\text{existence\_count}(g) + 1)^{\alpha}}$
- $\alpha \in \{0.1, 0.5, 1.0\}$ tùy theo `section.random_level`

**2. Penalty về Đa dạng (Diversity Penalty)**:

$$
\text{penalty}(g) = \max_{g_s \in G_{\text{selected}}} \{\text{cosine\_sim}(g.\text{embedding}, g_s.\text{embedding})\}
$$

Nếu $G_{\text{selected}}$ rỗng hoặc embedding thiếu: $\text{penalty}(g) = 0$

**3. Điểm số Cuối cùng (Final Score)**:

$$
\text{final\_score}(g) = \text{score}(g) - \lambda \times \text{penalty}(g)
$$

Với $\lambda = 0.3$ (diversity weight — hệ số kiểm soát độ mạnh của penalty)

### Ý nghĩa các thành phần

| Thành phần | Ý nghĩa                                                | Weight                 |
| ------------ | -------------------------------------------------------- | ---------------------- |
| Similarity   | Độ liên quan group với custom_text                   | 70%                    |
| Exist score  | Ưu tiên groups ít được dùng (prefer-fresh)        | 30%                    |
| Penalty      | Tránh chọn groups quá giống những groups đã chọn | -30% (trừ vào final) |

**Alpha parameter** (kiểm soát randomness):

- $\alpha = 0.1$ (low): freshness ít ảnh hưởng, deterministic hơn
- $\alpha = 0.5$ (medium): cân bằng
- $\alpha = 1.0$ (high): freshness mạnh, randomness cao

### Pseudo Code

```
FUNCTION select_groups_greedy(candidates, top_k, random_level, query_embedding, diversity_weight = 0.3):
    selected ← []
    selected_embeddings ← []
    alpha ← get_alpha(random_level)  // 0.1, 0.5, or 1.0
  
    FOR iteration FROM 1 TO min(top_k, len(candidates)):
        best_group ← NULL
        best_score ← -∞
      
        FOR EACH group IN candidates:
            IF group IN selected:
                CONTINUE
          
            // Step 1: Tính base score
            similarity ← cosine_similarity(group.embedding, query_embedding) OR 0
            exist_score ← 1 / (group.existence_count + 1) ^ alpha
            base_score ← 0.7 * similarity + 0.3 * exist_score
          
            // Step 2: Tính diversity penalty
            penalty ← 0.0
            FOR EACH selected_embedding IN selected_embeddings:
                penalty ← max(penalty, cosine_similarity(group.embedding, selected_embedding))
          
            // Step 3: Tính final score
            final_score ← base_score - diversity_weight * penalty
          
            // Step 4: Cập nhật best group
            IF final_score > best_score:
                best_group ← group
                best_score ← final_score
      
        IF best_group IS NULL:
            BREAK
      
        // Step 5: Thêm best group vào selected list
        selected.append(best_group)
        selected_embeddings.append(best_group.embedding)
  
    RETURN selected
```

### Ví dụ Thực thi

**Giả sử**: top_k=3, 5 candidate groups với embeddings và existence_count

| Group | Similarity | Existence Count | Base Score                     |
| ----- | ---------- | --------------- | ------------------------------ |
| A     | 0.85       | 2               | 0.7×0.85 + 0.3×(1/3) = 0.695 |
| B     | 0.72       | 5               | 0.7×0.72 + 0.3×(1/6) = 0.554 |
| C     | 0.68       | 1               | 0.7×0.68 + 0.3×(1/2) = 0.626 |
| D     | 0.81       | 0               | 0.7×0.81 + 0.3×1 = 0.867     |
| E     | 0.65       | 3               | 0.7×0.65 + 0.3×(1/4) = 0.530 |

**Iteration 1** (selected_embeddings = []):

- Tất cả groups có penalty = 0
- Final scores = base scores
- Chọn D (highest = 0.867)
- selected = [D], selected_embeddings = [D.emb]

**Iteration 2** (selected_embeddings = [D.emb]):

- A: penalty = cos_sim(A.emb, D.emb) = 0.92 → final = 0.695 - 0.3×0.92 = 0.419
- B: penalty = cos_sim(B.emb, D.emb) = 0.78 → final = 0.554 - 0.3×0.78 = 0.320
- C: penalty = cos_sim(C.emb, D.emb) = 0.55 → final = 0.626 - 0.3×0.55 = 0.461
- E: penalty = cos_sim(E.emb, D.emb) = 0.81 → final = 0.530 - 0.3×0.81 = 0.287
- Chọn C (highest = 0.461)
- selected = [D, C], selected_embeddings = [D.emb, C.emb]

**Iteration 3** (selected_embeddings = [D.emb, C.emb]):

- A: penalty = max(0.92, 0.88) = 0.92 → final = 0.695 - 0.3×0.92 = 0.419
- B: penalty = max(0.78, 0.76) = 0.78 → final = 0.554 - 0.3×0.78 = 0.320
- E: penalty = max(0.81, 0.79) = 0.81 → final = 0.530 - 0.3×0.81 = 0.287
- Chọn A (highest = 0.419)
- selected = [D, C, A]

**Kết quả**: [D, C, A] (groups theo diversity + similarity + freshness)

---

## Thuật Toán Slot Distribution (Phân phối Slots)

**Mục Đích**:

- Chia công bằng số lượng questions cho mỗi group đã xếp hạng
- Đảm bảo tất cả top groups đều có mặt trong exam (không bỏ qua group)
- Tránh tập trung quá nhiều questions vào một group

**Công thức Toán học**:

$$
\text{base\_slots} = \left\lfloor \frac{\text{top\_k}}{\text{n\_groups}} \right\rfloor
$$

$$
\text{remainder} = \text{top\_k} \mod \text{n\_groups}
$$

Nhóm $0$ đến $\text{remainder}-1$: $\text{base\_slots} + 1$ questions
Nhóm $\text{remainder}$ đến $n-1$: $\text{base\_slots}$ questions

**Pseudo Code**:

```
FUNCTION distribute_slots(ranked_groups, top_k):
    IF ranked_groups IS EMPTY:
        RETURN {}
  
    n ← len(ranked_groups)
    base_slots ← top_k / n (integer division)
    remainder ← top_k % n
  
    slot_map ← {}
  
    FOR i FROM 0 TO n-1:
        group ← ranked_groups[i]
        slots ← base_slots
      
        IF i < remainder:
            slots ← slots + 1
      
        slot_map[group] ← slots
  
    RETURN slot_map
```

**Ý nghĩa**:

- Chia base slots: top_k / n_groups (integer division)
- Tính remainder: top_k % n_groups (phần dư)
- n_groups đầu tiên (i < remainder) nhận +1 extra slot
- Kết quả: tất cả slots được distributed, tổng = top_k

**Ví dụ**:

- top_k=15, n=4 groups
- base_slots = 15 / 4 = 3
- remainder = 15 % 4 = 3
- Groups: [3+1, 3+1, 3+1, 3] = [4, 4, 4, 3]
- Tổng: 4+4+4+3 = 15 ✓

---

## Thuật Toán Answer Shuffling (Xáo trộn Đáp án)

**Mục Đích**:

- Tránh pattern cố định (ví dụ lúc nào đáp án đúng cũng ở vị trí C)
- Tăng độ khó và công bằng của exam (người làm không thể dự đoán vị trí đáp án đúng)
- Giữ tính toàn vẹn của answer metadata bằng cách lưu shuffled indices

**Pseudo Code**:

```
FUNCTION shuffle_answers(question):
    answers ← DB.get_by_question(question.id)
    indices ← [0, 1, 2, ..., len(answers)-1]

    seed ← current_timestamp_nanoseconds  // High-precision timestamp
    rng ← new Random(seed)  // Create RNG with timestamp seed

    rng.shuffle(indices)
    RETURN indices
```

**Ý nghĩa**:

- Lấy đáp án của question từ DB
- Tạo list indices theo thứ tự gốc [0, 1, 2, ...]
- Seed RNG với nanosecond-precision timestamp (đảm bảo uniqueness cho mỗi shuffle)
- Shuffle indices dựa trên seeded RNG (truly random, không thể predict)
- Return shuffled indices

**Quy trình Sử Dụng**:

1. Lấy danh sách đáp án của question
2. Tạo list indices: [0, 1, 2, ..., n-1]
3. Shuffle indices dùng timestamp seed
4. Lưu shuffled indices vào `answer_order` trong QuestionExamTest
5. Client dùng `answer_order` để hiển thị đáp án theo thứ tự đã xáo

**Ví dụ**: 4 đáp án gốc [A, B, C, D]
Shuffled indices (timestamp seed): [2, 0, 3, 1]
Hiển thị trên exam: [C, A, D, B]

**Randomness Guarantee**:

- Mỗi lần gọi `_shuffle_answers()` dùng timestamp nanosecond hiện tại làm seed
- Mỗi nanosecond khác nhau → seed khác → shuffle result khác
- Không thể predict hoặc reproduce shuffle result ngoài hệ thống
- Đảm bảo "truly random" thay vì dùng global random state

---

## Hàm Shuffle Answers (Xáo trộn Đáp án)

**Mục Đích**:

- Randomize thứ tự đáp án để tránh pattern cố định
- Sử dụng nanosecond-precision timestamp làm seed cho "truly random" shuffle
- Mỗi lần shuffle cho kết quả khác nhau, không thể predict

**Pseudo Code**:

```
FUNCTION shuffle_answers(question, rng = NULL):
    answers ← DB.get_by_question(question.id)
    indices ← [0, 1, 2, ..., len(answers)-1]
  
    IF rng IS NULL:
        seed ← current_timestamp_nanoseconds
        rng ← new Random(seed)
  
    rng.shuffle(indices)
    RETURN indices
```

**Ý nghĩa**:

- Lấy tất cả đáp án của question từ DB
- Tạo list indices từ 0 đến n-1
- Nếu không có external RNG: tạo RNG mới với nanosecond timestamp làm seed
- Shuffle indices dựa trên RNG (truly random)
- Return shuffled indices

**Randomness Guarantee**:

- Timestamp nanosecond hiện tại → seed unique mỗi lần gọi
- Mỗi seed khác → shuffle result khác
- Không thể reproduce hoặc predict kết quả
- Đảm bảo answer order luôn randomized, không có pattern

---

## Hàm Lấy Questions Theo Tiêu Chí (get_by_criteria)

Hàm này là nền tảng để lấy questions theo subject, topics, difficulty, và question_type.

**Pseudo Code**:

```
FUNCTION get_by_criteria(subject, topics, difficulty, question_types = NULL):
    query ← DB.SELECT(Question)
  
    query ← query.WHERE(
        (Question.subject == subject)
        AND (Question.topic IN topics)
        AND (Question.difficulty == difficulty)
        AND (Question.parent_question IS NULL)  // Exclude composite parent questions
        AND (Question.status == APPROVED)  // Only approved questions
    )
  
    IF question_types NOT NULL:
        query ← query.WHERE(Question.question_type IN question_types)
  
    RETURN query.execute()
```

**Ý nghĩa**:

- Lọc theo subject (chính xác)
- Lọc theo topics (list — một question có thể thuộc multiple topics)
- Lọc theo difficulty (chính xác)
- Loại bỏ parent questions (chỉ lấy standalone hoặc sub-questions)
- Loại bỏ non-approved questions (chỉ APPROVED được dùng)
- Tùy chọn filter theo question_type

**Hàm Mở Rộng: get_by_criteria_with_fallback**

Wrapper của `get_by_criteria` thêm logic fallback:

```
FUNCTION get_by_criteria_with_fallback(subject, topics, difficulty, fallback_difficulties = NULL, question_types = NULL):
    questions ← get_by_criteria(subject, topics, difficulty, question_types)
  
    IF questions IS EMPTY AND fallback_difficulties NOT NULL:
        FOR EACH fallback_diff IN fallback_difficulties:
            questions ← get_by_criteria(subject, topics, fallback_diff, question_types)
            IF questions NOT EMPTY:
                BREAK
  
    RETURN questions
```

---

## Hàm Lấy Question Groups Theo Metadata (find_by_metadata)

Hàm này lấy candidate groups theo subject, topics, và difficulty.

**Pseudo Code**:

```
FUNCTION find_by_metadata(subject, topic, difficulty, from_user_id = NULL):
    topics ← topic AS LIST (if not already list)
  
    query ← DB.SELECT(QuestionGroup)
  
    query ← query.WHERE(
        (QuestionGroup.subject == subject)
        AND (QuestionGroup.topic IN topics)
        AND (QuestionGroup.difficulty == difficulty)
    )
  
    IF from_user_id NOT NULL:
        query ← query.WHERE(QuestionGroup.from_user_id == from_user_id)
  
    RETURN query.execute()
```

**Ý nghĩa**:

- Lọc theo subject, topics, difficulty (cơ bản — không validate status)
- Tùy chọn scope theo user (from_user_id) để multi-tenancy

---

## Thuật Toán Cosine Search (cosine_search)

Tìm kiếm semantic tương tự cho question groups dựa trên vector embedding.

**Pseudo Code**:

```
FUNCTION cosine_search(candidates, query_vector, threshold = 0.75):
    IF candidates IS EMPTY OR query_vector IS NULL:
        RETURN []
  
    results ← []
    query_norm ← L2_norm(query_vector)
  
    IF query_norm == 0:
        RETURN []
  
    FOR EACH group IN candidates:
        IF group.vector_embedding IS NULL:
            CONTINUE
      
        group_embedding ← parse_vector(group.vector_embedding)
        group_norm ← L2_norm(group_embedding)
      
        IF group_norm == 0:
            CONTINUE
      
        cosine_sim ← dot_product(group_embedding, query_vector) / (group_norm * query_norm)
      
        IF cosine_sim >= threshold:
            results.append((cosine_sim, group))
  
    // Sort by similarity descending
    results.sort(BY cosine_sim DESC)
  
    RETURN [group FOR (_, group) IN results]
```

**Ý nghĩa**:

- Tính cosine similarity từ scratch trong Python (tránh pgvector issues)
- Lọc theo threshold (default 0.75)
- Return groups theo similarity giảm dần (best first)
- Tự động skip groups không có embedding hoặc norm = 0

---

## Status Lifecycle

```
PENDING (0) → Mới sinh, chờ review
    ↓
ACCEPTED (1) → Dùng được
 hoặc REJECTED (2) → Không dùng
```

---

## Summary

Luồng tạo đề thi: 5 bước (resolve → create instance → process sections → update counts → build response) với 2 chế độ chọn questions (direct vs group-based). Sử dụng weighted sampling (fairness), difficulty fallback (resilience), semantic ranking (relevance), diversity penalty (tránh duplicates). Exam được tạo status PENDING, sẵn cho review trước khi accept/reject.
