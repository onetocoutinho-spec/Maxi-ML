#!/usr/bin/env python3
"""
zion-ml — operação multi-conta de Mercado Livre.

Uso:
  python cli.py contas                          lista clientes, contas e situação
  python cli.py checar <slug>                   testa credencial de uma conta
  python cli.py coletar [alvo] [--sem-visitas]  coleta snapshot (alvo = slug | cliente | todas)
  python cli.py alertas [alvo] [--horas 24]     mostra alertas do período
  python cli.py relatorio [cliente]             gera o HTML do painel
  python cli.py rotina [alvo]                   coletar + avaliar + relatório (uso diário)
  python cli.py resumo [--horas 24]             resumo em texto no terminal
  python cli.py notificar [--resumo]            envia pelo canal configurado
  python cli.py testar-notificacao              testa o canal (faça isso primeiro)
  python cli.py imagem-ambientada <slug> <MLB>  foto de capa ambientada via OpenAI (custa por chamada)
"""
from __future__ import annotations

import argparse
import sys
import traceback

# Windows: quando a saída vai para arquivo (log da rotina agendada), o Python
# usa a codificação local (cp1252) e quebra em acento ou símbolo. Forçar UTF-8
# aqui evita UnicodeEncodeError derrubar a coleta no meio.
for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core import (cobertura, confrontos, cupons, db, diagnostico, funil,
                  humano, imagens, manutencao, notify, posicoes, precificacao,
                  promocoes, publicacao, relatorio_cupom, report, rules,
                  tarifas, vigilancia)
from core.collectors import (
    coletar_buy_box,
    coletar_catalogo,
    coletar_destaques,
    coletar_meus_anuncios,
    coletar_saude_da_conta,
)
from core.config import carregar_clientes, obter_conta, resolver_contas
from core.ml_api import MLClient
from core.utils import agora_iso, brl, cor, para_br, truncar

VERDE, VERM, AMAR, CINZA, FIM = (
    cor("\033[32m"), cor("\033[31m"), cor("\033[33m"), cor("\033[90m"), cor("\033[0m")
)


def _cli_para(conta) -> MLClient:
    return MLClient(conta.slug, user_id_esperado=conta.user_id)


# ----------------------------------------------------------------------
def cmd_contas(_args) -> int:
    for cliente in carregar_clientes(apenas_ativos=False):
        marca = VERDE if cliente.status == "ativo" else CINZA
        print(f"\n{marca}● {cliente.nome}{FIM}  [{cliente.id}]  {CINZA}{cliente.nicho}{FIM}")
        if cliente.coordenar_preco and len(cliente.contas) > 1:
            print(f"  {AMAR}↳ preço coordenado entre as contas{FIM}")
        for conta in cliente.contas:
            estado = f"{VERDE}pronta{FIM}" if conta.configurada else f"{VERM}sem user_id{FIM}"
            env = conta.dir / ".env"
            cred = f"{VERDE}.env ok{FIM}" if env.exists() else f"{VERM}.env ausente{FIM}"
            print(f"    {conta.slug:<26} {conta.papel:<11} {estado:<20} {cred}"
                  f"  {CINZA}{len(conta.palavras_chave)} termos, "
                  f"{len(conta.produtos_vigiados)} "
                  f"{'ficha vigiada' if len(conta.produtos_vigiados) == 1 else 'fichas vigiadas'}{FIM}")
    print()
    return 0


def _decodificar(bruto: bytes) -> str:
    """Texto de programa do Windows, sem confiar na página de código."""
    for codec in ("utf-8", "cp1252", "cp850", "latin-1"):
        try:
            return bruto.decode(codec)
        except UnicodeDecodeError:
            continue
    return bruto.decode("utf-8", errors="replace")


def _resultado_tarefa(codigo: str) -> str:
    """
    Traduz o 'último resultado' do Agendador do Windows.

    O painel mostra números como 267011 e ninguém sabe o que são. 267011 é
    0x41303: a tarefa nunca rodou. Sem a tradução, um código de "tudo normal"
    parece erro e um erro de verdade passa como número inofensivo.
    """
    tabela = {
        "0": "concluída com sucesso",
        "1": "FALHOU (erro genérico do programa)",
        "2": "FALHOU: arquivo não encontrado",
        "267009": "está em execução agora",
        "267010": "não foi executada ainda nesta janela",
        "267011": "nunca executou",
        "267014": "foi encerrada pelo usuário",
        "2147942401": "FALHOU: arquivo ou caminho não encontrado",
        "2147942402": "FALHOU: caminho não encontrado",
        "2147942405": "FALHOU: acesso negado",
        "3221225786": "encerrada com Ctrl+C",
    }
    limpo = (codigo or "").strip()
    nome = tabela.get(limpo)
    if nome:
        return f"{nome} ({limpo})"
    return f"código {limpo}" if limpo and limpo != "?" else "?"


def _sem_acento(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c))


def cmd_maquina(args) -> int:
    """
    Raio-x da MÁQUINA, não da conta: qual Python está rodando, se as
    bibliotecas estão onde deviam, e se as tarefas agendadas do Windows
    continuam de pé.

    Existe porque o diagnóstico à distância chegou num ponto cego: a rotina
    de hora em hora parou de deixar registro, e não dava para saber se era o
    agendador que não dispara, o Python errado sendo usado, ou o arquivo .bat
    escolhendo o interpretador de fora do ambiente. Adivinhar isso por
    dedução custou tempo; perguntar à máquina custa um ciclo.
    """
    import platform
    import re
    import subprocess as _sp
    from datetime import datetime, timezone
    from pathlib import Path

    print(f"\n{'─' * 62}")
    print(f"  MÁQUINA — {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    print(f"{'─' * 62}\n")

    raiz = Path(__file__).resolve().parent
    print(f"  pasta ................ {raiz}")
    print(f"  python em uso ........ {sys.executable}")
    print(f"  versão ............... {platform.python_version()}")

    venv = raiz / ".venv" / "Scripts" / "python.exe"
    if not venv.exists():
        venv = raiz / ".venv" / "bin" / "python"
    print(f"  python do ambiente ... {venv if venv.exists() else 'NÃO ENCONTRADO'}")

    mesmo = venv.exists() and Path(sys.executable).resolve() == venv.resolve()
    if venv.exists() and not mesmo:
        print(f"  {AMAR}ATENÇÃO: rodando FORA do ambiente do projeto.{FIM}")
        print(f"  {CINZA}É o que produz 'No module named yaml' — o Python de fora")
        print(f"  não tem as bibliotecas instaladas aqui dentro.{FIM}")

    # A lista vem do requirements.txt, não de uma lista escrita à mão aqui:
    # lista à mão envelhece e passa a acusar falta de coisa que o projeto nem
    # usa — foi o que aconteceu com o 'dotenv', que nunca fez parte daqui.
    apelidos = {"pyyaml": "yaml", "python-dotenv": "dotenv",
                "beautifulsoup4": "bs4", "pillow": "PIL"}
    pacotes = []
    try:
        for linha in (raiz / "requirements.txt").read_text(encoding="utf-8").splitlines():
            linha = linha.split("#")[0].strip()
            if not linha:
                continue
            nome = re.split(r"[<>=!\[]", linha)[0].strip().lower()
            pacotes.append(apelidos.get(nome, nome))
    except Exception:
        pacotes = ["yaml", "requests"]

    print(f"\n  bibliotecas (do requirements.txt):")
    for nome in pacotes:
        try:
            mod = __import__(nome)
            onde = getattr(mod, "__file__", "?") or "?"
            print(f"    {VERDE}ok{FIM}    {nome:10} {CINZA}{onde}{FIM}")
        except Exception as erro:
            print(f"    {VERM}FALTA{FIM} {nome:10} {CINZA}{erro} "
                  f"— rode instalar.bat{FIM}")

    print(f"\n  tarefas agendadas do Windows:")
    if platform.system() != "Windows":
        print(f"    {CINZA}(não é Windows — nada a conferir){FIM}")
    else:
        for tarefa in ("ZionML-Rotina", "ZionML-Vigia"):
            try:
                # SEM text=True: o schtasks escreve na página de código do
                # console, e deixar o Python adivinhar produz "PrÃ³xima
                # ExecuÃ§Ã£o". Rótulo com acento quebrado nunca casa com o
                # que se procura, e o campo aparece como "?" — foi assim que
                # este diagnóstico voltou sem a última e a próxima execução.
                # Passa pelo cmd só para fixar a página de código em UTF-8
                # antes do schtasks falar. Sem isso a saída vem em cp850
                # quando o vigia roda sem console, e os rótulos acentuados
                # chegam ilegíveis — "última" e "próxima" viravam "?".
                r = _sp.run(f'chcp 65001 >nul & schtasks /query /tn "{tarefa}" /fo list /v',
                            shell=True, capture_output=True, timeout=30)
                saida = _decodificar(r.stdout)
                if r.returncode != 0:
                    print(f"    {VERM}ausente{FIM}  {tarefa} "
                          f"{CINZA}— não existe no Agendador. "
                          f"Rode instalar_automacao.bat para recriar.{FIM}")
                    continue
                # O schtasks fala o idioma do Windows, e os rótulos em
                # português não batem com os em inglês. Em vez de listar as
                # traduções uma a uma — que é como este diagnóstico já falhou
                # uma vez —, procura por pedaço do rótulo.
                campos = {}
                for linha in saida.splitlines():
                    if ":" in linha:
                        chave, _, valor = linha.partition(":")
                        # setdefault, não atribuição: o schtasks tem VÁRIAS
                        # linhas começando por "Repetir:" — "A Cada",
                        # "Até: Hora", "Parar Se Ainda Estiver em Execução" —
                        # e todas viram a mesma chave "repetir" ao cortar no
                        # primeiro dois-pontos. Sobrescrevendo, a agenda
                        # aparecia como "parar se ainda estiver em execução".
                        campos.setdefault(_sem_acento(chave.strip().lower()),
                                          valor.strip())

                def campo(*pedacos, padrao="?"):
                    # Percorre na ordem dos PEDAÇOS, não na ordem das linhas:
                    # o schtasks lista "Tipo de Agendamento: Somente uma vez"
                    # antes de "Repetir: A Cada: 1 Hora(s)", e varrer por
                    # linha faria a tarefa horária aparecer como "uma vez".
                    for pedaco in pedacos:
                        for chave, valor in campos.items():
                            if pedaco in chave and valor:
                                return valor
                    return padrao

                # Os pedaços procurados são de propósito trechos SEM acento
                # de dentro da palavra: "Última" pode chegar com o Ú
                # estragado, mas o "ltima" continua lá; o mesmo vale para
                # "xima" em "Próxima" e "result" em "Resultado". Assim a
                # leitura funciona mesmo se a codificação falhar.
                estado = campo("status", "estado")
                proxima = campo("next run", "xima")
                ultima = campo("last run", "ltima")
                resultado = campo("last result", "result")
                # "Repetir: A Cada:  1 Hora(s)" tem dois-pontos no meio do
                # próprio rótulo, então a chave que sobra é só "repetir" e o
                # resto vem junto no valor. Procurar pelo rótulo inteiro não
                # acha nada.
                # Último recurso, se até os pedaços falharem: datas têm
                # formato fixo e são ASCII. A que está no futuro é a próxima.
                if ultima == "?" or proxima == "?":
                    agora_local = datetime.now()
                    achadas = []
                    for valor in campos.values():
                        m = re.match(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2})",
                                     valor.strip())
                        if not m:
                            continue
                        d, mes, ano, hora, minuto = (int(x) for x in m.groups())
                        try:                       # dd/mm no Brasil, mm/dd nos EUA
                            quando = datetime(ano, mes, d, hora, minuto)
                        except ValueError:
                            try:
                                quando = datetime(ano, d, mes, hora, minuto)
                            except ValueError:
                                continue
                        achadas.append((quando, valor.strip()))
                    futuras = [x for x in achadas if x[0] > agora_local]
                    passadas = [x for x in achadas if x[0] <= agora_local]
                    if proxima == "?" and futuras:
                        proxima = min(futuras)[1]
                    if ultima == "?" and passadas:
                        ultima = max(passadas)[1]

                agenda = campo("repetir", "repeat", "tipo de agendamento",
                               "schedule type", padrao="")
                agenda = re.sub(r"^(a cada|every)\s*:?\s*", "", agenda,
                                flags=re.IGNORECASE).strip()
                print(f"    {tarefa}")
                print(f"      estado ....... {estado}")
                if ultima.startswith("30/11/1999") or ultima.startswith("11/30/1999"):
                    print(f"      última ....... {AMAR}nunca executou{FIM} "
                          f"{CINZA}(tarefa recém-criada conta como nunca){FIM}")
                else:
                    print(f"      última ....... {ultima}  →  {_resultado_tarefa(resultado)}")
                print(f"      próxima ...... {proxima}")
                if agenda:
                    print(f"      agenda ....... {agenda}")
            except Exception as erro:
                print(f"    {VERM}erro ao consultar {tarefa}: {str(erro)[:70]}{FIM}")

        import os
        inicializar = Path(os.environ.get("APPDATA", "")) / (
            "Microsoft/Windows/Start Menu/Programs/Startup/zion-ml-vigia.bat")
        if inicializar.exists():
            print(f"    {VERDE}ok{FIM}       atalho na pasta de Inicialização do Windows")
            print(f"      {CINZA}(sobe o vigia no logon sem depender do Agendador){FIM}")

    print(f"\n  sinais de vida:")
    for nome, caminho in (("batimento do vigia", raiz / "data" / "vigia.batimento"),
                          ("subida do vigia", raiz / "data" / "vigia.subiu"),
                          ("log da rotina", raiz / "data" / "rotina.log")):
        if not caminho.exists():
            print(f"    {AMAR}ausente{FIM}  {nome}")
            continue
        idade = datetime.now(timezone.utc).timestamp() - caminho.stat().st_mtime
        unidade = f"{idade/3600:.1f}h" if idade > 3600 else f"{int(idade/60)}min"
        cor_ = VERDE if idade < 3600 else AMAR
        print(f"    {cor_}{unidade:>7}{FIM}  {nome}")

    print()
    return 0


def cmd_compactar(args) -> int:
    """
    Condensa o histórico velho: guarda a curva, descarta o minuto a minuto.

    Roda sozinho de madrugada. Este comando existe para quando você quiser
    antecipar, mudar a janela, ou só ver quanto tem para condensar sem mexer
    em nada (--simular).
    """
    con = db.conectar()
    r = manutencao.compactar(con, dias=args.dias, simular=args.simular)
    total = r["anuncios"] + r["concorrentes"]

    print()
    print(f"  janela detalhada ..... últimos {r['dias']} dias")
    print(f"  corte ................ {r['corte'][:10]}")
    print(f"  leituras anteriores .. {total}"
          f" ({r['anuncios']} próprias, {r['concorrentes']} de concorrentes)")

    if not total:
        print(f"\n  {VERDE}Nada a condensar — o histórico ainda cabe inteiro.{FIM}\n")
        con.close()
        return 0

    if args.simular:
        print(f"\n  {AMAR}Simulação: nada foi alterado.{FIM}")
        print(f"  {CINZA}Rode sem --simular para condensar de verdade.{FIM}\n")
        con.close()
        return 0

    print(f"  linhas de resumo ..... {r['linhas_de_resumo']}")
    print(f"\n  {CINZA}recuperando espaço em disco…{FIM}")
    manutencao.recuperar_espaco(con)
    con.close()
    print(f"  {VERDE}Pronto. A curva de preço, vendas e status continua inteira;")
    print(f"  o que saiu foi a leitura de 5 em 5 minutos daquele período.{FIM}\n")
    return 0


def _painel_de_custos(con) -> int:
    """Cobertura de custo de TODAS as contas, numa tela só."""
    from core.precificacao import IDADE_MAXIMA_DIAS, panorama
    contas = resolver_contas(None, exigir_credencial=False)
    print(f"\n  {'conta':<28} {'ativos':>7} {'c/ custo':>9} {'planilha':>10} "
          f"{'abaixo':>7}  situação")
    print(f"  {'-' * 78}")
    sem_planilha = 0
    for conta in contas:
        p_ = panorama(con, conta)
        idade = p_["idade"]
        if not p_["planilha"]:
            sem_planilha += 1
            print(f"  {truncar(str(conta.cliente_nome), 26):<28} {p_['ativos']:>7} "
                  f"{'—':>9} {'—':>10} {'—':>7}  {AMAR}sem planilha{FIM}")
            continue
        if p_["erro"]:
            print(f"  {truncar(str(conta.cliente_nome), 26):<28} {p_['ativos']:>7} "
                  f"{'—':>9} {str(idade)+'d':>10} {'—':>7}  {VERM}{p_['erro'][:28]}{FIM}")
            continue

        cobertura = f"{p_['com_custo']}/{p_['ativos']}"
        if p_["com_custo"] < p_["ativos"]:
            situacao = f"{AMAR}faltam {p_['ativos'] - p_['com_custo']}{FIM}"
        elif idade is not None and idade > IDADE_MAXIMA_DIAS:
            situacao = f"{VERM}planilha vencida{FIM}"
        else:
            situacao = f"{VERDE}completa{FIM}"
        cor_idade = VERM if (idade or 0) > IDADE_MAXIMA_DIAS else CINZA
        print(f"  {truncar(str(conta.cliente_nome), 26):<28} {p_['ativos']:>7} "
              f"{cobertura:>9} {cor_idade}{str(idade)+'d':>10}{FIM} "
              f"{p_['abaixo_do_piso']:>7}  {situacao}")

    print(f"\n  {CINZA}'abaixo' = anúncios vendendo abaixo do piso de margem hoje.")
    print(f"  Planilha com mais de {IDADE_MAXIMA_DIAS} dias é tratada como vencida: custo")
    print(f"  velho não deixa o alerta mudo, deixa ERRADO com ar de certeza.{FIM}")
    if sem_planilha:
        print(f"\n  {CINZA}Para pedir os custos de uma conta, gere a lista pronta:{FIM}")
        print(f"    python cli.py precos SLUG --modelo\n")
    else:
        print()
    return 0


