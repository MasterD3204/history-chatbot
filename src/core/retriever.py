# --- File: src/core/retriever.py (ĐÃ SỬA LỖI HOÀN CHỈNH) ---

import sys
import os
from collections import defaultdict
from typing import List, Dict

# Thêm thư mục gốc của dự án (đi lên 2 cấp từ file hiện tại) vào sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from src.core.weaviate_client import client
from src.core.config import class_name

TOP_K_BM25 = 50
TOP_K_VEC = 50
RRF_K = 60

collection = client.collections.get(class_name)

def safe_extract_obj(o):
    """
    Hỗ trợ cả trường hợp response element là object có attrs hoặc dict.
    Trả về dict chứa các thuộc tính cần thiết.
    """
    props = getattr(o, "properties", {})
    
    # === PHẦN SỬA LỖI QUAN TRỌNG ===
    # Lấy đối tượng metadata, có thể là None
    metadata = getattr(o, "metadata", None)
    
    score = None
    if metadata: 
        score = getattr(metadata, "score", None) or \
                getattr(metadata, "certainty", None) or \
                getattr(metadata, "distance", None)

    return {
        "uuid": str(getattr(o, "uuid", None)),
        "content": props.get("content"),
        "document_name": props.get("document_name"),
        "page": props.get("pages"),
        "url": props.get("url"),
        "score": score
    }


def query_hybrid_alpha(query_text, vector, alpha, limit) -> List[Dict]:
    """
    Thực hiện truy vấn hybrid và trả về danh sách các đối tượng với siêu dữ liệu.
    """
    response = collection.query.hybrid(
        query=query_text,
        vector=vector,
        alpha=alpha,
        limit=limit,
        query_properties=['content'],
        # Yêu cầu Weaviate trả về các thuộc tính này
        return_properties=["content", "document_name", "pages", "url"],
        return_metadata=["score", "certainty", "distance"] # Yêu cầu trả về các metadata liên quan
    )

    results = []
    for idx, o in enumerate(response.objects):
        info = safe_extract_obj(o)
        info["rank"] = idx + 1
        results.append(info)
    return results

def rrf_fusion(lists_of_results, k=RRF_K, top_k=5) -> List[Dict]:
    """
    Thực hiện RRF fusion và giữ lại đầy đủ thông tin của tài liệu.
    """
    accum = defaultdict(float)
    meta = {}
    for res_list in lists_of_results:
        for item in res_list:
            docid = item["uuid"]
            rank = item.get("rank")
            if rank is None:
                continue
            accum[docid] += 1.0 / (k + rank)
            if docid not in meta:
                # Lưu toàn bộ thông tin của tài liệu khi gặp lần đầu
                meta[docid] = item

    fused = [{"id": docid, "rrf_score": score, **meta[docid]} for docid, score in accum.items()]
    fused.sort(key=lambda x: x["rrf_score"], reverse=True)
    return fused[:top_k]

def format_retrieved_docs(docs: List[Dict]) -> Dict[str, any]:
    """
    Định dạng tài liệu truy xuất thành context string cho LLM và danh sách nguồn.
    """
    # Tạo context string với chỉ mục nguồn
    formatted_context = []
    for i, doc in enumerate(docs):
        if doc.get("content"):
            formatted_context.append(f"[SOURCE {i+1}]:\n{doc['content']}")
    
    context_string = "\n\n---\n\n".join(formatted_context)
    
    # Tạo danh sách nguồn để hiển thị
    sources = [
        {
            "document_name": doc.get("document_name"),
            "page": doc.get("pages"),
            "url": doc.get("url")
        }
        for doc in docs
    ]
    
    return {"context": context_string, "sources": sources}


def retriever_fn(query: str, embedding_model, search_type: str, top_k: int) -> Dict[str, any]:
    """
    Hàm retriever chính, trả về một dictionary chứa context và sources.
    """
    query_vector = embedding_model.encode(query).tolist()
    final_docs = []

    print(f"Executing {search_type} search with top_k={top_k}")

    if search_type == "semantic":
        final_docs = query_hybrid_alpha(query, query_vector, alpha=1.0, limit=top_k)
    elif search_type == "keyword":
        final_docs = query_hybrid_alpha(query, query_vector, alpha=0.0, limit=top_k)
    else:  # Mặc định là 'hybrid'
        bm25_results = query_hybrid_alpha(query, query_vector, alpha=0.0, limit=TOP_K_BM25)
        vec_results = query_hybrid_alpha(query, query_vector, alpha=1.0, limit=TOP_K_VEC)
        final_docs = rrf_fusion([bm25_results, vec_results], k=RRF_K, top_k=top_k)
    
    # Định dạng kết quả cuối cùng
    return format_retrieved_docs(final_docs)