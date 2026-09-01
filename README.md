# Licitacións abertas · provincia de Pontevedra

Panel web que mostra as **licitacións públicas abertas** (en prazo de presentación)
que se executan na **provincia de Pontevedra**, actualizado automaticamente
**4 veces ao día** e publicado en GitHub Pages. Sen servidor, sen manter nada.

- **Fonte:** datos abertos oficiais de **PLACSP** (Plataforma de Contratación do
  Sector Público). Cobre o Concello de Vigo, a Deputación de Pontevedra, os demais
  concellos, e os entes da Xunta cuxa execución é en Pontevedra (código NUTS ES114).
- **Filtros:** só licitacións en estado "en prazo"; as fóra de prazo e as antigas
  ocúltanse soas.
- **Vistas:** todas por día · últimos 5 días · buscador por organismo ou texto.

---

## Posta en marcha (unha soa vez, ~5 minutos)

1. **Crea un repositorio novo en GitHub** (por exemplo `licitacions-pontevedra`).
   Pode ser **público** (recomendado: as execucións programadas son gratuítas e
   ilimitadas nos repos públicos).

2. **Sobe estes ficheiros** ao repositorio (arrastrándoos na web de GitHub, ou con
   git). A estrutura ten que quedar así:

   ```
   .
   ├─ .github/
   │   └─ workflows/
   │       └─ actualizar.yml
   ├─ scraper.py
   ├─ requirements.txt
   └─ README.md
   ```

   > Importante: a carpeta ten que chamarse exactamente `.github/workflows` (co punto
   > diante) ou GitHub non verá o workflow.

3. **Activa GitHub Pages co modo Actions:**
   `Settings` → `Pages` → en **Build and deployment**, no apartado **Source**,
   elixe **GitHub Actions**. (Non fai falta escoller rama.)

4. **Lanza a primeira actualización á man:**
   Vai á pestana **Actions** → workflow **"Actualizar licitacións Pontevedra"** →
   botón **Run workflow**. Tarda un par de minutos.
   - Se é a primeira vez, quizais teñas que pulsar antes *"I understand my workflows,
     go ahead and enable them"*.

5. **Abre o teu panel.** A URL aparece en `Settings` → `Pages` (algo como
   `https://O-TEU-USUARIO.github.io/licitacions-pontevedra/`). A partir de aí,
   actualízase soa 4 veces ao día.

---

## Usar o teu propio dominio (opcional)

Se tes un dominio, en `Settings` → `Pages` → **Custom domain** escríbeo e garda.
Logo, no teu provedor de DNS, apunta o dominio a GitHub Pages (un rexistro `CNAME`
a `O-TEU-USUARIO.github.io`, ou os `A` de GitHub para dominios raíz). GitHub xera
o certificado HTTPS automaticamente.

---

## Axustes que igual queres tocar

Todo está no ficheiro `.github/workflows/actualizar.yml`:

- **Horas de actualización** (liña `cron`). Están en **UTC**. Exemplo actual
  `0 5,11,17,23 * * *` = 05:00, 11:00, 17:00 e 23:00 UTC. Para cambialas, edita esa
  liña. (Recorda: en hora galega hai +1 h en inverno e +2 h en verán.)
- **Cantos meses descarga** (`--meses 4`). Máis meses = máis cobertura pero descarga
  máis pesada. Se queres o **ano enteiro**, quita `--meses 4` (deixa só
  `python scraper.py --saida public --nome-html index.html`); tarda máis e baixa
  bastantes máis datos.
- **Antigüidade** das que non teñen data de peche: `--antiguidade-max-dias N`
  (por defecto 120).

---

## Notas

- As execucións programadas de GitHub **pódense atrasar** uns minutos cando hai moita
  carga; é normal. Ademais, **GitHub desactiva o cron se o repo leva 60 días sen
  actividade**; abonda con entrar e relanzalo (ou facer calquera commit) para reactivalo.
- Se nunha execución PLACSP non responde, o script **non toca o panel anterior**
  (a execución márcase en vermello, pero segues vendo os últimos datos bos).
- Podes probar o scraper no teu ordenador antes de subilo:
  `pip install requests` e logo `python scraper.py --abrir`.

Datos públicos (Ministerio de Facenda / Lei de transparencia). Verifica sempre o
prazo na ficha oficial de cada licitación antes de presentar unha oferta.
