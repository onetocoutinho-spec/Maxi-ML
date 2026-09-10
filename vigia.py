#!/usr/bin/env python3
"""
Vigia contínuo — o mais perto de tempo real que a API do Mercado Livre permite.

Fica rodando e, a cada poucos minutos, relê os anúncios concorrentes conhecidos.
Mudou preço, frete grátis, estoque ou status: alerta sai na hora.

Por que um processo residente e não uma tarefa agendada de 5 em 5 minutos:
o token fica quente na memória, não há custo de subir o Python a cada ciclo,
e o intervalo pode ser menor que o mínimo do Agendador do Windows.

  python vigia.py                    todas as contas, intervalo do config
  python vigia.py --intervalo 120    a cada 2 minutos
  python vigia.py enio-toldos-principal

Ctrl+C encerra. Fechar a janela também.
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

RAIZ = Path(__file__).resolve().parent
ARQ_LOG = RAIZ / "data" / "vigia.log"
ARQ_BATIMENTO = RAIZ / "data" / "vigia.batimento"
ARQ_SUBIU = RAIZ / "data" / "vigia.subiu"

# Rodando por pythonw.exe (sem janela) não existe stdout: escrever nele
# levantaria exceção e mataria o vigia no primeiro print. Nesse caso a saída
# vai para arquivo.
_SEM_CONSOLE = sys.stdout is None or getattr(sys.stdout, "fileno", None) is None
if _SEM_CONSOLE:
    ARQ_LOG.parent.mkdir(parents=True, exist_ok=True)
    _saida = open(ARQ_LOG, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _saida
else:
    for _f in (sys.stdout, sys.stderr):
        try:
            _f.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from core import db, notify, promocoes, rules, vigilancia
from core.collectors import coletar_meus_anuncios
from core.config import resolver_contas
from core.ml_api import MLClient
from core.utils import TZ_BR, agora_iso, cor

if _SEM_CONSOLE:
    VERDE = VERM = AMAR = CINZA = FIM = ""
else:
    VERDE, VERM, AMAR, CINZA, FIM = (
        cor("\033[32m"), cor("\033[31m"), cor("\033[33m"), cor("\033[90m"), cor("\033[0m")
    )


def arquivos_de_codigo() -> list[Path]:
    """Os arquivos cujo conteúdo o vigia carregou na memória ao subir."""
    return [RAIZ / "vigia.py", *(RAIZ / "core").glob("*.py"),
            *(RAIZ / "scripts").glob("*.py")]


def marca_do_codigo() -> float:
    """A data do arquivo de código mais recente. Muda quando alguém publica."""
    return max((a.stat().st_mtime for a in arquivos_de_codigo() if a.exists()),
               default=0.0)


def registrar_subida(marca: float) -> None:
    """
    Grava QUANDO o vigia subiu e com QUAL versão do código — em arquivo
    separado do batimento.

    O batimento é reescrito a cada ciclo, então usar a data dele como "hora em
    que o vigia subiu" dá sempre 'agora': era esse o bug que fazia o guardião
    nunca perceber código novo, e o vigia rodar por horas a versão antiga
    enquanto o arquivo no disco já estava corrigido.
    """
    try:
        ARQ_SUBIU.parent.mkdir(parents=True, exist_ok=True)
        ARQ_SUBIU.write_text(f"{agora_iso()}\n{marca:.0f}\n", encoding="utf-8")
    except Exception:
        pass


def reiniciar_com_codigo_novo() -> None:
    """
    Sobe um vigia novo e sai. Sem isso, publicar correção não adianta nada até
    alguém reiniciar na mão — o processo em execução continua com o código
    velho na memória.

    Processo novo e destacado em vez de os.execv: no Windows o execv tem
    comportamento diferente do Unix e o processo pode morrer sem deixar
    substituto, que é justamente o que não pode acontecer aqui.
    """
    import subprocess as _sp
    print(f"{AMAR}{relogio()}  código atualizado — reiniciando o vigia{FIM}")
    comando = [sys.executable, str(RAIZ / "vigia.py"), *sys.argv[1:]]
    extras: dict = {"cwd": str(RAIZ)}
    if hasattr(_sp, "DETACHED_PROCESS"):              # Windows
        extras["creationflags"] = _sp.DETACHED_PROCESS | _sp.CREATE_NEW_PROCESS_GROUP
    else:
        extras["start_new_session"] = True
    try:
        _sp.Popen(comando, **extras)
    except Exception as erro:
        print(f"{VERM}não consegui reiniciar sozinho: {erro}{FIM}")
        return                      # continua vivo com o código velho: pior
                                    # que reiniciar, melhor que morrer calado
    sys.exit(0)


def buraco_desde_o_ultimo_batimento() -> float | None:
    """
    Quanto tempo o vigia passou fora do ar, em segundos.

    Lido ANTES do primeiro batimento desta execução: depois, o arquivo já
    carrega a hora de agora e o buraco some. None quando não há batimento
    anterior — primeira execução da vida não é buraco.
    """
    if not ARQ_BATIMENTO.exists():
        return None
    try:
        from datetime import timezone
        carimbo = datetime.fromisoformat(
            ARQ_BATIMENTO.read_text(encoding="utf-8").strip())
        if carimbo.tzinfo is None:
            carimbo = carimbo.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - carimbo).total_seconds()
    except Exception:
        return None


def avisar_que_ficou_cego(segundos: float) -> None:
    """
    Conta no canal de alertas que houve uma janela sem vigilância.

    Silêncio pode significar duas coisas opostas — nada mudou, ou ninguém
    estava olhando — e do lado de quem recebe elas são idênticas. Um sistema
    de alerta que não sabe dizer qual das duas foi não é confiável: o operador
    passa a supor que o silêncio é bom, justo quando ele não é.
    """
    minutos = int(segundos // 60)
    quanto = f"{minutos // 60}h{minutos % 60:02d}" if minutos >= 60 else f"{minutos} min"
    try:
        notify.enviar(
            f"*Zion ML — janela sem vigilância*\n\n"
            f"O vigia ficou {quanto} fora do ar e acabou de voltar.\n"
            f"Causa comum: o computador dormiu ou foi desligado.\n\n"
            f"Nada se perdeu: a próxima comparação é contra a última leitura "
            f"antes da parada, então mudança que aconteceu nesse intervalo "
            f"aparece nos alertas agora — só chega atrasada.")
    except Exception:
        pass


def bater_ponto() -> None:
    """
    Marca 'estou vivo'. A rotina de hora em hora confere este arquivo e, se
    estiver velho, sobe o vigia de novo. É mais confiável que procurar o
    processo pelo nome — há vários pythonw na máquina.
    """
    try:
        ARQ_BATIMENTO.parent.mkdir(parents=True, exist_ok=True)
        ARQ_BATIMENTO.write_text(agora_iso(), encoding="utf-8")
    except Exception:
        pass

# Frete é uma chamada por anúncio. No ciclo curto conferimos poucos, e de
# tempos em tempos ampliamos — assim o custo fica estável e nada fica velho
# demais.
CICLOS_ENTRE_FRETES_LARGOS = 12


def relogio() -> str:
    return datetime.now(TZ_BR).strftime("%H:%M:%S")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("alvo", nargs="?", default=None)
    p.add_argument("--intervalo", type=int, default=None,
                   help="segundos entre ciclos (padrão: config, ou 300)")
    p.add_argument("--sem-frete", action="store_true")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--uma-vez", action="store_true",
                   help="roda um ciclo e sai (para teste)")
    a = p.parse_args()

    cfg = notify.carregar_config()
    regras = cfg.get("regras") or {}
    intervalo = a.intervalo or int(regras.get("intervalo_vigia_segundos", 300))
    intervalo = max(60, intervalo)
    cep = str(regras.get("cep_referencia", "01001000"))
    fretes_proprios = int(regras.get("fretes_proprios_por_rodada", 8))
    promocoes_por_rodada = int(regras.get("promocoes_por_rodada", 6))

    contas = resolver_contas(a.alvo)
    if not contas:
        print(f"{VERM}Nenhuma conta autorizada.{FIM}")
        return 1

    print(f"\n{'═' * 66}")
    print(f"  VIGIA — {len(contas)} conta(s), ciclo de {intervalo}s")
    print(f"  Alertas críticos saem no canal configurado assim que aparecem.")
    print(f"  Ctrl+C para encerrar.")
    print(f"{'═' * 66}\n")

    clientes: dict[str, MLClient] = {}
    ciclo = 0
    codigo_ao_subir = marca_do_codigo()

    # Antes de bater o primeiro ponto: o batimento antigo é a única memória
    # de quando o vigia parou de existir.
    buraco = buraco_desde_o_ultimo_batimento()
    tolerancia = intervalo * 3
    if buraco is not None and buraco > tolerancia:
        print(f"{AMAR}{relogio()}  voltando depois de "
              f"{int(buraco // 60)} min fora do ar{FIM}")
        avisar_que_ficou_cego(buraco)

    registrar_subida(codigo_ao_subir)

    while True:
        ciclo += 1
        bater_ponto()

        # Código novo no disco: sobe de novo antes de trabalhar. A folga de 5s
        # evita reiniciar no meio de uma publicação que ainda está gravando
        # arquivos.
        if not a.uma_vez and marca_do_codigo() > codigo_ao_subir + 5:
            reiniciar_com_codigo_novo()

        # Pedidos deixados em pedidos/ saem em até um ciclo, não em uma hora.
        try:
            import subprocess as _sp
            _sp.run([sys.executable, str(Path(__file__).resolve().parent /
                                         "scripts" / "fila.py")],
                    cwd=str(Path(__file__).resolve().parent),
                    capture_output=True, timeout=900)
        except Exception:
            pass
        largo = (ciclo % CICLOS_ENTRE_FRETES_LARGOS == 1)
        max_frete = 0 if a.sem_frete else (40 if largo else 8)
        con = db.conectar()
        total_alertas = 0

        for conta in contas:
            try:
                if conta.slug not in clientes:
                    clientes[conta.slug] = MLClient(conta.slug, user_id_esperado=conta.user_id)
                cli = clientes[conta.slug]

                carimbo = agora_iso()

                # meus anúncios: 2 chamadas para 38 itens, sem visitas.
                # Barato o bastante para caber no ciclo curto.
                # Frete próprio por rodízio: alguns por rodada, girando, para
                # a tabela do Mercado Livre não mudar sem ninguém ver. Medir
                # todos a cada 5 minutos seria uma chamada por anúncio por
                # ciclo; medir uma vez por dia era pouco, porque o ML mexe no
                # frete a toda hora.
                meus = coletar_meus_anuncios(con, conta, cli, carimbo,
                                             com_visitas=False, cep=cep,
                                             max_fretes=fretes_proprios)
                con.commit()
                n_meus = rules.avaliar_mudancas_proprias(con, conta, carimbo)

                r = vigilancia.vigiar(con, conta, cli, carimbo, cep=cep, max_frete=max_frete)
                n_deles = 0
                if not r.get("aviso"):
                    n_deles = rules.avaliar_mudancas_concorrentes(con, conta, carimbo)

                # Campanhas do Mercado Livre, por rodízio. O ML libera campanha
                # anúncio por anúncio e no aplicativo aceitar é um toque, sem
                # menção a custo. Quem avisa primeiro evita o toque errado.
                n_promo = 0
                try:
                    ativos = [l["item_id"] for l in con.execute(
                        "SELECT item_id FROM snap_anuncio WHERE conta_slug = ? "
                        "AND coletado_em = ? AND status = 'active' "
                        "ORDER BY vendidos DESC", (conta.slug, carimbo))]
                    fatia = promocoes.fila(con, conta, ativos, promocoes_por_rodada)
                    if fatia:
                        _, carimbo_promo = promocoes.coletar(con, conta, cli, fatia)
                        con.commit()
                        n_promo = rules.avaliar_promocoes(con, conta, carimbo_promo)
                except Exception as erro_promo:
                    # Campanha indisponível não pode derrubar o ciclo: preço e
                    # estoque são o essencial e já foram lidos.
                    print(f"{CINZA}{relogio()}  {conta.slug}: campanhas — "
                          f"{str(erro_promo)[:80]}{FIM}")

                n = n_meus + n_deles + n_promo
                total_alertas += n
                marca = f"{VERM}{n} mudança(s){FIM}" if n else f"{CINZA}sem mudança{FIM}"
                detalhe = f"{meus} meus"
                if promocoes_por_rodada:
                    detalhe += f", {promocoes_por_rodada} campanhas"
                if fretes_proprios:
                    detalhe += f" ({fretes_proprios} fretes seus)"
                if r.get("aviso"):
                    detalhe += f", {CINZA}{r['aviso']}{FIM}"
                else:
                    detalhe += f", {r['itens']} deles ({r['fretes']} fretes)"
                print(f"{CINZA}{relogio()}{FIM}  {conta.slug}: {detalhe} → {marca}")

            except Exception as erro:
                # Banco ocupado não é falha: é a coleta completa escrevendo do
                # outro lado. Espera e tenta de novo uma vez, porque perder o
                # ciclo abre um buraco na série — e a série é o produto.
                if "database is locked" in str(erro).lower():
                    print(f"{AMAR}{relogio()}  {conta.slug}: banco ocupado, "
                          f"tentando de novo em 20s{FIM}")
                    time.sleep(20)
                    try:
                        con.close()
                        con = db.conectar()
                        continue
                    except Exception:
                        pass
                print(f"{VERM}{relogio()}  {conta.slug}: {str(erro)[:110]}{FIM}")
                clientes.pop(conta.slug, None)   # força reconexão no próximo ciclo
                if a.debug:
                    traceback.print_exc()

        # A descarga de pendentes acontece TODO ciclo, não só quando o próprio
        # vigia achou mudança. Antes era condicional, e isso segurava alerta:
        # uma coleta disparada pela fila ou pela rotina gravava alerta crítico
        # no banco e ele ficava lá parado até o vigia, por acaso, achar uma
        # mudança sua. Consulta em banco vazio é barata; alerta crítico esperando
        # três horas não é.
        # Esta etapa NÃO pode derrubar o vigia. Já derrubou duas vezes em
        # 01/09/2026 com "database is locked": a rotina de hora em hora estava
        # no meio de uma coleta grande, segurou o lock por mais que os 60s de
        # busy_timeout, e o processo inteiro morreu no meio do laço — levando
        # junto TODOS os alertas das contas até alguém perceber. Falhar aqui
        # custa um ciclo: os pendentes continuam pendentes e saem no próximo,
        # que é justamente para isso que esta chamada roda todo ciclo.
        try:
            resultado = notify.notificar_pendentes(con)
            if "nenhum alerta pendente" not in resultado.detalhe:
                print(f"       {VERDE}→ {resultado.detalhe}{FIM}")
        except Exception as erro:
            print(f"       {AMAR}não deu para descarregar os pendentes agora "
                  f"({str(erro)[:80]}) — ficam para o próximo ciclo{FIM}")

        try:
            con.close()
        except Exception:
            pass

        if a.uma_vez:
            print(f"{CINZA}ciclo único concluído{FIM}")
            return 0

        try:
            time.sleep(intervalo)
        except KeyboardInterrupt:
            raise


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n{AMAR}vigia encerrado{FIM}")
        sys.exit(0)
