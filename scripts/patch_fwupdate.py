# -*- coding: utf-8 -*-
"""
patch_fwupdate.py — acrescenta modelos a whitelist ModelName do atualizador de
firmware da ADATA (FWUpdate_*.exe), sem alterar as imagens de firmware assinadas.

POR QUE ISTO EXISTE
-------------------
O instalador oficial traz, num ZIP embutido no EXE, um UpdateFWInfo.ini com uma
lista ModelName. Se o Model Number que o SSD reporta nao estiver nessa lista, o
atualizador simplesmente nao mostra o disco -- em nenhuma maquina, em nenhuma
configuracao. No pacote FWUpdate_32F66 a linha do PS5 esta coberta por numero de
peca (todos os APSFG-*), mas a linha GAMMIX so pelo nome de marketing; nenhum
AGAMMIXS70B-* consta. Drives de varejo que se identificam pelo numero de peca
ficam de fora, mesmo com a versao de firmware atual constando em FWVersion --
ou seja, a ADATA pretendia que fossem atualizaveis.

COMO FUNCIONA
-------------
O tamanho COMPRIMIDO do membro INI e preservado: recomprime o texto novo e
preenche o resto com zeros depois do bloco BFINAL do deflate (o descompressor
para no BFINAL e ignora o resto). Assim nenhum offset do ZIP ou do PE se desloca
e o tamanho do EXE nao muda. So o CRC32 e o tamanho descomprimido sao reescritos,
no cabecalho local e no diretorio central.

As imagens .fw NAO sao tocadas. O script aborta se qualquer byte dentro delas
mudar -- o firmware gravado no SSD e o oficial da ADATA, bit por bit.

USO
---
    python patch_fwupdate.py --exe FWUpdate_3.2.F.66.exe \
                             --add "AGAMMIXS70B-2T-CS" \
                             --out FWUpdate_3.2.F.66_PATCHED.exe

    # so inspecionar, sem gerar nada:
    python patch_fwupdate.py --exe FWUpdate_3.2.F.66.exe --listar

Requer apenas Python 3 e a biblioteca padrao. Sem dependencias.

AVISO: leia o README antes. Atualizacao de firmware pode brickar o SSD e voce
perde qualquer chance de RMA. Faca backup completo.

Dominio publico (CC0). Sem garantia de especie alguma.
"""
import argparse
import hashlib
import os
import re
import struct
import sys
import zlib

INI_NOME = "UpdateFWInfo.ini"


# ---------------------------------------------------------------- leitura do zip
def acha_membros(d):
    """Localiza os membros do ZIP embutido varrendo por assinaturas de cabecalho
    local. Retorna lista de dicts. Nao usa o EOCD porque o ZIP esta no meio de um
    PE e os offsets do EOCD sao relativos ao inicio do ZIP, nao do arquivo."""
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


def inflar(bloco, meth):
    if meth == 0:
        return bloco
    if meth == 8:
        return zlib.decompressobj(-15).decompress(bloco)
    raise ValueError("metodo de compressao %d nao suportado" % meth)


def decodifica_ini(bruto):
    """O INI da ADATA e UTF-16LE com BOM. Detecta mesmo assim, por seguranca."""
    if bruto.startswith(b"\xff\xfe"):
        return bruto.decode("utf-16-le"), "utf-16-le"
    if bruto.startswith(b"\xfe\xff"):
        return bruto.decode("utf-16-be"), "utf-16-be"
    if bruto.startswith(b"\xef\xbb\xbf"):
        return bruto.decode("utf-8-sig"), "utf-8-sig"
    return bruto.decode("utf-8"), "utf-8"


def comprime(b):
    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    return co.compress(b) + co.flush()


