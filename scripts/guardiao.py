#!/usr/bin/env python3
"""
Guardião do vigia: confere o batimento e ressuscita se necessário.

Chamado pela rotina de hora em hora. Se o vigia morreu — travou, a máquina
reiniciou, alguém fechou a janela — ele volta sozinho, sem janela.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BATIMENTO = RAIZ / "data" / "vigia.batimento"
SUBIU = RAIZ / "data" / "vigia.subiu"

def _intervalo_configurado() -> int:
    """
    Lê o intervalo do vigia sem importar o core — o guardião precisa funcionar
    mesmo se alguma coisa do core estiver quebrada. Se ele depender do que
    está quebrado, deixa de ser guardião.
    """
    import re
    caminho = RAIZ / "config" / "notificacoes.yaml"
    try:
        m = re.search(r"intervalo_vigia_segundos:\s*(\d+)",
                      caminho.read_text(encoding="utf-8"))
        return int(m.group(1)) if m else 300
    except Exception:
        return 300


# Tolerância: 3 ciclos. Um ciclo lento não pode disparar um segundo vigia.
TOLERANCIA_SEGUNDOS = _intervalo_configurado() * 3


def idade_do_batimento() -> float | None:
    if not BATIMENTO.exists():
        return None
    try:
        carimbo = datetime.fromisoformat(BATIMENTO.read_text(encoding="utf-8").strip())
    except Exception:
        return None
    if carimbo.tzinfo is None:
        carimbo = carimbo.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - carimbo).total_seconds()


def executavel_sem_janela() -> str:
    pythonw = RAIZ / ".venv" / "Scripts" / "pythonw.exe"
    if pythonw.exists():
        return str(pythonw)
    python = RAIZ / ".venv" / "Scripts" / "python.exe"
    return str(python) if python.exists() else sys.executable


def codigo_mudou_depois_do_vigia() -> bool:
    """
    O vigia carrega o código na memória ao subir. Se um arquivo do core mudou
    depois disso, o processo em execução está rodando a versão antiga — e
    correções entregues não valem até ele reiniciar.

    Compara com data/vigia.subiu, escrito UMA vez quando o vigia sobe.

    Usava o batimento antes, e era um bug silencioso: o batimento é reescrito
    a cada ciclo, então "quando o vigia subiu" dava sempre 'agora' e nenhuma
    atualização de código era detectada. O vigia rodou horas com a versão
    velha na memória enquanto o disco já tinha a nova.
    """
    if not SUBIU.exists():
        # Vigia vivo sem registro de subida = processo anterior a esta versão,
        # que ainda não sabia registrar. Por definição está com código velho.
        return BATIMENTO.exists()
    subiu_em = SUBIU.stat().st_mtime
    alvos = [RAIZ / "vigia.py", *(RAIZ / "core").glob("*.py"),
             *(RAIZ / "scripts").glob("*.py")]
    return any(a.exists() and a.stat().st_mtime > subiu_em + 60 for a in alvos)


def derrubar_vigia() -> int:
    """
    Mata qualquer vigia em execução. Feito em Python de propósito: a mesma
    coisa em .bat exige PowerShell aninhado com aspas escapadas, que quebra
    de um jeito silencioso e difícil de ver.
    """
    mortos = 0
    try:
        import platform
        if platform.system() == "Windows":
            saida = subprocess.run(
                ["wmic", "process", "where",
                 "name like '%python%'", "get", "processid,commandline", "/format:csv"],
                capture_output=True, text=True, timeout=30)
            for linha in saida.stdout.splitlines():
                if "vigia.py" in linha:
                    partes = [x for x in linha.strip().split(",") if x.strip().isdigit()]
                    if partes:
                        subprocess.run(["taskkill", "/PID", partes[-1], "/F"],
                                       capture_output=True, timeout=15)
                        mortos += 1
        else:
            r = subprocess.run(["pkill", "-f", "vigia.py"], capture_output=True, timeout=15)
            mortos = 1 if r.returncode == 0 else 0
    except Exception as erro:
        print(f"não consegui derrubar o vigia antigo: {erro}")
    BATIMENTO.unlink(missing_ok=True)
    SUBIU.unlink(missing_ok=True)
    return mortos


def main() -> int:
    if "--so-derrubar" in sys.argv:
        n = derrubar_vigia()
        print(f"vigia derrubado ({n} processo(s))" if n else "nenhum vigia rodando")
        return 0

    if "--reiniciar" in sys.argv:
        n = derrubar_vigia()
        print(f"vigia antigo derrubado ({n} processo(s))" if n else "nenhum vigia rodando")

    idade = idade_do_batimento()

    if idade is not None and idade < TOLERANCIA_SEGUNDOS and codigo_mudou_depois_do_vigia():
        print("código atualizado depois que o vigia subiu — reiniciando")
        derrubar_vigia()
        idade = None

    if idade is not None and idade < TOLERANCIA_SEGUNDOS:
        print(f"vigia vivo (último batimento há {int(idade)}s)")
        return 0

    motivo = "nunca iniciou" if idade is None else f"parado há {int(idade)}s"
    print(f"vigia {motivo} — subindo de novo")

    try:
        kwargs = {"cwd": str(RAIZ), "close_fds": True}
        if hasattr(subprocess, "CREATE_NO_WINDOW"):        # Windows
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        subprocess.Popen([executavel_sem_janela(), str(RAIZ / "vigia.py")], **kwargs)
        print("vigia reiniciado")
        return 0
    except Exception as erro:
        print(f"falhou ao reiniciar o vigia: {erro}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
