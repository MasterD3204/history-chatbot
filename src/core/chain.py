
import sys
import os

# Thêm thư mục gốc của dự án (đi lên 2 cấp từ file hiện tại) vào sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda, RunnableBranch
from sentence_transformers import SentenceTransformer
from src.core.config import class_name, embedding_model_name
from src.core.retriever import retriever_fn
from src.core.llm_handle import get_llm
from src.core.prompt import prompt


embedding_model = SentenceTransformer(embedding_model_name)



# 4. Xây dựng RAG Chain
# Chain này sẽ:
#   a. Lấy câu hỏi của người dùng.
#   b. Dùng retriever để truy xuất các tài liệu liên quan.
#   c. Đưa các tài liệu và câu hỏi vào prompt.
#   d. Truyền prompt đến LLM.
#   e. Phân tích kết quả đầu ra thành chuỗi.
openai_chain = prompt | get_llm("openai") | StrOutputParser()
gemini_chain = prompt | get_llm("gemini") | StrOutputParser()
cohere_chain = prompt | get_llm("cohere") | StrOutputParser() # Đây sẽ là nhánh mặc định
default_chain = prompt | get_llm("default") | StrOutputParser()


branch = RunnableBranch(
    (lambda x: x.get("llm_choice") == "openai", openai_chain),
    (lambda x: x.get("llm_choice") == "cohere", cohere_chain),
    (lambda x: x.get("llm_choice") == "gemini", gemini_chain),
    default_chain  # Nhánh mặc định nếu không có lựa chọn nào khớp
)

retriever_runnable = RunnableLambda(lambda query: retriever_fn(query, embedding_model))


rag_chain = (
    {
        "context": (lambda x: x["question"]) | retriever_runnable,
        "question": lambda x: x["question"],
        "llm_choice": lambda x: x["llm_choice"] # Quan trọng: phải truyền llm_choice vào cho Branch
    }
    | branch
)
