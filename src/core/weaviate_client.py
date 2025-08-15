import os
import weaviate
from weaviate.classes.init import Auth
import os
from dotenv import load_dotenv

load_dotenv()

# Lấy từ biến môi trường
WEAVIATE_CLUSTER_URL = os.getenv("WEAVIATE_CLUSTER_URL")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")

if not all([WEAVIATE_CLUSTER_URL, WEAVIATE_API_KEY]):
    raise ValueError("Client URL và API KEY chưa được thiết lập.")

# Khởi tạo Weaviate Client
print("\nĐang kết nối đến Weaviate...")
client = weaviate.connect_to_weaviate_cloud(
    cluster_url=WEAVIATE_CLUSTER_URL,
    auth_credentials=Auth.api_key(WEAVIATE_API_KEY),
)

if client.is_ready():
    print("Kết nối Weaviate thành công!")
else:
    raise ConnectionError("Không thể kết nối đến Weaviate. Vui lòng kiểm tra URL và API Key.")


