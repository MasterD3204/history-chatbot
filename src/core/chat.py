import streamlit as st
from typing import Dict, Any

# Import RAG chain đã được xây dựng hoàn chỉnh từ module của bạn
from chain import rag_chain
# Import LLM_MAP để lấy danh sách các model cho người dùng chọn
from llm_handle import LLM_MAP

# --- 1. CẤU HÌNH TRANG VÀ TIÊU ĐỀ ---

# st.set_page_config để đặt tiêu đề và icon cho tab trình duyệt
st.set_page_config(page_title="Chatbot Lịch sử", page_icon="📜")

# st.title để hiển thị tiêu đề chính trên trang
st.title("📜 Chatbot Lịch sử Việt Nam")
st.caption("Cung cấp bởi các mô hình ngôn ngữ tiên tiến")

# --- 2. CẤU HÌNH THANH BÊN (SIDEBAR) ---

# st.sidebar cho phép tạo một thanh công cụ bên cạnh
with st.sidebar:
    st.header("Cấu hình")

    # Tạo một dropdown (selectbox) để người dùng chọn model
    # LLM_MAP.keys() sẽ lấy ra các lựa chọn: "gemini", "openai", "default"
    selected_model = st.selectbox(
        label="Chọn mô hình LLM",
        options=list(LLM_MAP.keys()),
        index=0  # Mặc định chọn model đầu tiên trong danh sách
    )

    # Tạo một thanh trượt (slider) để điều chỉnh nhiệt độ (temperature)
    # temperature = st.slider(
    #     label="Mức độ sáng tạo (Temperature)",
    #     min_value=0.0,
    #     max_value=1.0,
    #     value=0.5, # Giá trị mặc định
    #     step=0.1
    # )
    
    st.info("Lưu ý: Thay đổi mô hình hoặc cấu hình sẽ được áp dụng cho câu hỏi tiếp theo.")


# --- 3. KHỞI TẠO LỊCH SỬ CHAT ---

# Sử dụng st.session_state để lưu trữ tin nhắn giữa các lần chạy lại
# Điều này rất quan trọng để duy trì cuộc trò chuyện
if "messages" not in st.session_state:
    st.session_state.messages = [
        # Tin nhắn chào mừng ban đầu từ trợ lý
        {"role": "assistant", "content": "Xin chào! Tôi có thể giúp gì cho bạn về lịch sử Việt Nam?"}
    ]

# --- 4. HIỂN THỊ CÁC TIN NHẮN CŨ ---

# Lặp qua danh sách tin nhắn đã lưu và hiển thị chúng
for message in st.session_state.messages:
    # st.chat_message tạo một container cho tin nhắn với avatar tương ứng
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- 5. XỬ LÝ NHẬP LIỆU MỚI TỪ NGƯỜI DÙNG ---

# st.chat_input tạo một ô nhập liệu cố định ở cuối trang
if user_prompt := st.chat_input("Nhập câu hỏi của bạn..."):

    # 5.1. Lưu và hiển thị câu hỏi của người dùng
    st.session_state.messages.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        st.markdown(user_prompt)

    # 5.2. Tạo và hiển thị phản hồi từ LLM
    with st.chat_message("assistant"):
        # st.spinner tạo ra hiệu ứng chờ (animation) với thông báo
        with st.spinner("Đang suy nghĩ..."):
            
            # Chuẩn bị input cho RAG chain
            # Bao gồm câu hỏi, lựa chọn model và các cấu hình khác
            input_data: Dict[str, Any] = {
                "question": user_prompt,
                "llm_choice": selected_model
            }

            # Gọi RAG chain để lấy câu trả lời
            response = rag_chain.invoke(input_data)
            
            # Hiển thị câu trả lời
            st.markdown(response)

    # 5.3. Lưu lại câu trả lời của trợ lý vào lịch sử chat
    st.session_state.messages.append({"role": "assistant", "content": response})