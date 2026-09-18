import os, io, time, sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
import pandas as pd
import requests

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-in-render")
DB_PATH = os.getenv("DB_PATH", "tiktok_monitor.db")

API_URL = "https://api.scrapecreators.com/v1/tiktok/profile"
TIMEOUT = 60
REQUEST_DELAY = 1.0
CACHE_MAX_AGE = os.getenv("SCRAPECREATORS_CACHE_MAX_AGE", "1").strip()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS accounts(
      username TEXT PRIMARY KEY, added_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS stats(
      id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL,
      display_name TEXT, posts INTEGER, following INTEGER, followers INTEGER,
      likes INTEGER, checked_at TEXT NOT NULL, status TEXT NOT NULL)""")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(stats)").fetchall()}
    if "display_name" not in cols:
        conn.execute("ALTER TABLE stats ADD COLUMN display_name TEXT")
    conn.commit()
    return conn

def norm(v):
    v = str(v).strip()
    if "tiktok.com/@" in v:
        v = v.split("tiktok.com/@", 1)[1].split("/", 1)[0].split("?", 1)[0]
    return v.lstrip("@").strip()

def api_key():
    return os.getenv("SCRAPECREATORS_API_KEY", "").strip()

def _find_profile(payload):
    # ScrapeCreators/TikTok response shapes can vary. These are common containers.
    candidates = [
        payload.get("user"),
        payload.get("user_info"),
        payload.get("userInfo"),
        payload.get("profile"),
        (payload.get("data") or {}).get("user") if isinstance(payload.get("data"), dict) else None,
        (payload.get("data") or {}).get("user_info") if isinstance(payload.get("data"), dict) else None,
        payload.get("data") if isinstance(payload.get("data"), dict) else None,
    ]
    for c in candidates:
        if isinstance(c, dict) and any(k in c for k in (
            "unique_id","uniqueId","nickname","aweme_count","follower_count","following_count","total_favorited"
        )):
            return c
    if isinstance(payload, dict) and any(k in payload for k in (
        "unique_id","uniqueId","nickname","aweme_count","follower_count","following_count","total_favorited"
    )):
        return payload
    return {}

def _pick(d, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d.get(k)
    return None

def fetch_profile(username):
    checked = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = {"username": username, "display_name": None, "posts": None,
           "following": None, "followers": None, "likes": None,
           "checked_at": checked, "status": ""}
    key = api_key()
    if not key:
        out["status"] = "SCRAPECREATORS_API_KEY belum dikonfigurasi"
        return out

    params = {"handle": username}
    if CACHE_MAX_AGE:
        params["cache_max_age"] = CACHE_MAX_AGE

    try:
        r = requests.get(
            API_URL,
            headers={"x-api-key": key, "Accept": "application/json"},
            params=params,
            timeout=TIMEOUT,
        )
        try:
            p = r.json()
        except ValueError:
            out["status"] = f"HTTP {r.status_code}: respons bukan JSON"
            return out

        if r.status_code != 200:
            msg = p.get("error") or p.get("message") or p.get("detail") or str(p)
            out["status"] = f"HTTP {r.status_code}: {msg}"
            return out

        if p.get("success") is False:
            out["status"] = str(p.get("error") or p.get("message") or "Request gagal")
            return out

        profile = _find_profile(p)
        if not profile:
            out["status"] = "Profil tidak ditemukan / format respons tidak dikenali"
            return out

        stats = profile.get("stats") if isinstance(profile.get("stats"), dict) else {}
        out.update({
            "username": _pick(profile, "unique_id", "uniqueId", "unique_id_str") or username,
            "display_name": _pick(profile, "nickname", "display_name", "displayName"),
            "posts": _pick(profile, "aweme_count", "videoCount", "video_count") if not stats else _pick(stats, "videoCount", "video_count"),
            "following": _pick(profile, "following_count", "followingCount") if not stats else _pick(stats, "followingCount", "following_count"),
            "followers": _pick(profile, "follower_count", "followerCount") if not stats else _pick(stats, "followerCount", "follower_count"),
            "likes": _pick(profile, "total_favorited", "heartCount", "likes_count", "like_count") if not stats else _pick(stats, "heartCount", "likes_count", "like_count"),
            "status": "OK",
        })
        return out
    except requests.Timeout:
        out["status"] = "Timeout provider API"
    except requests.RequestException as e:
        out["status"] = f"Network error: {e}"
    return out

def save_stat(x):
    c = get_db()
    c.execute("""INSERT INTO stats(username,display_name,posts,following,followers,likes,checked_at,status)
      VALUES(?,?,?,?,?,?,?,?)""", (x["username"],x["display_name"],x["posts"],x["following"],
      x["followers"],x["likes"],x["checked_at"],x["status"]))
    c.commit(); c.close()

def latest():
    c=get_db()
    rows=c.execute("""SELECT s.* FROM stats s JOIN
      (SELECT username,MAX(id) mid FROM stats GROUP BY username) x ON s.id=x.mid
      ORDER BY s.username""").fetchall()
    c.close(); return rows

@app.route("/")
def index():
    c=get_db()
    accounts=c.execute("SELECT * FROM accounts ORDER BY username").fetchall()
    history=c.execute("SELECT * FROM stats ORDER BY id DESC LIMIT 1000").fetchall()
    c.close()
    return render_template("index.html",accounts=accounts,latest=latest(),history=history,
                           api_configured=bool(api_key()))

@app.post("/accounts/add")
def add_accounts():
    values=request.form.get("usernames","").splitlines()
    c=get_db(); now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"); n=0
    for v in values:
        u=norm(v)
        if u: n+=c.execute("INSERT OR IGNORE INTO accounts VALUES(?,?)",(u,now)).rowcount
    c.commit(); c.close(); flash(f"{n} akun baru ditambahkan."); return redirect(url_for("index"))

@app.post("/accounts/upload")
def upload_accounts():
    f=request.files.get("file")
    if not f: flash("Pilih file TXT/CSV."); return redirect(url_for("index"))
    raw=f.read().decode("utf-8-sig",errors="replace")
    if f.filename.lower().endswith(".csv"):
        frame=pd.read_csv(io.StringIO(raw))
        col=next((x for x in frame.columns if x.lower() in ("username","user","account")),frame.columns[0])
        values=frame[col].dropna().astype(str).tolist()
    else: values=raw.splitlines()
    c=get_db(); now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"); n=0
    for v in values:
        u=norm(v)
        if u: n+=c.execute("INSERT OR IGNORE INTO accounts VALUES(?,?)",(u,now)).rowcount
    c.commit(); c.close(); flash(f"{n} akun baru diimport."); return redirect(url_for("index"))

@app.post("/accounts/delete/<username>")
def delete_account(username):
    c=get_db(); c.execute("DELETE FROM accounts WHERE username=?",(username,)); c.commit(); c.close()
    flash(f"@{username} dihapus."); return redirect(url_for("index"))

@app.post("/check-all")
def check_all():
    c=get_db(); users=[r["username"] for r in c.execute("SELECT username FROM accounts ORDER BY username")]; c.close()
    ok=0
    for i,u in enumerate(users):
        x=fetch_profile(u); save_stat(x)
        if x["status"]=="OK": ok+=1
        if i<len(users)-1: time.sleep(REQUEST_DELAY)
    flash(f"Pengecekan selesai: {ok}/{len(users)} berhasil."); return redirect(url_for("index"))

@app.post("/stats/delete/<username>")
def delete_stats(username):
    c=get_db(); c.execute("DELETE FROM stats WHERE username=?",(username,)); c.commit(); c.close()
    flash(f"Statistik @{username} dihapus."); return redirect(url_for("index"))

@app.post("/stats/reset")
def reset_stats():
    c=get_db(); c.execute("DELETE FROM stats"); c.commit(); c.close()
    flash("Semua statistik dan riwayat direset."); return redirect(url_for("index"))

@app.get("/export/<kind>.<fmt>")
def export(kind,fmt):
    c=get_db()
    q=("""SELECT s.username,s.display_name,s.posts,s.following,s.followers,s.likes,s.checked_at,s.status
          FROM stats s JOIN (SELECT username,MAX(id) mid FROM stats GROUP BY username) x ON s.id=x.mid
          ORDER BY s.username""" if kind=="latest" else
       "SELECT username,display_name,posts,following,followers,likes,checked_at,status FROM stats ORDER BY id DESC")
    d=pd.read_sql_query(q,c); c.close()
    b=io.BytesIO()
    if fmt=="csv":
        b.write(d.to_csv(index=False).encode("utf-8-sig")); mime="text/csv"
    else:
        with pd.ExcelWriter(b,engine="openpyxl") as w: d.to_excel(w,index=False,sheet_name="TikTok Stats")
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    b.seek(0)
    return send_file(b,mimetype=mime,as_attachment=True,download_name=f"tiktok_{kind}.{fmt}")

@app.get("/health")
def health():
    return {"ok": True, "provider": "ScrapeCreators", "api_configured": bool(api_key())}

if __name__=="__main__":
    get_db().close()
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
