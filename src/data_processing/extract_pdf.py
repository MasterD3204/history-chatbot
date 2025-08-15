import fitz  # PyMuPDF
import os
import re
import json

# ---------- CẤU HÌNH CHUNG ----------
MARGIN_TOP = 60
MARGIN_X = 15
MIN_VERTICAL_GAP = 10
SEPARATOR_PADDING = 5
MARGIN_BOTTOM_FALLBACK = 80

# Chunk theo số từ
CHUNK_SIZE_WORDS = 200
CHUNK_OVERLAP_WORDS = 50

# Đường dẫn tới file config (JSON)
# JSON expected structure:
# {
#   "fileA.pdf": {"Name document": "Tên A", "url": "...", "start_page": 5, "end_page": 80},
#   "fileB": {"Name document": "Tên B", "url": "...", "start_page": 1, "end_page": 30},
#   ...
# }
CONFIG_PATH = "/content/config.json"

# ---------- BẢN ĐỒ SỬA LỖI (giữ nguyên) ----------
CORRECTION_MAP = {
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
    "sống dã": "sống dã", 
    "l ch s": "lịch sử",
    "m ièn": "miền",
    "Dắc San": "Bắc Sơn", 
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
    "V I": "VI",
    "I I": "II",
    "I I I": "III",
    "I V": "IV",
    "E S R": "ESR",
    "T C N": "TCN",
    "S C N": "SCN", 
    "B P": "BP", 
    "DÁU TÍC H": "DẤU TÍCH",
    "N GƯỜI": "NGƯỜI",
}

# ---------- Hàm tiện ích ----------
def load_config(path):
    if not os.path.exists(path):
        print(f"   ! Không tìm thấy config file tại: {path}. Bỏ qua load config.")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            if not isinstance(cfg, dict):
                print("   ! config.json không có định dạng dict ở cấp top-level. Trả về dict rỗng.")
                return {}
            return cfg
    except Exception as e:
        print(f"   ! Lỗi khi đọc config.json: {e}")
        return {}

def find_config_for_filename(filename, config_dict):
    """
    Cố gắng tìm config entry cho `filename` theo nhiều chiến lược:
    1) exact match với filename (ví dụ 'abc.pdf')
    2) exact match với base name (no ext) (ví dụ 'abc')
    3) case-insensitive match
    4) contains / substring heuristics
    Trả về (key, entry) nếu tìm thấy, khác None nếu không tìm thấy.
    """
    if not config_dict:
        return None, None

    # chuẩn hoá
    fname = filename
    base = os.path.splitext(filename)[0]

    # 1) exact filename
    if fname in config_dict:
        return fname, config_dict[fname]

    # 2) base name exact
    if base in config_dict:
        return base, config_dict[base]

    # 3) case-insensitive exact
    lower_map = {k.lower(): k for k in config_dict.keys()}
    if fname.lower() in lower_map:
        k = lower_map[fname.lower()]
        return k, config_dict[k]
    if base.lower() in lower_map:
        k = lower_map[base.lower()]
        return k, config_dict[k]

    # 4) substring heuristics: try to find a config key that contains base or vice versa
    for k in config_dict.keys():
        if base.lower() in k.lower() or k.lower() in base.lower():
            return k, config_dict[k]

    # no match
    return None, None

def apply_corrections(text, correction_map):
    for wrong, correct in correction_map.items():
        text = text.replace(wrong, correct)
    return text

def remove_citation_numbers(text):
    citation_regex = r'(?<=[\w"”’)])\d+'
    return re.sub(citation_regex, '', text)

