# push.py - FernBrom 每日推播 + 天氣 + 植物小知識
import os
import random
from datetime import datetime, timezone
from flask import Flask, jsonify
from linebot import LineBotApi
from linebot.models import TextSendMessage
from supabase import create_client, Client
import requests
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit
import urllib3

# -------------------- 警告抑制 --------------------
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# -------------------- 環境變數 --------------------
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CWA_API_KEY = os.getenv("CWA_API_KEY")  # 中央氣象署授權碼

# -------------------- 初始化 --------------------
app = Flask(__name__)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN) if LINE_CHANNEL_ACCESS_TOKEN else None
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# -------------------- 城市對照表 --------------------
CITY_MAPPING = {
    "基隆": "基隆市", "台北": "臺北市", "新北": "新北市", "板橋": "新北市",
    "桃園": "桃園市", "中壢": "桃園市", "新竹": "新竹市", "竹北": "新竹縣",
    "台中": "臺中市", "台南": "臺南市", "高雄": "高雄市"
}

# -------------------- 天氣 API --------------------
def get_weather(city):
    city_name = CITY_MAPPING.get(city, city)
    if not CWA_API_KEY:
        return {"success": False, "message": "未設定氣象API金鑰"}
    dataset_id = 'F-C0032-001'  # 一般天氣預報-今明36小時
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{dataset_id}?Authorization={CWA_API_KEY}&format=JSON&locationName={city_name}"
    try:
        res = requests.get(url, timeout=10, verify=False)
        res.raise_for_status()
        data = res.json()
        location = data['records']['location'][0]
        elements = location['weatherElement']
        weather_status = elements[0]['time'][0]['parameter']['parameterName']
        rain_prob = int(elements[1]['time'][0]['parameter']['parameterName'])
        min_temp = int(elements[2]['time'][0]['parameter']['parameterName'])
        max_temp = int(elements[4]['time'][0]['parameter']['parameterName'])
        return {
            "success": True,
            "city": location['locationName'],
            "status": weather_status,
            "max_temp": max_temp,
            "min_temp": min_temp,
            "rain_prob": rain_prob
        }
    except Exception as e:
        return {"success": False, "message": f"天氣取得失敗: {e}"}

def get_watering_advice(weather_data):
    rain_prob = weather_data.get('rain_prob', 0)
    temp = weather_data.get('max_temp', 25)
    if rain_prob >= 70:
        return "今天會下雨，戶外植物不用澆水，室內等土乾再澆"
    elif rain_prob >= 40:
        return "有下雨機會，室內植物今天先不用澆"
    elif temp >= 30:
        return "天氣炎熱，可以幫植物補水，但等土乾再澆"
    elif temp <= 15:
        return "天氣偏冷，植物進入休眠期，減少澆水"
    else:
        return "天氣不錯，正常澆水就好"

# -------------------- 植物小知識 --------------------
_last_fact = None
LOCAL_FACTS = [
    "仙人掌的刺其實是變態葉，用來減少水分蒸發",
    "香蕉是莓果，草莓不是，植物界也搞詐欺",
    "蘆薈晚上會釋放氧氣，很適合放臥室",
    "竹子其實是草，不是樹，一天可長一米",
    "向日葵會跟著太陽轉，是因為莖部生長素怕光",
    "鳳梨每一粒「眼睛」都是一朵花",
    "含羞草閉合不是害羞，是為了嚇跑草食動物",
    "番茄是水果，但我們當蔬菜用",
    "龜背芋的洞洞讓陽光穿透到下面的葉子",
    "多肉植物晚上吸收二氧化碳，白天關閉氣孔"
]

def get_daily_plant_fact():
    global _last_fact
    fact = random.choice(LOCAL_FACTS)
    attempts = 0
    while fact == _last_fact and attempts < 5:
        fact = random.choice(LOCAL_FACTS)
        attempts += 1
    _last_fact = fact
    return fact

# -------------------- 用戶管理 --------------------
def get_subscribers():
    if not supabase: return []
    try:
        res = supabase.table('subscribers').select('*').eq('is_active', True).execute()
        return res.data or []
    except: return []

def get_user_city(user_id):
    if not supabase: return None
    try:
        res = supabase.table('users').select('city').eq('user_id', user_id).execute()
        if res.data and res.data[0].get('city'):
            return res.data[0]['city']
        return "桃園"  # 預設
    except: return "桃園"

def update_last_push(user_id, date_str):
    if not supabase: return
    try:
        supabase.table('subscribers').update({'last_push_date': date_str}).eq('user_id', user_id).execute()
    except: pass

# -------------------- 每日推播 --------------------
def send_daily_push():
    if not line_bot_api or not supabase:
        print("LINE 或 Supabase 未初始化")
        return
    today = datetime.now(timezone.utc).date().isoformat()
    subscribers = get_subscribers()
    for sub in subscribers:
        if sub.get('last_push_date') == today:
            continue
        user_id = sub['user_id']
        city = get_user_city(user_id)
        weather_text = ""
        weather = get_weather(city)
        if weather['success']:
            advice = get_watering_advice(weather)
            weather_text = f"\n今日天氣（{weather['city']}）：{weather['status']}，最高{weather['max_temp']}°C，最低{weather['min_temp']}°C，降雨機率{weather['rain_prob']}%\n澆水建議：{advice}"
        message_text = f"🌱 蕨積早安！\n\n今日植物小知識：{get_daily_plant_fact()}{weather_text}"
        try:
            line_bot_api.push_message(user_id, TextSendMessage(text=message_text))
            update_last_push(user_id, today)
            print(f"推播成功: {user_id}")
        except Exception as e:
            print(f"推播失敗 {user_id}: {e}")

# -------------------- 排程器 --------------------
def init_scheduler():
    scheduler = BackgroundScheduler()
    tz = pytz.timezone('Asia/Taipei')
    scheduler.add_job(send_daily_push, CronTrigger(hour=8, minute=0, timezone=tz), id='daily_push', replace_existing=True)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())
    print("排程器啟動，每天 08:00 推播")
    return scheduler

# -------------------- 測試端點 --------------------
@app.route("/push-daily", methods=['GET'])
def test_push():
    send_daily_push()
    return jsonify({"status": "push triggered"})

@app.route("/", methods=['GET'])
def health():
    return jsonify({"status": "running"})

# -------------------- 啟動 --------------------
if __name__ == "__main__":
    scheduler = init_scheduler()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
