from langchain.text_splitter import RecursiveCharacterTextSplitter
import uuid
from tqdm import tqdm

def chunk_text(text):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=512,
        chunk_overlap=128,
        length_function=len,
        add_start_index=True # Thêm chỉ mục bắt đầu của chunk trong văn bản gốc
    )

    chunks = text_splitter.split_text(text)

    return chunks

def embedd_chunk(chunks, embedding_model):
    print(f"Bắt đầu tạo embeddings cho {len(chunks)} chunk...")

    all_embeddings = embedding_model.encode(
        chunks, 
        show_progress_bar=True,
        batch_size=32 # Bạn có thể điều chỉnh batch_size tùy vào RAM/VRAM
    )

    chunks_with_embeddings = [
        {"content": chunk, "vector": embedding.tolist()} 
        for chunk, embedding in zip(chunks, all_embeddings)
    ]

    print(f"Hoàn tất. Đã tạo embedding cho {len(chunks_with_embeddings)} chunk.")
    return chunks_with_embeddings

def generate_uuid(text_chunk: str):
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, text_chunk))

def load_data_to_weaviate(chunks_with_embeddings, collection):
    print(f"\nĐang nhập {len(chunks_with_embeddings)} chunk (với embeddings) vào Weaviate...")
    with collection.batch.fixed_size(batch_size=100, concurrent_requests=1) as batch:
        for data_obj in tqdm(chunks_with_embeddings, desc="Đang thêm chunk vào Weaviate"):
            properties = {
                "content": data_obj["content"]
            }
            vector = data_obj["vector"]

            batch.add_object(
                properties = properties,
                vector = vector,
                uuid=generate_uuid(data_obj["content"])
            )

    