def cmd_precos(args) -> int:
    """
    Confere a planilha de custo e mostra o piso de cada anúncio.

    Serve para duas coisas: validar a planilha antes de confiar nela — dizendo
    o que casou, o que sobrou e o que ficou de fora — e responder a pergunta
    que motiva tudo isto, que é até onde dá para descer o preço.
    """
    if (args.alvo or "").lower() == "todas":
        con = db.conectar()
        codigo = _painel_de_custos(con)
        con.close()
        return codigo

    conta = obter_conta(args.alvo)
    caminho = precificacao.caminho_da_planilha(conta)

    if args.modelo:
        from pathlib import Path as _P
        destino = conta.dir / "custos-para-preencher.csv"
        con = db.conectar()
        n = precificacao.modelo_para_o_cliente(con, conta, destino)
        con.close()
        if not n:
            print(f"\n{VERDE}Todos os anúncios ativos já têm custo cadastrado.{FIM}\n")
            return 0
        print(f"\n{VERDE}Lista gerada com {n} anúncio(s) sem custo:{FIM}")
        print(f"  {destino}")
        print(f"\n{CINZA}Mande esse arquivo para o cliente. Ele preenche só a coluna")
        print(f"'custo' — o MLB e o título já vão prontos, então o casamento é exato")
        print(f"e nenhuma linha sobra. Quando voltar, salve como {FIM}custos.csv{CINZA}")
        print(f"na mesma pasta e rode {FIM}python cli.py precos {conta.slug}{CINZA}.{FIM}\n")
        return 0

    if not caminho:
        print(f"\n{AMAR}Nenhuma planilha de custo nesta conta.{FIM}")
        print(f"{CINZA}Coloque um arquivo chamado {FIM}custos.csv{CINZA} (ou .xlsx) em:{FIM}")
        print(f"  {conta.dir}")
        print(f"\n{CINZA}Colunas mínimas: uma que identifique o anúncio")
        print(f"(item_id, MLB, SKU ou titulo) e uma de custo. Opcionais:")
        print(f"embalagem, frete, imposto, outros.{FIM}\n")
        return 1

    itens, avisos = precificacao.ler_planilha(caminho)
    print(f"\n  planilha .............. {caminho.name}")
    for aviso in avisos:
        print(f"  {CINZA}{aviso}{FIM}")
    if not itens:
        print(f"\n{VERM}Não consegui usar nenhuma linha.{FIM}\n")
        return 1
    print(f"  linhas com custo ...... {len(itens)}")

    con = db.conectar()
    ultimo = db.ultima_coleta(con, "snap_anuncio", conta.slug)
    if not ultimo:
        con.close()
        print(f"\n{AMAR}Sem coleta ainda. Rode coletar antes.{FIM}\n")
        return 1
    anuncios = con.execute(
        "SELECT * FROM snap_anuncio WHERE conta_slug = ? AND coletado_em = ?",
        (conta.slug, ultimo)).fetchall()
    _, sobras = precificacao.casar_com_anuncios(itens, anuncios)
    resultado = precificacao.calcular(con, conta, itens)
    con.close()

    idade = precificacao.idade_da_planilha(caminho)
    if idade is not None:
        cor_ = VERM if idade > precificacao.IDADE_MAXIMA_DIAS else CINZA
        print(f"  atualizada há ........ {cor_}{idade} dia(s){FIM}")
        if idade > precificacao.IDADE_MAXIMA_DIAS:
            print(f"  {VERM}Planilha vencida. Custo velho não deixa o alerta mudo —")
            print(f"  deixa ERRADO, com o mesmo ar de certeza.{FIM}")

    margem = float((conta.parametros or {}).get("margem_minima_percentual", 0))
    print(f"  anúncios com custo .... {len(resultado)} de {len(anuncios)}")
    print(f"  margem mínima ......... {margem:.0f}%")

    medidos = [r for r in resultado if r.get("origem_comissao") == "medida"]
    supostos = [r for r in resultado if r.get("origem_comissao") != "medida"]
    if medidos:
        faixa = f"{min(r['comissao'] for r in medidos):.1%} a {max(r['comissao'] for r in medidos):.1%}"
        print(f"  comissão do ML ........ {VERDE}medida em {len(medidos)} anúncio(s), "
              f"{faixa}{FIM}")
    if supostos:
        print(f"  {AMAR}{len(supostos)} anúncio(s) ainda usam a comissão aproximada do "
              f"conta.yaml.{FIM}")
        print(f"  {CINZA}Rode {FIM}python cli.py tarifas {conta.slug}{CINZA} para medir "
              f"a real.{FIM}")
    if not margem:
        print(f"  {AMAR}margem_minima_percentual está zerada em conta.yaml — "
              f"o piso vai sair igual ao empate{FIM}")

    if resultado:
        print(f"\n  {'anúncio':<38} {'preço':>11} {'piso':>11} {'folga':>8}")
        print(f"  {'-' * 70}")
        for r in sorted(resultado, key=lambda x: (x["folga_pct"] is None, x["folga_pct"] or 0)):
            cor_ = VERM if r["abaixo_do_piso"] else (AMAR if (r["folga_pct"] or 99) < 5 else VERDE)
            folga = f"{r['folga_pct']:+.1f}%" if r["folga_pct"] is not None else "—"
            print(f"  {truncar(r['titulo'], 36):<38} {brl(r['preco']):>11} "
                  f"{brl(r['piso']):>11} {cor_}{folga:>8}{FIM}")

        apertados = [r for r in resultado if r["abaixo_do_piso"]]
        if apertados:
            print(f"\n  {VERM}{len(apertados)} anúncio(s) já estão abaixo do piso "
                  f"hoje — vendendo com margem menor que a combinada.{FIM}")

    if sobras:
        print(f"\n  {AMAR}{len(sobras)} linha(s) da planilha não casaram com nenhum "
              f"anúncio:{FIM}")
        for s_ in sobras[:8]:
            print(f"    {CINZA}{truncar(s_['identificador'], 60)}{FIM}")
        if len(sobras) > 8:
            print(f"    {CINZA}… e mais {len(sobras) - 8}{FIM}")
        print(f"  {CINZA}Casa por MLB, por título igual ou por título parecido. "
              f"O jeito mais seguro é pôr o MLB na planilha.{FIM}")

    sem_custo = len(anuncios) - len(resultado)
    if sem_custo:
        print(f"\n  {CINZA}{sem_custo} anúncio(s) da conta continuam sem custo "
              f"cadastrado — para esses, o alerta de preço segue sem veredito.{FIM}")
    print()
    return 0


def cmd_tarifas(args) -> int:
    """
    Pergunta ao Mercado Livre quanto ele cobra de cada anúncio.

    Serve para conferir o número que está em conta.yaml. A comissão ali é uma
    aproximação por tipo de anúncio; a real varia por categoria e ainda tem
    parcela fixa. Enquanto os dois não baterem, todo piso de preço calculado
    por este sistema está errado — e errado para menos, que é o lado ruim.
    """
    conta = obter_conta(args.alvo)
    con = db.conectar()
    cli = _cli_para(conta)

    print(f"\n{CINZA}perguntando a tarifa de cada anúncio ao Mercado Livre…{FIM}")
    linhas, carimbo = tarifas.levantar(con, conta, cli)
    con.close()

    if not carimbo:
        print(f"\n{AMAR}Sem coleta ainda. Rode coletar antes.{FIM}\n")
        return 1
    if not linhas:
        print(f"\n{AMAR}Nenhum anúncio ativo com categoria e tipo conhecidos.{FIM}\n")
        return 1

    sem_resposta = [l for l in linhas if l["taxa_reais"] is None]
    ok = [l for l in linhas if l["taxa_reais"] is not None]

    print(f"  anúncios consultados .. {len(linhas)}")
    print(f"  coleta de referência .. {para_br(carimbo)}")

    if ok:
        print(f"\n  {'anúncio':<34} {'preço':>10} {'tipo':<14} "
              f"{'taxa':>10} {'%':>7} {'fixa':>8} {'supunha':>8}")
        print(f"  {'-' * 98}")
        for l in sorted(ok, key=lambda x: -(x["taxa_pct"] or 0)):
            sup = f"{l['suposta_pct']:.0f}%" if l["suposta_pct"] is not None else "—"
            # vermelho quando o real supera o que o conta.yaml supunha
            pior = (l["suposta_pct"] is not None
                    and l["taxa_pct"] is not None
                    and l["taxa_pct"] > l["suposta_pct"] + 0.5)
            cor_ = VERM if pior else VERDE
            # A taxa fixa por unidade existe em faixa de preço baixo. Precisa
            # aparecer: somada ao percentual, é ela que decide item barato.
            fixa = l.get("fixa_reais")
            fixa_txt = brl(fixa) if fixa else "—"
            print(f"  {truncar(l['titulo'], 32):<34} {brl(l['preco']):>10} "
                  f"{humano.tipo_anuncio(l['tipo']):<14} {brl(l['taxa_reais']):>10} "
                  f"{cor_}{l['taxa_pct']:>6.1f}%{FIM} {CINZA}{fixa_txt:>8} {sup:>8}{FIM}")

        com_fixa = [l for l in ok if l.get("fixa_reais")]
        if com_fixa:
            print(f"\n  {AMAR}{len(com_fixa)} anúncio(s) pagam taxa FIXA por unidade "
                  f"além do percentual.{FIM}")
        else:
            print(f"\n  {CINZA}Nenhum anúncio paga taxa fixa por unidade — todos estão "
                  f"acima da faixa de preço em que ela incide.{FIM}")

        m = tarifas.media_ponderada(ok)
        print()
        if m["por_venda_pct"] is not None:
            print(f"  taxa média por real vendido ... {VERDE}{m['por_venda_pct']:.1f}%{FIM}"
                  f"  {CINZA}({m['vendas_consideradas']} vendas de histórico){FIM}")
        if m["por_anuncio_pct"] is not None:
            print(f"  faixa entre anúncios ......... {m['menor_pct']:.1f}% a "
                  f"{m['maior_pct']:.1f}%")

        divergentes = [l for l in ok if l["suposta_pct"] is not None
                       and l["taxa_pct"] is not None
                       and abs(l["taxa_pct"] - l["suposta_pct"]) > 0.5]
        if divergentes:
            print(f"\n  {AMAR}{len(divergentes)} anúncio(s) pagam taxa diferente da "
                  f"que está em conta.yaml.{FIM}")
            print(f"  {CINZA}Enquanto isso não for corrigido, o piso desses anúncios "
                  f"sai errado.{FIM}")
        else:
            print(f"\n  {VERDE}A comissão em conta.yaml bate com o que o ML cobra.{FIM}")

        com_frete = [l for l in ok if l["frete_gratis"]]
        if com_frete:
            print(f"\n  {AMAR}{len(com_frete)} anúncio(s) têm frete grátis — e o custo "
                  f"desse frete NÃO está nesta tabela.{FIM}")
            print(f"  {CINZA}A taxa acima é só a comissão. Em item volumoso o frete "
                  f"costuma pesar mais que ela.{FIM}")

    if sem_resposta:
        print(f"\n  {CINZA}{len(sem_resposta)} anúncio(s) sem resposta do ML "
              f"(categoria fora da tabela ou tipo não simulável).{FIM}")
    print()
    return 0


def cmd_promocoes(args) -> int:
    """
    Mostra o que o Mercado Livre está oferecendo para cada anúncio e diz se
    aceitar cabe no piso.

    O ML abre campanha o tempo todo e oferece anúncio por anúncio, com o preço
    já calculado. No aplicativo é um botão de aceitar, sem menção a custo — é
    assim que um anúncio saudável vira prejuízo em dois toques. Aqui a mesma
    oferta aparece com o veredito ao lado.
    """
    conta = obter_conta(args.alvo)
    con = db.conectar()
    carimbo_anuncios = db.ultima_coleta(con, "snap_anuncio", conta.slug)
    if not carimbo_anuncios:
        con.close()
        print(f"\n{AMAR}Sem coleta ainda. Rode coletar antes.{FIM}\n")
        return 1

    anuncios = {l["item_id"]: l for l in con.execute(
        "SELECT * FROM snap_anuncio WHERE conta_slug = ? AND coletado_em = ? "
        "AND status = 'active' ORDER BY vendidos DESC", (conta.slug, carimbo_anuncios))}

    if args.usar_cache:
        carimbo = db.ultima_coleta(con, "snap_promocao", conta.slug)
        if not carimbo:
            con.close()
            print(f"\n{AMAR}Nenhuma coleta de promoção no banco ainda.{FIM}\n")
            return 1
        quantas = 0
    else:
        cli = _cli_para(conta)
        print(f"\n{CINZA}perguntando as campanhas de {len(anuncios)} anúncio(s)…{FIM}")
        quantas, carimbo = promocoes.coletar(con, conta, cli, list(anuncios))

    linhas = con.execute(
        "SELECT * FROM snap_promocao WHERE conta_slug = ? AND coletado_em = ?",
        (conta.slug, carimbo)).fetchall()
    pisos = {r["item_id"]: r for r in precificacao.carregar(con, conta)}
    novas = {f"{l['item_id']}|{l['promocao_id']}|{l['status']}"
             for l in promocoes.novidades(con, conta.slug, carimbo)}
    con.close()

    if not linhas:
        print(f"\n{VERDE}Nenhuma campanha aberta para os anúncios desta conta.{FIM}\n")
        return 0

    liberadas = [l for l in linhas if l["status"] == "candidate"]
    rodando   = [l for l in linhas if l["status"] == "started"]
    print(f"  campanhas liberadas ... {len(liberadas)}")
    print(f"  já rodando ............ {len(rodando)}")
    if novas:
        print(f"  {AMAR}novas desde a última leitura … {len(novas)}{FIM}")

    if liberadas:
        print(f"\n{VERDE}LIBERADAS — o ML está oferecendo, ninguém aceitou ainda{FIM}")
        print(f"  {'anúncio':<30} {'campanha':<24} {'preço':>10} {'piso':>10} "
              f"{'sobra':>10}  quem paga")
        print(f"  {'-' * 100}")
        for l in sorted(liberadas, key=lambda x: (x["preco"] or 9e9)):
            a = anuncios.get(l["item_id"])
            r = pisos.get(l["item_id"])
            v_ = promocoes.veredito(l, r["piso"] if r else None,
                                    r["preco"] if r else None)
            cor_ = VERM if v_["cabe"] is False else (VERDE if v_["cabe"] else CINZA)
            sobra = brl(v_["sobra"]) if v_["sobra"] is not None else "—"
            piso  = brl(r["piso"]) if r and r["piso"] else "—"
            paga = (f"ML {l['parte_do_ml']:.0f}% / você {l['parte_do_vendedor']:.0f}%"
                    if l["parte_do_vendedor"] is not None else "—")
            marca = " ←NOVA" if f"{l['item_id']}|{l['promocao_id']}|{l['status']}" in novas else ""
            titulo = truncar(a["titulo"], 28) if a else l["item_id"]
            print(f"  {titulo:<30} {truncar(l['nome'] or l['tipo'], 22):<24} "
                  f"{brl(v_.get('preco')):>10} {piso:>10} {cor_}{sobra:>10}{FIM}  "
                  f"{CINZA}{paga}{FIM}{AMAR}{marca}{FIM}")

        furam = [l for l in liberadas
                 if promocoes.veredito(l, (pisos.get(l["item_id"]) or {}).get("piso"),
                                       None)["cabe"] is False]
        if furam:
            print(f"\n  {VERM}{len(furam)} campanha(s) colocariam o anúncio abaixo do "
                  f"piso. Aceitar essas é vender com margem menor que a combinada.{FIM}")

    if rodando:
        print(f"\n{CINZA}JÁ RODANDO — é o que explica o preço de vitrine de hoje{FIM}")
        for l in sorted(rodando, key=lambda x: (x["preco"] or 0)):
            a = anuncios.get(l["item_id"])
            titulo = truncar(a["titulo"], 28) if a else l["item_id"]
            fim_ = f" até {l['fim'][:10]}" if l["fim"] else ""
            print(f"  {CINZA}{titulo:<30} {truncar(l['nome'] or l['tipo'], 22):<24} "
                  f"{brl(l['preco']):>10}  de {brl(l['preco_original'])}{fim_}{FIM}")

    relampago = [l for l in liberadas if l["tipo"] == "LIGHTNING" and l["preco_minimo"]]
    if relampago:
        print(f"\n  {AMAR}Atenção às ofertas relâmpago: o ML aceita preço até "
              f"muito abaixo do sugerido.{FIM}")
        for l in relampago[:3]:
            a = anuncios.get(l["item_id"])
            titulo = truncar(a["titulo"], 28) if a else l["item_id"]
            print(f"  {CINZA}{titulo}: sugerido {brl(l['preco_sugerido'])}, "
                  f"mas aceita até {brl(l['preco_minimo'])}{FIM}")
    print()
    return 0


def _janela_do_resumo(r: dict, dias: int) -> str:
    """
    Como descrever o período do resumo, em uma linha.

    Com --desde, a janela é o recorte pedido; sem ele, é o período que a
    coleta realmente cobriu. Dizer "últimos 60 dias" quando a coleta só
    alcançou três já foi a origem de um número 30x maior que o real.
    """
    if r.get("desde"):
        # para_br() trata a string como UTC e converte para BRT — numa data
        # pura ("2026-08-29") isso volta um dia ("28/08"). Aqui a data já é
        # o dia pedido: reordena os pedaços e pronto.
        a, m, d = r["desde"].split("-")
        return f"a partir de {d}/{m}/{a}"
    per = r["periodo"]
    if per["de"]:
        return f"{para_br(per['de'])[:10]} a {para_br(per['ate'])[:10]}"
    return f"últimos {dias} dias"


def _texto_do_resumo_de_cupom(slug: str, r: dict, dias: int) -> str:
    """
    Monta, do MESMO dicionário que a tela usa, o texto que vai para o canal.

    Existe porque o texto curto da página responde "quanto vendeu" e o
    responsável também pergunta "vendeu O QUÊ" — a lista de itens só existia
    na tela. Nada aqui é texto livre: cada linha vem do banco.
    """
    linhas = [f"*Cupom · {humano.nome_da_conta(slug)}*", ""]

    for c in r["campanhas"]:
        beneficio = (f"{c['percentual']:.0f}%" if c["percentual"]
                     else brl(c["valor_fixo"]))
        # O nome sozinho não identifica: a conta pode ter tido outra campanha
        # com o mesmo apelido. O código é o que se procura no painel do ML.
        linhas.append(f"*Cupom: {c['nome']}*")
        linhas.append(f"código no Mercado Livre: {c['promocao_id']}")
        linhas.append(f"desconto de {beneficio} por venda"
                      + (f", compra mínima {brl(c['compra_minima'])}"
                         if c["compra_minima"] else ""))
        if c["fim"]:
            linhas.append(f"vale até {para_br(c['fim'])[:10]}")
        linhas.append(f"o Mercado Livre registra {c['cupons_usados'] or 0} "
                      f"cupom(ns) usado(s) nesta campanha")
        di = None if r.get("desde") else c.get("desde_o_inicio")
        if di and di["pedidos"]:
            linha = (f"nesta campanha (desde {para_br(c['inicio'])[:10]}): "
                     f"{di['pedidos']} vendas, {brl(di['faturamento'])}")
            if di["custo_pct"]:
                linha += f" — custo {brl(di['custo'])} ({di['custo_pct']:.1f}%)"
            linhas.append(linha)
        linhas.append("")

    linhas.append(f"*O QUE ISSO VENDEU* (medido pedido a pedido, "
                  f"{_janela_do_resumo(r, dias)})")
    linhas.append(f"cupons usados: {r.get('cupons', 0)}")
    linhas.append(f"vendas com cupom: {r['pedidos']}")
    linhas.append(f"faturamento: {brl(r['faturamento'])}")
    if r["ticket"]:
        linhas.append(f"ticket médio: {brl(r['ticket'])}")
    custo = f"custo dos cupons: {brl(r['custo'])}"
    if r["custo_sobre_faturamento"]:
        custo += f" ({r['custo_sobre_faturamento']:.1f}% do faturamento)"
    linhas.append(custo)

    rodape = ["", "Faturamento é o valor dos pedidos que usaram cupom — "
                  "não é venda que só aconteceu por causa dele."]

    if not r["produtos"]:
        return "\n".join(linhas + rodape)

    # A lista sai INTEIRA: quem lê quer conferir se o produto dele está ali,
    # e "… e mais 3 produto(s)" era exatamente a linha que não deixava.
    # O único corte é o do Telegram, que recusa mensagem acima de 4096
    # caracteres — aí tiram-se os últimos, que são os de menos venda, e o
    # texto diz quantos ficaram de fora em vez de sumir com eles em silêncio.
    itens = [f"• {truncar(x['titulo'] or x['item_id'], 60)} — "
             f"{x['pedidos']} venda(s), {brl(x['custo'])} em cupom"
             for x in r["produtos"]]
    # Com uma campanha só, o título diz de qual cupom é a lista — sem isso,
    # quem recebe tem de deduzir que é a campanha citada lá em cima.
    de_qual = (f" — {r['campanhas'][0]['nome']}"
               if len(r["campanhas"]) == 1 else "")
    cabeca = linhas + ["", f"*ITENS VENDIDOS COM CUPOM{de_qual}* "
                           f"({len(itens)} produtos)"]

    def montar(quantos: int) -> str:
        corpo = itens[:quantos]
        if quantos < len(itens):
            corpo = corpo + [f"… e mais {len(itens) - quantos} produto(s) com "
                             f"menos vendas (a lista completa está na página)"]
        return "\n".join(cabeca + corpo + rodape)

    texto = montar(len(itens))
    cabem = len(itens)
    while cabem > 1 and len(texto.encode("utf-8")) > 3900:
        cabem -= 1
        texto = montar(cabem)
    return texto


