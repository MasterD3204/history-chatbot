import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from typing import List, Dict, Any

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

if not all([GOOGLE_API_KEY, GOOGLE_CSE_ID]):
    raise ValueError("GOOGLE_API_KEY và GOOGLE_CSE_ID phải được thiết lập trong file .env")

def build_payload(query: str, num: int = 5, **params: Any) -> Dict[str, Any]:
    payload = {
        'key': GOOGLE_API_KEY,
        'cx': GOOGLE_CSE_ID,
        'q': query,
        'num': num,
    }
    payload.update(params)
    return payload

def make_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        response = requests.get('https://www.googleapis.com/customsearch/v1', params=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi gọi Google API: {e}")
        return {}

def get_google_search_results(query: str, num_results: int = 5) -> List[Dict[str, str]]:
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

def scrape_url_content(url: str) -> str:
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')
        paragraphs = [p.get_text() for p in soup.find_all('p')]
        meaningful_text = " ".join(p for p in paragraphs if len(p.split()) > 10)
        return meaningful_text.strip()
    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi scraping URL {url}: {e}")
        return ""
    except Exception as e:
        print(f"Lỗi không xác định khi xử lý URL {url}: {e}")
        return ""

def web_search_fn(query: str) -> List[Dict[str, Any]]:
    """
    Hàm chính: Tìm kiếm, scrape và trả về một danh sách các nguồn có kèm nội dung.
    Mỗi phần tử trong danh sách trả về sẽ là:
    {
        "document_name": "Tiêu đề trang web",
        "url": "http://...",
        "content": "Nội dung đã scrape..."
    }
    """
    print(f"Đang thực hiện Web Search cho câu hỏi: '{query}'")
    
    search_results = get_google_search_results(query, num_results=3)
    
    if not search_results:
        print("Google Search không trả về kết quả nào.")
        return []

    sources_with_content = []
    for result in search_results:
        print(f"Đang scraping: {result['link']}")
        content = scrape_url_content(result['link'])
        if content:
            sources_with_content.append({
                "document_name": result['title'],
                "url": result['link'],
                "content": content
            })
            
    if not sources_with_content:
        print("Scraping không lấy được nội dung từ bất kỳ URL nào.")

    return sources_with_content