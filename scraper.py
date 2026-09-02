#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 LICITACIÓNS ABERTAS · PROVINCIA DE PONTEVEDRA  ·  fonte: PLACSP
 Plataforma de Contratación do Sector Público (estatal)
================================================================================

POR QUE PLACSP
--------------
O Concello de Vigo, a Deputación de Pontevedra e moitos entes publican
DIRECTAMENTE en PLACSP (a plataforma estatal), non no portal galego. Por iso
non saían coa versión anterior. PLACSP publica datos abertos oficiais (feeds
Atom en formato CODICE) e dá acceso a TODO por dúas vías:

  · sindicacion_643  → perfís aloxados en PLACSP  (Concello de Vigo, Deputación…)
  · sindicacion_1044 → plataformas agregadas das CCAA  (portal galego: concellos
                        pequenos, Xunta, SERGAS…)

Xuntando as dúas fontes témolo todo, e cada licitación trae:
  · o seu ESTADO  ("EN PLAZO" = aberta, código PUB)
  · o LUGAR DE EXECUCIÓN en código NUTS  (ES114 = provincia de Pontevedra)
  · a data límite de presentación de ofertas.

QUE FAI
-------
1. Descarga os feeds oficiais (do ano en curso; ou dos últimos meses con --meses).
2. Queda só coas licitacións ABERTAS que se executan en Pontevedra (NUTS ES114
   ou, se falta o NUTS, cuxo órgano/localidade/obxecto é de Pontevedra).
3. Descarta as fóra de prazo e as demasiado antigas.
4. Xera dashboard.html (por día + últimos 5 días + buscador), CSV e JSON.

INSTALACIÓN:   pip install requests
USO:           python licitacions_pontevedra_placsp.py --abrir
               python licitacions_pontevedra_placsp.py --meses 4 --abrir   (máis lixeiro)
               python licitacions_pontevedra_placsp.py --debug             (diagnóstico)

NOTA: os feeds anuais son grandes (poden ser varios centos de MB). Se queres
descargas máis lixeiras usa --meses N (colle os N últimos meses en instantáneas).
O certificado SSL do portal ás veces falla; o script usa a mesma tolerancia que
'curl -k' (verify=False) só para este dominio oficial.
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import time
import unicodedata
import webbrowser
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    sys.exit("Falta 'requests'. Instálao con:  pip install requests")


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

FEEDS = {
    "643":  {  # Perfís aloxados en PLACSP (Vigo, Deputación, moitos concellos…)
        "base": "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/",
        "patron": "licitacionesPerfilesContratanteCompleto3_{periodo}.zip",
    },
    "1044": {  # Plataformas agregadas das CCAA (portal galego)
        "base": "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1044/",
        "patron": "PlataformasAgregadasSinMenores_{periodo}.zip",
    },
}

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "cbc": "urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2",
    "cbc-place-ext": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2",
    "cac-place-ext": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2",
}

ESTADOS = {"PRE": "Anuncio previo", "PUB": "En prazo", "EV": "En avaliación",
           "ADJ": "Adxudicada", "RES": "Resolta", "ANUL": "Anulada", "DES": "Deserta"}

# En vez de esixir un código concreto de "aberta", excluímos os que están
# claramente PECHADOS. Así, se PLACSP usa outro código para unha licitación en
# prazo, non a perdemos (o filtro real de "aberta" faino a data límite).
# Estados claramente PECHADOS (descártanse). PRE (anuncio previo) trátase á
# parte, na súa propia pestana.
ESTADOS_PECHADOS_CODE = {"EV", "ADJ", "RES", "ANUL", "DES"}
ESTADO_ANUNCIO = "PRE"

NUTS_PONTEVEDRA = "ES114"

# Días que unha licitación permanece na pestana "Novidades" desde que se detecta
DIAS_NOVIDADE = 3
# Antigüidade máxima dun anuncio previo para seguir amosándose
DIAS_ANUNCIO_MAX = 180

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "application/xml,text/xml,*/*;q=0.8",
    "Accept-Language": "gl-ES,es;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}