def cmd_cupons(args) -> int:
    """
    Campanhas de cupom do vendedor: quantos foram usados e quanto já custaram.

    Cupom é a campanha que some da vista: não altera o preço do anúncio, o
    desconto só aparece no checkout do comprador, e o orçamento é 100% seu — o
    Mercado Livre não entra com nada, ao contrário da campanha co-participada.
    O jeito de perceber que está caro é olhar o orçamento queimar, e é isso
    que este comando mostra.
    """
    # Ler o banco não exige credencial: conta desligada ainda tem histórico de
    # campanha, e é justamente nela que se quer conferir quanto o cupom custou.
    contas = resolver_contas(args.alvo, exigir_credencial=not args.usar_cache)
    if not contas:
        print(f"\n{AMAR}Nenhuma conta configurada nesse alvo.{FIM}\n")
        return 1

    con = db.conectar()
    algum = False
    vazios = 0

    for conta in contas:
        print(f"\n{conta}")

        if args.pagina or (args.enviar and not args.resumo):
            caminho, dados = relatorio_cupom.gerar(con, conta, dias=args.dias)
            texto = relatorio_cupom.texto_curto(dados)
            print(f"  {VERDE}página gerada:{FIM} {caminho}")
            print(f"  {CINZA}abra no navegador e mande o arquivo, ou copie o texto "
                  f"abaixo:{FIM}\n")
            print("  " + texto.replace("\n", "\n  "))

            if args.enviar and dados.get("vazio"):
                # Um relatório zerado no canal do cliente é pior que nenhum:
                # ele parece resultado. Já saiu um "0 vendas, R$ 0,00" para
                # dois destinos porque este comando enviava sem conferir.
                print(f"\n  {VERM}NÃO ENVIEI: o relatório está zerado "
                      f"({dados['vazio']}).{FIM}")
                print(f"  {AMAR}Um relatório com R$ 0,00 no canal parece "
                      f"resultado, e não é.{FIM}")
                if not dados["pedidos_no_banco"]:
                    print(f"  {CINZA}Rode a coleta de vendas antes:{FIM}")
                    print(f"  {CINZA}  cli.py cupons {conta.slug} --vendas "
                          f"--dias {args.dias} --limite 99999{FIM}")
                print()
                vazios += 1
                continue

            if args.enviar:
                # Manda o MESMO texto que acabou de ser impresso, gerado a
                # partir do banco. Não existe caminho aqui para mensagem
                # livre: o canal é do sistema, não um chat de uso geral.
                cfg = notify.carregar_config()
                r = notify.enviar(f"*Cupom · {humano.nome_da_conta(conta.slug)}*\n\n"
                                  + texto, cfg)
                if r.ok:
                    print(f"\n  {VERDE}enviado por {cfg.get('provedor')}{FIM} "
                          f"{CINZA}{r.detalhe}{FIM}")
                    if (cfg.get("provedor") or "console") == "console":
                        print(f"  {AMAR}Provedor ainda é 'console': saiu só na tela. "
                              f"Troque em config/notificacoes.yaml.{FIM}")
                else:
                    print(f"\n  {VERM}não enviou:{FIM} {r.detalhe}")
            print()
            continue

        if args.resumo:
            # O bloco que o responsável pela conta pede. Nada de campanha de
            # preço, nada de custo por anúncio: só o cupom que ele liberou,
            # quanto vendeu e quanto custou.
            r = cupons.resumo_da_campanha(con, conta.slug, dias=args.dias,
                                          desde=getattr(args, "desde", None))
            if not r["campanhas"] and not r["pedidos"]:
                print(f"  {CINZA}nenhuma campanha de cupom nesta conta.{FIM}")
                continue

            for c in r["campanhas"]:
                beneficio = (f"{c['percentual']:.0f}%" if c["percentual"]
                             else brl(c["valor_fixo"]))
                print(f"\n  {VERDE}CUPOM: {c['nome']}{FIM}  {CINZA}{c['promocao_id']}{FIM}")
                print(f"    desconto de {beneficio} por venda"
                      + (f", compra mínima {brl(c['compra_minima'])}"
                         if c["compra_minima"] else ""))
                if c["fim"]:
                    print(f"    vale até {para_br(c['fim'])[:10]}")
                print(f"    o Mercado Livre registra {c['cupons_usados'] or 0} "
                      f"cupom(ns) usado(s) nesta campanha")
                di = None if r.get("desde") else c.get("desde_o_inicio")
                if di and di["pedidos"]:
                    print(f"    {VERDE}nesta campanha (desde {para_br(c['inicio'])[:10]}): "
                          f"{di['pedidos']} vendas, {brl(di['faturamento'])}{FIM}"
                          + (f"  {CINZA}custo {brl(di['custo'])}"
                             f" ({di['custo_pct']:.1f}%){FIM}" if di["custo_pct"] else ""))

            janela = _janela_do_resumo(r, args.dias)
            print(f"\n  {VERDE}O QUE ISSO VENDEU{FIM}  {CINZA}(medido pedido a "
                  f"pedido, {janela}){FIM}")
            print(f"    {VERDE}cupons usados ....... {r.get('cupons', 0)}{FIM}")
            print(f"    vendas com cupom .... {r['pedidos']}")
            print(f"    {VERDE}faturamento ......... {brl(r['faturamento'])}{FIM}")
            if r["ticket"]:
                print(f"    ticket médio ........ {brl(r['ticket'])}")
            print(f"    custo dos cupons .... {brl(r['custo'])}"
                  + (f"  ({r['custo_sobre_faturamento']:.1f}% do faturamento)"
                     if r["custo_sobre_faturamento"] else ""))

            if r["produtos"]:
                print(f"\n  {'produto':<46} {'vendas':>7} {'custo':>11}")
                print(f"  {'-' * 66}")
                for x in r["produtos"]:
                    titulo = truncar(x["titulo"] or x["item_id"], 44)
                    print(f"  {titulo:<46} {x['pedidos']:>7} {brl(x['custo']):>11}")
                print(f"  {'-' * 66}")
                print(f"  {len(r['produtos'])} produto(s)")

            print()
            if args.desde:
                print(f"  {CINZA}O número do ML conta a campanha inteira; o "
                      f"medido aqui começa")
                print(f"  na data pedida — por isso podem não bater.{FIM}")
            else:
                print(f"  {CINZA}Os dois números de uso não batem por natureza: "
                      f"o do ML é")
                print(f"  desta campanha, e o medido na janela pode incluir "
                      f"campanha")
                print(f"  anterior — por isso a linha 'nesta campanha' existe.{FIM}")
            print(f"  {CINZA}Faturamento é o valor dos pedidos que usaram cupom "
                  f"— não é")
            print(f"  venda que só aconteceu por causa dele.{FIM}\n")

            if args.enviar:
                # Mesma trava do outro caminho: relatório zerado no canal do
                # cliente parece resultado, e não é.
                if not r["pedidos"]:
                    print(f"  {VERM}NÃO ENVIEI: nenhuma venda com cupom na "
                          f"janela.{FIM}")
                    print(f"  {CINZA}Rode a coleta antes:  cli.py cupons "
                          f"{conta.slug} --vendas --dias {args.dias} "
                          f"--limite 99999{FIM}\n")
                    vazios += 1
                    continue
                cfg = notify.carregar_config()
                envio = notify.enviar(
                    _texto_do_resumo_de_cupom(conta.slug, r, args.dias), cfg)
                if envio.ok:
                    print(f"  {VERDE}enviado por {cfg.get('provedor')}{FIM} "
                          f"{CINZA}{envio.detalhe}{FIM}\n")
                    if (cfg.get("provedor") or "console") == "console":
                        print(f"  {AMAR}Provedor ainda é 'console': saiu só na "
                              f"tela. Troque em config/notificacoes.yaml.{FIM}")
                else:
                    print(f"  {VERM}não enviou:{FIM} {envio.detalhe}\n")
            continue

        if args.vendas:
            cli = _cli_para(conta)
            if args.refazer:
                print(f"  {CINZA}vou reler do zero — o histórico só é apagado "
                      f"depois que os pedidos chegarem{FIM}")
            print(f"  {CINZA}lendo os pedidos dos últimos {args.dias} dias…{FIM}")
            r = cupons.coletar_vendas(con, conta, cli, dias=args.dias,
                                      limite_pedidos=args.limite,
                                      refazer=args.refazer)
            print(f"  pedidos lidos ....... {r['pedidos_lidos']} "
                  f"({r['pedidos_sem_cupom']} sem desconto, "
                  f"{r['pedidos_consultados']} consultados)")
            cob = cupons.periodo_coberto(con, conta.slug)
            if cob["de"]:
                span = (f"{para_br(cob['de'])[:10]} a {para_br(cob['ate'])[:10]}"
                        if cob["ate"] else "?")
                aviso = ""
                if cob["dias"] is not None and cob["dias"] < args.dias * 0.8:
                    aviso = (f"  {VERM}<- pediu {args.dias} dias, tem "
                             f"{cob['dias']:.0f}{FIM}")
                print(f"  período coberto ..... {span}{aviso}")
            if r.get("truncou_na_api"):
                print(f"  {VERM}O Mercado Livre não pagina além de 1000 pedidos por "
                      f"fatia e uma fatia de 1 dia estourou isso.{FIM}")
            if r["cortou"]:
                print(f"  {AMAR}ATENÇÃO: a janela tem {r['pedidos_na_janela']} pedidos e "
                      f"eu li os {r['pedidos_lidos']} mais recentes.{FIM}")
                print(f"  {AMAR}O total abaixo é PISO, não fechamento. "
                      f"Use --limite {min(r['pedidos_na_janela'], 1000)}.{FIM}")
            print(f"  linhas novas ........ {r['linhas_novas']}")

            resumo = cupons.resumo_de_custo(con, conta.slug, dias=args.dias)
            if not resumo["pedidos_com_cupom"]:
                print(f"  {CINZA}nenhuma venda com cupom nesta janela.{FIM}")
                continue

            # Não é "custo de cupom": o mesmo endpoint devolve cupom E
            # desconto de campanha de preço, e os dois podem ser bancados pelo
            # vendedor. O rótulo honesto é o que aparece para o comprador —
            # desconto no checkout — e a quebra abaixo diz de onde veio.
            print(f"\n  {VERDE}DESCONTO NO CHECKOUT — últimos {args.dias} dias{FIM}")
            print(f"    pedidos com desconto  {resumo['pedidos_com_cupom']}")
            print(f"    {AMAR}saiu do seu bolso ... {brl(resumo['custo_do_vendedor'])}{FIM}")
            print(f"    {CINZA}bancado pelo ML ..... {brl(resumo['bancado_pelo_ml'])}{FIM}")
            print(f"    {CINZA}desconto total ...... {brl(resumo['desconto_total'])}{FIM}")

            imp = cupons.impacto_do_cupom(con, conta.slug, dias=args.dias)
            if imp["pedidos_total"]:
                print(f"\n  {VERDE}O QUE PASSOU PELO CUPOM — {args.dias} dias{FIM}")
                print(f"    vendas com cupom .... {imp['pedidos_com_cupom']} de "
                      f"{imp['pedidos_total']} pedidos"
                      + (f"  ({imp['share_pedidos']:.1f}%)" if imp["share_pedidos"] else ""))
                print(f"    receita dessas ...... {brl(imp['receita_com_cupom'])} de "
                      f"{brl(imp['receita_total'])}"
                      + (f"  ({imp['share_receita']:.1f}%)" if imp["share_receita"] else ""))
                if imp["ticket_com"] and imp["ticket_sem"]:
                    dif = imp["ticket_com"] - imp["ticket_sem"]
                    seta = "acima" if dif >= 0 else "abaixo"
                    print(f"    ticket médio ........ {brl(imp['ticket_com'])} com cupom, "
                          f"{brl(imp['ticket_sem'])} sem "
                          f"{CINZA}({brl(abs(dif))} {seta}){FIM}")
                print(f"    custo do cupom ...... {brl(imp['custo_do_cupom'])}"
                      + (f"  ({imp['custo_sobre_receita_com']:.1f}% da receita que ele "
                         f"acompanhou)" if imp["custo_sobre_receita_com"] else ""))

                campanha = next((c for c in cupons.ultima(con, conta.slug)
                                 if c["status"] in cupons.VIVAS and c["inicio"]), None)
                if campanha:
                    ad = cupons.antes_e_depois(con, conta.slug, campanha["inicio"])
                    if ad and ad["incompleto"]:
                        print(f"    {CINZA}antes x durante: não dá para comparar — a "
                              f"coleta não cobre o período anterior à campanha.{FIM}")
                    elif ad and ad["antes"]["por_dia"] and ad["depois"]["por_dia"]:
                        a, d = ad["antes"]["por_dia"], ad["depois"]["por_dia"]
                        var = (d - a) / a * 100
                        print(f"    {CINZA}antes da campanha ... {brl(a)}/dia "
                              f"({ad['antes']['pedidos']} pedidos){FIM}")
                        # Campanha de três dias contra trinta não sustenta uma
                        # variação: um fim de semana, uma ruptura de estoque ou
                        # um feriado mexem mais nesse número que o cupom. Com
                        # pouca campanha rodada, mostra o ritmo e cala a %.
                        curto = (ad["depois"]["dias_corridos"] or 0) < 7
                        marca = "" if curto else f"  {var:+.0f}%"
                        print(f"    {CINZA}durante ............. {brl(d)}/dia "
                              f"({ad['depois']['pedidos']} pedidos){marca}{FIM}")
                        if curto:
                            print(f"    {CINZA}  (campanha com "
                                  f"{ad['depois']['dias_corridos']:.0f} dia(s) — cedo "
                                  f"demais para comparar com o período anterior){FIM}")

                print(f"  {CINZA}Isto é venda COM cupom, não venda CAUSADA pelo cupom:")
                print(f"  parte dessas pessoas compraria de qualquer jeito.{FIM}")

            tipos = cupons.por_tipo(con, conta.slug, dias=args.dias)
            if len(tipos) > 1 or (tipos and tipos[0]["tipo"] != "?"):
                rotulo = {"coupon": "cupom", "discount": "campanha de preço"}
                print(f"\n  {VERDE}CUPOM x CAMPANHA DE PREÇO{FIM}")
                for x in tipos:
                    print(f"    {rotulo.get(x['tipo'], x['tipo']):<20} "
                          f"{brl(x['do_vendedor']):>12} do seu bolso  "
                          f"{CINZA}({x['pedidos']} pedido(s), "
                          f"{x['campanhas']} campanha(s)){FIM}")

            campanhas = cupons.por_campanha(con, conta.slug, dias=args.dias)
            # As campanhas do próprio ML entram todas com custo zero para você
            # e são dezenas. Listadas uma a uma, empurram para fora da tela
            # justamente as que custam dinheiro.
            de_graca = [c for c in campanhas if not (c["do_vendedor"] or 0)]
            campanhas = [c for c in campanhas if (c["do_vendedor"] or 0) > 0]
            if campanhas:
                print(f"\n  {VERDE}DE ONDE VEM ESSE DESCONTO{FIM}")
                print(f"    {'tipo':<10} {'campanha':<22} {'pedidos':>8} "
                      f"{'seu custo':>12}  faixa por linha")
                print(f"    {'-' * 78}")
                for c in campanhas:
                    marca = c["campanha_do_ml"] or c["campanha_id"] or "—"
                    faixa = (f"{brl(c['menor'])} a {brl(c['maior'])}"
                             if c["menor"] is not None else "—")
                    print(f"    {c['tipo']:<10} {truncar(marca, 20):<22} "
                          f"{c['pedidos']:>8} {brl(c['do_vendedor']):>12}  "
                          f"{CINZA}{faixa}{FIM}")
                if de_graca:
                    bancado = sum(c["total"] or 0 for c in de_graca)
                    print(f"    {CINZA}{'—':<10} {len(de_graca)} campanha(s) do "
                          f"próprio ML: {brl(bancado)} que NÃO saiu de você{FIM}")

            linhas = cupons.custo_por_anuncio(con, conta.slug, dias=args.dias)
            pagos = [l for l in linhas if (l["custo_vendedor"] or 0) > 0]
            if pagos:
                print(f"\n  {'anúncio':<38} {'unid.':>6} {'seu custo':>11} "
                      f"{'por unid.':>10} {'preço hoje':>11} {'% do cheio':>11}")
                print(f"  {'-' * 92}")
                for l in pagos[:20]:
                    titulo = truncar(l["titulo"] or l["item_id"], 36)
                    pct = l["pct_do_cheio"]
                    marca = VERM if (pct or 0) >= 30 else (AMAR if (pct or 0) >= 15 else "")
                    preco = l["preco_vitrine"] or l["preco"]
                    print(f"  {titulo:<38} {l['unidades'] or 0:>6} "
                          f"{brl(l['custo_vendedor']):>11} {brl(l['por_unidade']):>10} "
                          f"{CINZA}{brl(preco):>11}{FIM} "
                          f"{marca}{(f'{pct:.0f}%' if pct is not None else '—'):>11}{FIM}")
                print(f"  {CINZA}'% do cheio' é estimativa: o preço de hoje já vem com a")
                print(f"  campanha aplicada, então o cheio é ele mais o desconto.{FIM}")
                if len(pagos) > 20:
                    print(f"  {CINZA}… e mais {len(pagos) - 20}{FIM}")
            else:
                print(f"\n  {CINZA}Nenhum cupom desta janela saiu do seu bolso: todos os")
                print(f"  descontos encontrados foram bancados pelo Mercado Livre.{FIM}")
            continue

        if args.sondar_vendas:
            cli = _cli_para(conta)
            print(f"  {CINZA}procurando cupom nos pedidos dos últimos "
                  f"{args.dias} dias…{FIM}")
            r = cupons.sondar_vendas(cli, dias=args.dias)
            print(f"  pedidos examinados … {r['pedidos_examinados']}")
            campos = r["campos_com_cupom_no_payload"]
            if isinstance(campos, dict) and campos:
                print(f"  {VERDE}campos de cupom no /orders/search:{FIM}")
                for caminho, vezes in sorted(campos.items()):
                    print(f"    {caminho}  ({vezes}x)")
            else:
                print(f"  {CINZA}{campos}{FIM}")
            for p in r["pedidos_com_valor_de_cupom"][:5]:
                print(f"  {VERDE}pedido {p['order_id']}{FIM} "
                      f"{(p['data'] or '')[:10]} total {brl(p['total'])}")
                print(f"    anúncios: {', '.join(str(i) for i in p['itens'])}")
                for caminho, valor in p["campos"].items():
                    print(f"    {caminho} = {valor}")
            exemplo = r.get("exemplo_orders_discounts")
            if exemplo:
                print(f"  {CINZA}exemplo de /orders/$ID/discounts:{FIM}")
                print(f"    {str(exemplo)[:600]}")
            print(f"  {AMAR}{r['conclusao']}{FIM}")
            continue

        if args.usar_cache:
            linhas = cupons.ultima(con, conta.slug)
            if not linhas:
                print(f"  {CINZA}nenhuma coleta de cupom no banco ainda.{FIM}")
                continue
        else:
            cli = _cli_para(conta)
            quantas, quantos_itens, _, aviso = cupons.coletar(con, conta, cli)
            if aviso:
                print(f"  {VERM}{aviso}{FIM}")
                continue
            if not quantas:
                print(f"  {CINZA}nenhuma campanha de cupom nesta conta.{FIM}")
                continue
            print(f"  {CINZA}{quantas} campanha(s), {quantos_itens} anúncio(s) "
                  f"participando{FIM}")
            linhas = cupons.ultima(con, conta.slug)

        vivas = [l for l in linhas if l["status"] in cupons.VIVAS]
        encerradas = [l for l in linhas if l["status"] not in cupons.VIVAS]
        movimento = cupons.movimento(con, conta.slug, horas=args.horas)
        algum = True

        for l in vivas:
            c = cupons.consumo(l)
            beneficio = (f"{l['percentual']:.0f}%" if l["percentual"]
                         else brl(l["valor_fixo"]))
            codigo = l["codigo"] or "aberto a todos"
            pct = c["gasto_pct"]
            cor_ = VERM if (pct or 0) >= 80 else (AMAR if (pct or 0) >= 50 else VERDE)

            print(f"\n  {VERDE}{l['nome']}{FIM}  {CINZA}{l['promocao_id']} · "
                  f"{l['status']}{FIM}")
            print(f"    desconto ............ {beneficio} "
                  f"(mínimo de compra {brl(l['compra_minima'])})")
            print(f"    código .............. {codigo}")
            print(f"    cupons usados ....... {l['cupons_usados'] or 0}")
            if c["gasto"] is not None:
                print(f"    orçamento ........... {cor_}{brl(c['gasto'])} de "
                      f"{brl(l['orcamento'])}  ({pct:.0f}% queimado){FIM}")
            if c["custo_medio"]:
                print(f"    custo por cupom ..... {brl(c['custo_medio'])}")
            if l["fim"]:
                print(f"    vale até ............ {l['fim'][:10]}")

            mov = movimento.get(l["promocao_id"])
            if mov and (mov["novos_usos"] or mov["orcamento_queimado"]):
                # Uso NEGATIVO não é defeito de conta: é venda cancelada, e o
                # Mercado Livre devolve o valor ao orçamento da campanha.
                # Imprimir "-1 uso(s), R$ -20,00" faz parecer bug do sistema.
                usos, valor = mov["novos_usos"], mov["orcamento_queimado"]
                if (usos or 0) < 0 or (valor or 0) < 0:
                    devolvido = (f", {brl(abs(valor))} voltaram ao orçamento"
                                 if valor else "")
                    print(f"    {CINZA}nas últimas {args.horas}h: "
                          f"{abs(usos or 0)} uso(s) devolvido(s) — venda "
                          f"cancelada{devolvido}{FIM}")
                else:
                    queimou = f", {brl(valor)} de orçamento" if valor else ""
                    print(f"    {AMAR}nas últimas {args.horas}h: "
                          f"{usos} uso(s){queimou}{FIM}")

            participantes = cupons.anuncios_da_campanha(con, conta.slug, l["promocao_id"])
            ativos = [p for p in participantes if p["status"] in ("started", "pending")]
            if participantes:
                print(f"    anúncios ............ {len(ativos)} ativo(s) de "
                      f"{len(participantes)} indicado(s)")
                for p in ativos[:5]:
                    titulo = truncar(p["titulo"] or p["item_id"], 42)
                    print(f"      {CINZA}{titulo:<44} {brl(p['preco_vitrine'] or p['preco'])}{FIM}")
                if len(ativos) > 5:
                    print(f"      {CINZA}… e mais {len(ativos) - 5}{FIM}")

        if encerradas:
            print(f"\n  {CINZA}encerradas: " + ", ".join(
                f"{e['nome']} ({e['cupons_usados'] or 0} usos)" for e in encerradas[:6])
                + f"{FIM}")

    con.close()

    if algum:
        print(f"\n  {CINZA}O orçamento de cupom sai inteiro do seu bolso: o Mercado "
              f"Livre não co-participa neste tipo de campanha.{FIM}")
    print()
    return 1 if vazios else 0


