import sys
import os
from typing import Dict, List, Any

# Thêm thư mục gốc vào sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda, RunnableBranch, RunnableParallel

from sentence_transformers import SentenceTransformer

from src.core.config import embedding_model_name
from src.core.retriever import retriever_fn
from src.core.llm_handle import get_llm
from src.core.prompt import prompt as final_rag_prompt, CONDENSE_QUESTION_PROMPT, QUALITY_CHECK_PROMPT
from src.core.web_search import web_search_fn

embedding_model = SentenceTransformer(embedding_model_name)

# --- CÁC HÀM VÀ CHAIN CƠ BẢN ---

# 1. Chain tạo câu hỏi độc lập
standalone_question_chain = (
    CONDENSE_QUESTION_PROMPT
    | get_llm("gemini")
    | StrOutputParser()
)

# 2. Runnable truy xuất tài liệu (retriever)
# Bây giờ nó trả về một dict {"context": ..., "sources": ...}
retriever_runnable = RunnableLambda(
    lambda x: retriever_fn(
        query=x["standalone_question"],
        embedding_model=embedding_model,
        search_type=x.get("search_type", "hybrid"),
        top_k=x.get("top_k", 5)
    )
)

# 3. Chain sinh câu trả lời (từ prompt đã cập nhật)
def create_final_answer_chain():
    return RunnableBranch(
        (lambda x: x.get("llm_choice") == "openai", final_rag_prompt | get_llm("openai") | StrOutputParser()),
        (lambda x: x.get("llm_choice") == "cohere", final_rag_prompt | get_llm("cohere") | StrOutputParser()),
        final_rag_prompt | get_llm("gemini") | StrOutputParser(),
    )
final_answer_chain = create_final_answer_chain()

# 4. Chain kiểm tra chất lượng tài liệu
quality_check_chain = (
    RunnableParallel(
        # Lấy context string từ dict của retriever
        question=lambda x: x["standalone_question"],
        context=lambda x: x["retrieved_docs"]["context"]
    )
    | QUALITY_CHECK_PROMPT
    | get_llm("gemini")
    | StrOutputParser()
)

# --- LOGIC ĐIỀU PHỐI VÀ HÀM HỖ TRỢ ---

def combine_contexts(inputs: Dict) -> str:
    """Hàm logic kết hợp context từ RAG và/hoặc Web Search."""
    decision = inputs["quality_decision"].strip().upper()
    retrieved_context = inputs["retrieved_docs"]["context"]

    print(f"Quyết định của Quality Check: {decision}")

    if decision == "GOOD":
        print("Sử dụng context từ RAG.")
        return retrieved_context
    elif decision == "OKAY":
        print("Sử dụng kết hợp context từ RAG và Web Search.")
        web_context = web_search_fn(inputs["standalone_question"])
        # Web search không có chú thích nguồn có cấu trúc
        return f"Dưới đây là một số thông tin từ cơ sở dữ liệu nội bộ:\n{retrieved_context}\n\n---\n\nDưới đây là thông tin bổ sung từ tìm kiếm web (không có chú thích nguồn chi tiết):\n{web_context}"
    else: # "BAD"
        print("Sử dụng context từ Web Search.")
        web_context = web_search_fn(inputs["standalone_question"])
        return f"Tôi không tìm thấy thông tin trong cơ sở dữ liệu nội bộ. Dưới đây là thông tin từ tìm kiếm web (không có chú thích nguồn chi tiết):\n{web_context}"

def format_final_response(input_dict: Dict) -> str:
    """
    Nối danh sách nguồn tham khảo vào cuối câu trả lời của LLM.
    """
    llm_answer = input_dict.get("llm_answer", "")
    sources = input_dict.get("sources", [])
    
    if not sources:
        return llm_answer

    # Xây dựng phần nguồn tham khảo bằng Markdown
    source_list_md = "\n\n---\n\n**Nguồn tham khảo:**\n"
    unique_sources = []
    seen_sources = set()

    # Lọc các nguồn trùng lặp
    for source in sources:
        # Tạo một tuple để kiểm tra sự tồn tại
        source_tuple = (source.get("document_name"), source.get("url"), source.get("page"))
        if source.get("url") and source_tuple not in seen_sources:
            unique_sources.append(source)
            seen_sources.add(source_tuple)
    
    # Tạo danh sách Markdown
    for i, source in enumerate(unique_sources):
        doc_name = source.get("document_name", "Không rõ tên")
        url = source.get("url")
        page = source.get("page")
        
        # Tạo link Markdown
        source_item = f"{i+1}. [{doc_name}]({url})"
        if page:
            source_item += f" (Trang {page})"
        source_list_md += source_item + "\n"

    return llm_answer + source_list_md

# --- XÂY DỰNG RAG CHAIN HOÀN CHỈNH ---

# Bước 1: Chuẩn bị dữ liệu ban đầu
# Tạo câu hỏi độc lập và chạy retriever.
# Kết quả của retriever được gán vào 'retrieved_docs'
prepare_retrieval_chain = RunnablePassthrough.assign(
    standalone_question=RunnableBranch(
        (lambda x: x.get("chat_history"), standalone_question_chain),
        lambda x: x["question"],
    )
).assign(
    retrieved_docs=retriever_runnable
)

# Bước 2: Xây dựng đầu vào cho prompt cuối cùng
# Phần này quyết định context cuối cùng sẽ là gì (chỉ RAG, RAG + Web, hoặc chỉ Web)
final_input_constructor = RunnableParallel(
    question=lambda x: x["standalone_question"],
    chat_history=lambda x: x["chat_history"],
    llm_choice=lambda x: x["llm_choice"],
    context=RunnableBranch(
        (
            lambda x: x.get("use_web_search", False),
            RunnablePassthrough.assign(quality_decision=quality_check_chain) | RunnableLambda(combine_contexts)
        ),
        # Nếu không dùng web search, chỉ lấy context string từ retriever
        lambda x: x["retrieved_docs"]["context"]
    )
)

# Bước 3: Ghép nối tất cả lại thành chuỗi cuối cùng
rag_chain = (
    prepare_retrieval_chain
    | RunnablePassthrough.assign(
        # Chạy LLM để tạo câu trả lời, kết quả được gán vào 'llm_answer'
        llm_answer=(final_input_constructor | final_answer_chain)
    )
    # Lấy 'llm_answer' và 'sources' từ 'retrieved_docs' để định dạng ouput cuối cùng
    | RunnableLambda(
        lambda x: format_final_response({
            "llm_answer": x["llm_answer"],
            # Chỉ thêm nguồn khi không sử dụng tìm kiếm web (để đảm bảo tính chính xác)
            "sources": x["retrieved_docs"]["sources"] if not x.get("use_web_search") else []
        })
    )
)