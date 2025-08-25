import requests
from bs4 import BeautifulSoup
import os
import re
import logging
import time

# إعدادات التسجيل
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# إعدادات فيسبوك وقناة تيليجرام
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FACEBOOK_TOKEN = os.getenv("FACEBOOK_TOKEN")
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
TELEGRAM_URL = "https://t.me/s/alkulife"
LAST_POST_FILE = "lastpost.txt"
MAX_RETRIES = 5  # عدد المحاولات الأقصى في حالة الفشل

def clean_content_text_only(soup_element):
    """يستخرج النص النقي من عنصر BeautifulSoup."""
    return soup_element.get_text(separator="\n", strip=True)

def is_meaningful_text(text):
    """يتحقق مما إذا كان النص يحتوي على عدد كافٍ من الكلمات."""
    words = text.strip().split()
    return len(words) >= 40

def read_last_post_link(filepath):
    """يقرأ آخر رابط منشور تم إرساله من ملف."""
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read().strip()

def save_last_post_link(last_link, filepath=LAST_POST_FILE):
    """يحفظ رابط آخر منشور تم إرساله إلى ملف."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(last_link)

def rephrase_text_with_gemini(text):
    """يعيد صياغة النص باستخدام Gemini API مع إعادة المحاولة."""
    if not GEMINI_API_KEY:
        logging.error("GEMINI_API_KEY غير متاح. لا يمكن إعادة الصياغة.")
        return None

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
    prompt = f"أعد صياغة النص العربي التالي بأسلوب إخباري ومنظم ليناسب النشر على وسائل التواصل الاجتماعي، مع الحفاظ على المعنى الأصلي. اجعل النص مقسمًا إلى فقرات قصيرة وواضحة.\n\nالنص: {text}"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    data = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(api_url, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            candidates = response.json().get('candidates', [])
            if candidates:
                gemini_response_text = candidates[0]['content']['parts'][0]['text']
                logging.info(f"نجحت إعادة الصياغة مع Gemini في المحاولة رقم {attempt + 1}.")
                return gemini_response_text
        except requests.exceptions.RequestException as e:
            logging.warning(f"فشل الاتصال بـ Gemini API في المحاولة {attempt + 1}: {e}")
        except Exception as e:
            logging.warning(f"خطأ في معالجة استجابة Gemini في المحاولة {attempt + 1}: {e}")
        
        time.sleep(5) # انتظار 5 ثوانٍ قبل إعادة المحاولة

    logging.error(f"فشلت إعادة صياغة النص بعد {MAX_RETRIES} محاولات. سيتم تخطي هذا المنشور.")
    return None

def post_to_facebook(token, page_id, message, image_url=None):
    """يرسل منشورًا إلى صفحة فيسبوك مع إعادة المحاولة."""
    for attempt in range(MAX_RETRIES):
        try:
            if image_url:
                url = f"https://graph.facebook.com/v12.0/{page_id}/photos"
                data = {
                    "url": image_url,
                    "published": "true",
                    "access_token": token,
                    "caption": message
                }
                r = requests.post(url, data=data)
            else:
                url = f"https://graph.facebook.com/v12.0/{page_id}/feed"
                data = {
                    "message": message,
                    "access_token": token
                }
                r = requests.post(url, data=data)
            r.raise_for_status()
            logging.info(f"تم النشر على فيسبوك بنجاح في المحاولة رقم {attempt + 1}. 👍")
            return True
        except requests.exceptions.RequestException as e:
            logging.warning(f"فشل النشر على فيسبوك في المحاولة {attempt + 1}: {e}")
            if r.status_code == 400 or r.status_code == 403: # أخطاء قد لا تفيد فيها إعادة المحاولة
                 logging.error(f"خطأ فيسبوك {r.status_code}، لن يتم إعادة المحاولة.")
                 break
        except Exception as e:
            logging.warning(f"خطأ فيسبوك في المحاولة {attempt + 1}: {e}")

        time.sleep(5) # انتظار 5 ثوانٍ قبل إعادة المحاولة

    logging.error(f"فشل النشر على فيسبوك بعد {MAX_RETRIES} محاولات.")
    return False

def fetch_and_post_latest_posts():
    """يجلب المنشورات الجديدة، يعيد صياغتها، وينشرها على فيسبوك."""
    try:
        response = requests.get(TELEGRAM_URL)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
    except requests.exceptions.RequestException as e:
        logging.error(f"فشل في جلب محتوى تيليجرام: {e}")
        return

    last_link = read_last_post_link(LAST_POST_FILE)
    messages = soup.find_all('div', class_='tgme_widget_message_wrap')
    
    filtered_msgs = []
    for msg in messages:
        text_div = msg.find('div', class_='tgme_widget_message_text')
        if not text_div:
            continue
        text_content = text_div.get_text()
        if '👇' in text_content or msg.find('audio') or msg.find('video'):
            continue
        excluded_exts = ['mp3', 'ogg', 'wav', 'mp4', 'mov', 'avi', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'zip', 'rar']
        links = msg.find_all('a')
        if any(any(a.get('href', '').lower().endswith(ext) for ext in excluded_exts) for a in links):
            continue
        filtered_msgs.append(msg)

    filtered_msgs.reverse() # المنشورات الأحدث أولًا
    
    posts_to_process = []
    for msg in filtered_msgs:
        link_tag = msg.find('a', class_='tgme_widget_message_date')
        post_link = "https://t.me" + link_tag['href'] if link_tag and link_tag['href'].startswith('/') else link_tag['href']
        
        if last_link and post_link == last_link:
            break
        
        text_div = msg.find('div', class_='tgme_widget_message_text')
        content_text = clean_content_text_only(text_div)
        if not is_meaningful_text(content_text):
            continue

        photo_div = msg.find('a', class_=re.compile(r'tgme_widget_message_photo_wrap'))
        image_url = None
        if photo_div:
            style = photo_div.get('style','')
            m = re.search(r"background-image:url\('([^']+)'\)", style)
            if m:
                image_url = m.group(1)
        posts_to_process.append({
            'link': post_link,
            'content': content_text,
            'image': image_url
        })
    
    if not posts_to_process:
        logging.info("لا توجد منشورات جديدة للنشر.")
        return

    posts_to_process.reverse() # النشر بترتيب زمني صحيح
    
    for post in posts_to_process:
        # 1. إعادة صياغة النص مع المحاولات
        rephrased_text = rephrase_text_with_gemini(post['content'])
        if rephrased_text is None:
            # إذا فشلت إعادة الصياغة بعد كل المحاولات، نتوقف ولا ننشر
            logging.error("فشلت إعادة صياغة النص، سيتم إيقاف العملية.")
            return # إيقاف البرنامج
        
        # 2. النشر على فيسبوك مع المحاولات
        success = post_to_facebook(FACEBOOK_TOKEN, FACEBOOK_PAGE_ID, rephrased_text, post['image'])
        
        # 3. تحديث الرابط فقط إذا نجحت كلتا العمليتين
        if success:
            save_last_post_link(post['link'])
            logging.info("تم حفظ آخر منشور تم نشره بنجاح.")
        else:
            # إذا فشل النشر على فيسبوك، نتوقف
            logging.error("فشل النشر على فيسبوك، سيتم إيقاف العملية.")
            return # إيقاف البرنامج
        
        time.sleep(10) # انتظار 10 ثوانٍ قبل المنشور التالي

if __name__ == "__main__":
    fetch_and_post_latest_posts()