# A investigação, passo a passo

Este documento é o caminho completo — inclusive os becos sem saída, que consumiram a maior
parte do tempo. Se você só quer resolver o seu problema, o [README](README.md) basta. Isto
aqui é para quem quer entender o método, ou para quem tem um caso parecido com outro produto
e precisa saber como chegar sozinho na resposta.

A lição central: **a mensagem de erro apontava para o lugar errado, e eu segui a mensagem de
erro.** Custou horas.

---

## O ponto de partida

Um SSD **XPG GAMMIX S70 BLADE 2 TB**, comprado em 2022, com dois sintomas que pareciam não ter
relação nenhuma entre si:

1. **No Linux, o disco não existia.** Aparecia na BIOS, funcionava no Windows, mas nunca virava
   `/dev/nvme*`. O `dmesg` dizia: `nvme nvme0: Invalid MNAN value 0`.
2. **O atualizador de firmware da ADATA nunca enxergou o disco.** Em três anos, em várias
   máquinas, sozinho ou acompanhado. Lista sempre vazia. O ADATA SSD Toolbox, do mesmo
   fabricante, enxergava o disco normalmente e recomendava a atualização.

O paliativo para o sintoma 1 já estava em produção: `nvme_core.multipath=0` na linha de boot
do kernel. Funciona, custo de performance zero. Mas é um parâmetro global de kernel para
contornar um drive só, e não dá para levar num live USB de recuperação.

---

## Beco sem saída nº 1: acreditar na mensagem de erro

A mensagem diz `Invalid MNAN value 0`. MNAN é o **Maximum Number of Allocatable Namespaces**,
campo do Identify Controller, bytes 543:540. Zero é um valor absurdo — todo SSD tem pelo menos
um namespace. Parecia caso encerrado: firmware bugado, campo mal preenchido, fim.

A busca na internet confirma essa leitura em toda parte. Vários relatos, mesma conclusão.

**O que estava errado:** a hipótese explica o sintoma, mas nunca foi testada contra um
controle. Uma explicação que só se ajusta ao caso positivo não é uma explicação — é uma
narrativa.

---

## Beco sem saída nº 2: descompilar o atualizador

A partir do MNAN, veio uma segunda hipótese: se o campo está zerado, talvez o SSD esteja
recusando comandos Vendor Specific, e por isso o atualizador não conseguiria falar com ele.

Isso levou a horas descompilando o `FWUpdate_3.2.F.66.exe`, procurando onde ele enumerava os
discos, tentando entender qual comando falhava.

**O que estava errado, e por quê:** MNAN é campo **somente-leitura, puramente informativo**,
do Identify Controller. Ele não porteia comando nenhum. Bastava ler a especificação NVMe para
descartar a hipótese em cinco minutos — em vez disso, foram horas no desmontador.

Pior: a resposta **estava dentro daquele executável**, mas numa camada muito mais rasa do que
onde eu estava procurando. Eu estava lendo código de máquina quando o que importava era um
arquivo de texto ao lado.

---

## Beco sem saída nº 3: culpar o chipset

Hipótese seguinte: modo RAID, Intel VMD, Intel RST — alguma coisa na plataforma escondendo o
disco do atualizador.

Descartada por inspeção: todas as controladoras NVMe da máquina aparecem no Gerenciador de
Dispositivos como **"Controlador Padrão NVM Express"**. Chipset em modo NVMe puro. Não havia
camada nenhuma no meio.

Rápido de eliminar, mas foi mais uma hipótese perseguida por não ter medido nada ainda.

---

## A virada: medir em vez de supor

O ponto de inflexão foi trivial e deveria ter sido o **primeiro** passo: ler o Identify
Controller cru de **todos** os SSDs NVMe da máquina, não só do drive com problema.

No Windows isso é `IOCTL_STORAGE_QUERY_PROPERTY` com
`StorageDeviceProtocolSpecificProperty`, CNS = 1 — é o que o `scripts/diagnostico_nvme.ps1`
faz. No Linux, `nvme id-ctrl`.

O resultado desmontou tudo:

| Drive | Model Number | FR | CMIC | MNAN | OACS | Linux |
|---|---|---|---|---|---|---|
| S70 Blade 2 TB | `AGAMMIXS70B-2T-CS` | 3.2.F.2A | **0x4D** | 0 | 0x0007 | **quebra** |
| S70 Blade 4 TB | `XPG GAMMIX S70 BLADE` | 3.2.J.F0 | 0x00 | 0 | 0x0017 | ok |
| X16 Plus 2 TB | `X16 Plus 2TB` | H231225a | 0x00 | 0 | 0x0014 | ok |