# Concellos de Pontevedra (para etiquetar ámbito e como rede de seguridade se
# falta o NUTS). Nome oficial galego.
CONCELLOS_PONTEVEDRA = [
    "Agolada", "Arbo", "Baiona", "Barro", "Bueu", "Caldas de Reis", "Cambados",
    "Campo Lameiro", "A Cañiza", "Cangas", "Catoira", "Cerdedo-Cotobade",
    "O Covelo", "Crecente", "Cuntis", "Dozón", "A Estrada", "Forcarei",
    "Fornelos de Montes", "Gondomar", "O Grove", "A Guarda", "A Illa de Arousa",
    "Lalín", "A Lama", "Marín", "Meaño", "Meis", "Moaña", "Mondariz",
    "Mondariz-Balneario", "Moraña", "Mos", "As Neves", "Nigrán", "Oia",
    "Pazos de Borbén", "Poio", "Ponte Caldelas", "Ponteareas", "Pontecesures",
    "Pontevedra", "O Porriño", "Portas", "Redondela", "Ribadumia", "Rodeiro",
    "O Rosal", "Salceda de Caselas", "Salvaterra de Miño", "Sanxenxo",
    "Silleda", "Soutomaior", "Tomiño", "Tui", "Valga", "Vigo", "Vila de Cruces",
    "Vilaboa", "Vilagarcía de Arousa", "Vilanova de Arousa",
]
XUNTA_PATRONS = [
    "xunta de galicia", "conselleria", "consellería", "sergas", "servizo galego",
    "servicio gallego", "axencia galega", "agencia gallega", "instituto galego",
    "augas de galicia", "portos de galicia", "galaria", "sogama", "seaga",
    "amtega", "igvs", "universidade de vigo", "area sanitaria",
]


# ─────────────────────────────────────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────────────────────────────────────

def log(m): print(m, flush=True)

def sen_acentos(t):
    if not t: return ""
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower().strip()

_MUN_NORM = [sen_acentos(re.sub(r"^(O |A |As |Os )", "", c)) for c in CONCELLOS_PONTEVEDRA]

def txt(el, path):
    if el is None: return None
    try:
        f = el.find(path, NS)
        if f is not None and f.text: return f.text.strip()
    except Exception:
        pass
    return None