# ---------------------------------------------------------------------- programa
def main():
    ap = argparse.ArgumentParser(
        description="Acrescenta modelos a whitelist do atualizador da ADATA.")
    ap.add_argument("--exe", required=True, help="FWUpdate_*.exe original")
    ap.add_argument("--add", action="append", default=[], metavar="MODELO",
                    help="Model Number a acrescentar (repetivel). Use exatamente "
                         "a string que o SSD reporta em MN.")
    ap.add_argument("--out", help="arquivo a gerar (default: <exe>_PATCHED.exe)")
    ap.add_argument("--listar", action="store_true",
                    help="so mostra o conteudo do pacote e sai, sem gerar nada")
    ap.add_argument("--forcar", action="store_true",
                    help="grava mesmo se o modelo ja estiver na lista")
    a = ap.parse_args()

    if not os.path.exists(a.exe):
        sys.exit("nao achei o executavel: %s" % a.exe)

    orig = open(a.exe, "rb").read()
    print("entrada : %s" % os.path.abspath(a.exe))
    print("tamanho : %d bytes" % len(orig))
    print("sha256  : %s" % hashlib.sha256(orig).hexdigest())

    membros = acha_membros(orig)
    if not membros:
        sys.exit("nenhum ZIP embutido encontrado. Este executavel e do tipo certo?")

    print("\n=== membros do ZIP embutido ===")
    alvo = None
    for m in membros:
        try:
            cont = inflar(orig[m["dados"]:m["dados"] + m["csz"]], m["meth"])
            ok = (zlib.crc32(cont) & 0xFFFFFFFF) == m["crc"] and len(cont) == m["usz"]
        except Exception as e:
            print("  %-24s  ERRO: %s" % (m["nome"], e))
            continue
        print("  %-24s %9d B  hdr 0x%06X  CRC %s"
              % (m["nome"], len(cont), m["hdr"], "ok" if ok else "FALHA"))
        if m["nome"] == INI_NOME:
            alvo = m
            alvo["conteudo"] = cont

    if alvo is None:
        sys.exit("\n%s nao encontrado no pacote." % INI_NOME)
    if alvo["meth"] != 8:
        sys.exit("\n%s nao esta em deflate (metodo=%d); nao suportado."
                 % (INI_NOME, alvo["meth"]))

    txt, enc = decodifica_ini(alvo["conteudo"])
    print("\n=== %s (%s) ===" % (INI_NOME, enc))
    for l in txt.splitlines():
        if l.startswith(("TITLE=", "SOCID=", "ModelName=", "FWVersion=",
                         "iInternalFWVersionCheckPart=", "PowerCtrl=")):
            print("  %s" % l.strip())

    linhas = [l for l in txt.splitlines() if l.startswith("ModelName=")]
    if len(linhas) != 1:
        sys.exit("esperava exatamente 1 linha ModelName, achei %d" % len(linhas))
    linha_antiga = linhas[0].rstrip("\r")
    modelos = [x for x in linha_antiga[len("ModelName="):].split(";") if x]

    print("\n=== whitelist ModelName atual (%d entradas) ===" % len(modelos))
    for x in modelos:
        print("    %s" % x)

    if a.listar:
        print("\n(--listar: nada foi gerado)")
        return

    if not a.add:
        sys.exit("\nnada a fazer: informe ao menos um --add MODELO "
                 "(ou use --listar para so inspecionar).")

    ja = [x for x in a.add if x in modelos]
    if ja and not a.forcar:
        sys.exit("\nja esta na lista: %s\nNada a fazer. Se o atualizador ainda nao "
                 "enxerga o disco, o problema e outro -- confira a linha FWVersion "
                 "contra o FR do seu SSD." % ", ".join(ja))
    novos = [x for x in a.add if x not in modelos]

    # -------------------------------------------- candidatos que caibam no espaco
    # 1o: acrescenta tudo, preservando a lista original inteira.
    # Se nao couber no tamanho comprimido, vai descartando do FIM da lista
    # original -- as ultimas entradas costumam ser de outra linha de produto.
    candidatos = []
    for k in range(len(modelos), -1, -1):
        candidatos.append(novos + modelos[:k])

    escolhido = None
    for lista in candidatos:
        novo_txt = txt.replace(linha_antiga, "ModelName=" + ";".join(lista))
        if novo_txt == txt:
            sys.exit("falha ao substituir a linha ModelName (formato inesperado)")
        bruto = novo_txt.encode(enc)
        comp = comprime(bruto)
        if len(comp) <= alvo["csz"]:
            escolhido = (lista, bruto, comp)
            break
    if escolhido is None:
        sys.exit("nenhuma variante coube no tamanho comprimido original. "
                 "O nome que voce quer acrescentar e grande demais.")
    lista, bruto, comp = escolhido

    print("\n=== whitelist NOVA (%d entradas) ===" % len(lista))
    for x in lista:
        print("    %s%s" % (x, "   <<< ACRESCENTADO" if x in novos else ""))
    descartadas = [x for x in modelos if x not in lista]
    if descartadas:
        print("\n  ATENCAO: descartadas para caber no espaco disponivel:")
        for x in descartadas:
            print("      %s" % x)
        print("  (irrelevante se voce nao tem nenhum desses modelos)")

    folga = alvo["csz"] - len(comp)
    print("\ncomprimido: %d de %d bytes (padding de zeros: %d)"
          % (len(comp), alvo["csz"], folga))

    comp_pad = comp + b"\x00" * folga
    if inflar(comp_pad, 8) != bruto:
        sys.exit("o padding quebrou o inflate -- ABORTADO, nada foi gravado")

    # ------------------------------------------------------ monta o arquivo novo
    data = bytearray(orig)
    novo_crc = zlib.crc32(bruto) & 0xFFFFFFFF
    data[alvo["dados"]:alvo["dados"] + alvo["csz"]] = comp_pad
    struct.pack_into("<I", data, alvo["hdr"] + 14, novo_crc)      # crc32
    struct.pack_into("<I", data, alvo["hdr"] + 18, alvo["csz"])   # comprimido
    struct.pack_into("<I", data, alvo["hdr"] + 22, len(bruto))    # descomprimido

    n_cd = 0
    for m in re.finditer(rb"PK\x01\x02", data):
        p = m.start()
        if p + 46 > len(data):
            continue
        nlen = struct.unpack("<H", bytes(data[p + 28:p + 30]))[0]
        if nlen == 0 or nlen > 200 or p + 46 + nlen > len(data):
            continue
        if bytes(data[p + 46:p + 46 + nlen]) == INI_NOME.encode():
            struct.pack_into("<I", data, p + 16, novo_crc)
            struct.pack_into("<I", data, p + 20, alvo["csz"])
            struct.pack_into("<I", data, p + 24, len(bruto))
            n_cd += 1
            print("diretorio central corrigido em 0x%06X" % p)
    if n_cd != 1:
        sys.exit("esperava 1 entrada no diretorio central, achei %d -- ABORTADO" % n_cd)

    novo = bytes(data)

    # -------------------------------------------------- verificacao ANTES gravar
    print("\n=== verificacao do resultado (antes de gravar) ===")
    if len(novo) != len(orig):
        sys.exit("o tamanho do EXE mudou -- ABORTADO")

    m_orig = {m["nome"]: m for m in membros}
    m_novo = {m["nome"]: m for m in acha_membros(novo)}
    if set(m_orig) != set(m_novo):
        sys.exit("a lista de membros do ZIP mudou -- ABORTADO")

    problema = False
    for nome in sorted(m_novo):
        a_ = m_orig[nome]
        b_ = m_novo[nome]
        ca = inflar(orig[a_["dados"]:a_["dados"] + a_["csz"]], a_["meth"])
        cb = inflar(novo[b_["dados"]:b_["dados"] + b_["csz"]], b_["meth"])
        ha, hb = hashlib.sha256(ca).hexdigest(), hashlib.sha256(cb).hexdigest()
        crc_ok = (zlib.crc32(cb) & 0xFFFFFFFF) == b_["crc"] and len(cb) == b_["usz"]
        igual = ha == hb
        print("  %-24s CRC %-5s  %s" % (nome, "ok" if crc_ok else "FALHA",
                                        "identico" if igual else "alterado"))
        if not crc_ok:
            problema = True
        if nome.lower().endswith(".fw") and not igual:
            print("      *** IMAGEM DE FIRMWARE ALTERADA ***")
            print("      original : %s" % ha)
            print("      novo     : %s" % hb)
            problema = True
    if problema:
        sys.exit("\nverificacao FALHOU -- nada foi gravado")

    # so os bytes do membro INI e da entrada dele no diretorio central podem mudar
    dif = [i for i in range(len(orig)) if orig[i] != novo[i]]
    faixas_fw = [(m["dados"], m["dados"] + m["csz"])
                 for m in membros if m["nome"].lower().endswith(".fw")]
    tocou = [i for i in dif if any(x <= i < y for x, y in faixas_fw)]
    print("\n  bytes alterados : %d de %d" % (len(dif), len(orig)))
    print("  faixa alterada  : 0x%06X - 0x%06X" % (dif[0], dif[-1]))
    print("  dentro das .fw  : %d %s"
          % (len(tocou), "<-- OK, firmware intacto" if not tocou else "<-- PROBLEMA"))
    if tocou:
        sys.exit("\no patch tocou nas imagens de firmware -- nada foi gravado")

    saida = a.out or (os.path.splitext(a.exe)[0] + "_PATCHED.exe")
    with open(saida, "wb") as f:
        f.write(novo)

    print("\n" + "=" * 60)
    print("GERADO: %s" % os.path.abspath(saida))
    print("sha256: %s" % hashlib.sha256(novo).hexdigest())
    print("=" * 60)
    print("\nProximo passo: rode verifica_patch.py para uma conferencia")
    print("independente antes de executar qualquer coisa. E faca backup.")


if __name__ == "__main__":
    main()