**Os três reportam MNAN = 0. Dois funcionam perfeitamente no Linux.**

O MNAN nunca foi a causa. É um valor comum, aparentemente inofensivo, presente em SSDs
saudáveis. A mensagem de erro do kernel menciona MNAN porque é onde a rejeição **acontece** —
não onde ela é **decidida**.

Duas coisas ficaram evidentes na mesma tabela:

- O que distingue o drive quebrado é o **CMIC**, não o MNAN.
- O drive quebrado é o único cujo Model Number é um **número de peça** em vez do nome comercial.

A segunda observação parecia um detalhe cosmético. Era o caso inteiro.

---

## Sintoma 1 resolvido: é o CMIC

Do código do kernel, `drivers/nvme/host/multipath.c`, `nvme_mpath_init_identify()`:

```c
if (!multipath || !ctrl->subsys || !(ctrl->subsys->cmic & NVME_CTRL_CMIC_ANA))
        return 0;                                   /* NVME_CTRL_CMIC_ANA = 1 << 3 */
if (!ctrl->max_namespaces || ctrl->max_namespaces > le32_to_cpu(id->nn)) {
        dev_err(ctrl->device, "Invalid MNAN value %u\n", ctrl->max_namespaces);
        return -EINVAL;
}
```

O guarda está na primeira linha. **Só chega na verificação do MNAN quem tem o bit 3 do CMIC
ligado.** Quem tem CMIC = 0x00 sai pelo `return 0` e nunca vê essa checagem — por isso os
outros dois drives funcionam com o mesmo MNAN = 0.

Decompondo o CMIC do drive afetado:

```
0x4D = 0100 1101
       │││└──────── bit 0: subsistema tem mais de uma porta
       ││└───────── bit 2: controlador é função virtual SR-IOV
       │└────────── bit 3: subsistema suporta ANA          <<< o gatilho
       └─────────── bit 6: reservado (não deveria estar ligado)
```

Para um M.2 de consumidor, com uma porta, sem virtualização, isso é lixo. Um campo mal
inicializado no firmware de 2021. Com o bit 3 ligado, o kernel entra no caminho do ANA
(Asymmetric Namespace Access — recurso de storage empresarial multipath), encontra MNAN = 0, e
rejeita o dispositivo inteiro.

**A consequência prática é o que importa:** o alvo da correção é **zerar o CMIC**, não
"consertar o MNAN". Se você validar o sucesso relendo o MNAN, vai concluir erradamente que
falhou — ele continua 0, e continua sem problema.

E o firmware-alvo já estava provado empiricamente: o 4 TB, **na mesma máquina, mesma
plataforma de controladora**, rodando 3.2.J.F0 com CMIC = 0x00. Existia uma versão de firmware
para esta família que zera o campo.

Restava só... conseguir atualizar. O que nos leva de volta ao sintoma 2.

---

## Sintoma 2 resolvido: abrir o pacote, não o código

Desta vez, em vez de descompilar o executável, a pergunta foi outra: **o que tem dentro dele
além de código?**

Varrendo o `FWUpdate_3.2.F.66.exe` por assinaturas `PK\x03\x04`, apareceram três cabeçalhos
locais de ZIP — em `0x06FCC4`, `0x0E1474` e `0x0E1741` — com o EOCD em `0x151AE6`. Um arquivo
ZIP inteiro embutido no meio do PE:

| Membro | Tamanho | Conteúdo |
|---|---|---|
| `Micron-B47R_0.fw` | 712.704 B | firmware para NAND Micron B47R |
| `YMTC-X2-9060_1.fw` | 704.512 B | firmware para NAND YMTC X2-9060 |
| `UpdateFWInfo.ini` | 1.816 B | configuração, UTF-16LE |

O INI é o caso inteiro:

```ini
TITLE=FFU_3.2.F.66
SOCID=5236
ModelName=XPG GAMMIX S70;XPG GAMMIX S70 BLADE;APSFG-1T-CSUS;APSFG-2T-CSUS;APSFG-512GCS;APSFG-1TCS;APSFG-2TCS
FWVersion=3.2.F.P7;3.2.F.2A;3.2.F.2M;3.2.F.3C;3.2.F.46
iInternalFWVersionCheckPart=3
PowerCtrl=2
```

