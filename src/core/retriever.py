import sys
import os

# Thêm thư mục gốc của dự án (đi lên 2 cấp từ file hiện tại) vào sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from collections import defaultdict
from typing import List, Dict
from src.core.weaviate_client import client
from src.core.config import class_name

TOP_K_BM25 = 50
TOP_K_VEC  = 50
TOP_K_FINAL = 5
RRF_K = 60   

collection = client.collections.get(class_name)


def safe_extract_obj(o):
    """
    Hỗ trợ cả trường hợp response element là object có attrs hoặc dict.
    Trả về dict: {uuid, content, score_if_any}
    """
    # id
    obj_id = getattr(o, "uuid", None) or (o.get("uuid") if isinstance(o, dict) else None)

    # properties / content
    props = getattr(o, "properties", None) or (o.get("properties") if isinstance(o, dict) else {})
    content = None
    if isinstance(props, dict):
        content = props.get("content")  # theo yêu cầu: dùng thuộc tính "content"
    else:
        # props có thể là một object; thử getattr
        content = getattr(props, "get", lambda k, d=None: d)("content", None)

    # try to get score/certainty from returned metadata if present
    score = None
    add = getattr(o, "metadata", None) or (o.get("additional") if isinstance(o, dict) else None)
    if isinstance(add, dict):
        score = add.get("score") or add.get("certainty") or add.get("distance")
    else:
        # some clients put attributes differently; ignore if absent
        score = None

    return {"uuid": obj_id, "content": content, "score": score}

def query_hybrid_alpha(query_text, vector, alpha, limit) -> List[Dict]:
    """
    Dùng collection.query.hybrid để chạy:
    - alpha=0 -> pure BM25 (Weaviate dùng `query_text` cho BM25)
    - alpha=1 -> pure vector (Weaviate dùng provided vector for dense search)
    Lưu ý: khi truyền vector thì Weaviate ko tự vectorize query nữa.
    """
    resp = collection.query.hybrid(
        query = query_text,
        vector = vector,
        alpha = alpha,
        limit = limit,
        query_properties = ['content']
    ) # include_properties is called on the query object

    results = []
    for idx, o in enumerate(resp.objects):
        info = safe_extract_obj(o)
        info["rank"] = idx + 1
        results.append(info)
    return results

#  chuẩn bị RRF (Reciprocal Rank Fusion)
# RRF score for a doc = sum( 1 / (RRF_K + rank_i) ) over all input rank lists where rank_i is the 1-based rank.
def rrf_fusion(lists_of_results, k=RRF_K, top_k = 5):
    accum = defaultdict(float)
    meta = {}
    for res_list in lists_of_results:
        for item in res_list:
            docid = item["uuid"]
            rank = item.get("rank", None)
            if rank is None:
                continue
            accum[docid] += 1.0 / (k + rank)
            # keep a representative content/score (first occurrence)
            if docid not in meta:
                meta[docid] = {
                    "content": item.get("content"),
                    "source_ranks": []
                }
            meta[docid]["source_ranks"].append(rank)
    # create sorted list
    fused = []
    for docid, score in accum.items():
        fused.append({
            "id": docid,
            "rrf_score": score,
            "content": meta[docid]["content"],
            "ranks": meta[docid]["source_ranks"]
        })
    fused.sort(key=lambda x: x["rrf_score"], reverse=True)
    top_final = fused[:top_k]
    return top_final

def retriever_fn(query, embedding_model):
    query_vector = embedding_model.encode(query).tolist()
    bm25_results = query_hybrid_alpha(query, query_vector, alpha=0.0, limit=TOP_K_BM25)
    vec_results  = query_hybrid_alpha(query, query_vector, alpha=1.0, limit=TOP_K_VEC)
    top_final = rrf_fusion([bm25_results, vec_results], k=RRF_K)

    content = [doc['content'] for doc in top_final]

    context = "\n".join(content)
    return context
