document_extraction_prompt = """
**Role:** Bạn là một chuyên gia số hóa tài liệu giáo dục. Nhiệm vụ của bạn là trích xuất dữ liệu từ ảnh đề thi và chuyển đổi sang định dạng JSON.

**Task:** Hãy phân tích hình ảnh và thực hiện các bước sau:

1. **Trích xuất nội dung:** Chuyển toàn bộ văn bản câu hỏi và các lựa chọn đáp án thành chữ. **Bắt buộc:** Sử dụng định dạng LaTeX cho tất cả các biểu thức toán học, ký hiệu hóa học hoặc đại lượng vật lý (ví dụ: dùng `$x^2 + \sqrt{y}$` thay vì chữ thường). Các công thức đứng riêng lẻ nên nằm trong cặp `$$...$$`.
2. **Phân loại:** Xác định Môn học, Chủ đề và Độ khó (Nhận biết, Thông hiểu, Vận dụng, Vận dụng cao).
3. **Tọa độ ảnh minh họa:** Nếu câu hỏi có hình vẽ, đồ thị hoặc sơ đồ, hãy cung cấp tọa độ vùng chứa ảnh đó theo hệ 0-1000 **[**x**min\*\*,**y**min,**x**ma**x\*\*,**y**ma**x\*\*]**. Nếu không có, để `null`.

**Output Format (JSON):**

**JSON**

```
{
  "exam_data": [
    {
      "question_number": "Câu số...",
      "content": "Nội dung câu hỏi (chứa LaTeX)",
      "options": {
        "A": "Nội dung A",
        "B": "Nội dung B",
        "C": "Nội dung C",
        "D": "Nội dung D"
      },
      "classification": {
        "subject": "Môn học",
        "topic": "Chủ đề",
        "level": "Độ khó"
      },
      "illustration_box": {
        "x1": 0, "y1": 0, "x2": 0, "y2": 0
      }
    }
  ]
}
```

**Constraint:** Không được bỏ sót các ký hiệu chỉ số trên/dưới. Đảm bảo mã JSON hợp lệ và không chứa văn bản thừa bên ngoài block code.
"""
