# 사용할 LLM 을 한 곳에서 만듭니다.
# .env 의 GOOGLE_API_KEY 를 읽습니다.

import logging

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# 라이브러리가 화면에 띄우는 경고 문구를 끕니다.
logging.getLogger("google_genai").setLevel(logging.ERROR)
logging.getLogger("google.genai").setLevel(logging.ERROR)

MODEL_NAME = "gemini-3.6-flash"
llm = ChatGoogleGenerativeAI(model=MODEL_NAME)
