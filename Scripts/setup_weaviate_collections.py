from Core.weaviate_client import client

def setup_collection(class_name):
    if client.collections.exists(class_name):
        print(f"Collection '{class_name}' đã tồn tại. Đang tải về...")
        collection = client.collections.get(class_name)
        print(f"Collection '{class_name}' đã được tải thành công.")
    else:
        print(f"Đang tạo collection cho class '{class_name}'...")
        collection = client.collections.create(name=class_name, vector_config= None)
        print("Collections đã được tạo thành công.")
    return collection