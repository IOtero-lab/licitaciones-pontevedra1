#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnóstico PLACSP: ¿están estos expedientes dentro do ficheiro de datos
abertos de HOXE? Descarga os feeds anuais 643 e 1044 e busca cada ID.

Uso:
    python comprobar_expediente.py                      # busca os 2 de proba
    python comprobar_expediente.py "2625-441" "4011/2026" "outro-id"

Non depende do teu scraper. Só necesita 'requests'.
Resultado por cada expediente:
    · NON aparece en ningún feed  -> é atraso/consolidación de PLACSP (nada que
      tocar no teu código; agarda ou verifica mañá).
    · SÍ aparece  -> imprime feed, estado, NUTS, datas… e entón o problema está
      no teu parseo/filtro e xa sabemos onde mirar.
"""
import io
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import date

import requests

ANO = date.today().year

FEEDS = {
    "643": {
        "base": "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/",
        "patron": f"licitacionesPerfilesContratanteCompleto3_{ANO}.zip",
    },
    "1044": {
        "base": "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1044/",
        "patron": f"PlataformasAgregadasSinMenores_{ANO}.zip",
    },
}

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "cbc": "urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2",
    "cbc-place-ext": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2",
    "cac-place-ext": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2",
}

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "application/zip,application/xml,*/*;q=0.8",
}

# Firma dun ZIP real (para descartar páxinas HTML de erro con status 200)
ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def norm(s):
    """Normaliza un ID para comparar: minúsculas, sen espazos, / e - fóra."""
    return re.sub(r"[\s/_-]", "", (s or "").lower())


def txt(el, path):
    if el is None:
        return None
    x = el.find(path, NS)
    return x.text.strip() if x is not None and x.text else None


def descargar(url):
    print(f"  ↓ {url}")
    r = requests.get(url, headers=HEADERS, timeout=180)
    if r.status_code != 200:
        print(f"    ⚠ HTTP {r.status_code} — non dispoñible.")
        return None
    data = r.content
    if not data.startswith(ZIP_MAGIC):
        print(f"    ⚠ a resposta NON é un ZIP ({len(data)} bytes; "
              f"probablemente páxina de erro HTML). Saltada.")
        return None
    print(f"    ✓ {len(data)/1e6:.1f} MB, ZIP válido.")
    return data


def iter_atoms(data):
    """Cede (nome_ficheiro, bytes) de cada .atom, incluídos zips aniñados."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        print("    ⚠ ZIP corrupto.")
        return
    for name in z.namelist():
        low = name.lower()
        if low.endswith(".atom"):
            yield name, z.read(name)
        elif low.endswith(".zip"):
            try:
                for n2, b2 in iter_atoms(z.read(name)):
                    yield f"{name}!{n2}", b2
            except Exception:
                pass


def campos(status):
    """Extrae os mesmos campos que usa o teu scraper."""
    project = status.find("cac:ProcurementProject", NS)
    party = status.find(".//cac-place-ext:LocatedContractingParty/cac:Party", NS)
    organo = txt(party, ".//cac:PartyName/cbc:Name") if party is not None else None
    vni = status.find("cac-place-ext:ValidNoticeInfo", NS)
    return {
        "expediente": txt(status, "cbc:ContractFolderID"),
        "estado": txt(status, "cbc-place-ext:ContractFolderStatusCode"),
        "organo": organo,
        "nuts": txt(project, ".//cac:RealizedLocation/cbc:CountrySubentityCode") if project is not None else None,
        "ubicacion": txt(project, ".//cac:RealizedLocation/cbc:CountrySubentity") if project is not None else None,
        "fecha_limite": txt(status, ".//cac:TenderSubmissionDeadlinePeriod/cbc:EndDate"),
        "fecha_pub": txt(vni, ".//cac-place-ext:AdditionalPublicationDocumentReference/cbc:IssueDate") if vni is not None else None,
    }


def main():
    objetivos = sys.argv[1:] or ["2625-441", "4011/2026"]
    obj_norm = {norm(o): o for o in objetivos}
    print(f"➤ Buscando {len(objetivos)} expediente(s): {', '.join(objetivos)}")
    print(f"➤ Ano do feed: {ANO}\n")

    achados = {o: [] for o in objetivos}
    coincidencia_bruta = {o: [] for o in objetivos}  # aparición no XML cru

    for feed, cfg in FEEDS.items():
        print(f"=== FEED {feed} ===")
        data = descargar(cfg["base"] + cfg["patron"])
        if data is None:
            print()
            continue
        n_atom = n_entries = 0
        for nome, raw in iter_atoms(data):
            n_atom += 1
            # 1) rastro cru: o ID aparece en calquera parte do .atom?
            baixo = raw.lower()
            for on, orix in obj_norm.items():
                # busca tolerante: proba co ID orixinal e sen separadores
                if orix.lower().encode() in baixo or on.encode() in re.sub(rb"[\s/_-]", b"", baixo):
                    coincidencia_bruta[orix].append(f"{feed}:{nome}")
            # 2) parseo estruturado
            try:
                root = ET.fromstring(raw)
            except ET.ParseError:
                continue
            for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
                status = entry.find(".//cac-place-ext:ContractFolderStatus", NS)
                if status is None:
                    continue
                n_entries += 1
                exp = txt(status, "cbc:ContractFolderID")
                if exp and norm(exp) in obj_norm:
                    c = campos(status)
                    c["_feed"] = feed
                    c["_atom"] = nome
                    achados[obj_norm[norm(exp)]].append(c)
        print(f"    · {n_atom} ficheiros .atom · {n_entries:,} entradas procesadas\n")

    print("\n" + "=" * 60)
    print("RESULTADO")
    print("=" * 60)
    for o in objetivos:
        print(f"\n▶ Expediente: {o}")
        if achados[o]:
            for c in achados[o]:
                print(f"   ✔ ATOPADO no feed {c['_feed']}  ({c['_atom']})")
                print(f"       estado      : {c['estado']}")
                print(f"       organo      : {c['organo']}")
                print(f"       NUTS        : {c['nuts']}   ubicacion: {c['ubicacion']}")
                print(f"       fecha_pub   : {c['fecha_pub']}")
                print(f"       fecha_limite: {c['fecha_limite']}")
            print("   → Está no ficheiro. Se non sae na web, o fallo está no "
                  "parseo/filtro do teu scraper (mira eses campos).")
        elif coincidencia_bruta[o]:
            print(f"   ~ O ID aparece no XML cru ({coincidencia_bruta[o]}) pero "
                  "NON se parseou como entrada.")
            print("   → Probable diferenza de formato do ID ou estrutura do .atom. "
                  "Pásame ese .atom e afinamos o parseo.")
        else:
            print("   ✘ NON aparece en ningún feed de hoxe.")
            print("   → É atraso de consolidación de PLACSP, non do teu código. "
                  "Verifícao mañá tras un par de execucións.")
    print()


if __name__ == "__main__":
    main()
