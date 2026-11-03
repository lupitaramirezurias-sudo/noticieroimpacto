"""Genera una página por nota en /notas/ a partir de las notas de index.html.

Uso: python3 -I tools/generar_notas.py   (desde la raíz del repositorio)

- Lee cada <article class="story" id="n-..."> de index.html.
- Toma la hora de "Lo último" (<ol class="latest">) buscando el mismo título.
- Escribe notas/<slug>.html con título, fecha, hora, imagen, texto, firma y botones de compartir.
- Enlaza el título de cada nota en la portada (y los cuadros del mosaico) a su página.
- Actualiza sitemap.xml y la línea "Última actualización" de la portada.
"""
import html
import json
import os
import re
import unicodedata
from urllib.parse import quote
from datetime import datetime, timedelta, timezone

SITE = "https://noticieroimpactobmradioojinaga.mx"
TZ = timezone(timedelta(hours=-6))  # America/Chihuahua (sin horario de verano)
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def slugify(text):
    t = unicodedata.normalize("NFKD", text.replace("–", " ").replace("—", " ")).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t.replace("–", " ").replace("—", " ")).strip("-").lower()
    return t[:80].rstrip("-")


def fecha_larga(d):
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]} de {d.year}"


def hora_a_iso(fecha, hora_txt):
    m = re.match(r"(\d{1,2}):(\d{2})\s*(am|pm)", hora_txt.strip().lower())
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if ap == "pm" and h != 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return datetime(fecha.year, fecha.month, fecha.day, h, mi, tzinfo=TZ)


