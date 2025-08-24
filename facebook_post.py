import os
import feedparser
import requests
import re
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FACEBOOK_TOKEN = os.getenv("FACEBOOK_TOKEN")
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")

RSS_URL = "https://bidjadraft.github.io/rss/rss.xml"
LAST_ID_FILE = "last_sent_id.txt"

USER_AGENT_HEADER = {'User-Agent': 'Mozilla/5.0'}


def read_last_sent_id():
    if not os.path.exists(LAST_ID_FILE):
        return None
    try:
        with open(LAST_ID_FILE, "r") as f:
            return f.read().strip()
    except IOError as e:
        logging.error(f"Failed to read last sent ID file: {e}")
        return None


def write_last_sent_id(post_id):
    try:
        with open(LAST_ID_FILE, "w") as f:
            f.write(post_id)
    except IOError as e:
        logging.error(f"Failed to write last sent ID file: {e}")


def clean_html(raw_html):
    return re.sub(r'<[^>]+>', '', raw_html).strip()


def rephrase_text(text):
    import re
    sentences = re.split(r'(?<=[.!؟])\s+', text)
    reformatted = []

    for sentence in sentences:
        sentence = sentence.strip()
        sentence = re.sub(r'([.,!?؟])([^\s])', r'\1 \2', sentence)  # التأكد من وجود فراغ بعد علامات الترقيم
        reformatted.append(sentence)

    paragraphs = []
    for i in range(0, len(reformatted), 3):
        para = " ".join(reformatted[i:i+3])
        paragraphs.append(para)

    return "\n\n".join(paragraphs)


def post_to_facebook(token, page_id, message, image_url=None):
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
            r.raise_for_status()
            logging.info("Posted to Facebook with image successfully. 👍")
            return True
        else:
            url = f"https://graph.facebook.com/v12.0/{page_id}/feed"
            data = {
                "message": message,
                "access_token": token
            }
            r = requests.post(url, data=data)
            r.raise_for_status()
            logging.info("Posted to Facebook without image successfully. 👍")
            return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to post to Facebook: {e}")
        return False
    except Exception as e:
        logging.error(f"Facebook error: {e}")
        return False


def main():
    feed = feedparser.parse(RSS_URL)
    entries = feed.entries

    if not entries:
        logging.info("No posts found.")
        return

    last_id = read_last_sent_id()
    entries = sorted(entries, key=lambda e: e.get('published_parsed') or 0)

    to_send = []
    if not last_id:
        to_send = [entries[-1]]
    else:
        found = False
        for e in entries:
            pid = e.get('id') or e.get('link')
            if not pid:
                continue
            if found:
                to_send.append(e)
            elif pid == last_id:
                found = True

        if not found:
            to_send = entries

    if not to_send:
        logging.info("No new posts to send.")
        return

    for entry in to_send:
        post_id = entry.get('id') or entry.get('link')

        # استخراج النص من ns0_encoded أو content أو summary/description
        desc_text = ''
        if 'ns0_encoded' in entry:
            desc_text = entry['ns0_encoded']
        elif 'content' in entry and entry['content']:
            desc_text = entry['content'][0].get('value', '')
        else:
            desc_text = entry.get('summary', '') or entry.get('description', '')

        desc_text = clean_html(desc_text)
        rephrased_text = rephrase_text(desc_text)

        image_url = None
        image_fields = ['media_content', 'enclosures']
        for field in image_fields:
            if field in entry and entry[field]:
                image_url = entry[field][0].get('url')
                if image_url:
                    break

        logging.info(f"\n--- New Post ---")
        logging.info(f"ID: {post_id}")
        logging.info(f"Post Text:\n{rephrased_text}")
        if image_url:
            logging.info(f"Image: {image_url}")

        success = post_to_facebook(FACEBOOK_TOKEN, FACEBOOK_PAGE_ID, rephrased_text, image_url)
        if not success:
            logging.error("Failed to post to Facebook.")

        write_last_sent_id(post_id)
        logging.info("----------------\n")
        time.sleep(5)


if __name__ == "__main__":
    main()

