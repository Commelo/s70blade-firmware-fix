# diagnostico_nvme.ps1 -- le o Identify Controller de todos os SSDs NVMe e diz
# se o atualizador oficial da ADATA vai enxergar cada um.
#
# SOMENTE LEITURA. Nao escreve nada, nao altera nada.
# PRECISA rodar ELEVADO (como Administrador) -- o IOCTL exige.
#
#   powershell -ExecutionPolicy Bypass -File .\diagnostico_nvme.ps1
#
# Dominio publico (CC0). Sem garantia de especie alguma.

$ErrorActionPreference = "Continue"

# whitelist do pacote FWUpdate_32F66 (UpdateFWInfo.ini original da ADATA)
$WHITELIST = @(
    "XPG GAMMIX S70", "XPG GAMMIX S70 BLADE",
    "APSFG-1T-CSUS", "APSFG-2T-CSUS", "APSFG-512GCS", "APSFG-1TCS", "APSFG-2TCS"
)
$FWVERSIONS = @("3.2.F.P7", "3.2.F.2A", "3.2.F.2M", "3.2.F.3C", "3.2.F.46")

$elevado = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $elevado) {
    Write-Host "ATENCAO: nao esta elevado. O Identify Controller vai falhar." -ForegroundColor Red
    Write-Host "Abra o PowerShell como Administrador e rode de novo." -ForegroundColor Red
    Write-Host ""
}

$cs = @"
using System;
using System.Runtime.InteropServices;
public class NvmeId {
    [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Auto)]
    public static extern IntPtr CreateFile(string name, uint access, uint share, IntPtr sec,
        uint creation, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool DeviceIoControl(IntPtr h, uint code, byte[] inBuf, uint inSize,
        byte[] outBuf, uint outSize, ref uint returned, IntPtr overlapped);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool CloseHandle(IntPtr h);

    // IOCTL_STORAGE_QUERY_PROPERTY + StorageDeviceProtocolSpecificProperty (49)
    // com NVMeDataTypeIdentify / CNS=1 -> Identify Controller (4096 bytes)
    public static byte[] Identify(int driveNum, out string err) {
        err = "";
        IntPtr h = CreateFile("\\\\.\\PhysicalDrive" + driveNum, 0xC0000000u, 3u,
                              IntPtr.Zero, 3u, 0u, IntPtr.Zero);
        if (h.ToInt64() == -1) { err = "CreateFile: " + Marshal.GetLastWin32Error(); return null; }
        try {
            int HDR = 8 + 40;   // Version+Size + STORAGE_PROTOCOL_SPECIFIC_DATA
            byte[] buf = new byte[HDR + 4096];
            BitConverter.GetBytes((uint)49).CopyTo(buf, 0);    // PropertyId
            BitConverter.GetBytes((uint)0).CopyTo(buf, 4);     // PropertyStandardQuery
            BitConverter.GetBytes((uint)3).CopyTo(buf, 8);     // ProtocolTypeNvme
            BitConverter.GetBytes((uint)1).CopyTo(buf, 12);    // NVMeDataTypeIdentify
            BitConverter.GetBytes((uint)1).CopyTo(buf, 16);    // CNS = 1
            BitConverter.GetBytes((uint)0).CopyTo(buf, 20);
            BitConverter.GetBytes((uint)40).CopyTo(buf, 24);   // ProtocolDataOffset
            BitConverter.GetBytes((uint)4096).CopyTo(buf, 28); // ProtocolDataLength
            uint ret = 0;
            if (!DeviceIoControl(h, 0x2D1400u, buf, (uint)buf.Length, buf, (uint)buf.Length,
                                 ref ret, IntPtr.Zero)) {
                err = "DeviceIoControl: " + Marshal.GetLastWin32Error(); return null;
            }
            byte[] id = new byte[4096];
            Array.Copy(buf, HDR, id, 0, 4096);
            return id;
        } finally { CloseHandle(h); }
    }
}
"@
try { Add-Type -TypeDefinition $cs -ErrorAction Stop } catch { }

Write-Host ""
Write-Host "============ DIAGNOSTICO NVMe ============" -ForegroundColor Cyan
Write-Host ""

$discos = @(Get-Disk | Where-Object { $_.BusType -eq 'NVMe' } | Sort-Object Number)
if ($discos.Count -eq 0) {
    Write-Host "Nenhum disco NVMe encontrado." -ForegroundColor Red
    return
}

