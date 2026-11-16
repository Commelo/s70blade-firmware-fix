# S70 Blade Fix — destravando o atualizador de firmware da ADATA

> **Vídeo contando o caso** (português, com legendas em inglês):
> <https://www.youtube.com/watch?v=kgdAi8s8aTU>
>
> English version of this guide: [README.en.md](README.en.md)

Alguns SSDs **XPG GAMMIX S70 BLADE** nunca aparecem no atualizador oficial de firmware da
ADATA. Não é defeito, não é cabo, não é chipset, não é a sua máquina: é uma **lista de
modelos incompleta dentro do próprio instalador da ADATA**. O SSD se identifica com o
número de peça de varejo (`AGAMMIXS70B-2T-CS`), e essa string simplesmente não foi incluída
na lista. O atualizador olha, não reconhece, e mostra a lista vazia.

Este repositório documenta a causa, mostra como confirmar se é o seu caso, e traz um script
que acrescenta o seu modelo à lista **sem tocar em um único byte da imagem de firmware
assinada da ADATA**.

Resultado no caso que originou este trabalho: um SSD que passou **3 anos** sem conseguir
atualizar firmware foi atualizado de `3.2.F.2A` (2021) para `3.2.F.66` em cerca de trinta
segundos — e, de quebra, isso resolveu um bug que o deixava **invisível no Linux**.

---

## Índice

