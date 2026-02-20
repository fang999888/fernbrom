import os
import logging
import requests
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 日誌設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# DeepSeek API
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

SYSTEM_PROMPT = """
你是一位擁有20年經驗的環境永續發展專家，精通全球ESG發展史與碳管理。
請協助企業計算碳足跡，提供專業建議。
"""

def ask_deepseek_carbon(question: str):
    """呼叫 DeepSeek API 回覆碳盤查建議"""
    if not DEEPSEEK_API_KEY:
        return "❌ DEEPSEEK_API_KEY 未設定"
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question}
        ],
        "max_tokens": 400,
        "temperature": 0.2
    }
    try:
        resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        logger.error(f"DeepSeek 呼叫失敗: {e}")
        return "⚠️ AI 回覆失敗，請稍後再試"

# --------- CLI 測試 ---------
if __name__ == "__main__":
    print("碳盤查小幫手 CLI 測試")
    while True:
        q = input("請輸入企業碳盤查問題 (exit 離開): ")
        if q.lower() in ["exit", "quit"]:
            break
        answer = ask_deepseek_carbon(q)
        print("\n[建議]\n", answer, "\n")