foreach ($d in $discos) {
    $e = ""; $id = $null
    try { $id = [NvmeId]::Identify($d.Number, [ref]$e) } catch { $e = $_.Exception.Message }
    if ($null -eq $id) {
        Write-Host ("PhysicalDrive{0}: ERRO {1}" -f $d.Number, $e) -ForegroundColor Red
        Write-Host ""
        continue
    }

    $mn   = ([System.Text.Encoding]::ASCII.GetString($id, 24, 40)).Trim()
    $sn   = ([System.Text.Encoding]::ASCII.GetString($id,  4, 20)).Trim()
    $fr   = ([System.Text.Encoding]::ASCII.GetString($id, 64,  8)).Trim()
    $cmic = $id[76]
    $oacs = [BitConverter]::ToUInt16($id, 256)
    $frmw = $id[260]
    $fwug = $id[319]
    $nn   = [BitConverter]::ToUInt32($id, 516)
    $mnan = [BitConverter]::ToUInt32($id, 540)

    Write-Host ("--- PhysicalDrive{0}  ({1} GB)" -f $d.Number, [math]::Round($d.Size/1GB,1)) -ForegroundColor White
    Write-Host ("    MN (modelo)   : '{0}'" -f $mn)
    Write-Host ("    SN (serie)    : '{0}'" -f $sn)
    Write-Host ("    FR (firmware) : '{0}'" -f $fr)
    Write-Host ("    CMIC          : 0x{0:X2}   (bit3 = 0x08 = ANA)" -f $cmic)
    Write-Host ("    MNAN          : {0}" -f $mnan)
    Write-Host ("    NN            : {0}" -f $nn)
    Write-Host ("    OACS          : 0x{0:X4}  (bit2 = firmware download/commit)" -f $oacs)
    Write-Host ("    FRMW          : 0x{0:X2}   slots={1} slot1ReadOnly={2}" -f `
                 $frmw, (($frmw -shr 1) -band 0x7), [bool]($frmw -band 0x1))
    Write-Host ("    FWUG          : 0x{0:X2}   (granularidade do fw-download)" -f $fwug)
    Write-Host ""

    # ---------------------------------------------------------------- veredito
    $naWhitelist = $WHITELIST -contains $mn
    $versaoOk    = $FWVERSIONS -contains $fr
    $anaLigado   = ($cmic -band 0x08) -ne 0
    $podeFlash   = ($oacs -band 0x4) -ne 0

    if ($naWhitelist) {
        Write-Host "    [ok] O MN esta na whitelist do pacote FWUpdate_32F66." -ForegroundColor Green
        Write-Host "         O atualizador oficial deve enxergar este disco normalmente." -ForegroundColor Green
    } else {
        Write-Host "    [!!] O MN NAO esta na whitelist do pacote FWUpdate_32F66." -ForegroundColor Yellow
        Write-Host "         O atualizador oficial NAO vai mostrar este disco --" -ForegroundColor Yellow
        Write-Host "         em nenhuma maquina, sozinho ou acompanhado." -ForegroundColor Yellow
        Write-Host "         >>> E este o problema que o patch_fwupdate.py resolve. <<<" -ForegroundColor Yellow
    }

    if ($versaoOk) {
        Write-Host ("    [ok] FR '{0}' esta na lista FWVersion (origem permitida)." -f $fr) -ForegroundColor Green
        if (-not $naWhitelist) {
            Write-Host "         Ou seja: a ADATA queria que este disco fosse atualizavel," -ForegroundColor Yellow
            Write-Host "         e so o nome ficou de fora. E o caso classico deste projeto." -ForegroundColor Yellow
        }
    } else {
        Write-Host ("    [--] FR '{0}' NAO esta na lista FWVersion do pacote." -f $fr) -ForegroundColor DarkGray
        Write-Host "         Este pacote nao tem nada a oferecer para este disco -- mesmo" -ForegroundColor DarkGray
        Write-Host "         com o MN corrigido ele vai dizer que nao precisa atualizar." -ForegroundColor DarkGray
        Write-Host "         Normal se voce JA atualizou, ou se este pacote e de outra linha." -ForegroundColor DarkGray
    }

    if (-not $podeFlash) {
        Write-Host "    [!!] OACS sem bit 2: este controlador nao aceita fw download." -ForegroundColor Red
    }

    if ($anaLigado) {
        Write-Host ("    [!!] CMIC=0x{0:X2} tem o bit ANA (0x08) LIGADO." -f $cmic) -ForegroundColor Yellow
        Write-Host "         Este e o disco que o Linux rejeita com 'Invalid MNAN value 0'." -ForegroundColor Yellow
        Write-Host "         Paliativo: nvme_core.multipath=0 na linha de boot." -ForegroundColor Yellow
        Write-Host "         Definitivo: atualizar o firmware (zera o CMIC)." -ForegroundColor Yellow
    } else {
        Write-Host ("    [ok] CMIC=0x{0:X2} sem o bit ANA -- o Linux aceita este disco." -f $cmic) -ForegroundColor Green
    }
    Write-Host ""
}

Write-Host "=== whitelist do pacote FWUpdate_32F66, para referencia ===" -ForegroundColor Cyan
Write-Host ("  ModelName = {0}" -f ($WHITELIST -join "; "))
Write-Host ("  FWVersion = {0}" -f ($FWVERSIONS -join "; "))
Write-Host ""
Write-Host "Se o seu pacote for outro, abra a whitelist real com:" -ForegroundColor DarkGray
Write-Host "  python patch_fwupdate.py --exe SEU_ARQUIVO.exe --listar" -ForegroundColor DarkGray
Write-Host ""
