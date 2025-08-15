from langchain.text_splitter import RecursiveCharacterTextSplitter
import uuid
from tqdm import tqdm
import json
import re

def embedd_chunks(chunks, embedding_model, batch_size=32):
    """
    chunks: list of either
      - dict {"text": "...", "metadata": {...}}
      - or plain string "..."
    embedding_model: object with .encode(list_of_texts, show_progress_bar=True, batch_size=...)
    Trả về list các dict: {"content": text, "vector": embedding.tolist(), "metadata": metadata}
    """
    # chuẩn bị texts
    texts = []
    metadatas = []
    for c in chunks:
        if isinstance(c, dict):
            text = c.get("text") or c.get("content") or ""
            meta = c.get("metadata", {})
        else:
            text = str(c)
            meta = {}
        texts.append(text)
        metadatas.append(meta)

    if not texts:
        return []

    print(f"Bắt đầu tạo embeddings cho {len(texts)} chunk...")
    all_embeddings = embedding_model.encode(
        texts,
        show_progress_bar=True,
        batch_size=batch_size
    )

    chunks_with_embeddings = []
    for text, emb, meta in zip(texts, all_embeddings, metadatas):
        chunks_with_embeddings.append({
            "content": text,
            "vector": emb.tolist(),
            "metadata": meta or {}
        })

    print(f"Hoàn tất. Đã tạo embedding cho {len(chunks_with_embeddings)} chunk.")
    return chunks_with_embeddings

def generate_uuid(text_chunk: str):
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, text_chunk))


def normalize_property_key(key: str):
    """
    Chuyển key metadata thành dạng phù hợp làm tên property: không space, không ký tự lạ.
    (Bạn nên đảm bảo schema Weaviate tương thích với tên này.)
    """
    # thay space bằng underscore, loại ký tự không alpha-num-_ 
    key = str(key)
    key = re.sub(r'\s+', '_', key)
    key = re.sub(r'[^0-9A-Za-z_]', '', key)
    # tránh bắt đầu bằng số (Weaviate có thể cho phép, nhưng an toàn thì thêm prefix)
    if re.match(r'^\d', key):
        key = "k_" + key
    return key


def prepare_properties_from_metadata(content: str, metadata: dict):
    """
    Tạo dict properties để upsert vào Weaviate:
    - normalize key names
    - convert list/dict -> JSON string (an toàn nếu schema chưa support array/object)
    - skip None
    """
    props = {"content": content}
    if not metadata:
        return props

    for k, v in metadata.items():
        if v is None:
            continue
        nk = normalize_property_key(k)
        # nếu là list hoặc dict -> JSON stringify (để tránh lỗi nếu schema không tương thích)
        if isinstance(v, (list, dict)):
            try:
                props[nk] = json.dumps(v, ensure_ascii=False)
            except Exception:
                props[nk] = str(v)
        # numbers/bool/str -> keep as-is (Weaviate sẽ map theo schema)
        elif isinstance(v, (int, float, bool, str)):
            # cast to native python types (str giữ nguyên)
            props[nk] = v
        else:
            # fallback
            props[nk] = str(v)
    return props


def load_data_to_weaviate(chunks_with_embeddings, collection, batch_size=100, concurrent_requests=1):
    """
    chunks_with_embeddings: list of {"content":..., "vector":..., "metadata": {...}}
    collection: object có interface .batch.fixed_size(...). Sử dụng cùng API batch của bạn.
    """
    print(f"\nĐang nhập {len(chunks_with_embeddings)} chunk (với embeddings) vào Weaviate...")
    failed = 0
    with collection.batch.fixed_size(batch_size=batch_size, concurrent_requests=concurrent_requests) as batch:
        for data_obj in tqdm(chunks_with_embeddings, desc="Đang thêm chunk vào Weaviate"):
            try:
                content = data_obj.get("content", "")
                vector = data_obj.get("vector")
                metadata = data_obj.get("metadata", {}) or {}

                # chuẩn bị properties (có gộp metadata)
                properties = prepare_properties_from_metadata(content, metadata)

                # tạo uuid bền vững
                uuid_str = generate_uuid(content, metadata)

                # add object
                batch.add_object(
                    properties=properties,
                    vector=vector,
                    uuid=uuid_str
                )
            except Exception as e:
                failed += 1
                print(f"  ! Lỗi khi thêm 1 chunk: {e}")
    if failed:
        print(f"Hoàn tất với {failed} chunk lỗi.")
    else:
        print("Hoàn tất import vào Weaviate thành công.")
    