def main():
    idx = open("index.html", encoding="utf-8").read()
    meta_fecha = re.search(r'<meta name="noticias-fecha" content="(\d{4}-\d{2}-\d{2})">', idx)
    hoy = datetime.now(TZ)
    fecha = datetime.strptime(meta_fecha.group(1), "%Y-%m-%d").replace(tzinfo=TZ) if meta_fecha else hoy

    horas = {}
    for t, b in re.findall(r"<li><time>([^<]+)</time><b>(.*?)</b></li>", idx):
        horas[html.unescape(b).strip()] = t.strip()

    css = idx[idx.index("<style>") + 7: idx.index("</style>")]
    fonts = re.search(r'<link rel="stylesheet" href="https://fonts\.googleapis\.com[^>]+>', idx).group(0)

    os.makedirs("notas", exist_ok=True)
    notas = []
    pat = re.compile(
        r'<article class="story" id="(n-[^"]+)"><img src="([^"]+)"([^>]*)><div>\s*'
        r'<span class="cat">([^<]+)</span><h3>(?:<a [^>]*>)?(.*?)(?:</a>)?</h3>\s*'
        r'<p>(.*?)</p>', re.S)
    for aid, img, img_attrs, cat, titulo, texto in pat.findall(idx):
        mv = re.search(r'data-video="([^"]+)"', img_attrs)
        video = html.unescape(mv.group(1)) if mv else ""
        titulo_txt = html.unescape(re.sub("<[^>]+>", "", titulo)).strip()
        slug = slugify(titulo_txt)
        hora = horas.get(titulo_txt, "")
        dt = hora_a_iso(fecha, hora) if hora else None
        notas.append(dict(aid=aid, img=img, cat=cat.strip(), titulo=titulo_txt,
                          texto=texto.strip(), slug=slug, hora=hora, dt=dt, video=video))

    for n in notas:
        url = f"{SITE}/notas/{n['slug']}.html"
        resumen = html.unescape(re.sub("<[^>]+>", "", n["texto"]))
        desc = (resumen[:155] + "…") if len(resumen) > 156 else resumen
        iso = n["dt"].isoformat() if n["dt"] else fecha.isoformat()
        publicado = f"{fecha_larga(fecha)}{', ' + n['hora'] if n['hora'] else ''}"
        ld = {
            "@context": "https://schema.org", "@type": "NewsArticle",
            "headline": n["titulo"], "image": [f"{SITE}/{n['img']}"],
            "datePublished": iso, "dateModified": iso,
            "author": {"@type": "Organization", "name": "Noticiero Impacto BM Radio"},
            "publisher": {"@type": "NewsMediaOrganization", "name": "Noticiero Impacto BM Radio",
                          "logo": {"@type": "ImageObject", "url": f"{SITE}/img/logo-bm-radio.png"}},
            "mainEntityOfPage": url, "articleSection": n["cat"], "inLanguage": "es-MX",
        }
        otras = [o for o in notas if o["slug"] != n["slug"]][:4]
        otras_html = "\n".join(
            f'<li><a href="{o["slug"]}.html"><img src="../{o["img"]}" alt="" width="120" height="70">'
            f'<span><span class="cat">{html.escape(o["cat"])}</span><b>{html.escape(o["titulo"])}</b></span></a></li>'
            for o in otras)
        t_esc = html.escape(n["titulo"])
        if n["video"]:
            # Video de Facebook incrustado; los reels son verticales (9:16), lo demás horizontal (16:9).
            vert = "/reel/" in n["video"]
            src = ("https://www.facebook.com/plugins/video.php?href=" + quote(n["video"], safe="")
                   + "&show_text=false&width=" + ("400" if vert else "780"))
            media = (f'<div class="art-video{" v" if vert else ""}"><iframe src="{html.escape(src)}" title="{t_esc}" '
                     f'loading="lazy" scrolling="no" frameborder="0" allowfullscreen '
                     f'allow="autoplay; clipboard-write; encrypted-media; picture-in-picture; web-share"></iframe></div>')
        else:
            media = f'<img class="art-img" src="../{n["img"]}" alt="{t_esc}">'
        page = f"""<!doctype html>
<html lang="es-MX">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{t_esc} | Noticiero Impacto BM Radio</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Noticiero Impacto BM Radio">
<meta property="og:title" content="{t_esc}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:image" content="{SITE}/{n['img']}">
<meta property="og:url" content="{url}">
<meta property="og:locale" content="es_MX">
<meta property="article:published_time" content="{iso}">
<link rel="icon" href="../img/logo-bm-radio.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
{fonts}
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
<style>{css}
.art-wrap{{max-width:780px;margin:0 auto;padding-block:28px}}
.art-wrap h1{{font-family:var(--head);font-weight:900;font-size:clamp(1.7rem,4vw,2.6rem);line-height:1.12;letter-spacing:-.015em;margin:8px 0 10px}}
.art-meta{{color:var(--muted);font-size:.95rem;display:flex;gap:6px 14px;flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:18px}}
.art-meta b{{color:var(--ink)}}
.art-img{{width:100%;height:auto;display:block;margin-bottom:18px}}
.art-video{{position:relative;width:100%;aspect-ratio:16/9;background:#000;margin-bottom:18px}}
.art-video.v{{max-width:400px;aspect-ratio:9/16;margin-inline:auto}}
.art-video iframe{{position:absolute;inset:0;width:100%;height:100%;border:0}}
.art-body{{font-size:1.18rem;line-height:1.7}}
.firma{{margin:22px 0 14px;padding:12px 14px;background:var(--soft);border-left:4px solid var(--red);font-weight:700}}
.back{{display:inline-block;margin-bottom:6px;color:var(--red);font-family:var(--head);font-weight:800;font-size:.85rem;text-transform:uppercase}}
.related{{max-width:780px;margin:0 auto;padding-bottom:30px}}
.related ul{{list-style:none;margin:0;padding:0;display:grid;gap:12px}}
.related a{{display:grid;grid-template-columns:120px minmax(0,1fr);gap:12px;align-items:center}}
.related img{{width:120px;height:70px;object-fit:cover}}
.related b{{display:block;font-family:var(--head);font-weight:800;line-height:1.25}}
</style>
</head>
<body>
<div class="topbar"><div class="wrap"><span>Noticiero Impacto BM Radio · Ojinaga, Chihuahua</span><span class="soc"><a class="fb" href="https://www.facebook.com/noticieroimpacto" target="_blank" rel="noopener" aria-label="Facebook">f</a></span></div></div>
<header class="masthead"><div class="wrap" style="grid-template-columns:1fr">
  <a class="logo" href="../" style="justify-self:center"><img src="../img/logo-bm-radio.png" alt="BM Radio"><span class="name">Noticiero <span>Impacto</span><small>BM Radio Ojinaga</small></span></a>
</div></header>
<nav class="menu" aria-label="Secciones"><div class="wrap"><a href="../">Inicio</a><a href="../#lo-ultimo">Noticias</a><a href="../#hoy">Clima y cruce</a><a href="../#radio">Escuchar en vivo</a><a href="../#contacto">Contacto</a></div></nav>
<main class="wrap">
  <article class="art-wrap">
    <a class="back" href="../">← Portada</a>
    <span class="cat" style="display:block">{html.escape(n['cat'])}</span>
    <h1>{t_esc}</h1>
    <div class="art-meta"><span>Publicado: <b><time datetime="{iso}">{publicado}</time></b></span><span>Por <b>Redacción Noticiero Impacto</b></span></div>
    {media}
    <div class="art-body"><p>{n['texto']}</p></div>
    <p class="firma">Noticiero Impacto BM Radio Ojinaga | noticieroimpactobmradioojinaga.mx</p>
    <div class="share" data-title="{t_esc}" data-url="{url}"></div>
  </article>
  <section class="related" aria-labelledby="rel-h">
    <h2 class="h-sec" id="rel-h">Más <span>noticias</span></h2>
    <ul>
{otras_html}
    </ul>
  </section>
</main>
<footer><div class="wrap"><span><img src="../img/logo-bm-radio.png" alt="">BM Radio · Noticiero Impacto · Ojinaga, Chihuahua</span><span>100.9 · 101.7 · 100.1 FM</span></div></footer>
<script>
document.querySelectorAll('.share').forEach(function(s){{
  var u=s.dataset.url,t=s.dataset.title+' | Noticiero Impacto BM Radio';
  s.innerHTML='<a class="sh-wa" target="_blank" rel="noopener" href="https://wa.me/?text='+encodeURIComponent(t+' '+u)+'">Compartir en WhatsApp</a><a class="sh-fb" target="_blank" rel="noopener" href="https://www.facebook.com/sharer/sharer.php?u='+encodeURIComponent(u)+'">Facebook</a>';
}});
</script>
</body>
</html>
"""
        open(f"notas/{n['slug']}.html", "w", encoding="utf-8").write(page)

    # Enlaces en la portada
    by_aid = {n["aid"]: n for n in notas}
    def link_story(m):
        aid, rest_before, titulo = m.group(1), m.group(2), m.group(3)
        n = by_aid.get(aid)
        if not n:
            return m.group(0)
        return f'<article class="story" id="{aid}">{rest_before}<h3><a href="notas/{n["slug"]}.html">{titulo}</a></h3>'
    idx = re.sub(r'<article class="story" id="(n-[^"]+)">(.*?)<h3>(?:<a [^>]*>)?(.*?)(?:</a>)?</h3>',
                 link_story, idx, flags=re.S)
    for n in notas:
        idx = idx.replace(f'href="#{n["aid"]}"', f'href="notas/{n["slug"]}.html"')
        idx = re.sub(r'(<div class="share" data-title="' + re.escape(html.escape(n["titulo"], quote=True)) + r'")(?: data-url="[^"]*")?',
                     r'\1 data-url="' + f'{SITE}/notas/{n["slug"]}.html"', idx)
        idx = re.sub(r'(<div class="share" data-title="' + re.escape(n["titulo"]) + r'")(?: data-url="[^"]*")?',
                     r'\1 data-url="' + f'{SITE}/notas/{n["slug"]}.html"', idx)

    # Última actualización
    ahora = hoy
    h12 = ahora.strftime("%I:%M").lstrip("0") + (" pm" if ahora.hour >= 12 else " am")
    upd = f'<span id="updated">Última actualización: {ahora.day} de {MESES[ahora.month - 1]}, {h12}</span>'
    if 'id="updated"' in idx:
        idx = re.sub(r'<span id="updated">[^<]*</span>', upd, idx)
    else:
        idx = idx.replace('<span class="soc">', upd + '\n  <span class="soc">', 1)
    open("index.html", "w", encoding="utf-8").write(idx)

    # Sitemap
    d = ahora.strftime("%Y-%m-%d")
    urls = [f"  <url><loc>{SITE}/</loc><lastmod>{d}</lastmod><changefreq>hourly</changefreq><priority>1.0</priority></url>"]
    for f in sorted(os.listdir("notas")):
        if f.endswith(".html"):
            urls.append(f"  <url><loc>{SITE}/notas/{f}</loc><lastmod>{d}</lastmod><priority>0.8</priority></url>")
    open("sitemap.xml", "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls) + "\n</urlset>\n")
    print(f"{len(notas)} notas generadas")


if __name__ == "__main__":
    main()
