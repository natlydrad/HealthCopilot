from openai import OpenAI
client = OpenAI()

def parse_ingredients(text):
    prompt = f"""
    Extract foods from: "{text}".
    Return JSON array with objects: name, quantity (float), unit (string).
    If unknown quantity, use null.
    """
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={ "type": "json_object" }
    )
    return resp.choices[0].message.parsed
