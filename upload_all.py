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
TARGET_GUID_ENV = os.getenv("TARGET_GUID", "")
RUBIKA_SESSION_BASE64 = os.getenv("RUBIKA_SESSION_BASE64")

SESSION_FILE_PATH = Path("github_session.rp")
TEMP_FILE_PATH = Path("current_download.tmp")

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

def get_real_target_guid(client: Client) -> str:
    """دریافت GUID واقعی کاربر یا کانال (روبیکا رشته "me" را در سرور قبول نمی‌کند)"""
    target = TARGET_GUID_ENV.strip() if TARGET_GUID_ENV and TARGET_GUID_ENV.strip() else ""
    
    if not target or target.lower() == "me":
        print("🔍 در حال استخراج GUID واقعی حساب کاربری شما...")
        try:
            me_data = client.get_me()
            if isinstance(me_data, dict):
                user_info = me_data.get("user")
                if isinstance(user_info, dict) and user_info.get("user_guid"):
                    target = user_info["user_guid"]
                elif me_data.get("user_guid"):
                    target = me_data["user_guid"]
        except Exception as err:
            print(f"⚠️ خطای دریافت get_me: {err}")
            
    if not target or target.lower() == "me":
        target = "me"
        print("⚠️ GUID واقعی یافت نشد، استفاده از me")
    else:
        print(f"🎯 شناسه نهایی مقصد (GUID): {target}")

    return target

def upload_to_rubika(client: Client, file_path: Path, caption: str, target: str):
    print(f"📤 [2/3] در حال آپلود فایل [{file_path.name}] به روبیکا (مقصد: {target})...")
    start_time = time.time()
    
    try:
        client.send_document(
            target,
            str(file_path),
            caption=caption
        )
    except Exception as e:
        print(f"⚠️ روش send_document خطای {e} داد، در حال تلاش با روش send_message (file_inline)...")
        client.send_message(
            target,
            text=caption,
            file_inline=str(file_path)
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
        # استخراج GUID واقعی اکانت
        real_target = get_real_target_guid(client)

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
                        upload_to_rubika(client, file_path, file_caption, real_target)
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
