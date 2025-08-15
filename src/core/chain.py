import sys
import os
import re
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

# --- CÁC HÀM VÀ CHAIN CƠ BẢN (giữ nguyên) ---

standalone_question_chain = (
    CONDENSE_QUESTION_PROMPT | get_llm("gemini") | StrOutputParser()
)

retriever_runnable = RunnableLambda(
    lambda x: retriever_fn(
        query=x["standalone_question"],
        embedding_model=embedding_model,
        search_type=x.get("search_type", "hybrid"),
        top_k=x.get("top_k", 5)
    )
)

def create_final_answer_chain():
    return RunnableBranch(
        (lambda x: x.get("llm_choice") == "openai", final_rag_prompt | get_llm("openai") | StrOutputParser()),
        (lambda x: x.get("llm_choice") == "cohere", final_rag_prompt | get_llm("cohere") | StrOutputParser()),
        final_rag_prompt | get_llm("gemini") | StrOutputParser(),
    )
final_answer_chain = create_final_answer_chain()

quality_check_chain = (
    RunnableParallel(
        question=lambda x: x["standalone_question"],
        context=lambda x: x["retrieved_docs"]["context"]
    )
    | QUALITY_CHECK_PROMPT
    | get_llm("gemini")
    | StrOutputParser()
)

# <--- LOGIC ĐIỀU PHỐI VÀ HÀM HỖ TRỢ (VIẾT LẠI HOÀN TOÀN) --->

def orchestrate_context_and_sources(inputs: Dict) -> Dict:
    """
    Hàm điều phối chính: quyết định và xây dựng context/sources cuối cùng.
    Hàm này đảm bảo context và sources luôn đồng bộ 100%.
    """
    decision = inputs["quality_decision"].strip().upper()
    rag_docs = inputs["retrieved_docs"]["sources"] # Đây là danh sách các doc từ retriever
    web_docs = inputs["web_search_results"]      # Đây là danh sách các doc từ web_search_fn
    
    print(f"Quyết định của Quality Check: {decision}")

    final_docs_to_process = []
    if decision == "GOOD":
        print("Sử dụng sources từ RAG.")
        final_docs_to_process = rag_docs
    elif decision == "BAD":
        print("Sử dụng sources từ Web Search.")
        final_docs_to_process = web_docs
    else: # "OKAY"
        print("Kết hợp sources từ RAG và Web Search.")
        final_docs_to_process = rag_docs + web_docs

    if not final_docs_to_process:
        return {"context": "Không tìm thấy thông tin phù hợp.", "sources": []}

    # Xây dựng context và sources cuối cùng từ danh sách đã chọn
    final_context_parts = []
    final_sources = []
    for i, doc in enumerate(final_docs_to_process):
        # Lấy nội dung từ retriever_fn (đã có trong source object) hoặc web_search_fn
        content = doc.get("content", "Không có nội dung.")
        final_context_parts.append(f"[SOURCE {i+1}]:\n{content}")
        
        # Tạo đối tượng source nhất quán để định dạng cuối cùng
        final_sources.append({
            "document_name": doc.get("document_name"),
            "url": doc.get("url"),
            "page": doc.get("page") # Sẽ là None cho nguồn web, không sao cả
        })
        
    final_context = "\n\n---\n\n".join(final_context_parts)
    
    return {"context": final_context, "sources": final_sources}


def format_final_response(input_dict: Dict) -> str:
    """
    Phân tích câu trả lời của LLM, chỉ hiển thị các nguồn thực sự được trích dẫn.
    (Hàm này giữ nguyên như phiên bản sửa lỗi trước, nó đã đúng)
    """
    llm_answer = input_dict.get("llm_answer", "")
    original_sources = input_dict.get("sources", [])
    
    no_info_string = "tôi xin lỗi, thông tin này không có trong các tài liệu của tôi"
    if no_info_string in llm_answer.lower() or not original_sources:
        return llm_answer

    cited_indices = re.findall(r'\[(\d+)\]', llm_answer)
    if not cited_indices:
        return llm_answer

    cited_doc_indices = sorted(list(set([int(i) - 1 for i in cited_indices])))
    
    filtered_sources = []
    for i in cited_doc_indices:
        if 0 <= i < len(original_sources):
            filtered_sources.append(original_sources[i])

    if not filtered_sources:
        return llm_answer

    source_list_md = "\n\n---\n\n**Nguồn tham khảo:**\n"
    for i, source in enumerate(filtered_sources):
        doc_name = source.get("document_name", "Không rõ tên")
        url = source.get("url")
        page = source.get("page")
        
        source_item = f"{i+1}. [{doc_name}]({url})"
        if page:
            source_item += f" (Trang {page})"
        source_list_md += source_item + "\n"

    return llm_answer + source_list_md

# --- XÂY DỰNG RAG CHAIN HOÀN CHỈNH (giữ nguyên cấu trúc) ---

# Bước 1: Tạo câu hỏi độc lập
prepare_standalone_question = RunnablePassthrough.assign(
    standalone_question=RunnableBranch(
        (lambda x: x.get("chat_history"), standalone_question_chain),
        lambda x: x["question"],
    )
)

# Bước 2: Truy xuất tài liệu RAG và chạy Web Search (nếu cần) song song
retrieval_and_search = RunnablePassthrough.assign(
    retrieved_docs=retriever_runnable,
    web_search_results=RunnableBranch(
        (lambda x: x.get("use_web_search", False), RunnableLambda(lambda x: web_search_fn(x["standalone_question"]))),
        lambda x: [] # Trả về danh sách rỗng nếu không dùng web search
    )
)

# Bước 3: Điều phối context và sources
orchestration_chain = RunnableBranch(
    (
        lambda x: x.get("use_web_search", False),
        RunnablePassthrough.assign(
            quality_decision=quality_check_chain,
        ) | RunnableLambda(orchestrate_context_and_sources)
    ),
    # Nếu không dùng web search, chỉ cần lấy kết quả từ retriever
    lambda x: {
        "context": x["retrieved_docs"]["context"], 
        "sources": x["retrieved_docs"]["sources"]
    }
)

# Bước 4: Tạo đầu vào cuối cùng cho LLM
final_llm_input_constructor = lambda x: {
    "question": x["standalone_question"],
    "chat_history": x["chat_history"],
    "llm_choice": x["llm_choice"],
    "context": x["final_context_and_sources"]["context"]
}

# Bước 5: Ghép nối tất cả lại thành chuỗi cuối cùng
rag_chain = (
    prepare_standalone_question
    | retrieval_and_search
    | RunnablePassthrough.assign(
        final_context_and_sources=orchestration_chain
    )
    | RunnablePassthrough.assign(
        llm_answer=(final_llm_input_constructor | final_answer_chain)
    )
    | RunnableLambda(
        lambda x: format_final_response({
            "llm_answer": x["llm_answer"],
            "sources": x["final_context_and_sources"]["sources"]
        })
    )
)