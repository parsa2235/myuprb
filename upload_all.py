import os
import sys
import time
import base64
import re
import requests
from pathlib import Path
from urllib.parse import urlparse, unquote
from rubpy import Client

# دریافت ورودی‌ها
LINKS_TEXT = os.getenv("LINKS_TEXT", "")
CAPTION = os.getenv("CAPTION", "")
TARGET_GUID_ENV = os.getenv("TARGET_GUID")
RUBIKA_SESSION_BASE64 = os.getenv("RUBIKA_SESSION_BASE64")

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

def get_filename_from_url(url: str, response: requests.Response) -> str:
    """استخراج نام و پسوند اصلی فایل از لینک یا هدر"""
    cd = response.headers.get("content-disposition", "")
    match = re.findall(r'filename="(.+?)"', cd)
    if match:
        filename = match[0]
    else:
        parsed_path = urlparse(url).path
        filename = Path(unquote(parsed_path)).name
    
    # ایمن‌سازی نام فایل
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '_', filename).strip()
    if not filename or '.' not in filename:
        filename = f"file_{int(time.time())}.bin"
    return filename

def download_file(url: str) -> Path:
    print(f"📥 [1/3] در حال دانلود فایل از لینک...")
    start_time = time.time()
    
    with requests.get(url, stream=True, timeout=60, allow_redirects=True) as r:
        r.raise_for_status()
        
        filename = get_filename_from_url(url, r)
        save_path = Path(filename)
        
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
                        
    print(f"✅ دانلود فایل [{filename}] در {time.time() - start_time:.1f} ثانیه کامل شد.")
    return save_path

def resolve_target_guid(client: Client) -> str:
    """استخراج GUID واقعی اکانت برای جلوگیری از خطای سرور"""
    target = (TARGET_GUID_ENV or "").strip()
    if not target or target.lower() == "me":
        me_info = client.get_me()
        user_data = me_info.get("user", {}) if isinstance(me_info, dict) else {}
        target = user_data.get("user_guid") or me_info.get("user_guid") or "me"
        print(f"👤 مقصد ارسال: پیام‌های ذخیره‌شده (GUID: {target})")
    else:
        print(f"🎯 مقصد ارسال: {target}")
    return target

def upload_to_rubika(client: Client, file_path: Path, caption: str, target_guid: str):
    print(f"📤 [2/3] در حال آپلود فایل [{file_path.name}] به روبیکا...")
    start_time = time.time()
    
    client.send_document(
        target_guid,
        file_path,
        caption=caption
    )
    print(f"🚀 آپلود با موفقیت در {time.time() - start_time:.1f} ثانیه انجام شد.")

def main():
    setup_session()
        
    urls = extract_urls(LINKS_TEXT)
    if not urls:
        print("❌ هیچ لینکی یافت نشد.")
        sys.exit(1)

    total_count = len(urls)
    print(f"📋 تعداد کل لینک‌ها: {total_count} عدد\n")

    with Client(name="github_session") as client:
        target_guid = resolve_target_guid(client)

        for idx, url in enumerate(urls, 1):
            print("="*50)
            print(f"🔄 لینک [{idx} از {total_count}]: {url}")
            print("="*50)

            file_path = None
            try:
                # ۱. دانلود فایل با نام و پسوند واقعی
                file_path = download_file(url)
                file_caption = CAPTION if CAPTION else f"آپلود شده از لینک:\n{url}"

                # ۲. آپلود
                max_retries = 3
                for attempt in range(1, max_retries + 1):
                    try:
                        upload_to_rubika(client, file_path, file_caption, target_guid)
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
                # ۳. پاکسازی فایل
                if file_path and file_path.exists():
                    file_path.unlink()
                    print(f"🧹 [3/3] فایل [{file_path.name}] از دیسک پاک شد.\n")

    print("🏁 تمام شد!")

if __name__ == "__main__":
    main()
