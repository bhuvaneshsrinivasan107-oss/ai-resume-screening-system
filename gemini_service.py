import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

client = None

if API_KEY:
    client = genai.Client(api_key=API_KEY)


def ask_gemini(prompt):

    if not client:
        return None, "Gemini API key is not configured."

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        return response.text, None

    except Exception as e:
        return None, str(e)