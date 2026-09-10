"""
A casca visual dos painéis HTML — tokens, tipografia e os pedaços que se repetem.

Existe para que o painel comparativo (scripts/painel_metricas.py) e a página
por loja (scripts/painel_loja.py) sejam a MESMA família visual sem copiar CSS
entre os dois. Mexeu aqui, mexeu nos dois — que é a regra da pasta core/.

Não sabe nada sobre Mercado Livre: só formata número e devolve HTML.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=-3))


# ----------------------------------------------------------------------
# Formatação
# ----------------------------------------------------------------------
def e(t) -> str:
    """Escapa para HTML. Título de anúncio vem do vendedor e pode ter < e &."""
    return html.escape(str(t if t is not None else ""))


def rs(v, casas: int = 0) -> str:
    """Número no formato brasileiro. 27894.23 -> '27.894'."""
    if v is None:
        return "—"
    inteiro = f"{v:,.{casas}f}"
    return inteiro.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def pct(v, casas: int = 1, sinal: bool = False) -> str:
    """Percentual em pt-BR. Espera pontos percentuais, não fração."""
    if v is None:
        return "—"
    corpo = f"{v:+.{casas}f}" if sinal else f"{v:.{casas}f}"
    return corpo.replace(".", ",") + "%"


def data_curta(iso: str | None) -> str:
    """'2026-09-10' -> '10/09'. Aceita ISO com hora."""
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(str(iso)[:19].replace("Z", "")).strftime("%d/%m")
    except ValueError:
        return str(iso)[:10]


def dias_ate(iso: str | None) -> int | None:
    """Quantos dias faltam para uma data. Negativo se já passou."""
    if not iso:
        return None
    try:
        alvo = datetime.fromisoformat(str(iso)[:19].replace("Z", "")).date()
    except ValueError:
        return None
    return (alvo - datetime.now(TZ).date()).days


# ----------------------------------------------------------------------
# Pedaços de HTML
# ----------------------------------------------------------------------
def chip(texto: str, tom: str = "neutro") -> str:
    """Pastilha de estado. tom: bom | atencao | critico | neutro."""
    return f'<span class="chip chip--{tom}">{e(texto)}</span>'


def barra(fracao: float, tom: str = "acento", titulo: str = "") -> str:
    """Barra horizontal de 0 a 1, para comparar dentro de uma coluna."""
    largura = max(0.0, min(float(fracao or 0), 1.0)) * 100
    t = f' title="{e(titulo)}"' if titulo else ""
    return (f'<span class="mini"{t}>'
            f'<span class="mini__cheio mini__cheio--{tom}" style="width:{largura:.1f}%"></span></span>')


def vazio(mensagem: str) -> str:
    return f'<p class="nada">{e(mensagem)}</p>'


# ----------------------------------------------------------------------
# CSS base — os dois painéis herdam isto
# ----------------------------------------------------------------------
CSS_BASE = """
:root {
  --papel:#f1f4f3; --superficie:#ffffff; --tinta:#121a19; --tinta-fraca:#5c6d69;
  --linha:#dde4e2; --acento:#0f6b64; --acento-fraco:#e3efed;
  --bom:#2c7a51; --atencao:#a2600f; --critico:#a83a2c;
  --bom-fundo:#e6f2ea; --atencao-fundo:#f8eddb; --critico-fundo:#f7e5e2;
  --sombra:0 1px 2px rgba(18,26,25,.05), 0 8px 24px -12px rgba(18,26,25,.14);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --papel:#0c1211; --superficie:#141d1c; --tinta:#e2eae7; --tinta-fraca:#8ba09b;
    --linha:#243230; --acento:#4fb3a8; --acento-fraco:#17302d;
    --bom:#5cb583; --atencao:#d1943f; --critico:#dd7566;
    --bom-fundo:#162b21; --atencao-fundo:#2e2415; --critico-fundo:#301c19;
    --sombra:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
  }
}
:root[data-theme="dark"] {
  --papel:#0c1211; --superficie:#141d1c; --tinta:#e2eae7; --tinta-fraca:#8ba09b;
  --linha:#243230; --acento:#4fb3a8; --acento-fraco:#17302d;
  --bom:#5cb583; --atencao:#d1943f; --critico:#dd7566;
  --bom-fundo:#162b21; --atencao-fundo:#2e2415; --critico-fundo:#301c19;
  --sombra:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
}

