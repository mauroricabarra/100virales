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
TARGET_URL   = "https://la100.cienradios.com/virales/"
OUTPUT_JSON  = "la100_virales.json"
OUTPUT_RSS   = "la100_virales.xml"
DEBUG        = False   # True → imprime el HTML crudo en consola (útil para ajustar selectores)
# ─────────────────────────────────────────────────────────────────────────────


def fetch_html(url: str) -> str:
    """Abre el URL en Chrome headless y devuelve el page_source."""
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
        time.sleep(4)   # espera JS / lazy-load
        html = driver.page_source
    finally:
        driver.quit()

    return html


def parse_html(base_url: str, html: str) -> list[dict]:
    """
    Extrae artículos del HTML. Usa tres estrategias en cascada:
      1. <article> tags  (WordPress estándar)
      2. div con clases que contengan 'post' o 'article'
      3. Fallback genérico con cualquier <a> que tenga imagen hermana
    """
    soup = BeautifulSoup(html, "lxml")

    if DEBUG:
        print("─── HTML CRUDO (primeros 5000 chars) ───")
        print(html[:5000])

    # ── Estrategia 1: <article> tags ─────────────────────────────────────────
    containers = soup.find_all("article")

    # ── Estrategia 2: divs con clases tipo 'post' ────────────────────────────
    if not containers:
        containers = soup.find_all(
            "div",
            class_=lambda c: c and any(
                k in " ".join(c).lower() for k in ("post", "article", "card", "nota", "viral", "item-post")
            )
        )
        # filtra los que sean demasiado grandes (wrappers) — quedarse con hojas
        containers = [c for c in containers if c.find("a") and c.find("img")]

    if not containers:
        print("⚠ No se encontraron contenedores. Activá DEBUG=True para inspeccionar el HTML.")
        return []

    print(f"✔ Contenedores encontrados: {len(containers)}")

    items = []
    for post in containers:

        # ── Título + link ────────────────────────────────────────────────────
        title_tag = (
            post.find("h1", class_=lambda c: c and "title" in " ".join(c).lower()) or
            post.find("h2", class_=lambda c: c and "title" in " ".join(c).lower()) or
            post.find("h3", class_=lambda c: c and "title" in " ".join(c).lower()) or
            post.find(["h1", "h2", "h3"])   # cualquier heading como último recurso
        )
        if not title_tag:
            continue

        # el link puede estar en el heading o ser su ancestro/hermano
        link_tag = title_tag.find("a") or post.find("a", href=True)
        if not link_tag:
            continue

        title = title_tag.get_text(strip=True)
        link  = urljoin(base_url, link_tag["href"])

        # ── Imagen ───────────────────────────────────────────────────────────
        img_tag = post.find("img")
        image_src = ""
        if img_tag:
            # algunos temas usan data-src (lazy load)
            image_src = img_tag.get("data-src") or img_tag.get("src", "")
            if image_src:
                image_src = urljoin(base_url, image_src)

        # ── Descripción ──────────────────────────────────────────────────────
        desc_tag = post.find("p")
        description = desc_tag.get_text(strip=True) if desc_tag else ""

        # ── Fecha ────────────────────────────────────────────────────────────
        pub_date = ""
        time_tag = post.find("time")
        if time_tag:
            pub_date = time_tag.get("datetime") or time_tag.get_text(strip=True)
        else:
            date_tag = post.find(
                class_=lambda c: c and any(
                    k in " ".join(c).lower() for k in ("date", "fecha", "meta", "time")
                )
            )
            if date_tag:
                pub_date = date_tag.get_text(strip=True)

        items.append({
            "title":       title,
            "link":        link,
            "description": description,
            "image_src":   image_src,
            "pub_date":    pub_date,
        })

    print(f"✔ Artículos parseados: {len(items)}")
    return items


# ── Outputs ───────────────────────────────────────────────────────────────────

def save_json(items: list[dict], filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=4)
    print(f"✔ JSON guardado: {filepath}")


def save_rss(items: list[dict], filepath: str, feed_url: str) -> None:
    """Genera un feed RSS 2.0 válido a partir de los items."""
    rss  = ET.Element("rss", version="2.0")
    rss.set("xmlns:media", "http://search.yahoo.com/mrss/")

    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text       = "La 100 – Virales"
    ET.SubElement(channel, "link").text        = feed_url
    ET.SubElement(channel, "description").text = "Noticias virales de La 100 – cienradios.com"
    ET.SubElement(channel, "language").text    = "es-ar"
    ET.SubElement(channel, "lastBuildDate").text = datetime.utcnow().strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )

    for item in items:
        entry = ET.SubElement(channel, "item")
        ET.SubElement(entry, "title").text       = item["title"]
        ET.SubElement(entry, "link").text        = item["link"]
        ET.SubElement(entry, "description").text = item["description"]
        ET.SubElement(entry, "pubDate").text      = item["pub_date"]
        ET.SubElement(entry, "guid").text        = item["link"]

        if item.get("image_src"):
            media = ET.SubElement(entry, "media:content")
            media.set("url", item["image_src"])
            media.set("medium", "image")

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")   # Python ≥ 3.9
    with open(filepath, "wb") as f:
        tree.write(f, encoding="utf-8", xml_declaration=True)
    print(f"✔ RSS guardado: {filepath}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"→ Scrapeando {TARGET_URL} ...")
    try:
        html  = fetch_html(TARGET_URL)
        items = parse_html(TARGET_URL, html)

        if items:
            save_json(items, OUTPUT_JSON)
            save_rss(items, OUTPUT_RSS, TARGET_URL)
        else:
            print("✘ Sin artículos. Revisá los selectores o activá DEBUG=True.")

    except Exception as e:
        print(f"✘ Error: {e}")
        raise


if __name__ == "__main__":
    main()