- [Isso resolve o meu problema?](#isso-resolve-o-meu-problema)
- [O que exatamente está quebrado](#o-que-exatamente-está-quebrado)
- [O bônus: o bug do Linux](#o-bônus-o-bug-do-linux)
- [Passo a passo](#passo-a-passo)
- [Avisos e riscos](#avisos-e-riscos)
- [O que foi verificado e o que não foi](#o-que-foi-verificado-e-o-que-não-foi)
- [Arquivos deste repositório](#arquivos-deste-repositório)

---

## Isso resolve o meu problema?

Há **dois problemas distintos** aqui. O primeiro é o que este projeto resolve diretamente.
O segundo é uma consequência feliz que só se aplica a parte das pessoas.

### Problema 1 — o atualizador não enxerga o SSD

**Sintoma:** você baixa o firmware oficial no site da ADATA, executa, e a lista de discos
aparece **vazia** — ou o disco simplesmente não está lá. Acontece em qualquer computador,
com o SSD sozinho ou acompanhado, com ou sem outros discos instalados. O ADATA SSD Toolbox
**enxerga** o disco normalmente e até recomenda a atualização; só o atualizador não vê.

**Quem é afetado:** qualquer SSD cujo Model Number reportado seja um número de peça que não
esteja na whitelist do pacote. No pacote `FWUpdate_32F66` a lista é:

```
ModelName=XPG GAMMIX S70;XPG GAMMIX S70 BLADE;APSFG-1T-CSUS;APSFG-2T-CSUS;APSFG-512GCS;APSFG-1TCS;APSFG-2TCS
```

Repare no padrão: a linha do **PS5** (`APSFG-*`) está coberta **exaustivamente por número de
peça**, os cinco. A linha **GAMMIX** está coberta **só pelo nome de marketing**. Nenhum
`AGAMMIXS70B-*` aparece. Quem escreveu a lista assumiu que todo S70 Blade se identifica pelo
nome comercial — e uma parte da produção não se identifica assim.

> **Como saber se é o seu caso:** rode `scripts/diagnostico_nvme.ps1` (Windows, como
> administrador). Se o campo `MN` do seu SSD **não estiver** na linha `ModelName` acima, é
> exatamente este problema.

### Problema 2 — o SSD é invisível no Linux

**Sintoma:** o SSD aparece na BIOS e funciona no Windows, mas no Linux não vira `/dev/nvmeXn1`.
O `dmesg` mostra:

```
nvme nvme0: Invalid MNAN value 0
```

**Quem é afetado:** apenas quem está no firmware antigo da família `3.2.F.xx`. Este problema
é **causado pelo firmware velho** e resolvido pela atualização — ou seja, é consequência do
Problema 1, não uma coisa separada.

### Tabela de decisão

| Seu sintoma | Este projeto ajuda? |
|---|---|
| Atualizador oficial mostra lista vazia | **Sim** — é exatamente isso |
| SSD invisível no Linux, `Invalid MNAN value 0` no dmesg | **Sim**, se você também não consegue atualizar |
| SSD invisível no Linux mas o atualizador funciona | Não precisa deste projeto — só atualize normalmente |
| SSD não aparece nem na BIOS | Não. Isso é hardware |
| SSD aparece mas está lento / com erros | Não. Isso é outro assunto |
| Outra marca / outro modelo de SSD | A **técnica** pode servir, o arquivo não. Veja [DIAGNOSTICO.md](DIAGNOSTICO.md) |

---

## O que exatamente está quebrado

O instalador `FWUpdate_3.2.F.66.exe` é um executável do Windows com um **arquivo ZIP embutido**
no meio dele. Dentro do ZIP existem três membros:

| Membro | Tamanho | O que é |
|---|---|---|
| `Micron-B47R_0.fw` | 712.704 B | Imagem de firmware para drives com NAND Micron B47R |
| `YMTC-X2-9060_1.fw` | 704.512 B | Imagem de firmware para drives com NAND YMTC X2-9060 |
| `UpdateFWInfo.ini` | 1.816 B | Arquivo de configuração, em UTF-16 |

O `UpdateFWInfo.ini` é onde mora o problema:

```ini
[UPDATEINFO]
TITLE=FFU_3.2.F.66
SOCID=5236
ModelName=XPG GAMMIX S70;XPG GAMMIX S70 BLADE;APSFG-1T-CSUS;...
FWVersion=3.2.F.P7;3.2.F.2A;3.2.F.2M;3.2.F.3C;3.2.F.46
iInternalFWVersionCheckPart=3
PowerCtrl=2
```

Duas listas fazem a filtragem:

- **`ModelName`** — quais modelos podem receber este firmware.
- **`FWVersion`** — de quais versões de origem é permitido subir.

O detalhe que fecha o caso: a versão `3.2.F.2A` do SSD afetado **está** na lista `FWVersion`.
A ADATA claramente pretendia que drives nessa versão fossem atualizáveis por este pacote. O
que faltou foi só o nome. É esquecimento, não bloqueio deliberado.

### A correção

Acrescentar `AGAMMIXS70B-2T-CS` à linha `ModelName`. Só isso.

Só que o INI está comprimido dentro de um ZIP dentro de um EXE. Se o arquivo crescer, todos
os deslocamentos do ZIP e da estrutura do PE se movem, e o executável quebra. A solução usada
aqui mantém o **tamanho comprimido idêntico**:

1. Recomprime o INI modificado com deflate.
2. Preenche o que sobrou com zeros depois do bloco final do stream deflate. O descompressor
   para no marcador `BFINAL` e ignora o resto — os zeros são inertes.
3. Reescreve apenas o **CRC32** e o **tamanho descomprimido** no cabeçalho local e no
   diretório central do ZIP.

Nenhum deslocamento se move. O tamanho do executável não muda. E — o ponto crítico — as duas
imagens `.fw` **não são tocadas**: continuam sendo os binários originais assinados pela ADATA.
O firmware que vai para o SSD é o firmware oficial, bit por bit.

> **Isso não é um firmware modificado.** O firmware é o da ADATA, sem alteração. O que foi
> modificado é a lista de modelos do instalador, um arquivo de texto de configuração. O
> script se recusa a gravar o resultado se qualquer byte dentro das imagens de firmware for
> alterado.

---

## O bônus: o bug do Linux

Se você chegou aqui pelo `Invalid MNAN value 0`, esta seção é para você. O diagnóstico que
circula na internet está errado, e isso importa: leva as pessoas a procurar solução no lugar
errado.

O kernel do Linux, em `drivers/nvme/host/multipath.c`, função `nvme_mpath_init_identify()`:

```c
if (!multipath || !ctrl->subsys || !(ctrl->subsys->cmic & NVME_CTRL_CMIC_ANA))
        return 0;                                   /* NVME_CTRL_CMIC_ANA = 1 << 3 */
if (!ctrl->max_namespaces || ctrl->max_namespaces > le32_to_cpu(id->nn)) {
        dev_err(ctrl->device, "Invalid MNAN value %u\n", ctrl->max_namespaces);
        return -EINVAL;
}
```

A mensagem de erro fala de MNAN, então todo mundo culpa o MNAN. Mas repare na primeira linha:
**só chega na verificação do MNAN quem tem o bit 3 do CMIC ligado.**

Foram medidos três SSDs NVMe na mesma máquina:

| Drive | Model Number | Firmware | CMIC | MNAN | Linux |
|---|---|---|---|---|---|
| S70 Blade 2 TB | `AGAMMIXS70B-2T-CS` | 3.2.F.2A | **0x4D** | 0 | **quebra** |
| S70 Blade 4 TB | `XPG GAMMIX S70 BLADE` | 3.2.J.F0 | 0x00 | 0 | ok |
| X16 Plus 2 TB | `X16 Plus 2TB` | H231225a | 0x00 | 0 | ok |

**Os três reportam MNAN = 0. Dois funcionam perfeitamente.** O MNAN não é a causa. O
discriminador é o **CMIC**.

`0x4D` = `0100 1101` → bits 0 (multi-port), 2 (função virtual SR-IOV), **3 (ANA)** e 6
(reservado). Para um M.2 de consumidor com uma porta só, isso é lixo — campo mal inicializado
no firmware de 2021. Com o bit 3 ligado, o kernel entra no caminho do ANA (Asymmetric
Namespace Access, uma coisa de storage empresarial), encontra MNAN = 0, e rejeita o
dispositivo inteiro.

**Consequência prática:** o objetivo da atualização não é "consertar o MNAN" — o MNAN vai
continuar 0 e não tem problema nenhum. O objetivo é **zerar o CMIC**. Valide o sucesso
relendo o CMIC, não o MNAN.

**Solução paliativa,** se você não quiser atualizar firmware: `nvme_core.multipath=0` na linha
de boot do kernel. Custo de performance zero em drive de porta única. Coloque em
`GRUB_CMDLINE_LINUX` (todas as entradas), **não** em `GRUB_CMDLINE_LINUX_DEFAULT` — este
último pula as entradas de recuperação, e se a raiz do sistema estiver nesse disco, você fica
sem recuperação.

---

## Passo a passo

### 0. Faça backup. De verdade.

Não é aviso decorativo. Você vai gravar firmware. Se der errado, o SSD morre e **não há RMA**
para dispositivo com atualizador modificado. A ADATA já brickou drives desta família num
incidente com o firmware 3.2.9.1 — usando o atualizador oficial deles, sem modificação
nenhuma.

Se o SSD que você vai atualizar é o **disco de boot** (era o caso aqui), backup significa
**imagem completa do disco**, não cópia de arquivos. Uma falha derruba o sistema junto.

### 1. Descubra o que o seu SSD reporta

```powershell
# PowerShell como Administrador
powershell -ExecutionPolicy Bypass -File .\scripts\diagnostico_nvme.ps1
```

No Linux:

```bash
sudo nvme id-ctrl /dev/nvme0 | grep -E '^(mn|sn|fr|cmic|oacs|frmw|fwug|mnan)'
```

Anote `MN`, `FR`, `CMIC` e `OACS`. Você precisa que:

- `MN` **não** esteja na lista `ModelName` (senão o problema é outro);
- `FR` **esteja** na lista `FWVersion` do pacote (senão o pacote vai recusar mesmo assim);
- `OACS` tenha o **bit 2** ligado (Firmware Download/Commit suportado). `0x0007` e `0x0017`
  ambos servem.

### 2. Baixe o pacote oficial

Vá ao site da ADATA, seção de suporte do XPG GAMMIX S70 BLADE, e baixe o pacote de firmware.
No caso deste trabalho: `FWUpdate_32F66.zip`, contendo `FWUpdate_3.2.F.66.exe`.

**Baixe você mesmo, do site do fabricante.** Este repositório não redistribui firmware nem
executável da ADATA — nem deve.

### 3. Gere o executável com a lista corrigida

```bash
python scripts/patch_fwupdate.py \
    --exe "FWUpdate_3.2.F.66.exe" \
    --add "AGAMMIXS70B-2T-CS" \
    --out "FWUpdate_3.2.F.66_PATCHED.exe"
```

Troque `AGAMMIXS70B-2T-CS` pelo `MN` **exato** que o passo 1 mostrou para o seu SSD.

Precisa só de Python 3 com biblioteca padrão — sem dependências.

**Não tem Python instalado?** No Windows:

1. Baixe o instalador em <https://www.python.org/downloads/> (qualquer versão 3.8 ou mais nova).
2. Na primeira tela do instalador, **marque "Add python.exe to PATH"** antes de clicar em
   *Install Now*. Sem isso o comando `python` não é encontrado.
3. Feche e abra de novo o PowerShell e confira:

   ```powershell
   python --version
   ```

   Tem que aparecer algo como `Python 3.12.x`. Se abrir a Microsoft Store em vez disso, o
   passo 2 foi pulado: rode o instalador de novo e marque a opção.

Alternativa em uma linha, pelo gerenciador de pacotes do Windows: `winget install Python.Python.3.12`.
Se você já tem o Blender, o Python embutido nele também serve (`4.x/python/bin/python.exe`).

**No PowerShell, escreva o comando em uma linha só.** A barra `\` no fim da linha, usada nos
exemplos acima, só funciona em terminais do tipo bash:

```powershell
python scripts/patch_fwupdate.py --exe "FWUpdate_3.2.F.66.exe" --add "AGAMMIXS70B-2T-CS" --out "FWUpdate_3.2.F.66_PATCHED.exe"
```

Rode os comandos de dentro da pasta do repositório, com o `FWUpdate_3.2.F.66.exe` baixado na
mesma pasta (ou passe o caminho completo em `--exe`).

O script imprime a lista antes e depois, avisa se precisou descartar alguma entrada para
caber no tamanho comprimido, e **aborta** se qualquer byte das imagens de firmware for tocado.

> **Reprodutibilidade.** Rodando com Python 3.10 sobre o `FWUpdate_3.2.F.66.exe` original
> (SHA-256 `0bad90b3f4852f4764f9492c67e40f5ef22d9f2ca99d3d3435c5e7b0827b4260`), a saída tem
> SHA-256 `ae5bd4041c3bf3053fdf5faf33450b4049a60ee68e7109541e78ff77bda1acd9` — bit por bit o
> mesmo arquivo que foi usado no flash documentado aqui. Se o seu bater, você tem exatamente o
> executável verificado. Se não bater, não entre em pânico: versões diferentes de zlib podem
> gerar bytes comprimidos diferentes. O que decide é o veredito do passo 4, não o hash.

### 4. Confira antes de rodar

```bash
python scripts/verifica_patch.py \
    --original "FWUpdate_3.2.F.66.exe" \
    --patched  "FWUpdate_3.2.F.66_PATCHED.exe"
```

Este script **não escreve nada**. Ele compara o SHA-256 de cada imagem `.fw` entre os dois
executáveis e só dá veredito `APROVADO` se:

- as imagens `.fw` estiverem **idênticas** ao original;
- os CRCs do ZIP estiverem consistentes;
- o modelo novo estiver na whitelist;
- o tamanho do executável estiver preservado.

Se der `REPROVADO`, pare. Não use.

### 5. Prepare a máquina

- Desconecte ou desmonte discos que você **não** quer atualizar. O atualizador lista todos os
  que passam pelo filtro, e é fácil clicar no errado.
- Feche tudo. Nada de download, torrent, compilação rodando.
- **Notebook: na tomada.** Desktop: se tiver nobreak, é a hora de usar.
- Se tiver dois SSDs do mesmo modelo, identifique pelo **firmware atual**, não pelo nome — em
  máquinas com drives idênticos a enumeração confunde.

### 6. Rode como administrador

Execute o `_PATCHED.exe`. O SSD deve aparecer na lista agora. Confira o número de série na
tela antes de confirmar. Aceite o aviso, aguarde, reinicie quando pedir.

O flash em si leva segundos.

### 7. Verifique o resultado

```powershell
# PowerShell como Administrador
powershell -ExecutionPolicy Bypass -File .\scripts\verificar_apos_flash.ps1
```

Você quer ver duas coisas: o `FR` mudou, e o `CMIC` virou `0x00`. O script diz explicitamente
se você já pode remover o `nvme_core.multipath=0` da linha de boot.

---

## Avisos e riscos

**Leia antes de decidir.**

- **Atualização de firmware pode brickar um SSD.** Isso vale para o atualizador oficial
  também. O risco não é zero e não fica zero.
- **Você perde qualquer chance de RMA.** Um drive brickado com atualizador modificado não vai
  ser trocado na garantia. Assuma isso conscientemente.
- **Backup completo antes. Sem exceção.**
- **Isto não é software da ADATA e não tem relação com a ADATA.** É documentação
  independente de um defeito no produto deles.
- **Não use em modelo diferente do seu.** O nome do modelo, numa whitelist de fabricante, é
  procuração para a configuração de fábrica: binning da NAND, mapa de capacidade, stepping do
  controlador. Às vezes ele protege de um brick legítimo. Contornar a verificação é seguro
  **apenas** quando você tem evidência independente de que o firmware é o certo para o seu
  hardware.

No caso documentado aqui, essa evidência era a conjunção de cinco fatos:

1. `AGAMMIXS70B-2T-CS` é o número de peça **oficial de varejo** do S70 Blade 2 TB — não é
   string torta de fábrica; está na Amazon, Newegg, PCPartPicker.
2. A NAND do drive (Micron B47R) tem imagem **presente no pacote**.
3. O `SOCID=5236` do pacote bate com a controladora.
4. O PCI ID (`VEN_1CC1&DEV_5370`) é **idêntico** ao do S70 Blade 4 TB da mesma máquina, que a
   whitelist aceita — mesma plataforma de controladora.
5. A versão de origem `3.2.F.2A` **está** na lista `FWVersion` do próprio pacote.

Se você não consegue montar uma lista parecida para o seu caso, **não faça**.

---

## O que foi verificado e o que não foi

Sendo honesto sobre a base de evidência, porque isso importa quando o custo do erro é um SSD:

**Verificado empiricamente, num drive real:**

- O executável com a lista corrigida **passa a enxergar** o SSD. Confirmado.
- O flash completou e o Windows bootou normalmente — no próprio disco de boot.
- `FR` foi de `3.2.F.2A` para `3.2.F.66`. Confirmado por leitura direta do Identify Controller.
- `CMIC` foi de `0x4D` para `0x00`. **Isto resolve o bug do Linux.**
- As imagens `.fw` no executável modificado têm SHA-256 idêntico ao original.

**Não verificado:**

- **Amostra de um.** Um SSD, uma máquina, um pacote de firmware. Funcionou. Não é uma
  estatística.
- **A remoção do `nvme_core.multipath=0` foi testada depois em boot real e funcionou**
  (2026-11-16): o disco aparece no Linux sem o parâmetro. O que ainda falta é o registro — a
  saída de `lsblk` e de `/proc/cmdline` desse boot não está arquivada em `dados/`, então por
  enquanto é relato do autor, não log conferível.
- **O Model Number não muda com a atualização.** Continua `AGAMMIXS70B-2T-CS`. O MN vive na
  região de configuração gravada na fábrica, separada do código do firmware. Consequência:
  **atualizadores futuros da ADATA vão continuar cegos para este drive**, e o mesmo
  procedimento será necessário de novo.
- **`ActiveSlot` continua reportando 0**, que não é um valor válido pela especificação NVMe
  (deveria ser 1–7). Isso persiste na 3.2.F.66. Aparentemente cosmético — não causou nenhum
  problema observável.
- **A família de firmware `3.2.J.xx` não foi testada** neste drive. O 4 TB roda `3.2.J.F0`
  com CMIC = 0x00, então é presumivelmente boa também, mas não há caminho testado de `F.66`
  para `J.xx`.

**Caminhos que foram investigados e descartados:**

- **RAID / VMD / Intel RST** — todas as controladoras aparecem como "Controlador Padrão NVM
  Express". Chipset em modo NVMe puro. Não era isso.
- **MNAN bloqueando comandos Vendor Specific** — infundado. MNAN é campo somente-leitura,
  informativo, do Identify Controller (bytes 543:540). E o `OACS` prova que os comandos de
  firmware são aceitos. Foi essa hipótese errada que levou a horas descompilando o
  executável — camada errada do problema.
- **Editar CMIC ou MNAN à mão numa imagem de firmware** — inviável. A InnoGrit tem chaves
  AES-256 fundidas no silício e verifica a assinatura da imagem.
- **MPTool (ferramenta de produção)** — perda total de dados, risco alto de brick, sem RMA.
  Desnecessário.

---

## Arquivos deste repositório

```
s70blade-fix/
├── README.md                      este arquivo
├── README.en.md                   versão em inglês
├── DIAGNOSTICO.md                 a investigação completa, passo a passo
├── LICENSE                        domínio público (CC0)
├── scripts/
│   ├── diagnostico_nvme.ps1       lê MN/FR/CMIC/OACS/FRMW de todos os NVMe (Windows)
│   ├── extrair_pacote.py          extrai o ZIP embutido no instalador (.fw + .ini)
│   ├── patch_fwupdate.py          acrescenta modelos à whitelist do instalador
│   ├── verifica_patch.py          verificação somente-leitura antes de usar
│   └── verificar_apos_flash.ps1   confirma FR e CMIC depois do flash
└── dados/
    ├── whitelist_original.txt     o UpdateFWInfo.ini original, transcrito
    └── verificacao_pos_flash.txt  a saída real que confirma o resultado
```

Nenhum firmware, executável ou material com copyright da ADATA é redistribuído aqui. Baixe o
pacote do site do fabricante.

---

## Licença e responsabilidade

Os scripts deste repositório são de domínio público (CC0) — use como quiser.

**Sem garantia de espécie alguma.** Você é responsável pelo que fizer com o seu hardware. Se
o seu SSD brickar, a responsabilidade é sua. Leia a seção de avisos, faça backup, e decida com
os olhos abertos.

Este projeto não tem qualquer vínculo com ADATA, XPG ou InnoGrit.
