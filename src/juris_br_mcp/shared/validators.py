"""Validadores para numero CNJ e dados processuais."""

from __future__ import annotations

import re

# Formato CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO
# Ex.: 0001234-56.2023.8.26.0100
_CNJ_PATTERN = re.compile(r"^(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})$")

# Mesmo numero sem formatacao
_CNJ_DIGITS_PATTERN = re.compile(r"^\d{20}$")


def _formato_cnj_ok(numero: str) -> bool:
    limpo = numero.strip()
    if _CNJ_PATTERN.match(limpo):
        return True
    # Aceita versao sem pontuacao (20 digitos)
    digits_only = re.sub(r"[-.]", "", limpo)
    return bool(_CNJ_DIGITS_PATTERN.match(digits_only))


def calcular_digito_cnj(numero: str) -> int:
    """Calcula o digito verificador (DD) do numero CNJ (Res. CNJ 65/2008, modulo 97).

    DD = 98 - (NNNNNNN AAAA J TR OOOO 00 mod 97). Recebe o numero com ou sem
    formatacao; os digitos DD informados sao ignorados no calculo.
    """
    d = re.sub(r"\D", "", numero)
    if len(d) != 20:
        raise ValueError("Numero CNJ deve ter 20 digitos.")
    base = d[0:7] + d[9:13] + d[13] + d[14:16] + d[16:20] + "00"
    return 98 - (int(base) % 97)


def diagnosticar_numero_cnj(numero: str) -> str | None:
    """Retorna o motivo da invalidade do numero CNJ, ou None se for valido."""
    if not _formato_cnj_ok(numero):
        return (
            "Formato inválido. Use o padrão CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO "
            "ou os 20 dígitos sem formatação."
        )
    d = re.sub(r"\D", "", numero)
    esperado = calcular_digito_cnj(d)
    if int(d[7:9]) != esperado:
        return (
            f"Dígito verificador não confere: informado {d[7:9]}, esperado {esperado:02d}. "
            "Confira se o número foi digitado corretamente."
        )
    return None


def validar_numero_cnj(numero: str) -> bool:
    """Valida formato CNJ (com ou sem formatacao) e o digito verificador (modulo 97)."""
    return diagnosticar_numero_cnj(numero) is None


def normalizar_numero_cnj(numero: str) -> str:
    """Retorna o numero sem formatacao (20 digitos) para uso na API DataJud."""
    return re.sub(r"[-.]", "", numero.strip())


def extrair_tribunal_cnj(numero: str) -> str | None:
    """Extrai a sigla do tribunal a partir do numero CNJ.

    O segmento J.TT do numero CNJ indica:
    - J=1: STF
    - J=2: CNJ
    - J=3: STJ
    - J=4: Justica Federal
    - J=5: Trabalho
    - J=6: Eleitoral
    - J=7: Militar da Uniao
    - J=8: Estadual/DF
    - J=9: Militar Estadual

    Retorna None se o numero for invalido ou se o tribunal nao for identificavel
    sem tabela auxiliar (ex.: J=8 TT=26 = TJSP, mas exige lookup).
    """
    limpo = numero.strip()
    match = _CNJ_PATTERN.match(limpo)
    if not match:
        return None
    # grupos: nnnnnnn, dd, aaaa, j, tt, oooo
    j = match.group(4)
    tt = match.group(5)
    return f"J{j}T{tt}"  # placeholder - Fase 1 expande com tabela completa


__all__ = [
    "calcular_digito_cnj",
    "diagnosticar_numero_cnj",
    "extrair_tribunal_cnj",
    "normalizar_numero_cnj",
    "validar_numero_cnj",
]
