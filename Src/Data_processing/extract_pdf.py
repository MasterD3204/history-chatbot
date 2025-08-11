import fitz  # PyMuPDF
import os
import re

# ==============================================================================
# --- KHU VỰC CẤU HÌNH CHÍNH ---
# ==============================================================================

# 1. CẤU HÌNH DẢI TRANG CẦN XỬ LÝ
#    - Đặt số trang bạn muốn bắt đầu và kết thúc (số trang thật trong sách).
#    - Đặt là `None` để xử lý từ đầu hoặc đến cuối sách.
#    - Ví dụ: Bỏ qua 10 trang đầu và 5 trang cuối của sách 700 trang.
PROCESSING_CONFIG = {
    "start_page": 27,      # Bắt đầu trích xuất từ trang 11
    "end_page": 636,       # Kết thúc trích xuất ở trang 695
    # "start_page": None,  # Ví dụ: Xử lý từ đầu
    # "end_page": None,    # Ví dụ: Xử lý đến hết
}

# 2. CÁC THAM SỐ XỬ LÝ
MARGIN_TOP = 60
MARGIN_X = 15
MIN_VERTICAL_GAP = 10
SEPARATOR_PADDING = 5
MARGIN_BOTTOM_FALLBACK = 80

# 3. BẢN ĐỒ SỬA LỖI
CORRECTION_MAP = {
    # ==== Lỗi tách từ Tiếng Việt phổ biến ====
    "lịch sừ": "lịch sử",
    "In đônêxia": "Indonesia",
    "đứng thảng": "đứng thẳng",
    "ờ Chu": "ở Chu",
    "sáng tò": "sáng tỏ",
    "ghè đ o": "ghè đẽo",
    "riu tay": "rìu tay",
    "đác lực": "đắc lực",
    "v i họ": "với họ",
    "nư c": "nước",
    "thòi": "thời",
    "sô": "số",
    "n i": "nơi",
    "v i": "với",
    "chác chán": "chắc chắn",
    "đã phát triền": "đã phát triển",
    "Nhừng": "Những",
    "rieng": "riêng",
    "cùa": "của",
    "dirợc": "được",
    "hom": "hơn",
    "thúy điện": "thủy điện",
    "chiccrăng": "chiếc răng",
    "thòi": "thời",
    "sống dã": "sống dã", # Có thể đúng, nhưng cần xem lại ngữ cảnh
    "l ch s": "lịch sử",
    "m ièn": "miền",
    "Dắc San": "Bắc Sơn", # Lỗi OCR/gõ sai
    "ké liốp": "kế tiếp",
    "đi chi": "di chỉ",
    "cỏ": "có",
    "n i": "nơi",
    "d Dô": "dỗ",
    "thìry": "thủy",
    "vè": "về",
    "cỏ": "có",
    "SỤ": "SỰ",
    "HÌN H": "HÌNH",
    "T HÀN H": "THÀNH",
    "TR U YỀN": "TRUYỀN",
    "c ũ": "cũ",
    "s ử": "sử",
    "l i": "lại",
    "thê": "thế",
    "bo": "bỏ",

    # ==== Lỗi chữ/từ viết hoa ====
    # Lưu ý: Hàm fix_spaced_out_caps() sẽ xử lý hầu hết. Đây là các trường hợp đặc biệt.
    "V I": "VI",
    "I I": "II",
    "I I I": "III",
    "I V": "IV",
    "E S R": "ESR",
    "T C N": "TCN", # Trước Công Nguyên
    "S C N": "SCN", # Sau Công Nguyên
    "B P": "BP", # Before Present
    "DÁU TÍC H": "DẤU TÍCH",
    "N GƯỜI": "NGƯỜI",


    # ==== Lỗi chính tả / Nhận dạng sai khác ====
    "s kỳthời": "sơ kỳ thời", # Dính chữ

    "nư c khi": "nước khi",
    "di cốt Người": "di cốt của Người",
    "thòi Cánh Tân": "thời Cánh Tân",
    "lịch sửnguyên": "lịch sử nguyên",
    "ởViệt Nam": "ở Việt Nam",
    "đưực": "được",
    "van hóa San Vi đưực tìm tháy ử nhièu noi": "văn hóa Sơn Vi được tìm thấy ở nhiều nơi",
    "chiếm khoảng 1.": "chiếm khoảng 10%.",
    "chù": "chủ",
    "n i chếtác": "nơi chế tác",
    "L p": "Lớp",
    "ớ": "ở",
    "vỉ": "vì",
    "C 1": "C14",
    "sựkếtiếp": "sự kế tiếp",
    "hom": "hơn",

}

# ==============================================================================
# --- CÁC HÀM TIỆN ÍCH (Không cần thay đổi) ---
# ==============================================================================

def apply_corrections(text, correction_map):
    """Áp dụng các quy tắc sửa lỗi từ một bản đồ (dictionary)."""
    for wrong, correct in correction_map.items():
        text = text.replace(wrong, correct)
    return text

def remove_citation_numbers(text):
    """
    Sử dụng regex để tìm và loại bỏ các số chú thích dính liền với từ.
    Ví dụ: 'tài lược"3.' -> 'tài lược".' hoặc 'word2' -> 'word'
    """
    citation_regex = r'(?<=[\w"”’)])\d+'
    return re.sub(citation_regex, '', text)

