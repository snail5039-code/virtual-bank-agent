# 사용할 LLM 을 한 곳에서 만듭니다.
# src/.env 의 GEMINI_API_KEY 를 읽습니다. (웹 복사본도 키는 한 곳, src/.env 를 같이 씁니다)

import logging
from pathlib import Path

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv(Path(__file__).resolve().parents[2] / "src" / ".env")     # web/bank/model.py → 프로젝트/src/.env

# 라이브러리가 화면에 띄우는 경고 문구를 끕니다.
logging.getLogger("google_genai").setLevel(logging.ERROR)
logging.getLogger("google.genai").setLevel(logging.ERROR)

MODEL_NAME = "gemini-3.6-flash"
llm = ChatGoogleGenerativeAI(model=MODEL_NAME)