O drive reporta `AGAMMIXS70B-2T-CS`. Essa string **não está na lista `ModelName`** — nem como
substring, nem como prefixo, de jeito nenhum. Mas a versão atual dele, `3.2.F.2A`, **está na
lista `FWVersion`**.

É por isso que o atualizador nunca enxergou o disco: em nenhuma máquina, sozinho ou
acompanhado, com qualquer chipset. Não era ambiente. Era uma comparação de strings falhando,
sempre, em toda parte.

### Por que é esquecimento e não bloqueio deliberado

Isso importa: se a ADATA tivesse excluído esta SKU de propósito, contornar seria assumir um
risco que eles conheciam e eu não. As evidências de que foi acidente:

1. **A assimetria na própria lista.** A linha do PS5 (`APSFG-*`) está coberta **exaustivamente
   por número de peça** — todos os cinco SKUs. A linha GAMMIX está coberta **só pelo nome de
   exibição**. Quem escreveu assumiu que todo S70 Blade se identifica pelo nome de marketing.
2. **As duas convenções coexistem na mesma máquina.** O 4 TB reporta `XPG GAMMIX S70 BLADE`; o
   2 TB reporta `AGAMMIXS70B-2T-CS`. Mesma família, mesmo PCI ID, strings de identificação de
   gerações diferentes.
3. **`AGAMMIXS70B-2T-CS` é o número de peça oficial de varejo.** Está na Amazon, Newegg,
   BestBuy, PCPartPicker. Não é string torta de uma linha de produção qualquer.
4. **`3.2.F.2A` está na lista `FWVersion`.** A ADATA explicitamente pretendia que drives nesta
   versão fossem atualizáveis por este pacote.
5. **A própria ADATA identifica o SSD e recomenda este firmware** — pelo site e pelo Toolbox.
   Dois mecanismos de identificação do mesmo fabricante discordando entre si.
6. **Há relato de outro usuário com sintoma idêntico na versão idêntica** `3.2.F.2A`: Toolbox
   enxerga, atualizador com lista vazia. Problema de lote, não caso isolado.

### A nuance que não pode ser perdida

O argumento **não** é "é o mesmo hardware, logo o nome não importa". Numa whitelist de
fabricante, o model string é **procuração para a configuração de fábrica**: binning da NAND,
mapa de capacidade, stepping do controlador. Às vezes ele está lá protegendo de um brick
legítimo, e contorná-lo é como arrancar um fusível.

O que tornou seguro **neste caso** foi a conjunção específica:

- SKU oficial de varejo correta;
- NAND do drive (Micron B47R) com imagem **presente** no pacote;
- `SOCID=5236` batendo com a controladora;
- **mesmo PCI ID** (`VEN_1CC1&DEV_5370`) do 4 TB, que a whitelist aceita;
- versão de origem constando em `FWVersion`;
- outro usuário no mesmo firmware com o mesmo sintoma.

Se você não consegue montar uma lista dessas para o seu caso, a resposta certa é não fazer.

---

## A correção cirúrgica

O problema técnico: o INI está comprimido dentro de um ZIP dentro de um PE. Se o membro
crescer, todos os offsets subsequentes se deslocam e o executável quebra.

A solução preserva o **tamanho comprimido**:

1. Recomprime o INI modificado com deflate (nível 9).
2. Preenche o restante com zeros **depois** do bloco `BFINAL` do stream. O descompressor para
   no `BFINAL` e ignora tudo o que vem depois — os zeros são inertes.
3. Reescreve **apenas** o CRC32 e o tamanho descomprimido, em dois lugares: o cabeçalho local
   (offsets +14, +18, +22) e o diretório central (+16, +20, +24).

Nada se desloca. O tamanho do executável não muda. E as imagens `.fw` continuam intocadas —
byte por byte as originais assinadas pela ADATA.

Uma coisa não coube: com `AGAMMIXS70B-2T-CS` acrescentado, a linha ficou maior do que o espaço
comprimido disponível. Duas SKUs do PS5 (`APSFG-1TCS`, `APSFG-2TCS`) foram descartadas para
caber. Produto diferente, irrelevante nesta máquina — mas o script avisa quando faz isso, e é
uma decisão que você deve conferir.

Whitelist final:

```
AGAMMIXS70B-2T-CS;XPG GAMMIX S70;XPG GAMMIX S70 BLADE;APSFG-1T-CSUS;APSFG-2T-CSUS;APSFG-512GCS
```

