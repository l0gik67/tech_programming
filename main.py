import queue
import threading
import sys
import time
import requests
from bs4 import BeautifulSoup
from flask import Flask, Response, send_from_directory
import json
import os

app = Flask(__name__)

# ─── Очередь для передачи логов из парсера в SSE-поток
log_queue = queue.Queue()
is_running = False



def log(msg):
    """Отправляет строку в очередь и в stdout."""
    print(msg, flush=True)
    log_queue.put(("log", str(msg)))


def get_game_sitemaps():
    index_url = "https://stopgame.ru/sitemap.xml"
    resp = requests.get(index_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    soup = BeautifulSoup(resp.text, "xml")
    return [loc.text for loc in soup.find_all("loc") if "games_" in loc.text]


def get_all_game_urls():
    all_urls = []
    for sitemap_url in get_game_sitemaps():
        resp = requests.get(sitemap_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")
        urls = [loc.text for loc in soup.find_all("loc")]
        all_urls.extend(urls)
    return all_urls


def parse_game_page(url):
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    soup = BeautifulSoup(resp.text, "html.parser")

    dl = soup.find("dl", class_=lambda c: c and "_game-info__grid" in c)
    data = {}
    if dl:
        items = dl.find_all(["dt", "dd"])
        for i, tag in enumerate(items):
            if tag.name == "dt":
                key = tag.get_text(strip=True)
                if i + 1 < len(items) and items[i + 1].name == "dd":
                    data[key] = items[i + 1].get_text(strip=True)

    rating_tag = soup.find("span", class_=lambda c: c and "_game-rating_" in c)
    votes_tag = soup.find("span", class_=lambda c: c and "_total-game-votes_" in c)

    return {
        "url": url,
        "date": data.get("Дата выхода"),
        "developer": data.get("Разработчик"),
        "platforms": data.get("Платформы"),
        "rating": rating_tag.get_text(strip=True) if rating_tag else None,
        "votes": votes_tag.get_text(strip=True) if votes_tag else None,
    }


def run_parser():
    global is_running
    is_running = True
    try:
        log("🔍 Получаем список URL из sitemap...")
        urls = get_all_game_urls()
        log(f"✅ Найдено {len(urls)} игр")

        games = []
        for i, url in enumerate(urls, 1):
            log(f"[{i}/{len(urls)}] Парсим: {url}")
            try:
                game = parse_game_page(url)
                games.append(game)
                log(f"  → {game.get('developer', '—')} | {game.get('date', '—')} | ★ {game.get('rating', '—')}")
            except Exception as e:
                log(f"  ✗ Ошибка: {e}")
            time.sleep(0.5)

        log(f"\n🏁 Готово! Обработано {len(games)} игр.")
        log_queue.put(("done", json.dumps(games, ensure_ascii=False)))
    except Exception as e:
        log(f"💥 Критическая ошибка: {e}")
        log_queue.put(("done", "[]"))
    finally:
        is_running = False


# ─── Маршруты Flask ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/start", methods=["POST"])
def start():
    global is_running
    if is_running:
        return {"status": "already_running"}, 409
    # Очищаем старую очередь
    while not log_queue.empty():
        log_queue.get_nowait()
    threading.Thread(target=run_parser, daemon=True).start()
    return {"status": "started"}


@app.route("/stream")
def stream():
    """Server-Sent Events: клиент подписывается и получает логи в реальном времени."""

    def event_generator():
        while True:
            try:
                kind, data = log_queue.get(timeout=30)
                yield f"event: {kind}\ndata: {data}\n\n"
                if kind == "done":
                    break
            except queue.Empty:
                yield "event: ping\ndata: \n\n"  # keepalive

    return Response(event_generator(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    print("Сервер запущен: http://localhost:5000")
    app.run(debug=False, threaded=True, port=5000)