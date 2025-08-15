from langchain_cohere import ChatCohere
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
import os
from dotenv import load_dotenv
from langchain_core.runnables import RunnableBranch, RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser


load_dotenv()

cohere_api_key = os.getenv("COHERE_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")
gemini_api_key = os.getenv("GEMINI_API_KEY")

llm_cohere = ChatCohere(
    cohere_api_key=cohere_api_key,
    model="command-r-plus", 
    temperature=0.7

)

llm_openai = ChatOpenAI(
    base_url="http://10.0.6.170:30132/v1", 
    api_key=openai_api_key,
    model="gpt-4.1",  # Model mặc định
    temperature=0.7,
    default_headers={"App-Code": "fresher"}, # Header bắt buộc
    model_kwargs={"extra_body": {
        "service": "generate_summary_for_langchain_app", # Tham số bổ sung cho logging
   
    }}
)

llm_gemini = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key = gemini_api_key, temperature = 0.7)

LLM_MAP = {
    "gemini": llm_gemini,
    "openai": llm_openai,
    "cohere": llm_cohere,
    #"default": llm_gemini
}

def get_llm(llm_choice: str):
    """Hàm tiện ích để lấy LLM từ map, nếu không có thì trả về default."""
    return LLM_MAP.get(llm_choice, LLM_MAP["gemini"])


