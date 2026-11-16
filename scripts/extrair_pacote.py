# -*- coding: utf-8 -*-
"""
extrair_pacote.py -- extrai os arquivos embutidos no atualizador da ADATA.

O FWUpdate_*.exe carrega um ZIP no meio do PE, com as imagens de firmware (.fw)
e o UpdateFWInfo.ini. Este script localiza os membros varrendo as assinaturas de
cabecalho local, descomprime e grava cada um em disco, conferindo o CRC.

SOMENTE LEITURA sobre o executavel -- nada e modificado nele.

Para que serve:
  * inspecionar a whitelist sem depender do atualizador
  * obter a imagem .fw crua, caso voce queira o caminho via nvme-cli no Linux
    (fw-download / fw-commit) em vez do executavel do Windows

USO
    python extrair_pacote.py --exe FWUpdate_3.2.F.66.exe --out extraido/
    python extrair_pacote.py --exe FWUpdate_3.2.F.66.exe --out extraido/ --detalhes

AVISO sobre o caminho nvme-cli: NAO foi testado neste projeto. O executavel da
ADATA faz mais coisas que um fw-download cru (ha um PowerCtrl=2 e uma verificacao
interna de versao no INI). Um fw-download manual com a imagem errada, ou sem a
sequencia que o controlador espera, pode brickar o SSD. O caminho verificado
aqui foi o executavel com a whitelist corrigida.

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
    """Varre por cabecalhos locais de ZIP. Nao usa o EOCD porque os offsets dele
    sao relativos ao inicio do ZIP, nao do arquivo que o contem."""
    out = []
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
            continue          # assinatura falsa dentro de dados comprimidos
        ini = p + 30 + nlen + elen
        if ini + csz > len(d):
            continue
        out.append(dict(nome=nome, hdr=p, dados=ini, meth=meth,
                        crc=crc, csz=csz, usz=usz))
    return out


def texto(b):
    for enc in ("utf-16-le", "utf-8", "latin-1"):
        try:
            s = b.decode(enc)
            if s.count("\x00") < len(s) / 4:
                return s, enc
        except Exception:
            pass
    return None, None


def main():
    ap = argparse.ArgumentParser(description="Extrai o ZIP embutido no FWUpdate_*.exe")
    ap.add_argument("--exe", required=True)
    ap.add_argument("--out", default="extraido")
    ap.add_argument("--detalhes", action="store_true",
                    help="mostra o cabecalho hex e as strings iniciais das imagens .fw")
    a = ap.parse_args()

    if not os.path.exists(a.exe):
        sys.exit("nao achei: %s" % a.exe)
    d = open(a.exe, "rb").read()
    print("entrada: %s  (%d bytes)" % (os.path.abspath(a.exe), len(d)))
    print("sha256 : %s\n" % hashlib.sha256(d).hexdigest())

    membros = acha_membros(d)
    if not membros:
        sys.exit("nenhum ZIP embutido encontrado neste executavel.")

    os.makedirs(a.out, exist_ok=True)
    extraidos = {}
    for m in membros:
        bruto = d[m["dados"]:m["dados"] + m["csz"]]
        try:
            cont = bruto if m["meth"] == 0 else zlib.decompressobj(-15).decompress(bruto)
        except Exception as e:
            print("  [erro] %-24s %s" % (m["nome"], e))
            continue
        crc_ok = (zlib.crc32(cont) & 0xFFFFFFFF) == m["crc"] and len(cont) == m["usz"]
        destino = os.path.join(a.out, m["nome"])
        with open(destino, "wb") as f:
            f.write(cont)
        extraidos[m["nome"]] = cont
        print("  [%s] %-24s %9d B  hdr 0x%06X  sha256=%s"
              % ("ok" if crc_ok else "CRC!", m["nome"], len(cont), m["hdr"],
                 hashlib.sha256(cont).hexdigest()[:24]))

    ini = extraidos.get("UpdateFWInfo.ini")
    if ini:
        s, enc = texto(ini)
        if s:
            print("\n=== UpdateFWInfo.ini (%s) ===" % enc)
            for l in s.splitlines():
                l = l.strip()
                if l and not l.startswith("﻿["):
                    print("  %s" % l)

    if a.detalhes:
        for nome, cont in extraidos.items():
            if not nome.lower().endswith(".fw"):
                continue
            print("\n=== %s ===" % nome)
            print("  tamanho: %d bytes  (multiplo de 4096: %s)"
                  % (len(cont), len(cont) % 4096 == 0))
            print("  cabecalho:")
            for i in range(0, 128, 16):
                ch = cont[i:i + 16]
                print("    0x%04X  %-47s  %s"
                      % (i, " ".join("%02X" % b for b in ch),
                         "".join(chr(b) if 32 <= b < 127 else "." for b in ch)))
            print("  strings no inicio:")
            vistos = set()
            for mm in re.finditer(rb"[ -~]{4,}", cont[:8192]):
                t = mm.group().decode("ascii", "ignore")
                if t not in vistos:
                    vistos.add(t)
                    print("    0x%04X  %s" % (mm.start(), t))

    print("\nExtraido em: %s" % os.path.abspath(a.out))
    print("As imagens .fw sao binarios assinados da ADATA -- nao redistribua nem modifique.")


if __name__ == "__main__":
    main()
