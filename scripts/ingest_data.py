import sys
import os
script_dir = os.path.dirname(os.path.abspath(__file__)) # Lấy đường dẫn thư mục 'scripts'
project_root = os.path.dirname(script_dir) # Đi ngược lên một cấp để lấy thư mục gốc
sys.path.append(project_root) 

from src.core.weaviate_client import client
from src.data_processing.extract_pdf import process_all_pdfs_in_directory
from pathlib import Path
from src.data_processing.ingestion_utils import embedd_chunks, load_data_to_weaviate
from sentence_transformers import SentenceTransformer
from src.core.config import class_name

# tạo collection trên weaviate
if client.collections.exists(class_name):
    print(f"Collection '{class_name}' đã tồn tại. Đang tải về...")
    collection = client.collections.get(class_name)
    print(f"Collection '{class_name}' đã được tải thành công.")
else:
    print(f"Đang tạo collection cho class '{class_name}'...")
    collection = client.collections.create(name=class_name, vector_config= None)
    print("Collections đã được tạo thành công.")


base_dir = Path("/home/misa/history-chatbot")

# extract và làm sạch data
pdf_directory = base_dir / "data/raw data"
output_directory = base_dir / "data/clean data"
config_path = base_dir  / "src/data_processing/config_extract_data.json"

print("Đang tải model embedding...")
embedding_model = SentenceTransformer("Qwen/Qwen3-Embedding-0.6B")
print("Tải model thành công.")

# extrac từ file pdf và làm sạch, chunking data
chunks = process_all_pdfs_in_directory(
    pdf_directory,
    output_directory,
    config_path=config_path,
    default_start_page=1,
    default_end_page=None,   # None = tới cuối file
    chunk_size_words=512,
    chunk_overlap_words=128
)
chunks_with_embeddings = embedd_chunks(chunks, embedding_model)
load_data_to_weaviate(chunks_with_embeddings, collection)




