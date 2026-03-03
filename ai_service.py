import google.genai as genai
import os
import json

def get_ai_model():
    api_key = os.getenv('GEMINI_API_KEY') or os.getenv('API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing")
    client = genai.Client(api_key=api_key)
    return client

def process_user_request(prompt, context):
    client = get_ai_model()
    system_instruction = f"""
            Ты — ассистент курса. 
            ВАЖНЫЕ ПРАВИЛА:
            1. В листе 'Таблица выбора' названия курсов находятся в СТРОКАХ 5 и 6. Используй их как основные заголовки.
            2. В листе 'Расписание' хранятся ссылки на календари. Твоя задача — найти название курса и вернуть соответствующую ему ссылку.
            3. Если пользователь просит расписание, ищи совпадения названий между листами.
            
            Контекст:
            Курсы (Таблица выбора): {json.dumps(context.get('sheetData', []))}
            Расписание: {json.dumps(context.get('scheduleData', []))}
    """
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "system_instruction": system_instruction,
            "response_mime_type": "text/plain"
        }
    )
    return response.text

def process_user_request_json(prompt, context):
    client = get_ai_model()
    system_instruction = f"""
        Ты — ассистент курса. Возвращай только JSON.
        Логика: названия курсов в 'Таблица выбора' в строках 5-6.
        Если пользователь просит CSV или файл, определи тип действия.
        
        Контекст:
        Sheet Data: {json.dumps(context.get('sheetData', []))}
    """
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "system_instruction": system_instruction,
            "response_mime_type": "application/json"
        }
    )
    return response.text

def summarize_course_description(url, course_name):
    client = get_ai_model()
    prompt = f"Summarize the course description for '{course_name}' found at this URL: {url}"
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "response_mime_type": "text/plain"
        }
    )
    return response.text