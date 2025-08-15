# --- File: src/core/tools.py ---

import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from typing import List, Dict, Any

# Tải biến môi trường từ file .env
load_dotenv()

# Lấy các key từ biến môi trường một cách an toàn
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

# Kiểm tra xem các key đã được thiết lập chưa
if not all([GOOGLE_API_KEY, GOOGLE_CSE_ID]):
    raise ValueError("GOOGLE_API_KEY và GOOGLE_CSE_ID phải được thiết lập trong file .env")

def build_payload(query: str, num: int = 5, **params: Any) -> Dict[str, Any]:
    """Xây dựng payload cho request đến Google CSE API."""
    payload = {
        'key': GOOGLE_API_KEY,
        'cx': GOOGLE_CSE_ID,
        'q': query,
        'num': num,
    }
    payload.update(params)
    return payload

def make_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Thực hiện request và xử lý lỗi."""
    try:
        response = requests.get('https://www.googleapis.com/customsearch/v1', params=payload, timeout=10)
        response.raise_for_status()  # Ném lỗi nếu status code là 4xx hoặc 5xx
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi gọi Google API: {e}")
        return {} # Trả về dict rỗng nếu lỗi

def get_google_search_results(query: str, num_results: int = 5) -> List[Dict[str, str]]:
    """Lấy danh sách kết quả (metadata) từ Google."""
    payload = build_payload(query, num=num_results)
    response_json = make_request(payload)
    
    search_results = []
    for item in response_json.get('items', []):
        search_results.append({
            'title': item.get('title'),
            'link': item.get('link'),
            'snippet': item.get('snippet')
        })
    return search_results

# --- 2. HÀM SCRAPING NỘI DUNG WEB ---

def scrape_url_content(url: str) -> str:
    """
    Truy cập một URL, lấy nội dung HTML và trích xuất văn bản từ các thẻ <p>.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # Sử dụng BeautifulSoup để phân tích HTML
        soup = BeautifulSoup(response.text, 'lxml')

        # Trích xuất văn bản từ tất cả các thẻ <p> (paragraph)
        # Đây là một cách tiếp cận đơn giản nhưng hiệu quả cho nhiều trang tin tức/bài viết
        paragraphs = [p.get_text() for p in soup.find_all('p')]
        
        # Loại bỏ các đoạn văn bản quá ngắn và nối chúng lại
        meaningful_text = " ".join(p for p in paragraphs if len(p.split()) > 10)
        
        return meaningful_text.strip()

    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi scraping URL {url}: {e}")
        return ""
    except Exception as e:
        print(f"Lỗi không xác định khi xử lý URL {url}: {e}")
        return ""

# --- 3. HÀM CHÍNH ĐƯỢC CHAIN SỬ DỤNG ---

def web_search_fn(query: str) -> str:
    """
    Hàm chính: Tìm kiếm trên Google, sau đó scrape nội dung từ các URL kết quả.
    """
    print(f"Đang thực hiện Web Search cho câu hỏi: '{query}'")
    
    # Bước 1: Lấy danh sách URL từ Google Search
    search_results = get_google_search_results(query, num_results=3) # Chỉ lấy 3 kết quả hàng đầu để scrape
    
    if not search_results:
        print("Google Search không trả về kết quả nào.")
        return "Không tìm thấy thông tin phù hợp từ tìm kiếm web."

    # Bước 2: Scrape nội dung từ mỗi URL
    all_content = []
    for result in search_results:
        print(f"Đang scraping: {result['link']}")
        content = scrape_url_content(result['link'])
        if content:
            # Thêm tiêu đề và snippet để LLM có thêm ngữ cảnh
            full_snippet = f"Nguồn: {result['title']}\n{content}"
            all_content.append(full_snippet)
            
    if not all_content:
        print("Scraping không lấy được nội dung từ bất kỳ URL nào.")
        return "Không thể tải nội dung chi tiết từ các kết quả tìm kiếm web."

    # Bước 3: Kết hợp tất cả nội dung thành một context duy nhất
    return "\n\n---\n\n".join(all_content)

# context = web_search_fn("tìm hiểu về chủ tịch Hồ Chí Minh")
# print(context)