def parse_data(s):
    if not s: return None
    s = s.strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)          # ISO (CODICE)
    if m:
        try: return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError: return None
    m = re.match(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", s)
    if m:
        d, mth, y = m.groups(); y = ("20"+y) if len(y) == 2 else y
        try: return date(int(y), int(mth), int(d))
        except ValueError: return None
    return None

def iso(d): return d.isoformat() if isinstance(d, date) else None

def formato_importe(s):
    """'231264.00' -> '231.264,00 €'  (punto para miles, coma para decimais)."""
    if s is None or str(s).strip() == "":
        return ""
    try:
        val = float(str(s).strip().replace(",", "."))
    except ValueError:
        return str(s)
    enteiro, dec = f"{val:,.2f}".split(".")     # ex.: '231,264.00' -> '231,264','00'
    enteiro = enteiro.replace(",", ".")          # miles con punto
    return f"{enteiro},{dec} €"


def clasificar_ambito(organo, ciudad):
    """Etiqueta informativa: 'local' (Pontevedra), 'xunta' ou 'outros'."""
    ln = sen_acentos(organo or "") + " " + sen_acentos(ciudad or "")
    for mun in _MUN_NORM:
        if len(mun) >= 4 and re.search(rf"\b{re.escape(mun)}\b", ln):
            # concello / ente local de Pontevedra
            if any(w in ln for w in ("concello", "ayuntamiento", "deputacion",
                                     "diputacion", "mancomunidade", "consorcio",
                                     "area metropolitana")):
                return "local"
    if any(p in ln for p in XUNTA_PATRONS):
        return "xunta"
    for mun in _MUN_NORM:
        if len(mun) >= 4 and re.search(rf"\b{re.escape(mun)}\b", ln):
            return "local"
    return "outros"


def parece_pontevedra(organo, ciudad, objeto):
    """Rede de seguridade cando o NUTS falta ou é ambiguo.
    No órgano/localidade admítese calquera concello (mesmo curtos como 'Vigo',
    'Mos', 'Tui'); no obxecto (texto libre) só nomes longos, para evitar falsos."""
    oc = " ".join(sen_acentos(x) for x in (organo, ciudad) if x)
    if "pontevedra" in oc:
        return True
    for mun in _MUN_NORM:
        if mun and re.search(rf"\b{re.escape(mun)}\b", oc):
            return True
    ob = sen_acentos(objeto or "")
    if "pontevedra" in ob:
        return True
    for mun in _MUN_NORM:
        if len(mun) >= 6 and re.search(rf"\b{re.escape(mun)}\b", ob):
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# DESCARGA
# ─────────────────────────────────────────────────────────────────────────────

def periodos(args, hoxe):
    if args.meses and args.meses > 0:
        outs, y, m = [], hoxe.year, hoxe.month
        for _ in range(args.meses):
            outs.append(f"{y}{m:02d}")
            m -= 1
            if m == 0: m = 12; y -= 1
        return outs
    # anual (acumulado, actualízase a diario). En xaneiro engade o ano anterior.
    outs = [str(hoxe.year)]
    if hoxe.month == 1:
        outs.append(str(hoxe.year - 1))
    return outs

def descargar(session, url):
    try:
        r = session.get(url, timeout=600, stream=True, verify=False)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        buf = io.BytesIO()
        total = 0
        for chunk in r.iter_content(chunk_size=1 << 16):
            if chunk:
                buf.write(chunk); total += len(chunk)
                sys.stdout.write(f"\r    baixando… {total/1e6:.1f} MB")
                sys.stdout.flush()
        sys.stdout.write("\r")
        data = buf.getvalue()
        # Validar que é REALMENTE un zip (firma "PK"). Se PLACSP devolve unha
        # páxina de erro HTML no canto do zip, isto detéctao e sáltase.
        if len(data) < 4 or data[:2] != b"PK":
            cabecera = data[:60].decode("latin-1", "replace").replace("\n", " ")
            return None, f"resposta non-zip ({len(data)} bytes; empeza por: {cabecera!r})"
        return data, 200
    except requests.RequestException as e:
        return None, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# PARSEO CODICE
# ─────────────────────────────────────────────────────────────────────────────

def parsear_entry(entry):
    status = entry.find("cac-place-ext:ContractFolderStatus", NS)
    if status is None:
        return None
    estado_code = txt(status, "cbc-place-ext:ContractFolderStatusCode")
    expediente = txt(status, "cbc:ContractFolderID")

    lp = status.find("cac-place-ext:LocatedContractingParty", NS)
    party = lp.find("cac:Party", NS) if lp is not None else None
    organo = txt(party, "cac:PartyName/cbc:Name")
    ciudad = txt(party, "cac:PostalAddress/cbc:CityName")

    project = status.find("cac:ProcurementProject", NS)
    objeto = txt(project, "cbc:Name")
    nuts = txt(project, ".//cac:RealizedLocation/cbc:CountrySubentityCode")
    ubic = txt(project, ".//cac:RealizedLocation/cbc:CountrySubentity")

    budget = project.find("cac:BudgetAmount", NS) if project is not None else None
    importe = (txt(budget, "cbc:EstimatedOverallContractAmount")
               or txt(budget, "cbc:TotalAmount"))

    process = status.find("cac:TenderingProcess", NS)
    fecha_limite = txt(process, ".//cac:TenderSubmissionDeadlinePeriod/cbc:EndDate")
    hora_limite = txt(process, ".//cac:TenderSubmissionDeadlinePeriod/cbc:EndTime")

    updated = txt(entry, "atom:updated")
    vni = status.find("cac-place-ext:ValidNoticeInfo", NS)
    fecha_pub = txt(vni, ".//cac-place-ext:AdditionalPublicationDocumentReference/cbc:IssueDate")

    link = entry.find("atom:link", NS)
    url = link.get("href") if link is not None else None

    return {
        "expediente": expediente, "estado_code": estado_code,
        "estado": ESTADOS.get(estado_code, estado_code),
        "organo": organo, "ciudad": ciudad, "objeto": objeto,
        "nuts": nuts, "ubicacion": ubic, "importe": importe,
        "fecha_limite": fecha_limite, "hora_limite": hora_limite,
        "fecha_pub": fecha_pub or updated, "updated": updated, "url": url,
    }


def iter_entries_zip(data):
    """Percorre todos os .atom dun zip en memoria e cede cada <entry>.
    Se o zip está corrupto ou incompleto, non rompe: só avisa e non cede nada."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        log("    ⚠ o ficheiro descargado non é un zip válido. Sáltase.")
        return
    with z:
        for nome in z.namelist():
            if not nome.lower().endswith((".atom", ".xml")):
                continue
            try:
                raw = z.read(nome)
            except Exception:
                continue
            try:
                root = ET.fromstring(raw)
            except ET.ParseError:
                continue
            for entry in root.findall("atom:entry", NS):
                yield entry


# ─────────────────────────────────────────────────────────────────────────────
# PROCESO PRINCIPAL DE FILTRADO
# ─────────────────────────────────────────────────────────────────────────────

def procesar(args):
    hoxe = date.today()
    corte_antigo = hoxe - timedelta(days=args.antiguidade_max_dias)
    session = requests.Session(); session.headers.update(HEADERS)

    feeds = ["643", "1044"] if not args.so_feed else [args.so_feed]
    pers = periodos(args, hoxe)
    log(f"➤ Fontes PLACSP: {', '.join(feeds)} · períodos: {', '.join(pers)}")

    vistos = {}          # clave -> rexistro (dedup)
    n_entradas = n_pas = n_pv = 0
    debug_mostradas = 0
    algunha_descarga = False

    # Cargar "primeira detección" do JSON xa publicado (para a pestana Novidades)
    detectado_previo = cargar_detectado_previo(session, getattr(args, "estado_url", None))
    if detectado_previo:
        log(f"➤ Cargadas {len(detectado_previo)} datas de primeira detección previas.")

    # Períodos de reserva (feed anual) por se os mensuais non existen
    anual = [str(hoxe.year)] + ([str(hoxe.year - 1)] if hoxe.month == 1 else [])
    limite_anuncio = hoxe - timedelta(days=DIAS_ANUNCIO_MAX)

    def procesar_data(data):
        nonlocal n_entradas, n_pas, n_pv, debug_mostradas
        for entry in iter_entries_zip(data):
            r = parsear_entry(entry)
            if r is None:
                continue
            n_entradas += 1

            code = (r["estado_code"] or "").upper()
            # 1) descartar as claramente pechadas
            if code in ESTADOS_PECHADOS_CODE and not args.incluir_todo:
                continue
            # anuncio previo vai á súa pestana; o resto son "abertas"
            tipo = "anuncio" if code == ESTADO_ANUNCIO else "aberta"
            n_pas += 1

            # 2) provincia de Pontevedra. Regras:
            #    · ES114            -> Pontevedra (incluír)
            #    · ES111/112/113 ou outra provincia concreta -> descartar
            #    · ES11 (Galicia sen precisar) ou sen NUTS   -> rede de seguridade
            nuts = (r["nuts"] or "").upper().replace(" ", "")
            if nuts.startswith("ES114"):
                en_pv = True
            elif nuts[:5] in ("ES111", "ES112", "ES113"):
                en_pv = False                      # A Coruña, Lugo, Ourense
            elif nuts.startswith("ES11"):
                en_pv = parece_pontevedra(r["organo"], r["ciudad"], r["objeto"])
            elif nuts.startswith("ES") and len(nuts) >= 5:
                en_pv = False                      # provincia doutra CCAA
            else:
                en_pv = parece_pontevedra(r["organo"], r["ciudad"], r["objeto"])
            if not en_pv:
                continue
            n_pv += 1

            if args.debug and debug_mostradas < 3:
                log("\n    [debug] entry:")
                for k in ("expediente", "estado", "organo", "ciudad", "nuts",
                          "objeto", "fecha_pub", "fecha_limite", "importe"):
                    log(f"        {k}: {r.get(k)}")
                debug_mostradas += 1

            dlim = parse_data(r["fecha_limite"])
            dpub = parse_data(r["fecha_pub"])

            # 3) filtro de prazo / antigüidade segundo o tipo
            if tipo == "aberta":
                if dlim:
                    if dlim < hoxe and not args.incluir_todo:
                        continue
                else:
                    if dpub and dpub < corte_antigo and not args.incluir_todo:
                        continue
            else:  # anuncio previo: manter os recentes por data de publicación
                if dpub and dpub < limite_anuncio and not args.incluir_todo:
                    continue

            exp = r["expediente"] or r["url"] or ""
            detectado = detectado_previo.get(exp) or iso(hoxe)

            ambito = clasificar_ambito(r["organo"], r["ciudad"])
            rec = {
                "organismo": r["organo"] or "(órgano non indicado)",
                "ambito": ambito, "tipo": tipo,
                "objeto": r["objeto"] or "(sen descrición)",
                "estado": r["estado"],
                "importe": formato_importe(r["importe"]),
                "publicado": iso(dpub),
                "data_limite": iso(dlim),
                "hora_limite": r["hora_limite"],
                "detectado": detectado,
                "expediente": r["expediente"],
                "url": r["url"] or "https://contrataciondelsectorpublico.gob.es",
                "_upd": r["updated"] or "",
            }
            clave = exp or (r["organo"], r["objeto"])
            anterior = vistos.get(clave)
            if anterior is None:
                vistos[clave] = rec
            else:
                # conservar a detección máis temperá
                rec["detectado"] = min(rec["detectado"], anterior["detectado"])
                # preferir "aberta" sobre "anuncio"; se igual, o máis recente
                if anterior["tipo"] == "anuncio" and tipo == "aberta":
                    vistos[clave] = rec
                elif anterior["tipo"] == tipo and rec["_upd"] > anterior["_upd"]:
                    vistos[clave] = rec
                else:
                    anterior["detectado"] = rec["detectado"]

    def baixar_e_procesar(feed, cfg, per):
        nonlocal algunha_descarga
        url = cfg["base"] + cfg["patron"].format(periodo=per)
        log(f"\n➤ [{feed}] {cfg['patron'].format(periodo=per)}")
        data, code = descargar(session, url)
        if data is None:
            log(f"    ⚠ non dispoñible ({code}). Sáltase.")
            return False
        algunha_descarga = True
        log(f"    ✓ {len(data)/1e6:.1f} MB. Procesando…")
        procesar_data(data)
        return True

    for feed in feeds:
        cfg = FEEDS[feed]
        baixou = False
        for per in pers:
            if baixar_e_procesar(feed, cfg, per):
                baixou = True
        if not baixou and args.meses:
            log(f"    ↪ Ningún mensual dispoñible para [{feed}]; probo co feed anual…")
            for per in anual:
                baixar_e_procesar(feed, cfg, per)

    todas = list(vistos.values())
    for r in todas:
        r.pop("_upd", None)
    todas.sort(key=lambda r: r.get("publicado") or "", reverse=True)

    n_ab = sum(1 for r in todas if r["tipo"] == "aberta")
    n_an = sum(1 for r in todas if r["tipo"] == "anuncio")
    log(f"\n\n➤ Resumo: {n_entradas:,} entradas · {n_pas:,} non pechadas · "
        f"{n_pv:,} en Pontevedra · {n_ab:,} abertas + {n_an:,} anuncios previos.")
    return todas, algunha_descarga


def cargar_detectado_previo(session, url):
    """Le o JSON xa publicado para saber cándo se detectou cada expediente."""
    if not url:
        return {}
    try:
        r = session.get(url, timeout=30, verify=False)
        if r.status_code != 200:
            return {}
        datos = r.json()
    except Exception:
        return {}
    out = {}
    if isinstance(datos, list):
        for rec in datos:
            exp = rec.get("expediente") or rec.get("url")
            det = rec.get("detectado")
            if exp and det:
                out[exp] = det
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SAÍDAS
# ─────────────────────────────────────────────────────────────────────────────

def gardar_csv(recs, ruta):
    campos = ["tipo", "organismo", "ambito", "objeto", "estado", "importe",
              "publicado", "data_limite", "detectado", "expediente", "url"]
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        for r in recs: w.writerow(r)

def gardar_json(recs, ruta):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=2)

def gardar_panel(recs, ruta):
    payload = json.dumps(recs, ensure_ascii=False)
    xer = datetime.now().strftime("%d/%m/%Y %H:%M")
    out = PANEL_TEMPLATE.replace("__DATOS__", payload).replace("__XERADO__", xer)
    with open(ruta, "w", encoding="utf-8") as f: f.write(out)


PANEL_TEMPLATE = r"""<!DOCTYPE html>
<html lang="gl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Licitacións abertas · Pontevedra</title>
<style>
  :root{--mar:#0f3d3e;--mar2:#15595b;--area:#e8efe9;--papel:#f6f8f6;--tinta:#132420;
    --gris:#5e6b66;--liña:#d3ded7;--alerta:#a6431f;--branco:#fff;--dourado:#c98a2b;--xunta:#3a6ea5;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--papel);color:var(--tinta);font-size:15px;line-height:1.5;
    font-family:"Segoe UI",system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif}
  header{background:var(--mar);color:#eaf3ee;padding:26px 22px 18px}
  header .cab{max-width:1080px;margin:0 auto}
  header h1{margin:0;font-size:26px;font-weight:650}
  header p{margin:6px 0 0;color:#a9c8bd;font-size:13px}
  .barra{max-width:1080px;margin:0 auto;padding:14px 22px;display:flex;gap:12px;flex-wrap:wrap;
    align-items:center;position:sticky;top:0;background:var(--papel);z-index:5;border-bottom:1px solid var(--liña)}
  .tabs{display:flex;gap:4px;background:var(--area);padding:4px;border-radius:10px}
  .tab{border:0;background:transparent;padding:9px 16px;border-radius:8px;cursor:pointer;font-size:14px;color:var(--gris);font-weight:600}
  .tab.on{background:var(--branco);color:var(--mar);box-shadow:0 1px 3px rgba(0,0,0,.08)}
  .busca{flex:1;min-width:220px;display:flex;align-items:center;gap:8px;background:var(--branco);
    border:1px solid var(--liña);border-radius:10px;padding:8px 12px}
  .busca input{border:0;outline:0;font-size:15px;width:100%;background:transparent;color:var(--tinta)}
  .conta{color:var(--gris);font-size:13px;white-space:nowrap}
  main{max-width:1080px;margin:0 auto;padding:8px 22px 60px}
  .dia{margin-top:26px}
  .dia h2{font-size:15px;color:var(--mar2);margin:0 0 10px;padding-bottom:6px;border-bottom:2px solid var(--liña);
    display:flex;justify-content:space-between}
  .dia h2 span{color:var(--gris);font-weight:500}
  .card{background:var(--branco);border:1px solid var(--liña);border-left:4px solid var(--mar2);
    border-radius:10px;padding:14px 16px;margin-bottom:10px}
  .card.urxe{border-left-color:var(--alerta)} .card.axunta{border-left-color:var(--xunta)}
  .org{font-size:12.5px;color:var(--mar);font-weight:700;margin-bottom:3px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
  .tag{font-size:10.5px;font-weight:700;padding:1px 7px;border-radius:999px;background:var(--area);color:var(--mar2)}
  .tag.x{background:#e3edf7;color:var(--xunta)} .tag.o{background:#eee;color:#666}
  .tag.nova{background:#e2f0e6;color:#1f7a44}
  .card.anuncio{border-left-color:var(--dourado)}
  .pill.anuncio{background:#f3eede;color:var(--dourado)}
  .obj{font-size:15px;color:var(--tinta);margin:2px 0 10px}
  .meta{display:flex;flex-wrap:wrap;gap:14px;font-size:13px;color:var(--gris);align-items:center}
  .meta b{color:var(--tinta);font-weight:600}
  .pill{font-size:12px;padding:3px 9px;border-radius:999px;background:var(--area);color:var(--mar2)}
  .pill.urxe{background:#f6e2da;color:var(--alerta)} .pill.sendata{background:#f3eede;color:var(--dourado)}
  .meta a{color:var(--mar2);text-decoration:none;font-weight:600;margin-left:auto}
  .meta a:hover{text-decoration:underline}
  .baleiro{text-align:center;color:var(--gris);padding:60px 20px}
  footer{max-width:1080px;margin:0 auto;padding:20px 22px 50px;color:var(--gris);font-size:12px}
  @media(max-width:560px){.meta a{margin-left:0}}
</style></head><body>
<header><div class="cab">
  <h1>Licitacións abertas · provincia de Pontevedra</h1>
  <p>Fonte: PLACSP (perfís estatais + agregación CCAA) · actualizado o __XERADO__ ·
     inclúe todos os organismos que poden licitar na provincia de Pontevedra ·
     as fóra de prazo e antigas ocúltanse soas</p>
</div></header>
<div class="barra">
  <div class="tabs">
    <button class="tab on" data-v="dia">Todas por día</button>
    <button class="tab" data-v="novidades">Novidades</button>
    <button class="tab" data-v="cinco">Últimos 5 días</button>
    <button class="tab" data-v="anuncios">Anuncios previos</button>
  </div>
  <label class="busca">🔎 <input id="q" type="text" placeholder="Busca por organismo (p.ex. Vigo) ou texto…"></label>
  <span class="conta" id="conta"></span>
</div>
<main id="saida"></main>
<footer>Xerado localmente a partir dos datos abertos de PLACSP (Ministerio de Facenda).
  "Novidades" mostra as detectadas nos últimos 3 días. "Anuncios previos" son avisos
  anteriores á apertura, para ir preparando o orzamento. Verifica sempre o prazo na
  ficha oficial antes de presentar unha oferta.</footer>
<script>
const DATOS=__DATOS__;
const DIAS_NOVIDADE=3;
const hoxe=new Date(); hoxe.setHours(0,0,0,0);
const MESES=["xaneiro","febreiro","marzo","abril","maio","xuño","xullo","agosto","setembro","outubro","novembro","decembro"];
let vista="dia";
function d(i){if(!i)return null;const p=i.split("-");return new Date(+p[0],+p[1]-1,+p[2]);}
function fmt(i){const x=d(i);return x?x.getDate()+" "+MESES[x.getMonth()]+" "+x.getFullYear():"—";}
function dias(i){const x=d(i);return x?Math.round((x-hoxe)/86400000):null;}
function vixente(r){const dl=d(r.data_limite);return (!dl)||(dl>=hoxe);}
function novo(r){const t=dias(r.detectado);return t!==null&&t<=0&&t>-DIAS_NOVIDADE;}
function esc(s){return (s||"").replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}

function filtra(){
  const q=document.getElementById("q").value.trim().toLowerCase();
  let b;
  if(vista==="anuncios"){
    b=DATOS.filter(r=>r.tipo==="anuncio");
  }else{
    b=DATOS.filter(r=>r.tipo==="aberta"&&vixente(r));
    if(vista==="cinco"){const l=new Date(hoxe);l.setDate(l.getDate()-5);
      b=b.filter(r=>{const p=d(r.publicado);return p&&p>=l&&p<=hoxe;});}
    if(vista==="novidades"){b=b.filter(novo);}
  }
  if(q)b=b.filter(r=>(r.organismo||"").toLowerCase().includes(q)||(r.objeto||"").toLowerCase().includes(q));
  return b;
}

function tarxeta(r){
  const anuncio=r.tipo==="anuncio";
  const rest=dias(r.data_limite),urxe=!anuncio&&rest!==null&&rest<=5&&rest>=0;
  const ax=r.ambito==="xunta";
  let tag=r.ambito==="local"?'<span class="tag">Local</span>':ax?'<span class="tag x">Xunta</span>':'<span class="tag o">Outros</span>';
  if(novo(r)&&!anuncio)tag+='<span class="tag nova">nova</span>';
  let pill;
  if(anuncio)pill='<span class="pill anuncio">anuncio previo</span>';
  else if(r.data_limite===null)pill='<span class="pill sendata">sen data de peche</span>';
  else if(rest===0)pill='<span class="pill urxe">pecha hoxe</span>';
  else if(rest<0)pill='';
  else pill='<span class="pill'+(urxe?' urxe':'')+'">'+rest+' día'+(rest===1?'':'s')+' restantes</span>';
  const imp=r.importe?'<span>Importe: <b>'+esc(r.importe)+'</b></span>':'';
  const limite=anuncio?'':'<span>Data límite: <b>'+fmt(r.data_limite)+'</b></span>';
  return '<div class="card'+(urxe?' urxe':'')+(anuncio?' anuncio':(ax?' axunta':''))+'">'
    +'<div class="org">'+tag+esc(r.organismo)+'</div>'
    +'<div class="obj">'+esc(r.objeto)+'</div>'
    +'<div class="meta"><span>Publicado: <b>'+fmt(r.publicado)+'</b></span>'
    +limite+imp+pill
    +'<a href="'+esc(r.url)+'" target="_blank" rel="noopener">Ver ficha ↗</a></div></div>';
}

function pinta(){
  const l=filtra(),c=document.getElementById("saida");
  let etiqueta;
  if(vista==="anuncios")etiqueta=l.length===1?" anuncio previo":" anuncios previos";
  else if(vista==="novidades")etiqueta=l.length===1?" novidade":" novidades";
  else etiqueta=l.length===1?" licitación aberta":" licitacións abertas";
  document.getElementById("conta").textContent=l.length+etiqueta;
  if(!l.length){
    let m="Non hai nada que coincida.";
    if(vista==="novidades")m="Sen novidades nos últimos 3 días.";
    if(vista==="anuncios")m="Non hai anuncios previos agora mesmo.";
    c.innerHTML='<div class="baleiro">'+m+'<br>Proba a borrar o buscador ou cambiar de pestana.</div>';return;
  }
  // agrupar: por detección en "Novidades"; por publicación no resto
  const porDeteccion=(vista==="novidades");
  const g={};l.forEach(r=>{const k=(porDeteccion?r.detectado:r.publicado)||"0000";(g[k]=g[k]||[]).push(r);});
  let out="";Object.keys(g).sort().reverse().forEach(k=>{const gr=g[k];
    const cab=(k==="0000")?(porDeteccion?"Sen data":"Sen data de publicación"):(porDeteccion?"Detectadas o "+fmt(k):fmt(k));
    out+='<section class="dia"><h2>'+cab
      +'<span>'+gr.length+'</span></h2>';
    gr.forEach(r=>out+=tarxeta(r));out+='</section>';});
  c.innerHTML=out;
}
document.querySelectorAll(".tab").forEach(b=>b.onclick=()=>{
  document.querySelectorAll(".tab").forEach(x=>x.classList.remove("on"));
  b.classList.add("on");vista=b.dataset.v;pinta();});
document.getElementById("q").addEventListener("input",pinta);
pinta();
</script></body></html>
"""


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Licitacións abertas de Pontevedra (PLACSP)")
    ap.add_argument("--meses", type=int, default=0,
                    help="Usar as instantáneas dos N últimos meses (máis lixeiro). "
                         "Por defecto usa o feed anual acumulado.")
    ap.add_argument("--antiguidade-max-dias", type=int, default=120,
                    help="Descarta as SEN data límite publicadas hai máis de N días (def. 120)")
    ap.add_argument("--so-feed", choices=["643", "1044"], default=None,
                    help="Usar só un feed (643=perfís PLACSP, 1044=agregadas CCAA)")
    ap.add_argument("--incluir-todo", action="store_true",
                    help="Non filtrar por estado/prazo (depuración)")
    ap.add_argument("--saida", default=".",
                    help="Carpeta onde gardar os ficheiros (def. actual). "
                         "En GitHub Actions úsase 'public'.")
    ap.add_argument("--nome-html", default="dashboard.html",
                    help="Nome do HTML xerado (def. dashboard.html; en Pages: index.html)")
    ap.add_argument("--estado-url", default=None,
                    help="URL do JSON xa publicado (para lembrar a data de primeira "
                         "detección de cada licitación e alimentar a pestana Novidades)")
    ap.add_argument("--abrir", action="store_true")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    todas, algunha_descarga = procesar(args)

    # Rede de seguridade para o modo aloxado (GitHub Actions):
    # se NON se descargou ningún feed, non sobreescribas o panel bo anterior.
    if not algunha_descarga:
        log("\n✗ Non se puido descargar ningún feed de PLACSP. "
            "Non se rexenera o panel (consérvase o anterior).")
        sys.exit(1)

    os.makedirs(args.saida, exist_ok=True)
    ruta_html = os.path.join(args.saida, args.nome_html)
    ruta_csv = os.path.join(args.saida, "licitacions_pontevedra.csv")
    ruta_json = os.path.join(args.saida, "licitacions_pontevedra.json")
    gardar_csv(todas, ruta_csv)
    gardar_json(todas, ruta_json)
    gardar_panel(todas, ruta_html)

    n_loc = sum(1 for r in todas if r["ambito"] == "local")
    n_xun = sum(1 for r in todas if r["ambito"] == "xunta")
    n_out = sum(1 for r in todas if r["ambito"] == "outros")
    log("\n" + "=" * 64)
    log(f"  TOTAL: {len(todas)} licitacións abertas en Pontevedra "
        f"({n_loc} locais · {n_xun} Xunta · {n_out} outros)")
    log("=" * 64)
    log(f"  · {ruta_html}")
    log(f"  · {ruta_csv}")
    log(f"  · {ruta_json}")
    log("=" * 64)
    if not todas:
        log("  Non saíu nada. Proba:  --meses 3   ou   --debug   para ver que chega.")
    if args.abrir:
        webbrowser.open("file://" + os.path.abspath(ruta_html))


if __name__ == "__main__":
    main()
