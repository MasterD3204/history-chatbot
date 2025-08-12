import sys
import os
script_dir = os.path.dirname(os.path.abspath(__file__)) # Lấy đường dẫn thư mục 'scripts'
project_root = os.path.dirname(script_dir) # Đi ngược lên một cấp để lấy thư mục gốc
sys.path.append(project_root) 

from src.core.weaviate_client import client
from src.data_processing.extract_pdf import process_all_pdfs_in_directory, load_config_from_json
from pathlib import Path
from src.data_processing.ingestion_utils import chunk_text, embedd_chunk, load_data_to_weaviate
from sentence_transformers import SentenceTransformer


# tạo collection trên weaviate
class_name = "History Document"

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
config_dict = load_config_from_json(config_path)
process_all_pdfs_in_directory(pdf_directory, output_directory, config_dict)

print("Đang tải model embedding...")
embedding_model = SentenceTransformer("Qwen/Qwen3-Embedding-0.6B")
print("Tải model thành công.")

# chunking, embedding và load lên collection
for i, file_path in enumerate(output_directory.glob("*.txt")):
    print(f"--- Đang đọc file: {file_path.name} ---")
    text = noi_dung = file_path.read_text(encoding='utf-8')
    print(f"--- Đang thực hiện chunking")
    chunks = chunk_text(text)
    chunks_with_embeddings = embedd_chunk(chunks, embedding_model)
    load_data_to_weaviate(chunks_with_embeddings, collection)
    print(f"Hoàn tất nhập dữ liệu từ {i+1} file.")