def cmd_posicoes(args) -> int:
    """
    Importa medições de posição deixadas em pedidos/entrada/ e avalia os alertas.

    A medição em si vem de fora — a busca do Mercado Livre está bloqueada na
    API. Aqui ela vira histórico, e com histórico as duas regras que estavam
    paradas desde o bloqueio voltam a funcionar: queda de posição e concorrente
    novo no topo.
    """
    from pathlib import Path as _Path
    raiz = _Path(__file__).resolve().parent
    pendentes = posicoes.arquivos_pendentes(raiz)

    if not pendentes:
        print(f"\n{AMAR}Nenhuma medição para importar.{FIM}")
        print(f"{CINZA}Os arquivos entram em {FIM}pedidos/entrada/{CINZA} como .json.{FIM}\n")
        return 1

    con = db.conectar()
    total_alertas = 0
    for caminho in pendentes:
        dados = posicoes.ler_arquivo(caminho)
        if not dados:
            print(f"  {VERM}{caminho.name}: não é um JSON válido — deixei onde estava{FIM}")
            continue
        slug = str(dados.get("conta") or args.alvo or "").strip()
        if not slug:
            print(f"  {VERM}{caminho.name}: falta o campo 'conta'{FIM}")
            continue
        try:
            conta = obter_conta(slug)
        except Exception as erro:
            print(f"  {VERM}{caminho.name}: {erro}{FIM}")
            continue

        r = posicoes.importar(con, conta, dados)
        print(f"\n── {conta.cliente_nome} ({conta.slug}) · {caminho.name}")
        print(f"   termos medidos ............. {r['termos']}")
        print(f"   posições dos seus anúncios . {r['posicoes']}")
        print(f"   concorrentes na busca ...... {r['concorrentes']}")

        # avaliar_busca, não avaliar: esta importação traz posição, não coleta.
        # Rodar a avaliação inteira aqui faria todos os anúncios parecerem
        # sumidos — 41 alertas falsos no primeiro teste.
        gerados = rules.avaliar_busca(con, conta, r["carimbo"])
        total_alertas += gerados
        print(f"   alertas gerados ............ {gerados}")
        posicoes.arquivar(caminho)

    if total_alertas:
        resultado = notify.notificar_pendentes(con)
        print(f"\n{CINZA}notificação → {resultado.detalhe}{FIM}")
    con.close()
    print()
    return 0


def cmd_vendas(args) -> int:
    """
    Mostra os pedidos crus que o sistema enxerga, para comparar com o painel
    do Mercado Livre.

    Existe porque os números não bateram: o painel do vendedor mostrou 11
    unidades e R$ 10.301 em 7 dias, e o sistema contou 7 unidades e
    R$ 6.736,93. Diferença dessa ordem não se resolve por dedução — as
    hipóteses (janela de data diferente, filtro de status, valor com ou sem
    frete) produzem sintomas parecidos. Aqui a resposta vem dos pedidos.
    """
    from collections import Counter
    conta = obter_conta(args.alvo)
    cli = _cli_para(conta)
    dias = int(args.dias)

    # Sem filtro de status: é justamente o filtro que está sob suspeita.
    from core.ml_api import BASE
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    desde = (_dt.now(_tz.utc) - _td(days=dias)).strftime("%Y-%m-%dT%H:%M:%S.000-00:00")

    pedidos, offset = [], 0
    while True:
        dados = cli.get("/orders/search", seller=cli.user_id,
                        **{"order.date_created.from": desde},
                        offset=offset, limit=50, sort="date_desc") or {}
        lote = dados.get("results", [])
        pedidos.extend(lote)
        offset += 50
        if len(lote) < 50 or offset >= 500:
            break

    print(f"\n  janela ................ últimos {dias} dias (desde {desde[:10]})")
    print(f"  pedidos devolvidos .... {len(pedidos)}")
    if not pedidos:
        print(f"  {AMAR}Nenhum pedido. Pode ser escopo de pedidos não liberado no app.{FIM}\n")
        return 0

    por_status = Counter(str(p.get("status")) for p in pedidos)
    print(f"  por status ............ "
          + ", ".join(f"{k}={v}" for k, v in por_status.most_common()))

    print(f"\n  {'data':<12} {'status':<20} {'un':>3} {'itens (un×preço)':>18} {'total_amount':>14}")
    print(f"  {'-' * 72}")
    soma_itens = soma_total = 0.0
    unidades = 0
    for p_ in sorted(pedidos, key=lambda x: str(x.get("date_created"))):
        q = sum(int(i.get("quantity", 0)) for i in p_.get("order_items", []))
        v = sum(float(i.get("unit_price", 0)) * int(i.get("quantity", 0))
                for i in p_.get("order_items", []))
        total = float(p_.get("total_amount") or 0)
        status = str(p_.get("status"))
        if status not in ("cancelled", "invalid"):
            soma_itens += v
            soma_total += total
            unidades += q
        cor_ = CINZA if status in ("cancelled", "invalid") else ""
        fim_ = FIM if cor_ else ""
        print(f"  {cor_}{str(p_.get('date_created'))[:10]:<12} {status:<20} {q:>3} "
              f"{brl(v):>18} {brl(total):>14}{fim_}")

    print(f"  {'-' * 72}")
    print(f"  {'':<12} {'sem cancelados':<20} {unidades:>3} "
          f"{brl(soma_itens):>18} {brl(soma_total):>14}")
    print(f"\n  {CINZA}Compare com o painel do Mercado Livre em Métricas > Vendas.")
    print(f"  'Vendas brutas' costuma bater com a coluna de itens; total_amount")
    print(f"  inclui frete cobrado do comprador.{FIM}\n")
    return 0


def cmd_contatos(args) -> int:
    """
    Lista quem já falou com o bot, com o chat_id de cada um.

    O Telegram não deixa um bot escrever para alguém que nunca escreveu para
    ele — é proteção contra spam, e não tem como contornar. Então incluir uma
    pessoa tem sempre dois passos: ela manda qualquer mensagem para o bot, e
    só depois o chat_id dela existe para ser configurado. Este comando é o
    segundo passo.
    """
    import requests as _rq
    cfg = notify.carregar_config()
    p_ = cfg.get("telegram", {})
    token = p_.get("bot_token")
    if not token:
        print(f"\n{VERM}Sem bot_token configurado.{FIM}\n")
        return 1

    try:
        r = _rq.get(f"https://api.telegram.org/bot{token}/getUpdates",
                    params={"limit": 100}, timeout=30)
        dados = r.json()
    except Exception as erro:
        print(f"\n{VERM}Falha ao consultar o Telegram: {str(erro)[:90]}{FIM}\n")
        return 1

    if not dados.get("ok"):
        print(f"\n{VERM}Telegram recusou: {str(dados)[:200]}{FIM}\n")
        return 1

    # my_chat_member entra na lista de propósito: é o aviso que o Telegram
    # manda quando o bot é ADICIONADO a um grupo. Sem ele, descobrir o id de
    # um grupo exigiria alguém digitar lá dentro — e, com o modo privacidade
    # ligado (que é o padrão), o bot nem enxergaria a mensagem comum.
    conversas: dict[str, dict] = {}
    for item in dados.get("result", []):
        origem = (item.get("message") or item.get("edited_message")
                  or item.get("channel_post") or item.get("my_chat_member")
                  or item.get("chat_member") or {})
        chat = origem.get("chat") or {}
        cid = str(chat.get("id") or "")
        if not cid:
            continue
        pessoa = " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x)
        conversas[cid] = {
            "nome": chat.get("title") or pessoa or chat.get("username") or "(sem nome)",
            "tipo": chat.get("type"),
            "usuario": chat.get("username"),
        }

    ja_configurados = set(notify.destinos_telegram(p_))

    print(f"\n  {'chat_id':<16} {'quem':<28} {'tipo':<10} configurado")
    print(f"  {'-' * 66}")
    if not conversas:
        print(f"  {AMAR}Ninguém falou com o bot nas últimas horas.{FIM}")
        print(f"  {CINZA}O Telegram só guarda as mensagens recentes. Peça para a")
        print(f"  pessoa mandar qualquer coisa para o bot AGORA e rode de novo.{FIM}")
    for cid, info in conversas.items():
        marca = f"{VERDE}sim{FIM}" if cid in ja_configurados else f"{AMAR}não{FIM}"
        print(f"  {cid:<16} {truncar(info['nome'], 26):<28} {str(info['tipo']):<10} {marca}")

    faltando = [c for c in conversas if c not in ja_configurados]
    print(f"\n  destinos ativos hoje .. {len(ja_configurados)}")
    if faltando:
        print(f"\n  {CINZA}Para incluir, em config/notificacoes.yaml, no bloco telegram:{FIM}")
        print(f"    chat_id:")
        for cid in sorted(ja_configurados) + faltando:
            quem = conversas.get(cid, {}).get("nome", "")
            print(f'      - "{cid}"' + (f"   # {quem}" if quem else ""))
    grupos = [c for c, i in conversas.items() if str(i["tipo"]) in ("group", "supergroup")]
    if grupos:
        print(f"  {VERDE}Há grupo na lista — id negativo é grupo, é assim mesmo.{FIM}")
        print(f"  {CINZA}Um grupo como destino vale por todos os membros, e entrar ou")
        print(f"  sair da equipe deixa de mexer em configuração.{FIM}")
        print(f"  {AMAR}Atenção: se o grupo virar supergrupo, o id MUDA e o bot para")
        print(f"  de entregar em silêncio. Se as mensagens sumirem, rode isto de novo.{FIM}")
    else:
        print(f"  {CINZA}Para usar um grupo: crie o grupo, adicione o bot e rode este")
        print(f"  comando — o id aparece sozinho, sem ninguém precisar digitar lá dentro.{FIM}")
    print()
    return 0


def cmd_checar(args) -> int:
    conta = obter_conta(args.alvo)
    try:
        cli = _cli_para(conta)
    except Exception as erro:
        print(f"{VERM}✗ {conta.slug}: {erro}{FIM}")
        return 1
    rep = cli.reputacao()
    print(f"{VERDE}✓ {conta.slug}{FIM} → {rep.get('nickname')} (user_id {cli.user_id}), "
          f"nível {rep.get('nivel')}, {rep.get('transacoes')} transações")

    # Sonda de preço da vitrine.
    #
    # O campo `price` do item ignora campanha promocional: os toldos do Ênio
    # apareciam na busca de 12% a 46% abaixo do que a API dizia. A leitura de
    # /items/{id}/prices foi ligada para corrigir isso e voltou vazia em todos
    # os anúncios — e "voltou vazia" pode ser endpoint bloqueado, formato
    # diferente do esperado ou simplesmente ausência de promoção. Sem ver a
    # resposta crua, os três se parecem.
    con = db.conectar()
    ultimo = db.ultima_coleta(con, "snap_anuncio", conta.slug)
    linha = con.execute(
        "SELECT item_id, titulo, preco FROM snap_anuncio WHERE conta_slug = ? "
        "AND coletado_em = ? AND status = 'active' ORDER BY preco DESC LIMIT 1",
        (conta.slug, ultimo)).fetchone() if ultimo else None
    con.close()

    if not linha:
        return 0

    from core.ml_api import BASE
    print(f"\n{CINZA}sonda de preço em {linha['item_id']} "
          f"({truncar(linha['titulo'], 40)}, cadastro {brl(linha['preco'])}){FIM}")
    try:
        r = cli.sessao.get(f"{BASE}/items/{linha['item_id']}/prices",
                           headers=cli._headers(), timeout=30)
        print(f"  /items/ID/prices → HTTP {r.status_code}")
        print(f"  {CINZA}{r.text[:700]}{FIM}")
    except Exception as erro:
        print(f"  {VERM}erro de rede: {str(erro)[:100]}{FIM}")
    return 0


def _coletar_promocoes(con, conta, cli, carimbo, quantos: int) -> dict:
    """
    Confere as campanhas de uma fatia dos anúncios e devolve o que achou.

    Devolve o carimbo da coleta porque é ele que a regra usa para saber o que
    é novidade — sem isso, a comparação pegaria a coleta errada.
    """
    ultimo = db.ultima_coleta(con, "snap_anuncio", conta.slug)
    if not ultimo:
        return {}
    ativos = [l["item_id"] for l in con.execute(
        "SELECT item_id FROM snap_anuncio WHERE conta_slug = ? AND coletado_em = ? "
        "AND status = 'active' ORDER BY vendidos DESC", (conta.slug, ultimo))]
    fatia = promocoes.fila(con, conta, ativos, quantos)
    if not fatia:
        return {}
    n, carimbo_promo = promocoes.coletar(con, conta, cli, fatia)
    liberadas = con.execute(
        "SELECT COUNT(*) AS n FROM snap_promocao WHERE conta_slug = ? "
        "AND coletado_em = ? AND status = 'candidate'",
        (conta.slug, carimbo_promo)).fetchone()["n"]
    return {"itens": len(fatia), "linhas": n, "liberadas": liberadas,
            "carimbo": carimbo_promo}


