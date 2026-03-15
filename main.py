import asyncio
import httpx
import random
import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

app = FastAPI()

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

class SearchRequest(BaseModel):
    target: str

# Тільки ті сайти, де реально працює перевірка без браузера
SITES = {
    "Telegram": "https://t.me/{url}",
    "GitHub": "https://github.com/{url}",
    "Steam": "https://steamcommunity.com/id/{url}",
    "Reddit": "https://www.reddit.com/user/{url}",
    "Pinterest": "https://www.pinterest.com/{url}/"
}

def generate_brute_variants(root: str) -> List[str]:
    r = root.lower().strip()
    # Базовий трансліт
    tr = str.maketrans("зерабвгдийклмнопстуфхц", "zerabvhdyklmnopstufhtc")
    base = r.translate(tr)
    
    variants = {r, base}
    # Додаємо цифри 0-9 до кожного варіанту
    extended = set()
    for v in variants:
        extended.add(v)
        for i in range(10): # Авто-дописування цифр
            extended.add(f"{v}{i}")
            extended.add(f"{v}_{i}")
    return list(extended)

async def check_site(client: httpx.AsyncClient, site_name: str, url_template: str, username: str):
    url = url_template.format(url=username)
    
    # Імітуємо реальну людину (заголовки)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate", # Обов'язково для стиснення
        "DNT": "1",
        "Connection": "keep-alive"
    }

    try:
        # Велика затримка, щоб не отримати бан миттєво
        await asyncio.sleep(random.uniform(0.5, 1.5))
        resp = await client.get(url, headers=headers, follow_redirects=True, timeout=10.0)
        
        if resp.status_code == 200:
            html = resp.text
            
            # --- TELEGRAM: Жорстка фільтрація ---
            if site_name == "Telegram":
                # Якщо акаунта нема, в мета-тегах буде стандартний текст "Contact @..."
                # Ми шукаємо ознаки ЖИВОГО профілю (опис або фото)
                has_extra = "tgme_page_extra" in html
                has_photo = "tgme_page_photo_image" in html
                if not (has_extra or has_photo):
                    return None
            
            # --- GITHUB ---
            if site_name == "GitHub" and "vcard-details" not in html:
                return None

            # --- REDDIT ---
            if site_name == "Reddit" and "user-name" not in html.lower():
                return None

            # Якщо в тексті є фрази-маркери видалення
            if any(x in html.lower() for x in ["404 not found", "page not found", "doesn't exist"]):
                return None

            return {"site": site_name, "url": str(resp.url), "match": username}
    except:
        pass
    return None

@app.post("/api/search")
async def osint_search(request: SearchRequest):
    root = request.target.strip()
    if len(root) < 2: return {"social_profiles": []}

    variants = generate_brute_variants(root)
    results = []
    
    # Використовуємо один клієнт на всі запити
    async with httpx.AsyncClient(http2=True, verify=False) as client:
        # Обмежуємо швидкість: пачки по 5 запитів
        for i in range(0, len(variants), 5):
            chunk = variants[i:i+5]
            tasks = [check_site(client, name, tmpl, var) for name, tmpl in SITES.items() for var in chunk]
            
            chunk_res = await asyncio.gather(*tasks)
            for r in chunk_res:
                if r: results.append(r)
            
            await asyncio.sleep(1) # Пауза між пачками

    return {"social_profiles": results}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)