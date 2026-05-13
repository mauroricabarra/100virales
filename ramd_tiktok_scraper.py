import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from bs4 import BeautifulSoup

# ─── CONFIG ──────────────────────────────────────────────────────────────────
TARGET_URL  = "https://www.ramd.am/blog/trends-tiktok"
OUTPUT_JSON = "ramd_tiktok_trends.json"
OUTPUT_RSS  = "ramd_tiktok_trends.xml"
MAX_ITEMS   = 10   # últimas N semanas
DEBUG       = False
# ─────────────────────────────────────────────────────────────────────────────


def fetch_html(url: str) -> str:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    driver  = webdriver.Chrome(service=service, options=options)
    try:
        driver.get(url)
        WebDriverWait(driver, 20).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(4)
        html = driver.page_source
    finally:
        driver.quit()
    return html


def parse_html(html: str) -> list[dict]:
    """
    La página de ramd.am es una sola página con secciones por fecha.
    Estructura:
      <h2>  → fecha de la semana  (ej. "11 May 2026")
      <h4>  → nombre de cada trend dentro de esa semana
      <p>   → descripción del trend
    Genera un item RSS por semana con todos los trends de esa semana.
    """
    soup = BeautifulSoup(html, "lxml")

    if DEBUG:
        print(html[:5000])

    items = []

    # Buscar todos los h2 que parezcan fechas (contienen un número + mes)
    import re
    date_pattern = re.compile(r'\d{1,2}\s+\w+\s+\d{4}')

    all_headings = soup.find_all(["h2", "h3", "h4", "h5"])

    date_sections = []
    for h in all_headings:
        text = h.get_text(strip=True)
        if date_pattern.search(text):
            date_sections.append(h)

    print(f"✔ Secciones de fecha encontradas: {len(date_sections)}")

    for i, date_tag in enumerate(date_sections[:MAX_ITEMS]):
        date_text = date_tag.get_text(strip=True)

        # Recolectar todo el contenido hasta el próximo date header
        content_parts = []
        trend_titles  = []

        sibling = date_tag.find_next_sibling()
        next_date = date_sections[i + 1] if i + 1 < len(date_sections) else None

        while sibling and sibling != next_date:
            tag_name = sibling.name
            text     = sibling.get_text(strip=True)

            if not text:
                sibling = sibling.find_next_sibling()
                continue

            if tag_name in ("h3", "h4", "h5"):
                trend_titles.append(text)
                content_parts.append(f"\n### {text}\n")
            elif tag_name == "p":
                content_parts.append(text)
            elif tag_name in ("ul", "ol"):
                for li in sibling.find_all("li"):
                    content_parts.append(f"• {li.get_text(strip=True)}")

            sibling = sibling.find_next_sibling()

        description = " | ".join(trend_titles) if trend_titles else "Sin trends esta semana"
        full_content = "\n".join(content_parts)

        items.append({
            "title":       f"TikTok Trends – {date_text}",
            "link":        TARGET_URL,
            "description": description,
            "content":     full_content,
            "pub_date":    date_text,
            "image_src":   "",
        })

    print(f"✔ Items generados: {len(items)}")
    return items


def save_json(items: list[dict], filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=4)
    print(f"✔ JSON guardado: {filepath}")


def save_rss(items: list[dict], filepath: str) -> None:
    rss = ET.Element("rss", version="2.0")
    rss.set("xmlns:content", "http://purl.org/rss/1.0/modules/content/")

    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text       = "Ramdam – TikTok Trends"
    ET.SubElement(channel, "link").text        = TARGET_URL
    ET.SubElement(channel, "description").text = "Trends semanales de TikTok por Ramdam"
    ET.SubElement(channel, "language").text    = "en"
    ET.SubElement(channel, "lastBuildDate").text = datetime.utcnow().strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )

    for item in items:
        entry = ET.SubElement(channel, "item")
        ET.SubElement(entry, "title").text                = item["title"]
        ET.SubElement(entry, "link").text                 = item["link"]
        ET.SubElement(entry, "description").text          = item["description"]
        ET.SubElement(entry, "pubDate").text              = item["pub_date"]
        ET.SubElement(entry, "guid").text                 = f"{item['link']}#{item['pub_date'].replace(' ', '-')}"
        ET.SubElement(entry, "content:encoded").text      = item["content"]

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    with open(filepath, "wb") as f:
        tree.write(f, encoding="utf-8", xml_declaration=True)
    print(f"✔ RSS guardado: {filepath}")


def main():
    print(f"→ Scrapeando {TARGET_URL} ...")
    try:
        html  = fetch_html(TARGET_URL)
        items = parse_html(html)

        if items:
            save_json(items, OUTPUT_JSON)
            save_rss(items, OUTPUT_RSS)
        else:
            print("✘ Sin items. Activá DEBUG=True para inspeccionar.")
    except Exception as e:
        print(f"✘ Error: {e}")
        raise


if __name__ == "__main__":
    main()
