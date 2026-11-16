# -*- coding: utf-8 -*-
"""
verifica_patch.py — conferencia SOMENTE LEITURA do executavel modificado.

Compara o executavel gerado contra o original da ADATA e da um veredito. Nao
escreve nada, nao altera nada, nao toca no disco alem de ler os dois arquivos.

Rode isto ANTES de executar o instalador modificado. E uma verificacao
independente do script que gerou o arquivo -- se os dois discordarem, nao use.

Criterios para APROVADO:
  1. as imagens .fw tem SHA-256 IDENTICO ao original (o firmware nao foi tocado)
  2. todos os CRCs do ZIP estao consistentes com o conteudo
  3. o modelo esperado esta na whitelist ModelName (se --esperar for passado)
  4. o tamanho do executavel foi preservado

USO
    python verifica_patch.py --original FWUpdate_3.2.F.66.exe \
                             --patched  FWUpdate_3.2.F.66_PATCHED.exe \
                             --esperar  "AGAMMIXS70B-2T-CS"

Dominio publico (CC0). Sem garantia de especie alguma.
"""
import argparse
import hashlib
import os
import re
import struct
import sys
import zlib


def acha_membros(d):
    out = {}
    for m in re.finditer(rb"PK\x03\x04", d):
        p = m.start()
        if p + 30 > len(d):
            continue
        (_sig, _ver, _flag, meth, _mt, _md,
         crc, csz, usz, nlen, elen) = struct.unpack("<IHHHHHIIIHH", d[p:p + 30])
        if nlen == 0 or nlen > 200 or p + 30 + nlen > len(d):
            continue
        nome = d[p + 30:p + 30 + nlen].decode("ascii", "ignore")
        if not re.match(r"^[\w\.\- ]+$", nome):
            continue
        ini = p + 30 + nlen + elen
        if ini + csz > len(d):
            continue
        try:
            cont = d[ini:ini + csz] if meth == 0 else \
                zlib.decompressobj(-15).decompress(d[ini:ini + csz])
        except Exception as e:
            out[nome] = dict(erro=str(e), sha=None, ok=False, cont=None)
            continue
        ok = (zlib.crc32(cont) & 0xFFFFFFFF) == crc and len(cont) == usz
        out[nome] = dict(erro=None, sha=hashlib.sha256(cont).hexdigest(),
                         ok=ok, cont=cont, tam=len(cont))
    return out


def texto_ini(b):
    if b.startswith(b"\xff\xfe"):
        return b.decode("utf-16-le")
    if b.startswith(b"\xfe\xff"):
        return b.decode("utf-16-be")
    if b.startswith(b"\xef\xbb\xbf"):
        return b.decode("utf-8-sig")
    return b.decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser(description="Verificacao read-only do EXE modificado.")
    ap.add_argument("--original", required=True)
    ap.add_argument("--patched", required=True)
    ap.add_argument("--esperar", metavar="MODELO",
                    help="Model Number que deve constar na whitelist")
    a = ap.parse_args()

    for f in (a.original, a.patched):
        if not os.path.exists(f):
            sys.exit("nao achei: %s" % f)

    da = open(a.original, "rb").read()
    db = open(a.patched, "rb").read()

    print("original  : %-9d bytes  sha256=%s" % (len(da), hashlib.sha256(da).hexdigest()))
    print("modificado: %-9d bytes  sha256=%s" % (len(db), hashlib.sha256(db).hexdigest()))
    tam_ok = len(da) == len(db)
    print("tamanho preservado: %s" % ("sim" if tam_ok else "NAO"))

    ma, mb = acha_membros(da), acha_membros(db)

    print("\n=== membro a membro ===")
    fw_ok = True
    crc_ok = True
    for nome in sorted(set(ma) | set(mb)):
        A = ma.get(nome)
        B = mb.get(nome)
        if A is None or B is None:
            print("  %-24s  PRESENTE SO EM UM DOS ARQUIVOS" % nome)
            fw_ok = False
            continue
        igual = A["sha"] == B["sha"]
        if not B["ok"]:
            crc_ok = False
        print("  %-24s CRC_orig=%-5s CRC_novo=%-5s  %s"
              % (nome, "ok" if A["ok"] else "FALHA",
                 "ok" if B["ok"] else "FALHA",
                 "IDENTICO" if igual else "DIFERENTE"))
        if nome.lower().endswith(".fw"):
            print("      sha256 original  : %s" % A["sha"])
            print("      sha256 modificado: %s" % B["sha"])
            if not igual:
                print("      *** ALERTA: IMAGEM DE FIRMWARE ALTERADA -- NAO USE ***")
                fw_ok = False

    print("\n=== configuracao resultante ===")
    modelo_ok = True
    ini = mb.get("UpdateFWInfo.ini")
    if ini and ini["cont"] is not None:
        txt = texto_ini(ini["cont"])
        for l in txt.splitlines():
            if l.startswith(("TITLE=", "SOCID=", "ModelName=", "FWVersion=")):
                print("  %s" % l.strip())
        if a.esperar:
            modelo_ok = a.esperar in txt
            print("\n  contem '%s': %s" % (a.esperar, "SIM" if modelo_ok else "NAO"))
    else:
        print("  UpdateFWInfo.ini ilegivel")
        modelo_ok = False

    dif = [i for i in range(min(len(da), len(db))) if da[i] != db[i]]
    print("\n=== diff binario ===")
    if dif:
        print("  bytes alterados: %d   faixa: 0x%06X - 0x%06X"
              % (len(dif), dif[0], dif[-1]))
    else:
        print("  nenhum byte alterado (os arquivos sao iguais?)")

    print("\n" + "=" * 60)
    veredito = fw_ok and crc_ok and modelo_ok and tam_ok and bool(dif)
    print("VEREDITO: %s" % ("APROVADO" if veredito else "REPROVADO -- NAO USE"))
    print("  imagens .fw intactas ......... %s" % ("sim" if fw_ok else "NAO"))
    print("  CRCs do zip consistentes ..... %s" % ("sim" if crc_ok else "NAO"))
    if a.esperar:
        print("  modelo na whitelist .......... %s" % ("sim" if modelo_ok else "NAO"))
    else:
        print("  modelo na whitelist .......... nao conferido (passe --esperar)")
    print("  tamanho do EXE preservado .... %s" % ("sim" if tam_ok else "NAO"))
    print("=" * 60)
    if not veredito:
        print("\nNao execute este arquivo. Gere de novo a partir do original.")
        sys.exit(1)
    print("\nAprovado. Faca backup completo antes de executar.")


if __name__ == "__main__":
    main()
