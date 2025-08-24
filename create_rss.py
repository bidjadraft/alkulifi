import requests
from bs4 import BeautifulSoup
from xml.etree.ElementTree import Element, SubElement, ElementTree
import os
import re

url = "https://t.me/s/alkulife"
rss_file_path = "rss.xml"
last_post_file = "lastpost.txt"

def clean_content_text_only(soup_element):
    return soup_element.get_text(separator="\n", strip=True)

def is_meaningful_text(text):
    words = text.strip().split()
    return len(words) >= 40

def read_last_post_link(filepath):
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read().strip()

def save_last_post_link(last_link, filepath=last_post_file):
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(last_link)

def fetch_latest_posts(url, count=50, since_link=None):
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    messages = soup.find_all('div', class_='tgme_widget_message_wrap')

    filtered_msgs = []
    for msg in messages:
        text_div = msg.find('div', class_='tgme_widget_message_text')
        if not text_div:
            continue

        text_content = text_div.get_text()
        if '👇' in text_content:
            continue

        if msg.find('audio') or msg.find('video'):
            continue

        excluded_exts = ['mp3','ogg','wav','mp4','mov','avi','pdf','doc','docx','xls','xlsx','ppt','pptx','zip','rar']
        links = msg.find_all('a')
        if any(any(a.get('href','').lower().endswith(ext) for ext in excluded_exts) for a in links):
            continue

        filtered_msgs.append(msg)

    filtered_msgs.reverse()  # الأحدث أولاً

    posts = []
    for msg in filtered_msgs:
        link_tag = msg.find('a', class_='tgme_widget_message_date')
        link_raw = link_tag['href'] if link_tag else ""
        if not link_raw.startswith("https://t.me"):
            link_raw = "https://t.me" + link_raw

        if since_link is not None and link_raw == since_link:
            break

        text_div = msg.find('div', class_='tgme_widget_message_text')

        photo_div = msg.find('a', class_=re.compile(r'tgme_widget_message_photo_wrap'))
        image_url = None
        if photo_div:
            style = photo_div.get('style','')
            m = re.search(r"background-image:url\('([^']+)'\)", style)
            if m:
                image_url = m.group(1)

        content_text = clean_content_text_only(text_div)
        if not is_meaningful_text(content_text):
            continue

        posts.append({
            'link': link_raw,
            'content': content_text,
            'image': image_url
        })

        if len(posts) >= count:
            break

    return posts

def create_rss(posts, filepath):
    rss = Element('rss', version='2.0')
    rss.set('xmlns:content', 'http://purl.org/rss/1.0/modules/content/')
    channel = SubElement(rss, 'channel')

    SubElement(channel, 'title').text = 'قناة أبي جعفر عبدالله الخليفي'
    SubElement(channel, 'link').text = url
    SubElement(channel, 'description').text = f"آخر {len(posts)} منشورات من قناة أبي جعفر عبدالله الخليفي"

    for post in posts:
        item = SubElement(channel, 'item')
        SubElement(item, 'link').text = post['link']

        content_encoded = SubElement(item, '{http://purl.org/rss/1.0/modules/content/}encoded')
        content_encoded.text = post['content']

        if post['image']:
            enclosure = SubElement(item, 'enclosure')
            enclosure.set('url', post['image'])
            enclosure.set('length', '0')
            ext = post['image'].split('.')[-1].lower()
            the_type = 'image/jpeg'
            if ext == 'png':
                the_type = 'image/png'
            elif ext == 'gif':
                the_type = 'image/gif'
            enclosure.set('type', the_type)

    tree = ElementTree(rss)
    tree.write(filepath, encoding='utf-8', xml_declaration=True)

if __name__ == "__main__":
    last_link = read_last_post_link(last_post_file)
    posts = fetch_latest_posts(url, 50, since_link=last_link)
    if posts:
        save_last_post_link(posts[0]['link'])  # حفظ أحدث منشور أولاً
        create_rss(posts, rss_file_path)
        print(f"تم إنشاء ملف RSS وتحديث آخر منشور محفوظ في {last_post_file}")
        exit(0)
    else:
        print("لا توجد منشورات جديدة منذ آخر تحديث.")
        exit(1)
