"""
ELGAKU to'liq server — mustaqil fayl (hech narsa bilan qo'shilmaydi)

Nima qiladi:
  1) Saytni root papkadan ko'rsatadi: index.html, css/, images/, js/, music/
  2) GET  /api/apk/music        — musiqa ro'yxati (ilova uchun)
  3) POST /api/ai/chat           — AI murabbiy (elgaku_qa_base.json)

Ishga tushirish:
  pip install -r requirements.txt
  python server.py   (port 8000)

Reponga nima qo'yiladi:
  server.py
  requirements.txt
  elgaku_qa_base.json
  (mavjud: index.html, css/, images/, js/, music/)
"""

import json
import re
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)
from flask_cors import CORS
CORS(app)

ROOT = Path(__file__).parent
MUSIC_DIR = ROOT / "music"
QA_PATH = ROOT / "elgaku_qa_base.json"

# ── Q&A bazani yuklash ──
KB = json.loads(QA_PATH.read_text(encoding="utf-8")) if QA_PATH.exists() else {}
QA_INDEX = []
for cat in KB.get("categories", []):
    for item in cat.get("qa", []):
        kws = set()
        for q in item.get("q", []):
            for w in re.findall(r"[a-z']+", q.lower()):
                if len(w) >= 3:
                    kws.add(w)
        QA_INDEX.append({"kws": kws, "answer": item.get("a", "")})


def tokenize(text: str):
    return set(w for w in re.findall(r"[a-z']+", text.lower()) if len(w) >= 3)


def best_reply(message: str) -> str:
    msg = tokenize(message)
    if not msg:
        return "Salom! 👋 Men sizning shaxsiy murabbiyingizman. 'Bugun nima qilay?' deb yozing."
    best_score, best_answer = 0, None
    for e in QA_INDEX:
        s = len(msg & e["kws"])
        if s > best_score:
            best_score, best_answer = s, e["answer"]
    if best_answer and best_score >= 1:
        return best_answer
    return ("Tushundim! 🤔 Bu savolni hozircha topa olmadim. Lekin yordam bera olaman:\n\n"
            "• 'Bugun nima qilay?' — mashq tanlayman\n"
            "• 'Menga haftalik reja tuz' — to'liq jadval\n"
            "• 'Texnika maslahat' — yugurish uslubi\n"
            "• 'Motivatsiya kerak' — sizni ruhlantiraman 💪")


# ── MUSIQa endpoint (ilova musiqa pleeri uchun) ──
@app.get("/api/apk/music")
def list_music():
    """music/ papkadagi fayllar ro'yxatini JSON qaytaradi."""
    songs = []
    if MUSIC_DIR.exists():
        for f in sorted(MUSIC_DIR.iterdir()):
            if f.is_file() and f.suffix.lower() in (".mp3", ".m4a", ".wav", ".ogg"):
                songs.append({
                    "id": f.stem,
                    "title": f.stem.replace("_", " "),
                    "url": f"/music/{f.name}"
                })
    return jsonify({"songs": songs, "count": len(songs)})


# ── AI murabbiy endpoint ──
@app.post("/api/ai/chat")
def ai_chat():
    data = request.get_json(silent=True) or {}
    msg = (data.get("message") or "").strip()
    if not msg:
        return jsonify({"reply": "Iltimos, savol yozing! 👋"})
    return jsonify({"reply": best_reply(msg)})


# ── Sayt (root'dagi statik fayllar) ──
@app.get("/")
def index():
    idx = ROOT / "index.html"
    if idx.exists():
        return send_from_directory(ROOT, "index.html")
    return "ELGAKU server ishlayapti ✅"


@app.get("/<path:path>")
def static_files(path: str):
    full = ROOT / path
    if full.is_file():
        return send_from_directory(ROOT, path)
    return "Not found", 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