### A verificação, que é a parte que importa

Um segundo script, **somente leitura**, independente do primeiro, confere o resultado:

- SHA-256 de cada imagem `.fw`, comparado ao original → **idêntico**;
- CRCs do ZIP consistentes com o conteúdo → ok;
- tamanho do executável preservado → 1.476.608 B, igual;
- diff binário: **657 bytes** alterados, todos na faixa `0x0E1482`–`0x151A6F`, que é o campo
  CRC do cabeçalho local, os dados do INI e a entrada correspondente no diretório central.

Zero bytes alterados dentro das imagens de firmware. O primeiro script também **aborta**
sozinho se detectar qualquer alteração nelas — dupla checagem, por dois caminhos diferentes.

---

## O resultado

Com o executável modificado, **o atualizador da ADATA mostrou o SSD** — depois de três anos
nunca aparecendo, em nenhuma máquina, em nenhuma configuração.

Isso, por si só, já era a prova definitiva: a causa era **exclusivamente** a whitelist
`ModelName`. Nenhum componente de hardware envolvido.

O flash foi feito. Detalhe que aumenta bastante o custo de um erro: **o SSD atualizado era o
disco de boot do Windows** — a suposição inicial de que o sistema morava no 4 TB estava
errada, e isso só apareceu ao mapear a topologia dos discos antes do backup. Uma falha
derrubaria o sistema junto com os dados. Backup de imagem completa, não cópia de arquivos.

O Windows reiniciou normalmente. Leitura pós-flash:

```
PhysicalDrive2  AGAMMIXS70B-2T-CS
   SN=2M13******EL  FR=3.2.F.66  CMIC=0x00  MNAN=0
```

- `FR`: `3.2.F.2A` → **`3.2.F.66`**
- `CMIC`: `0x4D` → **`0x00`**
- `MNAN`: 0 → 0 (e está tudo certo assim)

A incerteza que restava — se a família `F.66` zeraria o CMIC, ou se só a `J.xx` faria isso —
foi resolvida a favor. Não foi preciso ir para a família J.

---

## O que ficou por resolver

**O Model Number não mudou.** Continua `AGAMMIXS70B-2T-CS`. O MN mora na região de
configuração gravada na fábrica (mass production config), separada do código do firmware; o
update não reescreve essa área. Consequência: **os próximos atualizadores da ADATA vão
continuar cegos para este drive**. O mesmo procedimento será necessário de novo, a cada
firmware novo, para sempre — a menos que a ADATA corrija a lista.

**`ActiveSlot` continua reportando 0**, valor que não é válido pela especificação NVMe
(deveria ser 1–7; os outros dois drives reportam 1). Persiste na 3.2.F.66. Aparentemente
cosmético, sem efeito observável.

**A remoção do `nvme_core.multipath=0` foi testada depois em boot real e funcionou**
(2026-11-16). Com CMIC = 0x00 o kernel sai pelo `return 0` e nem chega perto da checagem de
MNAN, e foi o que se observou: o disco aparece sem o parâmetro. Falta arquivar em `dados/` a
saída de `lsblk` e de `/proc/cmdline` desse boot; até lá é relato do autor, não log
conferível.

**Amostra de um.** Um SSD, uma máquina, um pacote de firmware.

---

## O método, destilado

O que teria economizado horas, na ordem em que deveria ter sido feito:

1. **Meça antes de teorizar.** Ler o Identify Controller de todos os drives foi o passo que
   resolveu o caso, e levou dez minutos. Foi feito tarde.
2. **Sempre tenha um controle.** Uma hipótese que explica só o caso positivo não é hipótese.
   Dois SSDs saudáveis com MNAN = 0 derrubaram semanas de diagnóstico errado em um segundo.
3. **A mensagem de erro diz onde a falha aconteceu, não onde ela foi decidida.** Leia o código
   ao redor. O guarda estava uma linha acima.
4. **Antes de descompilar, olhe o que é dado.** Executáveis carregam recursos, arquivos
   embutidos, configuração. A resposta estava num INI de texto dentro do EXE — não no código
   de máquina que eu passei horas lendo.
5. **A menor mudança que resolve.** Uma entrada numa lista de texto, com o firmware assinado
   intocado, é uma classe de risco completamente diferente de editar uma imagem de firmware.
6. **Verifique com uma ferramenta que não seja a que fez a mudança.** O script que gera não
   pode ser o único a atestar que gerou certo.
