from langchain.text_splitter import RecursiveCharacterTextSplitter

def chunk_text(text):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=512,
        chunk_overlap=128,
        length_function=len,
        add_start_index=True # Thêm chỉ mục bắt đầu của chunk trong văn bản gốc
    )

    chunks = text_splitter.split_text(text)

    # 3. In kết quả
    # for i, chunk in enumerate(chunks):
    #     print(f"--- Chunk {i+1} (Length: {len(chunk)}) ---")
    #     print(chunk)
    #     print("-" * 30)
    return chunks

# def embedd_chunk(chunks, embedding_model):
#     hash