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
    """يعيد صياغة النص باستخدام Gemini API."""
    if not GEMINI_API_KEY:
        logging.error("GEMINI_API_KEY غير متاح. سيتم إرسال النص الأصلي.")
        return text

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

    try:
        response = requests.post(api_url, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        candidates = response.json().get('candidates', [])
        if candidates:
            # استخراج النص المعاد صياغته من الاستجابة
            gemini_response_text = candidates[0]['content']['parts'][0]['text']
            return gemini_response_text
    except requests.exceptions.RequestException as e:
        logging.error(f"فشل الاتصال بـ Gemini API: {e}")
    except Exception as e:
        logging.error(f"خطأ في معالجة استجابة Gemini: {e}")
    
    # في حالة الفشل، نرجع النص الأصلي
    return text

def post_to_facebook(token, page_id, message, image_url=None):
    """يرسل منشورًا إلى صفحة فيسبوك، مع أو بدون صورة."""
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
        logging.info("تم النشر على فيسبوك بنجاح. 👍")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"فشل النشر على فيسبوك: {e}")
        return False
    except Exception as e:
        logging.error(f"خطأ فيسبوك: {e}")
        return False

def fetch_and_post_latest_posts():
    """يجلب المنشورات الجديدة من تيليجرام ويعيد صياغتها وينشرها على فيسبوك."""
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

    # المنشورات الأحدث أولًا
    filtered_msgs.reverse()
    
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

    # النشر بترتيب زمني صحيح (من الأقدم إلى الأحدث)
    posts_to_process.reverse() 
    
    for post in posts_to_process:
        # إعادة صياغة النص باستخدام Gemini
        rephrased_text = rephrase_text_with_gemini(post['content'])
        
        logging.info(f"\n--- منشور جديد ---")
        logging.info(f"الرابط: {post['link']}")
        logging.info(f"النص الأصلي:\n{post['content']}")
        logging.info(f"النص المعاد صياغته:\n{rephrased_text}")
        if post['image']:
            logging.info(f"الصورة: {post['image']}")
        
        # إرسال المنشور إلى فيسبوك
        success = post_to_facebook(FACEBOOK_TOKEN, FACEBOOK_PAGE_ID, rephrased_text, post['image'])
        if success:
            save_last_post_link(post['link'])
            logging.info("تم حفظ آخر منشور تم نشره بنجاح.")
        else:
            logging.error("فشل النشر، لم يتم تحديث ملف آخر منشور.")
        
        time.sleep(10) # انتظار 10 ثوانٍ قبل المنشور التالي لتجنب حظر API

if __name__ == "__main__":
    fetch_and_post_latest_posts()