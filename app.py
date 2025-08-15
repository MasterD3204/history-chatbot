# --- File: src/app/chat.py ---

import streamlit as st
import uuid
from typing import Dict, Any, List

# Import RAG chain và các thành phần cần thiết
# Đảm bảo các đường dẫn import này chính xác với cấu trúc thư mục của bạn
from src.core.chain import rag_chain
from src.core.llm_handle import get_llm
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# --- 1. CẤU HÌNH TRANG VÀ TIÊU ĐỀ ---
st.set_page_config(page_title="Chatbot Lịch sử", page_icon="📜", layout="wide")
st.title("📜 Chatbot Lịch sử Việt Nam")
st.caption("Trò chuyện, khám phá và học hỏi về lịch sử dân tộc.")

# --- 2. HÀM TIỆN ÍCH ---

def format_chat_history(messages: List[Dict[str, str]]) -> str:
    """Định dạng lịch sử chat thành một chuỗi duy nhất cho chain."""
    if not messages:
        return ""
    recent_messages = messages[-10:]
    return "\n".join([f"{msg['role']}: {msg['content']}" for msg in recent_messages])

@st.cache_data(show_spinner=False)
def generate_conversation_title(question, answer):
    """
    Dùng LLM (model nhanh) để tạo tiêu đề cho cuộc hội thoại.
    """
    title_prompt = ChatPromptTemplate.from_template(
        "Dựa vào câu hỏi và câu trả lời đầu tiên dưới đây, hãy tạo ra một tiêu đề ngắn gọn (tối đa 7 từ) cho cuộc trò chuyện này.\n\n"
        "Câu hỏi: {question}\n"
        "Câu trả lời: {answer}\n\n"
        "Tiêu đề:"
    )
    title_generation_chain = title_prompt | get_llm("gemini") | StrOutputParser()
    return title_generation_chain.invoke({"question": question, "answer": answer})

# --- 3. KHỞI TẠO VÀ QUẢN LÝ SESSION STATE ---

if "conversations" not in st.session_state:
    st.session_state.conversations = {}

if "active_conversation_id" not in st.session_state:
    st.session_state.active_conversation_id = None

# --- 4. CẤU HÌNH THANH BÊN (SIDEBAR) ---

with st.sidebar:
    st.header("Cài đặt")
    selected_model = st.selectbox(
        label="Chọn mô hình LLM",
        options=["gemini", "openai", "cohere"],
        key="llm_choice_selector"
    )

    use_web_search = st.toggle(
        "🚀 Bật tìm kiếm Web",
        value=False, # Mặc định là tắt
        help="Khi được bật, chatbot sẽ sử dụng Google Search để bổ sung thông tin khi cần thiết."
    )
    # THÊM MỚI: Các widget cho cấu hình tìm kiếm
    selected_search_type = st.selectbox(
        label="Chọn phương pháp tìm kiếm",
        options=["hybrid", "semantic", "keyword"],
        index=0, # Mặc định là hybrid
        key="search_type_selector",
        help="""
        - **Hybrid**: Kết hợp Keyword và Semantic để có kết quả tốt nhất (khuyến nghị).
        - **Semantic**: Tìm kiếm dựa trên ý nghĩa của câu hỏi.
        - **Keyword**: Tìm kiếm dựa trên từ khóa chính xác.
        """
    )

    top_k_value = st.slider(
        label="Số lượng tài liệu truy xuất (Top K)",
        min_value=1,
        max_value=10,
        value=5, # Giá trị mặc định
        step=1,
        key="top_k_slider",
        help="Số lượng tài liệu liên quan nhất được dùng để tạo câu trả lời."
    )
    # KẾT THÚC THÊM MỚI

    st.divider()

    if st.button("💬 Trò chuyện mới", use_container_width=True):
        new_conv_id = str(uuid.uuid4())
        st.session_state.active_conversation_id = new_conv_id
        st.session_state.conversations[new_conv_id] = {
            "title": "Cuộc trò chuyện mới",
            "messages": [
                {"role": "assistant", "content": "Xin chào! Tôi có thể giúp gì cho bạn về lịch sử Việt Nam?"}
            ]
        }
        st.rerun()

    st.header("Lịch sử trò chuyện")
    sorted_conv_ids = sorted(st.session_state.conversations.keys(), reverse=True)
    
    for conv_id in sorted_conv_ids:
        if st.button(st.session_state.conversations[conv_id]["title"], key=f"conv_{conv_id}", use_container_width=True):
            st.session_state.active_conversation_id = conv_id
            st.rerun()
            
    if st.session_state.conversations:
        st.divider()
        if st.button("🗑️ Xóa toàn bộ lịch sử", use_container_width=True, type="primary"):
            st.session_state.conversations = {}
            st.session_state.active_conversation_id = None
            st.rerun()

# --- 5. HIỂN THỊ GIAO DIỆN CHAT CHÍNH ---

if st.session_state.active_conversation_id:
    active_id = st.session_state.active_conversation_id
    current_messages = st.session_state.conversations[active_id]["messages"]

    for message in current_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_prompt := st.chat_input("Nhập câu hỏi của bạn..."):
        chat_history_for_chain = format_chat_history(current_messages[1:])

        st.session_state.conversations[active_id]["messages"].append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Đang suy nghĩ..."):
                # CẬP NHẬT: Thêm các lựa chọn mới vào input_data
                input_data: Dict[str, Any] = {
                    "question": user_prompt,
                    "llm_choice": selected_model,
                    "search_type": selected_search_type, # Thêm lựa chọn tìm kiếm
                    "top_k": top_k_value,                 # Thêm giá trị top_k
                    "chat_history": chat_history_for_chain,
                    "use_web_search": use_web_search
                }
                response = rag_chain.invoke(input_data)
                st.markdown(response)
        
        st.session_state.conversations[active_id]["messages"].append({"role": "assistant", "content": response})

        if len(current_messages) == 3:
            new_title = generate_conversation_title(user_prompt, response)
            st.session_state.conversations[active_id]["title"] = new_title
            st.rerun()

else:
    st.info("Bắt đầu cuộc trò chuyện của bạn bằng cách nhấn vào nút '💬 Trò chuyện mới' ở thanh bên trái.")