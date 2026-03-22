import json
import requests
import base64
import time
import random

API_KEY = "4F111763288F27D4A6B54BC567E2C8EC"
SECRET_KEY = "B85057DFA6178AC845D629440296EB1E"


class Text2ImageAPI:
    def __init__(self, url, api_key, secret_key):
        self.URL = url
        self.AUTH_HEADERS = {
            'X-Key': f'Key {api_key}',
            'X-Secret': f'Secret {secret_key}',
        }

    def get_model(self):
        response = requests.get(self.URL + 'key/api/v1/models', headers=self.AUTH_HEADERS)
        data = response.json()
        if data and isinstance(data, list) and len(data) > 0:
            return data[0]['id']
        raise ValueError("Некорректный ответ от API Kandinsky")

    def generate(self, prompt, model, width=1024, height=1024, style=None):
        selected_style = style if style else random.choice(["UHD", "DEFAULT"])
        params = {
            "type": "GENERATE",
            "numImages": 1,
            "width": width,
            "height": height,
            "generateParams": {"query": prompt, "no_text": True},
            "style": selected_style
        }
        data = {
            'model_id': (None, str(model)),
            'params': (None, json.dumps(params), 'application/json')
        }
        response = requests.post(self.URL + 'key/api/v1/text2image/run', headers=self.AUTH_HEADERS, files=data)
        if response.status_code == 201:
            return response.json()['uuid']
        print(f"Ошибка генерации: {response.status_code} - {response.text}")
        return None

    def check_generation(self, request_id, max_wait=180, delay=10):
        attempts = max_wait // delay
        while attempts > 0:
            response = requests.get(self.URL + 'key/api/v1/text2image/status/' + request_id, headers=self.AUTH_HEADERS)
            data = response.json()
            if data['status'] == 'DONE':
                return data['images']
            attempts -= 1
            time.sleep(delay)
        return None


def generate_image_with_kandinsky(prompt, additional_prompt=None):
    query = prompt + (f", {additional_prompt}" if additional_prompt else "")
    api = Text2ImageAPI('https://api-key.fusionbrain.ai/', API_KEY, SECRET_KEY)
    try:
        model_id = api.get_model()
        uuid = api.generate(query, model_id)
        if uuid:
            images = api.check_generation(uuid)
            if images:
                return base64.b64decode(images[0])
    except Exception as e:
        print(f"Ошибка Kandinsky: {e}")
    return None