def cmd_coletar(args) -> int:
    contas = resolver_contas(args.alvo)
    if not contas:
        print(f"{AMAR}Nenhuma conta configurada para '{args.alvo or 'todas'}'.{FIM}")
        return 1

    con = db.conectar()
    falhas = 0

    for conta in contas:
        carimbo = agora_iso()
        inicio = carimbo
        print(f"\n{CINZA}── {conta}{FIM}")
        def etapa(rotulo, funcao, essencial=False):
            """
            Cada coleta é independente. Se o Mercado Livre bloquear ou mudar um
            endpoint, as outras continuam — perder a busca não pode custar a
            leitura de preço e estoque, que é o essencial.
            """
            try:
                return funcao()
            except Exception as erro:
                marca = VERM if essencial else AMAR
                print(f"   {marca}{rotulo}: {str(erro)[:110]}{FIM}")
                if args.debug:
                    traceback.print_exc()
                return None

        try:
            cli = _cli_para(conta)

            cep_ref = str((notify.carregar_config().get("regras") or {})
                          .get("cep_referencia", "01001000"))
            n = etapa("anúncios próprios FALHOU",
                      lambda: coletar_meus_anuncios(con, conta, cli, carimbo,
                                                    com_visitas=not args.sem_visitas,
                                                    cep=cep_ref),
                      essencial=True)
            if n is not None:
                print(f"   anúncios próprios .......... {n}")

            r = etapa("destaques da categoria indisponíveis",
                      lambda: coletar_destaques(con, conta, cli, carimbo))
            if r is not None:
                print(f"   mais vendidos da categoria . {r[0]}   seus itens no top: {r[1]}")
                resumo = getattr(coletar_destaques, "ultimo_resumo", None)
                if resumo and r[0] == 0:
                    print(f"   {CINZA}  ({resumo['categorias']} categorias consultadas, "
                          f"{resumo['itens']} anúncios e {resumo['produtos']} produtos nos "
                          f"destaques, {resumo['vazias']} categorias sem ranking){FIM}")

            nc = etapa("catálogo indisponível",
                       lambda: coletar_catalogo(con, conta, cli, carimbo))
            if nc:
                print(f"   ofertas de catálogo ........ {nc}")

            cfg_v = notify.carregar_config().get("regras") or {}
            v = etapa("vigilância de concorrentes indisponível",
                      lambda: vigilancia.vigiar(
                          con, conta, cli, carimbo,
                          cep=str(cfg_v.get("cep_referencia", "01001000")),
                          max_frete=int(cfg_v.get("max_fretes_por_rodada", 40))))
            if v and v.get("itens"):
                print(f"   ofertas de concorrentes .... {v['itens']} em "
                      f"{v.get('produtos', 0)} produtos, {v['fretes']} fretes")
            elif v and v.get("aviso"):
                print(f"   {CINZA}vigilância: {v['aviso']}{FIM}")

            etapa("saúde da conta FALHOU",
                  lambda: coletar_saude_da_conta(con, conta, cli, carimbo))

            buy_box = etapa("catálogo indisponível",
                            lambda: coletar_buy_box(con, conta, cli, carimbo)) or []
            if buy_box:
                perdidos = sum(1 for b in buy_box if b.get("status") not in ("winning", "sharing_first_place"))
                print(f"   catálogo ................... {len(buy_box)} itens, {perdidos} sem buy box")

            # Campanhas do ML: rodízio, como o frete. São 47 abertas nesta
            # conta e elas não nascem de minuto em minuto — o que importa é
            # não deixar nenhum anúncio sem olhar por muito tempo.
            promo = etapa("campanhas do ML indisponíveis",
                          lambda: _coletar_promocoes(con, conta, cli, carimbo,
                                                     int(cfg_v.get("promocoes_por_rodada", 6))))
            if promo:
                print(f"   campanhas conferidas ....... {promo['itens']} anúncio(s), "
                      f"{promo['liberadas']} liberadas")

            # Cupom é barato de ler — uma chamada mais uma por campanha — e é a
            # única campanha que não deixa rastro no preço do anúncio. Sem
            # olhar aqui, ninguém descobre que existe até o dinheiro sumir.
            cup = etapa("campanhas de cupom indisponíveis",
                        lambda: cupons.coletar(con, conta, cli, carimbo))
            if cup and cup[0]:
                # 'indicado' e não 'participando': o endpoint devolve também os
                # candidatos — anúncio elegível que ninguém colocou na campanha.
                # Chamar os 300 de participantes fez a conta parecer inteira
                # dando desconto quando só 18 estavam dentro.
                print(f"   campanhas de cupom ......... {cup[0]} "
                      f"({cup[1]} anúncio(s) indicado(s))")
            elif cup and cup[3]:
                print(f"   {AMAR}cupons: {cup[3]}{FIM}")

            con.commit()

            gerados = rules.avaliar(con, conta, carimbo, buy_box=buy_box)
            if promo and promo.get("carimbo"):
                gerados += etapa("avaliação de campanhas falhou",
                                 lambda: rules.avaliar_promocoes(
                                     con, conta, promo["carimbo"])) or 0
            if cup and cup[0]:
                gerados += etapa("avaliação de cupons falhou",
                                 lambda: rules.avaliar_cupons(
                                     con, conta, cup[2])) or 0
            cor = VERM if gerados else VERDE
            print(f"   {cor}alertas gerados ............ {gerados}{FIM}")

            db.inserir(con, "execucao", {"iniciado_em": inicio, "terminado_em": agora_iso(),
                                         "comando": "coletar", "conta_slug": conta.slug,
                                         "ok": 1, "detalhe": f"{n} anúncios, {gerados} alertas"})
        except Exception as erro:
            falhas += 1
            print(f"   {VERM}✗ {erro}{FIM}")
            if args.debug:
                traceback.print_exc()
            db.inserir(con, "execucao", {"iniciado_em": inicio, "terminado_em": agora_iso(),
                                         "comando": "coletar", "conta_slug": conta.slug,
                                         "ok": 0, "detalhe": str(erro)[:500]})
        con.commit()

    # regra que só faz sentido olhando o cliente inteiro
    for cliente in carregar_clientes():
        if cliente.coordenar_preco and len(cliente.contas) > 1:
            n = rules.avaliar_canibalizacao(con, cliente, agora_iso())
            if n:
                print(f"\n{AMAR}⚠ {cliente.nome}: {n} alerta(s) de canibalização entre contas{FIM}")

    con.close()
    return 1 if falhas else 0


def cmd_alertas(args) -> int:
    con = db.conectar()
    slugs = [c.slug for c in resolver_contas(args.alvo, exigir_credencial=False)] if args.alvo else [None]
    vistos = set()
    total = 0
    for slug in slugs:
        for a in db.alertas_recentes(con, args.horas, slug):
            if a["id"] in vistos:
                continue
            vistos.add(a["id"])
            total += 1
            cor = VERM if a["critico"] else AMAR
            print(f"{cor}{'!' if a['critico'] else '·'}{FIM} {CINZA}{para_br(a['criado_em'])}{FIM} "
                  f"[{a['conta_slug']}] {a['mensagem']}")
    if not total:
        print(f"{VERDE}Sem alertas nas últimas {args.horas}h.{FIM}")
    con.close()
    return 0


def cmd_relatorio(args) -> int:
    con = db.conectar()
    caminhos = report.gerar(con, apenas_cliente=args.cliente)
    con.close()
    if not caminhos:
        print(f"{AMAR}Nada gerado — não há clientes ativos com dados coletados.{FIM}")
        return 1
    for c in caminhos:
        print(f"{VERDE}✓{FIM} {c}")
    return 0


def cmd_resumo(args) -> int:
    con = db.conectar()
    print(report.resumo_texto(con, args.horas))
    con.close()
    return 0


def cmd_mapear(args) -> int:
    contas = resolver_contas(args.alvo)
    con = db.conectar()
    cfg = notify.carregar_config()
    regras = cfg.get("regras") or {}
    cep = args.cep or str(regras.get("cep_referencia", "01001000"))
    com_frete = (not args.sem_frete) and bool(regras.get("mapa_com_frete", True))

    for conta in contas:
        print(f"\n{CINZA}── {conta}{FIM}")
        try:
            cli = _cli_para(conta)
        except Exception as erro:
            print(f"   {VERM}{erro}{FIM}")
            continue

        def mostrar(i, total, titulo):
            print(f"   {CINZA}[{i}/{total}]{FIM} {titulo[:56]}")

        r = confrontos.mapear(con, conta, cli, agora_iso(), cep=cep,
                              com_frete=com_frete,
                              progresso=mostrar if args.detalhado else None)
        if r.get("erro"):
            print(f"   {AMAR}{r['erro']}{FIM}")
            continue

        sozinho = r.get("sozinho") or []
        disputados = r.get("disputados") or []
        ranking = sorted(r["por_vendedor"].items(), key=lambda kv: -kv[1]["produtos"])

        print(f"\n   {'─' * 60}")
        print(f"   {r['produtos']} produtos de catálogo analisados")
        print(f"   {VERDE}{len(sozinho)} onde você é o ÚNICO vendedor{FIM}")
        print(f"   {len(disputados)} disputados · {len(r['perfis'])} concorrentes")
        print(f"   {'─' * 60}\n")

        if sozinho and not disputados:
            print(f"   {AMAR}Nenhum concorrente nos seus produtos de catálogo.{FIM}")
            print(f"   {CINZA}Isso não é falta de dado: você é o único vendedor de")
            print(f"   todos eles. Explica também os buy box ganhos — não há com")
            print(f"   quem disputar.")
            print(f"")
            print(f"   Seus concorrentes reais devem estar em anúncios FORA do")
            print(f"   catálogo. A API não busca por palavra-chave nem lê anúncio")
            print(f"   de terceiro por ID, então esses só entram por FICHA:")
            print(f"")
            print(f"     python cli.py vigiar {conta.slug} LINK_DA_FICHA_DE_CATALOGO \\")
            print(f"            --comparar-com MLB_DO_SEU_ANUNCIO")
            print(f"")
            print(f"   Quem vende fora do catálogo aparece na pesquisa de mercado")
            print(f"   do raio-x, mas não pode ser acompanhado automaticamente.{FIM}\n")
        for sid, v in ranking[:10]:
            perfil = r["perfis"].get(sid, {})
            media = sum(v["diffs"]) / len(v["diffs"]) if v["diffs"] else None
            frete = sum(v["fretes"]) / len(v["fretes"]) if v["fretes"] else None
            cor_ = VERM if v["vitorias"] else VERDE
            linha = (f"   {cor_}{perfil.get('nickname') or sid}{FIM}"
                     f"{' [oficial]' if perfil.get('loja_oficial') else ''} — "
                     f"{v['produtos']} produto(s), mais barato em {v['vitorias']}")
            if media is not None:
                linha += f", preço {abs(media):.1f}% {'acima' if media > 0 else 'abaixo'}"
            if frete is not None:
                linha += f", frete médio {brl(frete)}"
            print(linha)

        if args.procurar:
            alvo = args.procurar.lower()
            achados = [(sid, p_) for sid, p_ in r["perfis"].items()
                       if alvo in (p_.get("nickname") or "").lower()]
            print()
            if achados:
                for sid, p_ in achados:
                    v = r["por_vendedor"].get(sid, {})
                    print(f"   {VERDE}'{args.procurar}' encontrado:{FIM} {p_.get('nickname')} "
                          f"— disputa {v.get('produtos', 0)} produto(s)")
            else:
                print(f"   {AMAR}'{args.procurar}' não aparece entre os "
                      f"{len(r['perfis'])} concorrentes de catálogo.{FIM}")

    con.close()
    return 0


def cmd_limpar_alertas(args) -> int:
    """Apaga alertas de um período — usado quando uma leva sai errada."""
    con = db.conectar()
    # O corte vem do Python, no MESMO formato de agora_iso(). Com
    # datetime('now', ...) o SQLite devolve "2026-08-27 03:00:00" e o
    # criado_em é "2026-08-27T03:00:00+00:00": o 'T' é maior que o espaço na
    # ordem de texto, então a comparação dava verdadeiro para o dia inteiro e
    # a janela de horas não valia nada. É a terceira vez que este mesmo erro
    # aparece neste projeto — sempre que houver comparação de carimbo, o
    # limite se calcula aqui, não no SQL.
    from datetime import datetime, timedelta, timezone
    corte = (datetime.now(timezone.utc) - timedelta(hours=int(args.horas))).isoformat()
    sql = "DELETE FROM alerta WHERE criado_em >= ?"
    params = [corte]
    if args.regra:
        sql += " AND regra = ?"
        params.append(args.regra)

    quantos = con.execute(
        sql.replace("DELETE FROM alerta", "SELECT COUNT(*) c FROM alerta"), params
    ).fetchone()["c"]

    if not quantos:
        print(f"{CINZA}Nada a apagar.{FIM}")
        con.close()
        return 0

    alvo = f"da regra '{args.regra}'" if args.regra else "de todas as regras"
    if args.sim:
        # Sem --sim isto pede confirmação no teclado — e pela fila de pedidos
        # não há teclado nenhum: o comando ficaria pendurado até o limite de
        # 15 minutos e o pedido morreria por tempo.
        print(f"{CINZA}Apagando {quantos} alerta(s) {alvo} das últimas "
              f"{args.horas}h (--sim).{FIM}")
    else:
        resp = input(f"{AMAR}Apagar {quantos} alerta(s) {alvo} "
                     f"das últimas {args.horas}h? (s/N) {FIM}").strip().lower()
        if resp != "s":
            print("Cancelado.")
            con.close()
            return 0

    con.execute(sql, params)
    con.commit()
    con.close()
    print(f"{VERDE}{quantos} alerta(s) apagado(s).{FIM}")
    return 0


def cmd_promocao_sair(args) -> int:
    """Tira anúncios da campanha que manda no preço. Simula por padrão."""
    conta = obter_conta(args.slug)
    if not conta.configurada:
        print(f"{VERM}Conta '{args.slug}' sem user_id no registro.{FIM}")
        return 1
    cli = MLClient(conta.slug, user_id_esperado=conta.user_id)
    print(f"{CINZA}conta confirmada: {conta.slug} (user_id {conta.user_id}){FIM}")
    print()

    pisos = {}
    try:
        from core import db as _db, precificacao as _prec
        with _db.conectar() as _con:
            pisos = {p["item_id"]: p for p in _prec.carregar(_con, conta)}
    except Exception as e:
        print(f"{AMAR}sem piso para conferir: {e}{FIM}")
        print()

    erro = False
    for mlb in args.itens:
        r = publicacao.sair_de_promocao(cli, mlb, simular=not args.confirmar,
                                        tipo=args.tipo)
        print(f"{mlb}  {r.get('tipo')} {r.get('promocao_id') or ''}  "
              f"R$ {r.get('preco_hoje') or 0:,.2f} → "
              f"{('R$ %.2f' % r['passa_a_valer']) if r.get('passa_a_valer') else 'preço de tabela'}"
              f" ({r.get('passa_a_valer_tipo')})")
        if r.get("salto_pct") is not None:
            print(f"   salto de {r['salto_pct']:+.1f}%   {r.get('ativas')} promoção(ões) ativa(s)")
        # A data de fim decide sozinha em metade dos casos: campanha que expira
        # em dias não justifica sair, porque sair não tem reentrada garantida.
        if r.get("termina"):
            print(f"   {AMAR}essa campanha termina sozinha em {r['termina']}{FIM}")
        p = pisos.get(mlb)
        if p and p.get("piso"):
            falta = (r.get("preco_hoje") or 0) - p["piso"]
            print(f"   piso R$ {p['piso']:,.2f}   "
                  f"{VERM if falta < 0 else VERDE}hoje {falta:+,.2f}{FIM}")
        if r.get("offer_id"):
            print(f"   {CINZA}offer_id {r['offer_id']}{FIM}")

        if r.get("simulado"):
            print(f"   {AMAR}simulação — continua na campanha{FIM}")
        elif r.get("resultado") == "saiu":
            print(f"   {VERDE}saiu{FIM} — preço agora R$ {r.get('preco_agora')}")
        else:
            print(f"   {VERM}{r.get('resultado')}{FIM} {r.get('erro') or ''}")
            erro = True
        print()

    if not args.confirmar:
        print(f"{AMAR}SIMULAÇÃO — ninguém saiu de campanha.{FIM}")
        print(f"{CINZA}Sair NÃO tem reentrada garantida, e depois o ML ancora no "
              f"preço praticado para recusar aumento. Para valer, --confirmar.{FIM}")
    return 1 if erro else 0


def cmd_preco(args) -> int:
    """
    Muda o preço de anúncios. Simula por padrão.

    Mostra o piso de core/precificacao.py ao lado do preço novo — a régua é a
    mesma do resto do sistema, não recalculada aqui. Preço abaixo do piso não
    é bloqueado (às vezes se vende no vermelho de propósito), mas é gritado.
    """
    conta = obter_conta(args.slug)
    if not conta.configurada:
        print(f"{VERM}Conta '{args.slug}' sem user_id no registro.{FIM}")
        return 1

    if args.lista:
        import csv as _csv
        from pathlib import Path as _Path
        caminho = _Path(args.lista)
        if not caminho.exists():
            print(f"{VERM}Lista não encontrada: {caminho}{FIM}")
            return 1
        with caminho.open(encoding="utf-8-sig", newline="") as f:
            fila = [(l["item_id"].strip(), float(str(l["preco"]).replace(",", ".")))
                    for l in _csv.DictReader(f, delimiter=";")
                    if l.get("item_id") and l.get("preco")]
        if not fila:
            print(f"{VERM}Lista sem linhas com item_id;preco.{FIM}")
            return 1
    elif args.itens and args.para is not None:
        fila = [(mlb, args.para) for mlb in args.itens]
    else:
        print(f"{VERM}Informe um ou mais MLB com --para <valor>, ou --lista <arquivo.csv> "
              f"(colunas item_id;preco).{FIM}")
        return 1

    cli = MLClient(conta.slug, user_id_esperado=conta.user_id)
    print(f"{CINZA}conta confirmada: {conta.slug} (user_id {conta.user_id}){FIM}")
    print(f"{CINZA}{len(fila)} item(ns) na fila.{FIM}")
    print()

    pisos = {}
    try:
        from core import db as _db, precificacao as _prec
        with _db.conectar() as _con:
            pisos = {p["item_id"]: p for p in _prec.carregar(_con, conta)}
    except Exception as e:
        print(f"{AMAR}sem piso para conferir: {e}{FIM}")
        print()

    erro = False
    for mlb, preco_alvo in fila:
        r = publicacao.alterar_preco(cli, mlb, preco_alvo, simular=not args.confirmar)
        var = r.get("variacao_pct")
        print(f"{mlb}  {r.get('status_antes')}  R$ {r.get('preco_antes')} "
              f"→ R$ {r.get('preco_novo'):,.2f}"
              f"{f'  ({var:+.1f}%)' if var is not None else ''}")
        print(f"   {(r.get('titulo') or '')[:60]}")
        print(f"   {r.get('vendidos')} venda(s), estoque {r.get('estoque')}")

        p = pisos.get(mlb)
        if p and p.get("piso"):
            folga = preco_alvo - p["piso"]
            cor = VERDE if folga >= 0 else VERM
            print(f"   piso R$ {p['piso']:,.2f}   "
                  f"{cor}{'folga' if folga >= 0 else 'ABAIXO DO PISO'} "
                  f"R$ {abs(folga):,.2f}{FIM}")
        # O raio da escrita, antes de qualquer confirmação.
        if r.get("irmaos"):
            print(f"   {AMAR}mesmo user product ({r.get('user_product')}) — o preço PODE "
                  f"ir junto em {', '.join(r['irmaos'])}{FIM}")
        if r.get("irmaos_que_moveram"):
            print(f"   {AMAR}foram junto: {', '.join(r['irmaos_que_moveram'])}{FIM}")
        if r.get("irmaos_intactos"):
            print(f"   {CINZA}não acompanharam: {', '.join(r['irmaos_intactos'])}{FIM}")
        if r.get("aviso_irmaos"):
            print(f"   {VERM}{r['aviso_irmaos']}{FIM}")
        if r.get("promocoes_ativas"):
            print(f"   {AMAR}promoções ativas: {'; '.join(r['promocoes_ativas'])}{FIM}")
        # Sem isto, uma leitura de promoção que falhou passa por "não tem
        # promoção" — que é a diferença entre conferir e supor.
        if r.get("aviso_promocoes"):
            print(f"   {VERM}{r['aviso_promocoes']}{FIM}")

        if r.get("simulado"):
            print(f"   {AMAR}simulação — preço NÃO alterado{FIM}")
        elif r.get("resultado") == "alterado":
            print(f"   {VERDE}alterado{FIM} (na tela agora: R$ {r.get('preco_depois')})")
        else:
            print(f"   {VERM}{r.get('resultado')}{FIM} {r.get('erro') or ''}")
            erro = True
        print()

    if not args.confirmar:
        print(f"{AMAR}SIMULAÇÃO — nenhum preço foi alterado.{FIM}")
        print(f"{CINZA}Aumento grande pode ser recusado pelo ML "
              f"(ERROR_CREDIBILITY_DISCOUNTED_PRICE): ele ancora no preço "
              f"praticado. Para valer, repita com --confirmar.{FIM}")
    return 1 if erro else 0


