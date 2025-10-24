# main.py
import os
import time
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# === Ayarlar (.env ile sakla) ===
USERNAME = os.getenv("USERNAME")            # örn: 30472669726
PASSWORD = os.getenv("PASSWORD")            # örn: Stfa.1023
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

LOGIN_URL = "https://online.spor.istanbul/uyegiris"
REZERVASYON_URL = "https://online.spor.istanbul/uyeseanssecim"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36"
}

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": message}
        requests.post(url, data=data, timeout=10)
        print("📩 Telegram mesajı gönderildi:", message)
    except Exception as e:
        print("⚠️ Telegram gönderilemedi:", e)

def extract_hidden_inputs(soup):
    """Sayfadaki tüm hidden input'ları dict olarak döndürür."""
    data = {}
    for inp in soup.find_all("input", {"type": "hidden"}):
        name = inp.get("name")
        value = inp.get("value", "")
        if name:
            data[name] = value
    return data

def login(session: requests.Session):
    """Login denemesi. True dönerse başarılı."""
    print("🔐 Giriş sayfası alınıyor...")
    r = session.get(LOGIN_URL, headers=HEADERS, timeout=20)
    if r.status_code != 200:
        print("⚠️ Giriş sayfası alınamadı:", r.status_code)
        return False

    soup = BeautifulSoup(r.text, "html.parser")

    # Form içindeki hidden alanları al
    payload = extract_hidden_inputs(soup)

    # Tahmini alan isimleri: senin verdiğin örneğe göre.
    # Eğer formdaki input name farklıysa burayı değiştir.
    # Burada name attribute'larını kontrol edip uygun olanı seçiyoruz:
    # Önce doğrudan yaygın isimleri dene:
    candidate_user_keys = ["txtTCPasaport", "txtTC", "username", "ctl00$pageContent$txtTCPasaport"]
    candidate_pass_keys = ["txtSifre", "password", "ctl00$pageContent$txtSifre"]

    # Alan isimlerini formda varsa tespit et
    form_inputs = {inp.get("name"): inp for inp in soup.find_all("input")}
    user_key = None
    pass_key = None

    for k in candidate_user_keys:
        if k in form_inputs:
            user_key = k
            break

    for k in candidate_pass_keys:
        if k in form_inputs:
            pass_key = k
            break

    # Eğer bulamadıysak; bazen id/name farklıdır. 
    # fallback: aranan input'larda placeholder veya id eşleşmesine bak
    if not user_key:
        for name, inp in form_inputs.items():
            if inp.get("id", "").lower().find("tc") != -1 or inp.get("name", "").lower().find("tc") != -1:
                user_key = name
                break

    if not pass_key:
        for name, inp in form_inputs.items():
            if "sifre" in name.lower() or "password" in name.lower() or "pass" in name.lower():
                pass_key = name
                break

    # Eğer hala yoksa deneyeceğimiz varsayılan isimleri kullan
    if not user_key:
        user_key = "txtTCPasaport"
    if not pass_key:
        pass_key = "txtSifre"

    # payload'a kullanıcı bilgilerini ekle
    payload[user_key] = USERNAME
    payload[pass_key] = PASSWORD

    # Bir de formdaki submit butonunun name/value'su varsa eklemeye çalış
    # (ASP.NET sitelerinde genelde __EVENTTARGET vb. kullanılır)
    # Eğer sayfada lbtn veya btn gibi submit varsa onu ekle
    if "ctl00$pageContent$lbtnGiris" in form_inputs:
        payload["ctl00$pageContent$lbtnGiris"] = "Giriş"

    # POST isteği gönder (aynı URL veya form action URL'sine)
    form = soup.find("form")
    post_url = LOGIN_URL
    if form and form.get("action"):
        # action genelde relative olabilir, basitçe join et
        action = form.get("action")
        if action.startswith("http"):
            post_url = action
        else:
            post_url = requests.compat.urljoin(LOGIN_URL, action)

    print("🔐 Giriş verisi hazırlanıyor, POST =>", post_url)
    r2 = session.post(post_url, data=payload, headers=HEADERS, timeout=20, allow_redirects=True)
    print("🔁 Giriş POST sonrası status:", r2.status_code)

    # Giriş kontrolü: başarılıysa oturum sayfasında 'Çıkış' veya kullanıcı adın görünür olabilir
    text_after = r2.text.lower()
    if "çıkış" in text_after or "oturum" in text_after or USERNAME in text_after:
        print("✅ Giriş başarılı (HTML kontrolü ile tespit).")
        return True

    # Ayrıca rezervasyon sayfasını kontrol et
    rr = session.get(REZERVASYON_URL, headers=HEADERS, timeout=20)
    if rr.status_code == 200 and "Kalan Kontenjan" in rr.text:
        print("✅ Rezervasyon sayfasına erişildi; giriş başarılı.")
        return True

    print("❌ Giriş başarısız veya site ekstra koruma kullanıyor.")
    return False

def check_kontenjan_with_session(session: requests.Session):
    r = session.get(REZERVASYON_URL, headers=HEADERS, timeout=20)
    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")

    seanslar = soup.find_all("div", class_="well")
    bos_seanslar = []
    for seans in seanslar:
        try:
            kort = seans.find("label").get_text(strip=True)
            saat = seans.find("span", id=lambda x: x and "lblSeansSaat" in x).get_text(strip=True)
            kalan_text = seans.find("span", title="Kalan Kontenjan").get_text(strip=True)
            kalan = int(kalan_text)
            if kalan > 0:
                bos_seanslar.append(f"{kort} | {saat} | Kalan: {kalan}")
        except Exception:
            continue

    if bos_seanslar:
        mesaj = "🎾 Boş seans(lar) bulundu:\n\n" + "\n".join(bos_seanslar)
        send_telegram(mesaj)
        print("✅ Bildirim gönderildi.")
    else:
        print("⏳ Şu anda boş seans yok.")

def main_loop():
    session = requests.Session()
    session.headers.update(HEADERS)

    if not login(session):
        send_telegram("⚠️ Bot: Giriş başarısız oldu. Manuel kontrol gerekebilir.")
        # Eğer login başarısızsa yine de denemek istersen rezervasyon sayfasını bir kez daha çek:
        # check_kontenjan_with_session(session)
        return

    send_telegram("✅ Rezervasyon botu başlatıldı (logged requests sürümü).")
    while True:
        try:
            check_kontenjan_with_session(session)
        except Exception as e:
            print("⚠️ Hata:", e)
        time.sleep(60)

if __name__ == "__main__":
    main_loop()