def clean_and_join_text(text):
    """Hàm làm sạch văn bản cuối cùng."""
    text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    text = re.sub(r'\n{2,}', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()

def find_separator_y_by_gap_detection(page):
    """
    Tìm tọa độ Y của đường phân cách bằng cách phát hiện khoảng trống dọc lớn nhất.
    """
    blocks = page.get_text("blocks")
    blocks = [b for b in blocks if b[3] - b[1] > 5 and b[4].strip()]
    blocks.sort(key=lambda b: b[1])

    largest_gap = 0
    separator_y = None
    page_height = page.rect.height

    for i in range(len(blocks) - 1):
        current_block = blocks[i]
        next_block = blocks[i+1]
        current_bottom_y = current_block[3]
        next_top_y = next_block[1]

        if current_bottom_y > page_height / 3:
            gap = next_top_y - current_bottom_y
            if gap > largest_gap and gap > MIN_VERTICAL_GAP:
                largest_gap = gap
                separator_y = current_bottom_y

    return separator_y

# ==============================================================================
# --- QUY TRÌNH XỬ LÝ CHÍNH (Đã được nâng cấp) ---
# ==============================================================================

def extract_text_from_pdf(pdf_path, start_page=None, end_page=None):
    """
    Trích xuất văn bản từ một file PDF trong một dải trang chỉ định,
    sử dụng phương pháp tìm khoảng trống.
    """
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        # --- XỬ LÝ DẢI TRANG ---
        # Chuyển đổi từ số trang người dùng (1-based) sang chỉ số của PyMuPDF (0-based)
        start_index = (start_page - 1) if start_page else 0
        end_index = end_page if end_page else total_pages

        # Kiểm tra tính hợp lệ của dải trang
        if start_index < 0 or start_index >= total_pages:
            start_index = 0
            print(f"   ! Cảnh báo: start_page không hợp lệ, sẽ bắt đầu từ trang 1.")
        if end_index > total_pages:
            end_index = total_pages
        if start_index >= end_index:
            print(f"   ! Lỗi: start_page ({start_page}) phải nhỏ hơn end_page ({end_page}). Bỏ qua file này.")
            return None

        # In thông báo xác nhận
        print(f"-> Đang xử lý file: {os.path.basename(pdf_path)}")
        print(f"   -> Sẽ trích xuất từ trang {start_index + 1} đến trang {end_index} (tổng cộng {end_index - start_index} trang).")

        full_text_content = []
        # Lặp qua các trang trong dải chỉ định
        for page_num in range(start_index, end_index):
            page = doc.load_page(page_num)

            separator_y = find_separator_y_by_gap_detection(page)

            if separator_y:
                bottom_boundary = separator_y - SEPARATOR_PADDING
            else:
                bottom_boundary = page.rect.height - MARGIN_BOTTOM_FALLBACK

            content_rect = fitz.Rect(MARGIN_X, MARGIN_TOP, page.rect.width - MARGIN_X, bottom_boundary)
            text = page.get_text("text", clip=content_rect)
            full_text_content.append(text)

        doc.close()

        raw_text = "".join(full_text_content)
        cleaned_text = clean_and_join_text(raw_text)
        cleaned_text = remove_citation_numbers(cleaned_text)
        corrected_text = apply_corrections(cleaned_text, CORRECTION_MAP)

        print(f"   -> Trích xuất thành công {len(corrected_text.split())} từ.")
        return corrected_text

    except Exception as e:
        print(f"*** Lỗi khi xử lý file {pdf_path}: {e}")
        return None
import json

def load_config_from_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def process_all_pdfs_in_directory(pdf_dir, output_dir, config):
    """
    Hàm chính để lặp qua tất cả các file PDF và xử lý chúng theo cấu hình.
    """
    os.makedirs(output_dir, exist_ok=True)
    print(f"Bắt đầu quá trình trích xuất từ thư mục: '{pdf_dir}'")
    print(f"Kết quả sẽ được lưu tại: '{output_dir}'\n")

    pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")]
    if not pdf_files:
        print("Không tìm thấy file PDF nào trong thư mục được chỉ định.")
        return

    for filename in pdf_files:
        #file_config = config.get(filename)

        start_page = 27
        end_page = 636

        # if file_config: # Kiểm tra xem có cấu hình cho file này không
        #     start_page = file_config.get('start_page')
        #     end_page = file_config.get('end_page')
        pdf_path = os.path.join(pdf_dir, filename)

        # Truyền tham số start_page và end_page vào hàm xử lý
        clean_text = extract_text_from_pdf(pdf_path, start_page=start_page, end_page=end_page)

        if clean_text:
            output_filename = os.path.splitext(filename)[0] + ".txt"
            output_path = os.path.join(output_dir, output_filename)
            with open(output_path, "w", encoding="utf-8") as f_out:
                f_out.write(clean_text)
            print(f"   -> Đã lưu thành công vào file: {output_filename}\n")

    print("--- HOÀN TẤT TOÀN BỘ QUÁ TRÌNH ---")


# --- ĐIỂM BẮT ĐẦU CHẠY CHƯƠNG TRÌNH ---
if __name__ == "__main__":
    pdf_directory = "sach_pdf"
    output_directory = "sach_txt_sach"

    # Gọi hàm xử lý hàng loạt và truyền vào dictionary cấu hình
    process_all_pdfs_in_directory(pdf_directory, output_directory, PROCESSING_CONFIG)