def clean_and_join_text(text):
    text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    text = re.sub(r'\n{2,}', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()

def find_separator_y_by_gap_detection(page):
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

# ---------- Trích xuất từng trang ----------
def extract_pages_from_pdf(pdf_path, start_page=None, end_page=None):
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        start_index = (start_page - 1) if start_page else 0
        end_index = end_page if end_page else total_pages

        if start_index < 0 or start_index >= total_pages:
            start_index = 0
            print(f"   ! Cảnh báo: start_page không hợp lệ cho {os.path.basename(pdf_path)}, sẽ bắt đầu từ trang 1.")
        if end_index > total_pages:
            end_index = total_pages
        if start_index >= end_index:
            print(f"   ! Lỗi dải trang cho {os.path.basename(pdf_path)}. Bỏ qua file này.")
            doc.close()
            return None, None

        print(f"-> Đang xử lý file: {os.path.basename(pdf_path)}")
        print(f"   -> Sẽ trích xuất từ trang {start_index + 1} đến trang {end_index} (tổng cộng {end_index - start_index} trang).")

        page_texts = []
        page_numbers = []

        for page_num in range(start_index, end_index):
            page = doc.load_page(page_num)
            separator_y = find_separator_y_by_gap_detection(page)

            if separator_y:
                bottom_boundary = separator_y - SEPARATOR_PADDING
            else:
                bottom_boundary = page.rect.height - MARGIN_BOTTOM_FALLBACK

            content_rect = fitz.Rect(MARGIN_X, MARGIN_TOP, page.rect.width - MARGIN_X, bottom_boundary)
            text = page.get_text("text", clip=content_rect)

            text = clean_and_join_text(text)
            text = remove_citation_numbers(text)
            text = apply_corrections(text, CORRECTION_MAP)

            page_texts.append(text)
            page_numbers.append(page_num + 1)  # 1-based

        doc.close()
        total_words = sum(len(t.split()) for t in page_texts)
        print(f"   -> Trích xuất thành công {total_words} từ (tổng trên các trang).")
        return page_texts, page_numbers

    except Exception as e:
        print(f"*** Lỗi khi xử lý file {pdf_path}: {e}")
        return None, None

# ---------- Chunk theo số từ với mapping page offsets ----------
def chunk_full_text_by_words(full_text, page_offsets, chunk_size_words=CHUNK_SIZE_WORDS, chunk_overlap_words=CHUNK_OVERLAP_WORDS):
    if not full_text:
        return []

    tokens = list(re.finditer(r'\S+', full_text))
    n_words = len(tokens)
    if n_words == 0:
        return []

    chunk_size = max(1, int(chunk_size_words))
    chunk_overlap = max(0, int(chunk_overlap_words))
    step = max(1, chunk_size - chunk_overlap)

    chunks = []
    start_word_idx = 0
    text_len = len(full_text)

    while start_word_idx < n_words:
        end_word_idx_excl = min(n_words, start_word_idx + chunk_size)
        start_char = tokens[start_word_idx].start()
        end_char = tokens[end_word_idx_excl - 1].end()

        chunk_text = full_text[start_char:end_char]

        # pages covered
        pages_in_chunk = []
        for i, (page_num, offset) in enumerate(page_offsets):
            next_offset = page_offsets[i + 1][1] if i + 1 < len(page_offsets) else text_len
            if start_char < next_offset and end_char > offset:
                pages_in_chunk.append(page_num)

        chunks.append({
            "text": chunk_text,
            "start_char": start_char,
            "end_char": end_char,
            "pages": pages_in_chunk,
            "word_start": start_word_idx,
            "word_end": end_word_idx_excl - 1
        })

        if end_word_idx_excl >= n_words:
            break
        start_word_idx += step

    return chunks

# ---------- Hàm chính xử lý directory, đọc config và gắn metadata ----------
def process_all_pdfs_in_directory(pdf_dir, output_dir, config_path=CONFIG_PATH, default_start_page=1, default_end_page=None, chunk_size_words=CHUNK_SIZE_WORDS, chunk_overlap_words=CHUNK_OVERLAP_WORDS):
    os.makedirs(output_dir, exist_ok=True)
    print(f"Bắt đầu quá trình trích xuất từ thư mục: '{pdf_dir}'")
    print(f"Kết quả sẽ được lưu tại: '{output_dir}'\n")

    config = load_config(config_path)
    if config:
        print(f"   -> Đã load config từ: {config_path} (tìm thấy {len(config)} entries).")
    else:
        print("   -> Không có config (hoặc config rỗng). Sẽ xử lý file với dải trang mặc định nếu có.")

    pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")]
    if not pdf_files:
        print("Không tìm thấy file PDF nào trong thư mục được chỉ định.")
        return []

    all_chunks = []

    for filename in pdf_files:
        pdf_path = os.path.join(pdf_dir, filename)

        # tìm config cho file này
        config_key, cfg_entry = find_config_for_filename(filename, config)
        cfg_name = cfg_entry.get("Name document") if cfg_entry else None
        cfg_url = cfg_entry.get("url") if cfg_entry else None

        # lấy start/end trang ưu tiên từ config; fallback về default args
        try:
            cfg_start = int(cfg_entry.get("start_page")) if cfg_entry and cfg_entry.get("start_page") not in (None, "") else default_start_page
        except Exception:
            cfg_start = default_start_page
        try:
            cfg_end = int(cfg_entry.get("end_page")) if cfg_entry and cfg_entry.get("end_page") not in (None, "") else default_end_page
        except Exception:
            cfg_end = default_end_page

        if cfg_start is None:
            cfg_start = default_start_page
        # cfg_end can be None meaning to read till end

        if config_key:
            print(f"\n-> Match config for '{filename}' -> config key: '{config_key}', doc name: '{cfg_name}'")
        else:
            print(f"\n-> Không tìm config cho '{filename}', sẽ dùng dải trang mặc định / toàn file.")

        # extract pages using cfg_start/cfg_end
        page_texts, page_numbers = extract_pages_from_pdf(pdf_path, start_page=cfg_start, end_page=cfg_end)
        if page_texts is None:
            continue

        # build full_text + page_offsets
        full_text = ""
        page_offsets = []
        for pnum, ptext in zip(page_numbers, page_texts):
            page_offsets.append((pnum, len(full_text)))
            full_text += ptext + " "

        # chunk
        file_chunks = chunk_full_text_by_words(full_text, page_offsets, chunk_size_words=chunk_size_words, chunk_overlap_words=chunk_overlap_words)

        # attach metadata from config + chunk metadata
        for c in file_chunks:
            metadata = {
                "file": filename,
                # "config_key": config_key,
                "document_name": cfg_name,
                "url": cfg_url,
                # "config_start_page": cfg_start,
                # "config_end_page": cfg_end,
                "pages": c["pages"],
                # "start_char": c["start_char"],
                # "end_char": c["end_char"],
                # "word_start": c["word_start"],
                # "word_end": c["word_end"]
            }
            all_chunks.append({
                "text": c["text"],
                "metadata": metadata
            })

        # save cleaned full_text (optional)
        output_filename = os.path.splitext(filename)[0] + ".txt"
        output_path = os.path.join(output_dir, output_filename)
        try:
            with open(output_path, "w", encoding="utf-8") as f_out:
                f_out.write(full_text)
            print(f"   -> Đã lưu full cleaned text vào file: {output_filename}.")
        except Exception as e:
            print(f"   ! Không thể lưu file {output_filename}: {e}")

        print(f"   -> Tạo được {len(file_chunks)} chunk cho file: {filename}")

    print(f"\n--- HOÀN TẤT. Tổng chunk thu được: {len(all_chunks)} ---")
    return all_chunks