def cmd_sku(args) -> int:
    """Corrige o SELLER_SKU de um anúncio. Simula por padrão."""
    conta = obter_conta(args.slug)
    if not conta.configurada:
        print(f"{VERM}Conta '{args.slug}' sem user_id no registro.{FIM}")
        return 1
    cli = MLClient(conta.slug, user_id_esperado=conta.user_id)
    print(f"{CINZA}conta confirmada: {conta.slug} (user_id {conta.user_id}){FIM}\n")

    r = publicacao.corrigir_sku(cli, args.item, args.para, simular=not args.confirmar)
    print(f"{r['item_id']}  {r.get('status')}  {r.get('vendidos')} venda(s)")
    print(f"   {(r.get('titulo') or '')[:60]}")
    print(f"   SKU: {r.get('sku_antes')!r} → {r.get('sku_novo')!r}")

    if r.get("simulado"):
        print(f"   {AMAR}simulação — SKU NÃO alterado{FIM}")
        return 0
    if r.get("resultado") == "corrigido":
        print(f"   {VERDE}corrigido{FIM} (na tela agora: {r.get('sku_depois')!r})")
        return 0
    print(f"   {VERM}{r.get('resultado')}{FIM} {r.get('erro') or ''}")
    return 1


def cmd_disponibilidade(args) -> int:
    """Ajusta o prazo de disponibilidade de estoque (MANUFACTURING_TIME) de um ou mais anúncios. Simula por padrão."""
    conta = obter_conta(args.slug)
    if not conta.configurada:
        print(f"{VERM}Conta '{args.slug}' sem user_id no registro.{FIM}")
        return 1
    cli = MLClient(conta.slug, user_id_esperado=conta.user_id)
    print(f"{CINZA}conta confirmada: {conta.slug} (user_id {conta.user_id}){FIM}\n")

    prazo_alvo = None if args.remover else args.para
    erro = False
    for mlb in args.itens:
        r = publicacao.corrigir_disponibilidade(cli, mlb, prazo_alvo, simular=not args.confirmar)
        print(f"{r['item_id']}  {r.get('status')}  {r.get('vendidos')} venda(s)")
        print(f"   {(r.get('titulo') or '')[:60]}")
        print(f"   prazo: {r.get('prazo_antes')!r} → {r.get('prazo_novo')!r}")
        if r.get("simulado"):
            print(f"   {AMAR}simulação — prazo NÃO alterado{FIM}")
            continue
        if r.get("resultado") == "corrigido":
            print(f"   {VERDE}corrigido{FIM} (na tela agora: {r.get('prazo_depois')!r})")
        else:
            print(f"   {VERM}{r.get('resultado')}{FIM} {r.get('erro') or ''}")
            erro = True

    if not args.confirmar:
        print(f"\n{AMAR}SIMULAÇÃO — nada foi alterado. Repita com --confirmar para valer.{FIM}")
    return 1 if erro else 0


def cmd_descricao(args) -> int:
    """Substitui a descrição de um anúncio. Simula por padrão."""
    conta = obter_conta(args.slug)
    if not conta.configurada:
        print(f"{VERM}Conta '{args.slug}' sem user_id no registro.{FIM}")
        return 1
    cli = MLClient(conta.slug, user_id_esperado=conta.user_id)
    print(f"{CINZA}conta confirmada: {conta.slug} (user_id {conta.user_id}){FIM}\n")

    with open(args.arquivo, encoding="utf-8") as f:
        texto_novo = f.read()

    r = publicacao.corrigir_descricao(cli, args.item, texto_novo, simular=not args.confirmar)
    print(f"{r['item_id']}  {r.get('status')}  {r.get('vendidos')} venda(s)")
    print(f"   {(r.get('titulo') or '')[:60]}")
    print(f"   --- texto antes ---\n{r.get('texto_antes')}\n")
    print(f"   --- texto novo ---\n{r.get('texto_novo')}\n")

    if r.get("simulado"):
        print(f"   {AMAR}simulação — descrição NÃO alterada{FIM}")
        return 0
    if r.get("resultado") == "corrigido":
        print(f"   {VERDE}corrigido{FIM}")
        return 0
    print(f"   {VERM}{r.get('resultado')}{FIM} {r.get('erro') or ''}")
    return 1


def cmd_imagem_ambientada(args) -> int:
    """Gera uma foto de capa ambientada de um anúncio via API da OpenAI. Não simula: cada chamada tem custo real."""
    conta = obter_conta(args.slug)
    con = db.conectar()
    try:
        r = imagens.gerar_imagem_ambientada(con, conta.slug, args.item, prompt=args.prompt)
    finally:
        con.close()

    if r.get("erro"):
        print(f"{VERM}{r['erro']}{FIM}")
        return 1

    print(f"{VERDE}gerado{FIM}: {r['arquivo']}")
    print(f"   {(r.get('titulo') or '')[:70]}")
    if r.get("sku"):
        print(f"   SKU: {r['sku']}")
    return 0


def cmd_reativar(args) -> int:
    """Despausa anúncios. Simula por padrão; reativar tem volta (é só pausar)."""
    conta = obter_conta(args.slug)
    if not conta.configurada:
        print(f"{VERM}Conta '{args.slug}' sem user_id no registro.{FIM}")
        return 1
    cli = MLClient(conta.slug, user_id_esperado=conta.user_id)
    print(f"{CINZA}conta confirmada: {conta.slug} (user_id {conta.user_id}){FIM}\n")

    erro = False
    for mlb in args.itens:
        r = publicacao.reativar(cli, mlb, simular=not args.confirmar)
        print(f"{mlb}  {r.get('status_antes')}  R$ {r.get('preco')}  "
              f"estoque {r.get('estoque')}")
        print(f"   {(r.get('titulo') or '')[:60]}")
        if r.get("simulado"):
            print(f"   {AMAR}simulação — nada foi reativado{FIM}")
        elif r.get("resultado") == "reativado":
            print(f"   {VERDE}reativado{FIM} (status: {r.get('status_depois')}"
                  f"{'  sub: ' + str(r.get('sub_status')) if r.get('sub_status') else ''})")
        else:
            print(f"   {VERM}{r.get('resultado')}{FIM} {r.get('erro') or ''}")
            erro = True

    if not args.confirmar:
        print(f"\n{AMAR}SIMULAÇÃO — nada foi reativado.{FIM}")
        print(f"{CINZA}Antes de confirmar, garanta que nenhum deles tem gêmeo "
              f"já no ar — despausar duplicata é infração.{FIM}")
    return 1 if erro else 0


def cmd_encerrar(args) -> int:
    """Encerra anúncios pelo MLB. Simula por padrão; encerrar não tem volta."""
    conta = obter_conta(args.slug)
    if not conta.configurada:
        print(f"{VERM}Conta '{args.slug}' sem user_id no registro.{FIM}")
        return 1
    cli = MLClient(conta.slug, user_id_esperado=conta.user_id)
    print(f"{CINZA}conta confirmada: {conta.slug} (user_id {conta.user_id}){FIM}\n")

    houve_erro = False
    for mlb in args.itens:
        r = publicacao.encerrar(cli, mlb, simular=not args.confirmar)
        print(f"{mlb}  {r.get('status_antes')}  R$ {r.get('preco')}  "
              f"{r.get('vendidos')} venda(s)")
        print(f"   {(r.get('titulo') or '')[:60]}")
        if r.get("simulado"):
            print(f"   {AMAR}simulação — nada foi encerrado{FIM}")
            continue
        if r.get("resultado") == "encerrado":
            print(f"   {VERDE}encerrado{FIM} (status agora: {r.get('status_depois')})")
        else:
            print(f"   {VERM}{r.get('resultado')}{FIM} {r.get('erro') or ''}")
            houve_erro = True

    if not args.confirmar:
        print(f"\n{AMAR}SIMULAÇÃO — nada foi encerrado.{FIM}")
        print(f"{CINZA}Encerrar é definitivo: anúncio fechado não reativa. "
              f"Para valer, repita com --confirmar.{FIM}")
    return 1 if houve_erro else 0


def _montar_extras(peso: str | None, atributos: list[str] | None) -> dict[str, str] | None:
    """Junta --peso (vira WEIGHT) com --atributo ID=VALOR, repetível."""
    extras: dict[str, str] = {}
    if peso:
        extras["WEIGHT"] = peso
    for bruto in (atributos or []):
        if "=" not in bruto:
            raise ValueError(f"--atributo inválido: {bruto!r}. Use ID=VALOR.")
        aid, valor = bruto.split("=", 1)
        extras[aid.strip()] = valor.strip()
    return extras or None


def cmd_publicar(args) -> int:
    """Recadastra UM anúncio a partir de outro, declarando a forma de entrega.

    Nasce em simulação. Publicar de verdade exige --publicar, e mesmo assim
    um item por vez: escrita em conta de cliente não vira lote sem alguém
    tendo olhado o payload antes.
    """
    conta = obter_conta(args.slug)
    if not conta.configurada:
        print(f"{VERM}Conta '{args.slug}' sem user_id no registro.{FIM}")
        return 1

    # A trava do repositório: o MLClient compara o user_id do token com o do
    # registro e aborta se divergir. Não se contorna.
    cli = MLClient(conta.slug, user_id_esperado=conta.user_id)
    print(f"{CINZA}conta confirmada (destino): {conta.slug} (user_id {conta.user_id}){FIM}")

    # Origem numa conta diferente do destino: cada MLClient aborta sozinho se
    # o user_id do token não bater com o do registro — mesma trava, aplicada
    # duas vezes, uma por conta.
    cli_origem = cli
    if args.conta_origem and args.conta_origem != conta.slug:
        conta_origem = obter_conta(args.conta_origem)
        if not conta_origem.configurada:
            print(f"{VERM}Conta de origem '{args.conta_origem}' sem user_id no registro.{FIM}")
            return 1
        cli_origem = MLClient(conta_origem.slug, user_id_esperado=conta_origem.user_id)
        print(f"{CINZA}conta confirmada (origem)  : {conta_origem.slug} "
              f"(user_id {conta_origem.user_id}){FIM}")
    print()

    import csv
    import json
    import time
    from pathlib import Path

    # Um item pela linha de comando, ou uma fila vinda de planilha.
    if args.lista:
        caminho = Path(args.lista)
        if not caminho.exists():
            print(f"{VERM}Lista não encontrada: {caminho}{FIM}")
            return 1
        with caminho.open(encoding="utf-8-sig", newline="") as f:
            fila = [l for l in csv.DictReader(f, delimiter=";") if l.get("origem")]
    elif args.origem:
        fila = [{"origem": args.origem, "peso": args.peso, "preco": args.preco,
                 "titulo": args.titulo, "modalidade": args.modalidade}]
    else:
        print(f"{VERM}Informe um MLB de origem ou --lista <arquivo.csv>.{FIM}")
        return 1

    if args.sincronizar:
        if cli_origem is not cli:
            print(f"{VERM}--conta-origem não vale com --sincronizar: o anúncio "
                  f"sincronizado pendura no user_product_id da conta de ORIGEM, "
                  f"que não existe na conta de destino — não há produto para "
                  f"compartilhar entre contas diferentes.{FIM}")
            return 1
        conflitos = [nome for nome, valor in
                     (("--fotos", args.fotos), ("--titulo", args.titulo),
                      ("--peso", args.peso), ("--herdar-peso", args.herdar_peso),
                      ("--copiar-descricao", args.copiar_descricao))
                     if valor]
        if conflitos:
            print(f"{VERM}No modo --sincronizar, {', '.join(conflitos)} não tem "
                  f"efeito: foto, título, ficha e descrição pertencem ao User "
                  f"Product, não ao anúncio. Mudá-los é PUT no produto, e muda "
                  f"os dois anúncios do par.{FIM}")
            return 1

    # Fotos do disco: existem porque o que está publicado nem sempre é o
    # melhor que se tem. No Sofá Yara 140 o ML guardava 500x500 e o arquivo do
    # fornecedor era 1254x1254 — e o zoom do ML só liga a partir de 1200px.
    fotos_locais: list[Path] = []
    if args.fotos:
        if args.lista:
            print(f"{VERM}--fotos vale para UM anúncio; com --lista cada linha "
                  f"precisaria das suas. Rode um por vez.{FIM}")
            return 1
        for bruto in args.fotos:
            caminho = Path(bruto)
            if caminho.is_dir():
                achados = sorted(a for a in caminho.iterdir()
                                 if a.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
                if not achados:
                    print(f"{VERM}Pasta sem imagem: {caminho}{FIM}")
                    return 1
                fotos_locais.extend(achados)
            elif caminho.is_file():
                fotos_locais.append(caminho)
            else:
                print(f"{VERM}Arquivo de foto não encontrado: {caminho}{FIM}")
                return 1
        print(f"{CINZA}{len(fotos_locais)} foto(s) do disco, nesta ordem:{FIM}")
        for n, caminho in enumerate(fotos_locais, 1):
            print(f"{CINZA}  {n}. {caminho.name}{FIM}")

    print(f"{CINZA}{len(fila)} anúncio(s) na fila.{FIM}")
    resultados = []
    falhou = False

    for i, linha in enumerate(fila, 1):
        mlb = (linha.get("origem") or "").strip()
        peso = (linha.get("peso") or args.peso or "").strip() or None
        preco = linha.get("preco") or args.preco
        preco = float(str(preco).replace(",", ".")) if preco not in (None, "") else None
        titulo = (linha.get("titulo") or args.titulo or "").strip() or None
        modalidade = (linha.get("modalidade") or args.modalidade or "").strip() or None

        print(f"\n{CINZA}{'─' * 62}{FIM}")
        print(f"{CINZA}[{i}/{len(fila)}]{FIM}")
        try:
            if args.sincronizar:
                payload, origem = publicacao.montar_sincronizado(
                    cli, mlb,
                    envio=args.envio,
                    frete_gratis=not args.sem_frete_gratis,
                    estoque=args.estoque,
                    preco=preco,
                    tipo_anuncio=modalidade,
                )
                if args.acrescimo and preco is None:
                    base = origem.get("price") or 0
                    payload["price"] = round(base * (1 + args.acrescimo / 100.0), 2)
                prazo = (linha.get("prazo") or args.prazo or "").strip()
                if prazo:
                    # MANUFACTURING_TIME é "Disponibilidade de estoque" na tela.
                    # Vai como sale_term, não como atributo.
                    termos = [x for x in (payload.get("sale_terms") or [])
                              if x.get("id") != "MANUFACTURING_TIME"]
                    termos.append({"id": "MANUFACTURING_TIME", "value_name": prazo})
                    payload["sale_terms"] = termos
            else:
                # Item de outra conta: lê PRIMEIRO com o token do dono
                # (cli_origem), porque cli (destino) toma 403 access_denied
                # ao tentar ler item de terceiro por ID.
                origem_bruta = cli_origem.get(f"/items/{mlb}") if cli_origem is not cli else None
                payload, origem = publicacao.montar(
                    cli, mlb,
                    envio=args.envio,
                    frete_gratis=not args.sem_frete_gratis,
                    estoque=args.estoque,
                    preco=preco,
                    titulo=titulo,
                    tipo_anuncio=modalidade,
                    atributos_extras=_montar_extras(peso, args.atributo),
                    herdar_peso=args.herdar_peso,
                    caixa=(linha.get("caixa") or args.caixa or None),
                    peso_caixa=(linha.get("peso_caixa") or args.peso_caixa or None),
                    origem_bruta=origem_bruta,
                )
        except (ValueError, Exception) as erro:  # noqa: B014 - erro de rede também para a fila
            print(f"{VERM}{mlb}: {erro}{FIM}")
            resultados.append({"origem": mlb, "resultado": "erro ao montar",
                               "detalhe": str(erro)[:200]})
            falhou = True
            if not args.continuar:
                break
            continue

        if args.sincronizar:
            print(publicacao.resumo_do_sincronizado(payload, origem))
        else:
            print(publicacao.resumo_do_payload(payload, origem))
        if fotos_locais:
            print(f"  FOTOS       : {len(fotos_locais)} arquivo(s) do disco "
                  f"substituem as {len(payload['pictures'])} do anúncio de origem")
        if args.json:
            print(publicacao.payload_json(payload))

        if not args.publicar:
            resultados.append({"origem": mlb, "resultado": "simulado",
                               "titulo": payload.get("title")})
            continue

        if not args.sim:
            resp = input(f"{AMAR}Publicar na conta {conta.slug}? (s/N) {FIM}")
            if resp.strip().lower() != "s":
                print(f"{CINZA}Pulado.{FIM}")
                resultados.append({"origem": mlb, "resultado": "pulado"})
                continue

        # Subir foto é escrita: só acontece depois do sim, nunca na simulação.
        if fotos_locais:
            try:
                subidas = []
                for n, caminho in enumerate(fotos_locais, 1):
                    foto_id = publicacao.subir_foto(cli, caminho)
                    print(f"{CINZA}  foto {n}/{len(fotos_locais)} "
                          f"{caminho.name} → {foto_id}{FIM}")
                    subidas.append({"id": foto_id})
                payload["pictures"] = subidas
            except Exception as erro:
                print(f"{VERM}Falhou ao subir foto: {erro}{FIM}")
                print(f"{AMAR}Nada foi publicado.{FIM}")
                resultados.append({"origem": mlb, "resultado": "erro ao subir foto",
                                   "detalhe": str(erro)[:200]})
                falhou = True
                if not args.continuar:
                    break
                continue

        descricao = publicacao.descricao_de(cli_origem, mlb) if args.copiar_descricao else None
        r = publicacao.publicar(cli, payload, simular=False, descricao=descricao)

        if r.get("status") not in (200, 201):
            print(f"{VERM}Recusado ({r.get('status')}):{FIM}")
            print(json.dumps(r.get("corpo"), ensure_ascii=False, indent=2)[:1200])
            resultados.append({"origem": mlb, "resultado": f"recusado {r.get('status')}",
                               "detalhe": json.dumps(r.get("corpo"), ensure_ascii=False)[:400]})
            falhou = True
            if not args.continuar:
                print(f"{AMAR}Parando na primeira recusa. "
                      f"Use --continuar para seguir mesmo assim.{FIM}")
                break
            continue

        # O que vale é o RELIDO, não o que o POST respondeu.
        real = r.get("envio_real")
        ok = real == payload["shipping"]["mode"]
        cor_envio = VERDE if ok else VERM
        print(f"{VERDE}Publicado: {r['item_id']}{FIM}  {r.get('permalink')}")
        print(f"  POST respondeu : {r.get('envio_obtido')}")
        print(f"  relido agora   : {cor_envio}{real}{FIM} "
              f"(logistic {r.get('logistic_real')})")
        if r.get("tags_envio"):
            print(f"  tags de envio  : {AMAR}{r['tags_envio']}{FIM}")
        if not ok:
            print(f"{VERM}  O ML TIROU o Envios depois de aceitar. "
                  f"O anúncio existe, mas sem Mercado Envios.{FIM}")
            falhou = True
        resultados.append({"origem": mlb, "resultado": "publicado",
                           "novo_id": r["item_id"], "permalink": r.get("permalink"),
                           "envio_obtido": r.get("envio_obtido"),
                           "envio_real": real, "tags_envio": str(r.get("tags_envio")),
                           "logistic_type": r.get("logistic_real"),
                           "titulo": payload.get("title")})
        if not ok and not args.continuar:
            print(f"{AMAR}Parando: publicar o resto sem Envios só multiplica "
                  f"o problema. Use --continuar se quiser mesmo assim.{FIM}")
            break

        # Escrita em lote sem respiro é o jeito mais rápido de tomar 429.
        if i < len(fila):
            time.sleep(2)

    if resultados and args.publicar:
        destino = Path("relatorios") / f"publicacao-{conta.slug}.csv"
        destino.parent.mkdir(exist_ok=True)
        campos = ["origem", "resultado", "novo_id", "permalink", "envio_obtido",
                  "envio_real", "tags_envio", "logistic_type", "titulo", "detalhe"]
        with destino.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=campos, delimiter=";", extrasaction="ignore")
            w.writeheader()
            w.writerows(resultados)
        print(f"\n{VERDE}Log: {destino}{FIM}")

    if not args.publicar:
        print(f"\n{AMAR}SIMULAÇÃO — nada foi enviado ao Mercado Livre.{FIM}")
        print(f"{CINZA}Para publicar de verdade, repita com --publicar.{FIM}")
        return 0

    publicados = sum(1 for r in resultados if r["resultado"] == "publicado")
    print(f"\n{VERDE}{publicados} publicado(s){FIM} de {len(fila)} na fila.")
    print(f"{CINZA}Todos nascem com estoque {args.estoque}. "
          f"Confira na tela antes de subir estoque ou ativar.{FIM}")
    return 1 if falhou else 0


