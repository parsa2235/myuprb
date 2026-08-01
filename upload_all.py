import os
import sys
import time
import base64
import requests
from pathlib import Path
from rubpy import Client

# دریافت ورودی‌ها
LINKS_TEXT = os.getenv("LINKS_TEXT", "")
CAPTION = os.getenv("CAPTION", "")
TARGET_GUID = os.getenv("TARGET_GUID") or "me" # اگر خالی بود به پیام‌های ذخیره‌شده می‌فرستد
RUBIKA_SESSION_BASE64 = os.getenv("RUBIKA_SESSION_BASE64")

TEMP_FILE_PATH = Path("current_download.tmp")
SESSION_FILE_PATH = Path("github_session.rp")

def setup_session():
    """بازسازی فایل سشن کامل روبیکا (شامل کلید RSA)"""
    if not RUBIKA_SESSION_BASE64:
        print("❌ خطای امنیتی: کلید RUBIKA_SESSION_BASE64 در Secrets گیتهاب تنظیم نشده است.")
        sys.exit(1)
    
    try:
        session_bytes = base64.b64decode(RUBIKA_SESSION_BASE64.strip())
        with open(SESSION_FILE_PATH, "wb") as f:
            f.write(session_bytes)
        print("✅ فایل سشن روبیکا (شامل کلیدهای RSA) با موفقیت بازسازی شد.")
    except Exception as e:
        print(f"❌ خطای بازسازی سشن: {e}")
        sys.exit(1)

def extract_urls(text: str) -> list[str]:
    if not text:
        return []
    urls = []
    for line in text.strip().splitlines():
        line = line.strip()
        if line.startswith("http://") or line.startswith("https://"):
            urls.append(line)
    return urls

def download_file(url: str, save_path: Path):
    print(f"📥 [1/3] در حال دانلود فایل...")
    start_time = time.time()
    
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get('content-length', 0))
        downloaded = 0
        last_log = time.time()
        
        with open(save_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0 and (time.time() - last_log > 4 or downloaded == total):
                        percent = (downloaded / total) * 100
                        mb_down = downloaded / (1024 * 1024)
                        mb_tot = total / (1024 * 1024)
                        print(f"   📊 پیشرفت دانلود: {percent:.1f}% ({mb_down:.1f} MB / {mb_tot:.1f} MB)")
                        last_log = time.time()
                        
    print(f"✅ دانلود در {time.time() - start_time:.1f} ثانیه کامل شد.")

def upload_to_rubika(client: Client, file_path: Path, caption: str):
    print("📤 [2/3] در حال آپلود تکه‌تکه‌ای به روبیکا...")
    start_time = time.time()
    
    # اصلاح شد: استفاده از send_document به جای send_file
    client.send_document(
        target=TARGET_GUID,
        file=str(file_path),
        caption=caption
    )
    print(f"🚀 آپلود با موفقیت در {time.time() - start_time:.1f} ثانیه انجام شد.")

def cleanup_temp_file():
    if TEMP_FILE_PATH.exists():
        TEMP_FILE_PATH.unlink()
        print("🧹 [3/3] فایل از دیسک پاک شد. آماده برای فایل بعدی.\n")

def main():
    # ۱. بازسازی فایل سشن
    setup_session()
        
    urls = extract_urls(LINKS_TEXT)
    if not urls:
        print("❌ هیچ لینکی یافت نشد.")
        sys.exit(1)

    total_count = len(urls)
    print(f"📋 تعداد کل لینک‌ها: {total_count} عدد\n")

    # ۲. اتصال به روبیکا
    with Client(name="github_session") as client:
        for idx, url in enumerate(urls, 1):
            print("="*50)
            print(f"🔄 لینک [{idx} از {total_count}]: {url}")
            print("="*50)

            try:
                download_file(url, TEMP_FILE_PATH)
                file_caption = CAPTION if CAPTION else f"آپلود شده از لینک:\n{url}"

                max_retries = 3
                for attempt in range(1, max_retries + 1):
                    try:
                        upload_to_rubika(client, TEMP_FILE_PATH, file_caption)
                        break
                    except Exception as upload_err:
                        print(f"⚠️ تلاش {attempt} ناکام بود: {upload_err}")
                        if attempt == max_retries:
                            raise upload_err
                        time.sleep(5)

            except Exception as e:
                print(f"❌ خطا در پردازش: {e}")
                print("⏭️ رفتن به لینک بعدی...")
                
            finally:
                cleanup_temp_file()

    print("🏁 تمام شد!")

if __name__ == "__main__":
    main()