* { box-sizing:border-box; }
body {
  margin:0; background:var(--papel); color:var(--tinta);
  font:400 15px/1.55 "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
  -webkit-font-smoothing:antialiased;
}
h1,h2,h3 { font-family:"Bricolage Grotesque","IBM Plex Sans",sans-serif; text-wrap:balance; margin:0; }
a { color:var(--acento); }
a:focus-visible, [tabindex]:focus-visible { outline:2px solid var(--acento); outline-offset:2px; }

.mono { font-family:"IBM Plex Mono",ui-monospace,monospace; font-variant-numeric:tabular-nums; }
.num  { text-align:right; font-family:"IBM Plex Mono",ui-monospace,monospace; font-variant-numeric:tabular-nums; }

.folha { max-width:1180px; margin:0 auto; padding:40px 24px 72px; }

.cabeca { border-bottom:2px solid var(--tinta); padding-bottom:20px; margin-bottom:32px; }
.eyebrow {
  font-family:"IBM Plex Mono",monospace; font-size:11px; letter-spacing:.14em;
  text-transform:uppercase; color:var(--acento); margin:0 0 10px;
}
.cabeca h1 { font-size:clamp(30px,5vw,46px); font-weight:700; letter-spacing:-.02em; line-height:1.05; }
.cabeca .resumo { margin:14px 0 0; max-width:62ch; color:var(--tinta-fraca); }
.carimbo {
  display:flex; flex-wrap:wrap; gap:8px 20px; margin-top:16px;
  font-family:"IBM Plex Mono",monospace; font-size:12px; color:var(--tinta-fraca);
}
.carimbo b { color:var(--tinta); font-weight:500; }

.secao { margin-bottom:44px; }
.secao > h2 { font-size:22px; font-weight:700; letter-spacing:-.015em; }
.intro { margin:8px 0 18px; max-width:68ch; color:var(--tinta-fraca); font-size:14px; }
.rolagem { overflow-x:auto; }

.chip { display:inline-block; font-size:11.5px; font-weight:500; padding:1px 7px; border-radius:2px; white-space:nowrap; }
.chip--bom { background:var(--bom-fundo); color:var(--bom); }
.chip--atencao { background:var(--atencao-fundo); color:var(--atencao); }
.chip--critico { background:var(--critico-fundo); color:var(--critico); }
.chip--neutro { background:var(--acento-fraco); color:var(--acento); }

.tabela { width:100%; border-collapse:collapse; font-size:14px; }
.tabela th, .tabela td { padding:11px 14px; text-align:left; border-bottom:1px solid var(--linha); }
.tabela thead th {
  font-family:"IBM Plex Mono",monospace; font-size:10px; letter-spacing:.08em;
  text-transform:uppercase; color:var(--tinta-fraca); font-weight:400;
  border-bottom:1px solid var(--tinta); white-space:nowrap;
}
.tabela tbody th { font-weight:600; }
.tabela td small, .tabela th small { color:var(--tinta-fraca); font-weight:400; }
.tabela tbody tr:last-child th, .tabela tbody tr:last-child td { border-bottom:none; }
.tabela .titulo { max-width:38ch; line-height:1.35; }

.mini { display:inline-block; width:74px; height:8px; background:var(--linha); border-radius:2px; overflow:hidden; vertical-align:middle; }
.mini__cheio { display:block; height:100%; }
.mini__cheio--acento { background:var(--acento); }
.mini__cheio--bom { background:var(--bom); }
.mini__cheio--atencao { background:var(--atencao); }
.mini__cheio--critico { background:var(--critico); }

.nada { font-size:13.5px; color:var(--tinta-fraca); font-style:italic; }

.creditos {
  margin-top:40px; padding-top:16px; border-top:1px solid var(--linha);
  font-family:"IBM Plex Mono",monospace; font-size:11px; color:var(--tinta-fraca);
}
.creditos a { color:var(--tinta-fraca); }

@media (max-width:640px) { .folha { padding:28px 16px 56px; } }
"""

FONTES = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    'family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&'
    'family=IBM+Plex+Mono:wght@400;500&'
    'family=IBM+Plex+Sans:wght@400;500;600&display=swap">'
)


def pagina(titulo: str, corpo: str, css_extra: str = "") -> str:
    """Monta o arquivo final. Sem doctype/html/head: o Artifact embrulha."""
    return (f"<title>{e(titulo)}</title>\n{FONTES}\n"
            f"<style>{CSS_BASE}{css_extra}</style>\n\n"
            f'<div class="folha">{corpo}</div>\n')