def cmd_cobertura(args) -> int:
    """Quais produtos já têm clássico, premium e catálogo — e quais faltam."""
    con = db.conectar()
    houve = False
    for conta in resolver_contas(args.alvo, exigir_credencial=False):
        r = cobertura.analisar(con, conta.slug)
        print(f"\n{CINZA}{'─' * 62}{FIM}")
        print(cobertura.texto(r, detalhado=args.detalhado,
                              limite=args.limite).replace("*", ""))
        print(f"{CINZA}{'─' * 62}{FIM}")
        if r.get("erro"):
            continue
        houve = True

        if args.csv:
            import csv
            from pathlib import Path

            destino = Path(args.csv)
            with destino.open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["conta", "produto", "sku", "anuncios", "vendidos",
                            "classico", "premium", "catalogo", "falta",
                            "fichas", "item_ids"])
                for p in r["produtos"]:
                    w.writerow([conta.slug, p["titulo"], p["sku"], p["anuncios"],
                                p["vendidos"], p["eixos"]["classico"] or "-",
                                p["eixos"]["premium"] or "-",
                                p["eixos"]["catalogo"] or "-",
                                " ".join(p["falta"]), " ".join(p["fichas"]),
                                " ".join(p["item_ids"])])
            print(f"{VERDE}Planilha: {destino}{FIM}")

    con.close()
    return 0 if houve else 1


def cmd_diagnostico(args) -> int:
    """Raio-X automático: os achados que valem dinheiro, na tela e no Telegram."""
    con = db.conectar()
    houve = False
    for conta in resolver_contas(args.alvo, exigir_credencial=False):
        r = diagnostico.analisar(con, conta.slug)
        texto = diagnostico.texto_para_telegram(r)
        print(f"\n{CINZA}{'─' * 62}{FIM}")
        print(texto.replace("*", ""))
        print(f"{CINZA}{'─' * 62}{FIM}")

        if r.get("erro"):
            continue
        houve = True

        # detalhe da canibalização, que é o achado mais denso
        if r["canibalizacao"] and args.detalhado:
            print(f"\n{AMAR}Grupos com mais de um anúncio ativo:{FIM}")
            for c in r["canibalizacao"]:
                print(f"  {c['grupo']}: {c['anuncios']} anúncios · "
                      f"vencedor {c['vendas_vencedor']} vendas a {brl(c['preco_vencedor'])} · "
                      f"outros {c['vendas_outros']} vendas, "
                      f"{c['visitas_desperdicadas']} visitas")

        if args.enviar:
            resultado = notify.enviar(texto)
            cor_ = VERDE if resultado.ok else VERM
            print(f"\n{cor_}Telegram: {resultado.detalhe}{FIM}")

    con.close()
    return 0 if houve else 1


def cmd_funil(args) -> int:
    """Em qual degrau do funil cada anúncio ativo trava, e quanto vale consertar."""
    con = db.conectar()
    houve = False
    for conta in resolver_contas(args.alvo, exigir_credencial=False):
        r = funil.analisar(con, conta.slug, dias=args.dias, item_filtro=args.item)
        texto = funil.texto_resumo(r, limite=args.limite)
        print(f"\n{CINZA}{'─' * 62}{FIM}")
        print(f"{conta}")
        print(texto.replace("*", ""))
        print(f"{CINZA}{'─' * 62}{FIM}")

        if r.get("erro"):
            continue
        houve = True

        if args.veredito:
            filtrados = [i for i in r["itens"] if i["veredito"] == args.veredito]
            print(f"\n{AMAR}{args.veredito} ({len(filtrados)}):{FIM}")
            for i in filtrados[:args.limite]:
                print(f"  {truncar(i['titulo'], 55)} — {i['item_id']}")
                for c in i["causas"]:
                    print(f"    · {c['causa']}: {c['evidencia']}")

    con.close()
    return 0 if houve else 1


def _gravar_lista(caminho, chave, lista) -> None:
    """
    Reescreve UMA chave do concorrentes.yaml preservando o resto do arquivo.

    A versão anterior guardava só o texto antes da chave e jogava fora tudo
    que vinha depois — na prática, o primeiro cadastro apagava as explicações
    do arquivo. Como esse arquivo é lido por gente, e é onde está escrito o
    que dá e o que não dá para vigiar, apagar o comentário é apagar a
    instrução. Aqui a substituição é cirúrgica: troca só o bloco da chave.
    """
    import yaml as _yaml
    linhas = caminho.read_text(encoding="utf-8").splitlines(keepends=True)

    inicio = None
    for i, linha in enumerate(linhas):
        if linha.startswith(f"{chave}:"):
            inicio = i
            break

    corpo = _yaml.safe_dump({chave: lista}, allow_unicode=True,
                            sort_keys=False, default_flow_style=False)

    if inicio is None:                       # chave ainda não existe no arquivo
        caminho.write_text("".join(linhas).rstrip("\n") + "\n\n" + corpo,
                           encoding="utf-8")
        return

    # O bloco da chave vai até a primeira linha que volta à margem esquerda
    # sendo outra coisa: comentário, outra chave, qualquer conteúdo não
    # indentado. Linha em branco no meio não encerra o bloco.
    fim = len(linhas)
    for j in range(inicio + 1, len(linhas)):
        crua = linhas[j]
        if not crua.strip():
            continue
        if crua[0] not in " \t-":
            fim = j
            break

    resto = "".join(linhas[fim:])
    if resto.strip():
        corpo += "\n"          # respiro antes do comentário seguinte
    caminho.write_text("".join(linhas[:inicio]) + corpo + resto, encoding="utf-8")


def cmd_vigiar(args) -> int:
    """
    Acrescenta uma ficha de catálogo à vigilância, por link.

    Não confia no formato da URL: pergunta à API o que aquele ID realmente é.
    A página de catálogo parece um anúncio comum na tela, e adivinhar pelo
    endereço leva a cadastrar no lugar errado.

    Só ficha de catálogo entra. Anúncio avulso de terceiro é recusado com
    explicação — a API bloqueia a leitura dele por ID (403 access_denied),
    então cadastrar produziria uma vigilância que nunca traz dado nenhum.
    """
    import re as _re
    import yaml as _yaml

    conta = obter_conta(args.slug)
    m = _re.search(r"(ML[A-Z]?\d{6,})", args.link.upper().replace("-", ""))
    if not m:
        print(f"{VERM}Não achei um ID (MLB...) nesse link.{FIM}")
        return 1
    ident = m.group(1)

    alvo = None
    if args.comparar_com:
        ma = _re.search(r"(ML[A-Z]?\d{6,})", args.comparar_com.upper().replace("-", ""))
        alvo = ma.group(1) if ma else None

    # --- pergunta à API o que é ---
    #
    # Consulta crua, sem o tratamento do MLClient.get, porque aqui o CÓDIGO da
    # resposta é a informação: 404 é anúncio que não existe mais, 403 é acesso
    # negado, 200 é achou. Engolir tudo em "não respondeu" esconde a diferença
    # entre link morto e permissão faltando.
    cli = _cli_para(conta)
    eh_produto = False
    nome = None
    quantos_vendem = None
    diagnostico_http = {}

    def sondar(caminho: str):
        from core.ml_api import BASE
        try:
            r = cli.sessao.get(f"{BASE}{caminho}", headers=cli._headers(), timeout=30)
            diagnostico_http[caminho] = r.status_code
            return r.json() if r.status_code == 200 else None
        except Exception as erro:
            diagnostico_http[caminho] = f"erro de rede: {str(erro)[:60]}"
            return None

    produto = sondar(f"/products/{ident}")
    if produto and produto.get("id"):
        eh_produto = True
        nome = produto.get("name")
        try:
            quantos_vendem = len(cli.vendedores_do_produto(ident, limite=25))
        except Exception:
            pass

    if not eh_produto:
        # Antes havia aqui uma tentativa de ler o anúncio pelo ID, pelo
        # multiget /items?ids=. Ela foi retirada porque o Mercado Livre
        # devolve `access_denied` (403) para item de terceiro nos dois
        # caminhos — verificado com controle, num anúncio que o sistema lê
        # sem problema quando pedido pela ficha de catálogo. Insistir só
        # produzia a mensagem errada: parecia link morto, era bloqueio.
        print(f"\n{VERM}{ident} não é uma ficha de catálogo.{FIM}")
        for caminho_sondado, codigo in diagnostico_http.items():
            print(f"  {CINZA}{caminho_sondado} → {codigo}{FIM}")
        print()
        print(f"{AMAR}O Mercado Livre não deixa ler anúncio de outro vendedor "
              f"pelo ID.{FIM}")
        print(f"{CINZA}A API só devolve concorrente através da FICHA DE CATÁLOGO")
        print(f"(o endereço com /p/MLB...). Anúncio avulso, fora de catálogo,")
        print(f"pode ser DESCOBERTO na pesquisa de mercado, mas não pode ser")
        print(f"acompanhado automaticamente — nenhuma configuração resolve.{FIM}")
        print()
        print(f"{CINZA}O que fazer com esse link:{FIM}")
        print(f"  1. abra o anúncio dele e veja se tem 'Ver publicações do produto'")
        print(f"     ou um link /p/MLB... — se tiver, é essa ficha que se vigia")
        print(f"  2. se não tiver, ele vende fora do catálogo: use")
        print(f"     {CINZA}python cli.py diagnostico {conta.slug} --detalhado{FIM}"
              f" e a pesquisa de mercado")
        return 1

    caminho = conta.dir / "concorrentes.yaml"
    dados = _yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}

    lista = dados.get("produtos_vigiados") or []
    if any(str(x.get("produto", "")).upper() == ident for x in lista):
        print(f"{AMAR}{ident} já está vigiado.{FIM}")
        return 0
    entrada = {"produto": ident, "apelido": args.apelido or nome or ident}
    if alvo:
        entrada["comparar_com"] = alvo
    lista.append(entrada)
    _gravar_lista(caminho, "produtos_vigiados", lista)

    print(f"\n{VERDE}É uma FICHA DE CATÁLOGO.{FIM}")
    print(f"  {nome or ident}")
    if quantos_vendem is not None:
        print(f"  {quantos_vendem} vendedor(es) oferecem esse produto hoje")
    print(f"{CINZA}  Vigiando a ficha inteira: quem entrar depois aparece sozinho.{FIM}")

    if not alvo:
        print(f"  {AMAR}sem vínculo — não vai gerar alerta de preço{FIM}")
        print(f"{CINZA}Entra na próxima coleta.{FIM}")
        return 0

    print(f"  vinculado ao seu {alvo}")

    # Confere se as medidas batem. Vincular um 310x100 a um 230x100 produz
    # alerta de preço enganoso — e alerta enganoso é pior que alerta nenhum.
    import sqlite3 as _sq
    con = db.conectar()
    ultimo = db.ultima_coleta(con, "snap_anuncio", conta.slug)
    meu = None
    if ultimo:
        meu = con.execute(
            "SELECT titulo, preco FROM snap_anuncio WHERE conta_slug = ? "
            "AND coletado_em = ? AND item_id = ?", (conta.slug, ultimo, alvo)).fetchone()
    con.close()

    if not meu:
        print(f"  {AMAR}Não achei {alvo} entre os seus anúncios coletados.{FIM}")
        print(f"  {CINZA}Confira o ID — o vínculo só funciona com anúncio seu.{FIM}")
        return 0

    print(f"  seu: {truncar(meu['titulo'], 46)} — {brl(meu['preco'])}")

    def medida(texto):
        achado = _re.search(r"(\d{2,3})\s*[xX×]\s*(\d{2,3})", texto or "")
        return (int(achado.group(1)), int(achado.group(2))) if achado else None

    m_dele, m_meu = medida(nome or ""), medida(meu["titulo"])
    if m_dele and m_meu and m_dele != m_meu:
        dif_l = abs(m_dele[0] - m_meu[0])
        dif_a = abs(m_dele[1] - m_meu[1])
        grave = dif_l > 20 or dif_a > 20
        cor_ = VERM if grave else AMAR
        print(f"\n  {cor_}ATENÇÃO: as medidas não batem.{FIM}")
        print(f"  dele: {m_dele[0]}x{m_dele[1]}   seu: {m_meu[0]}x{m_meu[1]}")
        if grave:
            print(f"  {VERM}Diferença grande. O alerta de preço vai comparar produtos")
            print(f"  diferentes e te dar informação errada.{FIM}")
            print(f"  {CINZA}Rode de novo com o --comparar-com do anúncio da medida certa.{FIM}")
        else:
            print(f"  {CINZA}Diferença pequena; a comparação ainda faz sentido.{FIM}")

    print(f"{CINZA}Entra na próxima coleta.{FIM}")
    return 0


def cmd_notificar(args) -> int:
    con = db.conectar()
    if args.semanal:
        enviados = 0
        for conta in resolver_contas(args.alvo if hasattr(args, "alvo") else None,
                                     exigir_credencial=False):
            texto = confrontos.resumo_semanal(con, conta.slug)
            if texto:
                r = notify.enviar(texto)
                enviados += 1
                print(f"{CINZA}{conta.slug} → {r.detalhe}{FIM}")
        con.close()
        if not enviados:
            print(f"{AMAR}Sem dados de concorrência ainda. "
                  f"Rode o mapa primeiro (concorrentes.bat).{FIM}")
            return 1
        return 0
    if args.resumo:
        r = notify.enviar_resumo(con)
    else:
        r = notify.notificar_pendentes(con, forcar=args.forcar)
    con.close()
    cor = VERDE if r.ok else VERM
    print(f"{cor}{'ok' if r.ok else 'falhou'}{FIM}: {r.detalhe}")
    return 0 if r.ok else 1


def cmd_testar_notificacao(_args) -> int:
    cfg = notify.carregar_config()
    provedor = cfg.get("provedor", "console")
    print(f"{CINZA}provedor: {provedor} · destino: {cfg.get('destino')}{FIM}")
    r = notify.enviar(
        "*Zion ML* — mensagem de teste.\n\n"
        "Se você está lendo isto no WhatsApp, o canal está configurado. "
        "A partir daqui os alertas críticos chegam sozinhos.",
        cfg,
    )
    if r.ok:
        print(f"{VERDE}Enviado.{FIM} {CINZA}{r.detalhe}{FIM}")
        if provedor == "console":
            print(f"{AMAR}Ainda em modo console — troque 'provedor' em "
                  f"config/notificacoes.yaml para enviar de verdade.{FIM}")
        return 0
    print(f"{VERM}Falhou:{FIM} {r.detalhe}")
    return 1


def cmd_rotina(args) -> int:
    print(f"{CINZA}═══ rotina · {para_br(agora_iso())} ═══{FIM}")

    # Visitas custam uma chamada por anúncio ativo. Na rodada de hora em hora
    # isso não se paga — o número mal muda. Uma vez por dia basta.
    con_marca = db.conectar()
    from datetime import datetime
    from core.utils import TZ_BR
    if not args.sem_visitas:
        args.sem_visitas = not notify.na_hora_de(
            con_marca, "visitas_diarias", (6, 0), datetime.now(TZ_BR))
    con_marca.close()

    codigo = cmd_coletar(args)
    print()
    cmd_relatorio(argparse.Namespace(cliente=None))
    print()
    con = db.conectar()
    print(report.resumo_texto(con, 24))

    # A rotina roda várias vezes por dia. O resumo completo sai uma vez,
    # na hora configurada; nas demais rodadas só o que for crítico e novo.
    from datetime import datetime
    from core.utils import TZ_BR
    agora = datetime.now(TZ_BR)

    cfg_n = notify.carregar_config()
    regras_n = cfg_n.get("regras") or {}

    # Manutenção do histórico: uma vez por dia, de madrugada, ANTES do mapa —
    # que é o passo que mais grava linha. Compactar primeiro deixa espaço.
    dias_detalhe = int(regras_n.get("dias_de_historico_detalhado", 90))
    if dias_detalhe > 0 and notify.na_hora_de(
            con, "compactar_historico",
            notify._ler_horario(regras_n.get("horario_da_compactacao"), "03:00"), agora):
        try:
            r = manutencao.compactar(con, dias=dias_detalhe)
            if r["anuncios"] or r["concorrentes"]:
                print(f"{CINZA}histórico: {r['anuncios'] + r['concorrentes']} leituras "
                      f"anteriores a {r['corte'][:10]} viraram resumo diário{FIM}")
                manutencao.recuperar_espaco(con)
        except Exception as erro:
            print(f"{AMAR}compactação do histórico falhou: {str(erro)[:90]}{FIM}")

    # Mapa de concorrentes: uma vez por dia, na primeira rodada após o horário.
    if notify.na_hora_de(con, "mapa_diario", notify.horario_do_mapa(cfg_n), agora):
        print(f"\n{CINZA}mapeando concorrentes…{FIM}")
        cmd_mapear(argparse.Namespace(alvo=args.alvo, cep=None, sem_frete=False,
                                      procurar=None, detalhado=False, debug=args.debug))

    # Resumo semanal de concorrência, no dia da semana configurado.
    dia_semanal = int(regras_n.get("dia_do_resumo_semanal", 0))
    horario_semanal = notify._ler_horario(
        regras_n.get("horario_do_resumo_semanal") or regras_n.get("horario_do_resumo"),
        "07:30")
    if dia_semanal >= 0 and notify.na_hora_de(con, "resumo_semanal", horario_semanal,
                                              agora, dia_da_semana=dia_semanal):
        for conta in resolver_contas(args.alvo):
            texto = confrontos.resumo_semanal(con, conta.slug)
            if texto:
                r = notify.enviar(texto, cfg_n)
                print(f"{CINZA}resumo semanal → {r.detalhe}{FIM}")

    if args.resumo or notify.na_hora_de(con, "resumo_diario",
                                        notify.horario_do_resumo(cfg_n), agora):
        r = notify.enviar_resumo(con)
        print(f"\n{CINZA}resumo diário → {r.detalhe}{FIM}")
    else:
        r = notify.notificar_pendentes(con)
        print(f"\n{CINZA}notificação → {r.detalhe}{FIM}")

    con.close()
    return codigo


# ----------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser(prog="zion-ml", description="Operação multi-conta de Mercado Livre")
    p.add_argument("--debug", action="store_true", help="mostra o traceback completo em caso de erro")
    sub = p.add_subparsers(dest="comando", required=True)

    sub.add_parser("contas", help="lista clientes e contas").set_defaults(fn=cmd_contas)

    sub.add_parser("maquina",
                   help="raio-x da máquina: python, bibliotecas e tarefas agendadas"
                   ).set_defaults(fn=cmd_maquina)

    s = sub.add_parser("compactar",
                       help="condensa o histórico velho em resumo diário")
    s.add_argument("--dias", type=int, default=90,
                   help="quantos dias manter em detalhe (padrão: 90)")
    s.add_argument("--simular", action="store_true",
                   help="mostra o que seria condensado, sem alterar nada")
    s.set_defaults(fn=cmd_compactar)

    s = sub.add_parser("precos",
                       help="confere a planilha de custo e mostra o piso de preço")
    s.add_argument("alvo", help="slug da conta, ou 'todas' para o panorama")
    s.add_argument("--modelo", action="store_true",
                   help="gera a lista de anúncios sem custo, para o cliente preencher")
    s.set_defaults(fn=cmd_precos)

    s = sub.add_parser("tarifas",
                       help="pergunta ao ML a comissão real de cada anúncio")
    s.add_argument("alvo")
    s.set_defaults(fn=cmd_tarifas)

    s = sub.add_parser("promocoes",
                       help="campanhas que o ML oferece, com veredito de piso")
    s.add_argument("alvo")
    s.add_argument("--usar-cache", action="store_true",
                   help="lê a última coleta em vez de chamar a API")
    s.set_defaults(fn=cmd_promocoes)

    s = sub.add_parser("cupons",
                       help="campanhas de cupom: quantos foram usados e quanto custaram")
    s.add_argument("alvo", nargs="?", default=None,
                   help="slug da conta, id do cliente ou 'todas'")
    s.add_argument("--usar-cache", action="store_true",
                   help="lê a última coleta em vez de chamar a API")
    s.add_argument("--horas", type=int, default=24,
                   help="janela para comparar o uso com a leitura anterior")
    s.add_argument("--enviar", action="store_true",
                   help="manda o resumo do cupom pelo canal configurado (Telegram)")
    s.add_argument("--pagina", action="store_true",
                   help="gera a página HTML do cupom para o gestor da conta")
    s.add_argument("--resumo", action="store_true",
                   help="só o cupom: quanto vendeu e quanto custou (para o cliente)")
    s.add_argument("--limite", type=int, default=500,
                   help="quantos pedidos ler na janela (padrão 500)")
    s.add_argument("--refazer", action="store_true",
                   help="apaga o já registrado e relê a janela inteira")
    s.add_argument("--vendas", action="store_true",
                   help="mede quanto o cupom custou em cada anúncio, pelos pedidos")
    s.add_argument("--sondar-vendas", action="store_true",
                   help="procura onde o cupom aparece nos pedidos (só lê, não grava)")
    s.add_argument("--dias", type=int, default=30,
                   help="janela de pedidos para a sonda")
    s.add_argument("--desde", default=None, metavar="AAAA-MM-DD",
                   help="recorta o resumo a partir desta data (ex.: a data em "
                        "que a campanha começou), em vez de contar dias")
    s.set_defaults(fn=cmd_cupons)

    s = sub.add_parser("posicoes",
                       help="importa medições de posição na busca e avalia alertas")
    s.add_argument("alvo", nargs="?", default=None,
                   help="usado só se o arquivo não trouxer o campo 'conta'")
    s.set_defaults(fn=cmd_posicoes)

    sub.add_parser("contatos",
                   help="lista quem falou com o bot e o chat_id de cada um"
                   ).set_defaults(fn=cmd_contatos)

    s = sub.add_parser("vendas",
                       help="lista os pedidos crus, para conferir contra o painel do ML")
    s.add_argument("alvo")
    s.add_argument("--dias", type=int, default=7)
    s.set_defaults(fn=cmd_vendas)

    s = sub.add_parser("checar", help="testa a credencial de uma conta")
    s.add_argument("alvo")
    s.set_defaults(fn=cmd_checar)

    s = sub.add_parser("coletar", help="coleta snapshot e avalia alertas")
    s.add_argument("alvo", nargs="?", default=None, help="slug da conta, id do cliente ou 'todas'")
    s.add_argument("--sem-visitas", action="store_true", help="pula visitas (coleta bem mais rápida)")
    s.set_defaults(fn=cmd_coletar)

    s = sub.add_parser("alertas", help="lista alertas do período")
    s.add_argument("alvo", nargs="?", default=None)
    s.add_argument("--horas", type=int, default=24)
    s.set_defaults(fn=cmd_alertas)

    s = sub.add_parser("relatorio", help="gera o painel HTML")
    s.add_argument("cliente", nargs="?", default=None)
    s.set_defaults(fn=cmd_relatorio)

    s = sub.add_parser("resumo", help="resumo em texto dos alertas")
    s.add_argument("--horas", type=int, default=24)
    s.set_defaults(fn=cmd_resumo)

    s = sub.add_parser("rotina", help="coletar + relatório + notificar (uso diário)")
    s.add_argument("alvo", nargs="?", default=None)
    s.add_argument("--sem-visitas", action="store_true")
    s.add_argument("--resumo", action="store_true",
                   help="força o envio do resumo completo, mesmo fora da hora")
    s.set_defaults(fn=cmd_rotina)

    s = sub.add_parser("notificar", help="envia alertas pendentes pelo canal configurado")
    s.add_argument("alvo", nargs="?", default=None)
    s.add_argument("--resumo", action="store_true", help="envia o resumo do dia AGORA")
    s.add_argument("--semanal", action="store_true",
                   help="envia o resumo de concorrência AGORA")
    s.add_argument("--forcar", action="store_true",
                   help="ignora a janela de silêncio e inclui não-críticos")
    s.set_defaults(fn=cmd_notificar)

    s = sub.add_parser("mapear", help="descobre quem disputa cada produto de catálogo")
    s.add_argument("alvo", nargs="?", default=None)
    s.add_argument("--cep", default=None, help="CEP para calcular o frete dos concorrentes")
    s.add_argument("--sem-frete", action="store_true")
    s.add_argument("--procurar", default=None, help="procura um concorrente pelo nome")
    s.add_argument("--detalhado", action="store_true", help="mostra produto a produto")
    s.set_defaults(fn=cmd_mapear)

    s = sub.add_parser("promocao-sair", help="tira anúncios da campanha que manda no preço (simula por padrão)")
    s.add_argument("slug")
    s.add_argument("itens", nargs="+", help="um ou mais MLB")
    s.add_argument("--tipo", help="sair de um tipo específico (DEAL, SMART, "
                                  "PRICE_DISCOUNT, SELLER_CAMPAIGN); por padrão "
                                  "sai da mais barata")
    s.add_argument("--confirmar", action="store_true", help="sai de verdade")
    s.set_defaults(fn=cmd_promocao_sair)

    s = sub.add_parser("preco", help="muda o preço de anúncios pelo MLB (simula por padrão)")
    s.add_argument("slug")
    s.add_argument("itens", nargs="*", help="um ou mais MLB (não usar com --lista)")
    s.add_argument("--para", type=float, default=None,
                   help="preço novo, em reais — mesmo valor para todos os itens")
    s.add_argument("--lista", default=None,
                   help="CSV (;) com colunas item_id;preco — um valor por item")
    s.add_argument("--confirmar", action="store_true", help="altera de verdade")
    s.set_defaults(fn=cmd_preco)

    s = sub.add_parser("sku", help="corrige o SKU (SELLER_SKU) de um anúncio (simula por padrão)")
    s.add_argument("slug")
    s.add_argument("item", help="MLB do anúncio")
    s.add_argument("--para", required=True, help="SKU novo")
    s.add_argument("--confirmar", action="store_true", help="altera de verdade")
    s.set_defaults(fn=cmd_sku)

    s = sub.add_parser("disponibilidade",
                       help="ajusta o prazo de disponibilidade de estoque (MANUFACTURING_TIME) de anúncios (simula por padrão)")
    s.add_argument("slug")
    s.add_argument("itens", nargs="+", help="um ou mais MLB")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--para", help="prazo novo, ex: '7 dias'")
    g.add_argument("--remover", action="store_true",
                   help="remove o prazo de disponibilidade (o anúncio volta a não mostrar nenhum)")
    s.add_argument("--confirmar", action="store_true", help="altera de verdade")
    s.set_defaults(fn=cmd_disponibilidade)

    s = sub.add_parser("descricao", help="substitui a descrição de um anúncio (simula por padrão)")
    s.add_argument("slug")
    s.add_argument("item", help="MLB do anúncio")
    s.add_argument("--arquivo", required=True, help="arquivo .txt com o texto novo (UTF-8)")
    s.add_argument("--confirmar", action="store_true", help="altera de verdade")
    s.set_defaults(fn=cmd_descricao)

    s = sub.add_parser("imagem-ambientada",
                       help="gera foto de capa ambientada via API da OpenAI (custa por chamada, não simula)")
    s.add_argument("slug")
    s.add_argument("item", help="MLB do anúncio")
    s.add_argument("--prompt", help="sobrescreve o prompt padrão")
    s.set_defaults(fn=cmd_imagem_ambientada)

    s = sub.add_parser("reativar", help="despausa anúncios pelo MLB (simula por padrão)")
    s.add_argument("slug")
    s.add_argument("itens", nargs="+", help="um ou mais MLB")
    s.add_argument("--confirmar", action="store_true", help="reativa de verdade")
    s.set_defaults(fn=cmd_reativar)

    s = sub.add_parser("encerrar", help="encerra anúncios pelo MLB (simula por padrão)")
    s.add_argument("slug")
    s.add_argument("itens", nargs="+", help="um ou mais MLB")
    s.add_argument("--confirmar", action="store_true",
                   help="encerra de verdade — não tem volta")
    s.set_defaults(fn=cmd_encerrar)

    s = sub.add_parser("publicar",
                       help="recadastra UM anúncio a partir de outro (simula por padrão)")
    s.add_argument("slug")
    s.add_argument("origem", nargs="?", default=None,
                   help="MLB do anúncio que serve de base")
    s.add_argument("--lista", default=None,
                   help="CSV (;) com coluna 'origem' e, opcionais, "
                        "'peso', 'preco', 'titulo', 'modalidade'")
    s.add_argument("--continuar", action="store_true",
                   help="não para na primeira recusa")
    s.add_argument("--envio", default="me2", choices=publicacao.MODOS_DE_ENVIO,
                   help="forma de entrega DECLARADA (padrão me2)")
    s.add_argument("--sem-frete-gratis", action="store_true")
    s.add_argument("--estoque", type=int, default=1,
                   help="nasce em 1 de propósito")
    s.add_argument("--preco", type=float, default=None)
    s.add_argument("--titulo", default=None)
    s.add_argument("--modalidade", default=None,
                   help="gold_special (clássico) ou gold_pro (premium)")
    s.add_argument("--peso", default=None,
                   help="peso REAL do produto, ex: '25 kg'. Nunca herdado.")
    s.add_argument("--caixa", default=None,
                   help="medida REAL da embalagem em cm, ex: '140x86x90' "
                        "(comprimento x largura x altura). Nunca menor que a real.")
    s.add_argument("--peso-caixa", default=None,
                   help="peso bruto da embalagem, ex: '28 kg'")
    s.add_argument("--herdar-peso", action="store_true",
                   help="copia o WEIGHT do anúncio de origem — só use se souber "
                        "que aquele número está certo")
    s.add_argument("--atributo", action="append", default=None,
                   help="atributo extra ID=VALOR, repetível, ex: "
                        "--atributo EMPTY_GTIN_REASON='O produto não tem código cadastrado'")
    s.add_argument("--prazo", default=None,
                   help="prazo de disponibilidade, ex: '25 dias'. Vira o "
                        "sale_term MANUFACTURING_TIME. Coluna 'prazo' no CSV "
                        "manda por item.")
    s.add_argument("--acrescimo", type=float, default=None,
                   help="percentual sobre o preço da origem, ex: 8 para +8%%. "
                        "Usado quando --preco não é informado.")
    s.add_argument("--sincronizar", action="store_true",
                   help="pendura o anúncio novo no MESMO User Product da origem "
                        "— é o que o ML chama de anúncios sincronizados. "
                        "Fotos e ficha vêm do produto; título, peso e fotos não "
                        "se declaram aqui.")
    s.add_argument("--fotos", nargs="+", default=None,
                   help="arquivos de imagem do disco, NA ORDEM em que devem "
                        "aparecer, ou uma pasta (aí entra em ordem de nome). "
                        "Substitui as fotos herdadas do anúncio de origem.")
    s.add_argument("--copiar-descricao", action="store_true")
    s.add_argument("--conta-origem", default=None,
                   help="slug da conta DONA do anúncio de origem, quando é "
                        "diferente de <slug> — o ML recusa ler item de outro "
                        "vendedor (403 access_denied), então a leitura é feita "
                        "com o token desta conta antes de montar o payload "
                        "para publicar em <slug>")
    s.add_argument("--json", action="store_true", help="mostra o payload inteiro")
    s.add_argument("--publicar", action="store_true",
                   help="sai da simulação e escreve de verdade")
    s.add_argument("--sim", action="store_true", help="não pergunta antes de publicar")
    s.set_defaults(fn=cmd_publicar)

    s = sub.add_parser("cobertura",
                       help="quais produtos têm clássico, premium e catálogo")
    s.add_argument("alvo", nargs="?", default=None)
    s.add_argument("--detalhado", action="store_true", help="produto a produto")
    s.add_argument("--limite", type=int, default=25,
                   help="quantos produtos listar no detalhe")
    s.add_argument("--csv", default=None, help="grava a lista completa numa planilha")
    s.set_defaults(fn=cmd_cobertura)

    s = sub.add_parser("diagnostico", help="raio-X automático da conta")
    s.add_argument("alvo", nargs="?", default=None)
    s.add_argument("--enviar", action="store_true", help="manda no canal configurado")
    s.add_argument("--detalhado", action="store_true")
    s.set_defaults(fn=cmd_diagnostico)

    s = sub.add_parser("funil",
                       help="em qual degrau do funil cada anúncio trava (exposição/conversão/teto)")
    s.add_argument("alvo", nargs="?", default=None)
    s.add_argument("--dias", type=int, default=funil.JANELA_DIAS_PADRAO,
                   help="janela em dias (padrão 7, mesma da visitas_7d)")
    s.add_argument("--item", default=None, help="só este MLB")
    s.add_argument("--veredito", default=None,
                   help="detalha só um veredito: RUPTURA, PAUSADO, SEM_EXPOSICAO, "
                        "SEM_CONVERSAO, TETO_DE_CATEGORIA, SAUDAVEL, SEM_PAR_SUFICIENTE")
    s.add_argument("--limite", type=int, default=10)
    s.set_defaults(fn=cmd_funil)

    s = sub.add_parser("vigiar",
                       help="vigia uma ficha de catálogo por link (concorrente entra sozinho)")
    s.add_argument("slug")
    s.add_argument("link")
    s.add_argument("--comparar-com", default=None,
                   help="MLB do SEU anúncio que esse concorrente enfrenta")
    s.add_argument("--apelido", default=None)
    s.set_defaults(fn=cmd_vigiar)

    s = sub.add_parser("limpar-alertas",
                       help="apaga alertas de um período (para uma leva errada)")
    s.add_argument("--horas", type=int, default=6)
    s.add_argument("--regra", default=None, help="apaga só de uma regra")
    s.add_argument("--sim", action="store_true",
                   help="não pergunta (necessário pela fila de pedidos)")
    s.set_defaults(fn=cmd_limpar_alertas)

    sub.add_parser("testar-notificacao",
                   help="manda uma mensagem de teste pelo canal configurado"
                   ).set_defaults(fn=cmd_testar_notificacao)

    args = p.parse_args()
    for campo, padrao in (("sem_visitas", False), ("resumo", False), ("forcar", False),
                          ("cep", None), ("sem_frete", False), ("procurar", None),
                          ("detalhado", False), ("semanal", False), ("alvo", None),
                          ("horas", 24), ("regra", None), ("comparar_com", None),
                          ("apelido", None), ("link", None), ("slug", None),
                          ("enviar", False), ("limite", 25), ("csv", None)):
        if not hasattr(args, campo):
            setattr(args, campo, padrao)
    return args.fn(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError) as erro:
        # erro de configuração: mostrar a mensagem, não um traceback
        print(f"{VERM}{str(erro).strip(chr(39))}{FIM}")
        sys.exit(1)
    except BrokenPipeError:
        # acontece quando a saída é cortada por `| head`; não é erro
        sys.exit(0)
    except KeyboardInterrupt:
        print(f"\n{AMAR}interrompido{FIM}")
        sys.exit(130)
