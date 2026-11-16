# verificar_apos_flash.ps1 -- confirma se a atualizacao de firmware pegou.
#
# Duas perguntas: o FR mudou? e o CMIC zerou (bit ANA)?
# O CMIC e o que importa para o Linux -- o MNAN vai continuar 0 e isso e normal.
#
# SOMENTE LEITURA. PRECISA rodar ELEVADO (como Administrador).
#
#   powershell -ExecutionPolicy Bypass -File .\verificar_apos_flash.ps1
#   powershell -ExecutionPolicy Bypass -File .\verificar_apos_flash.ps1 -Antes "3.2.F.2A"
#
# Dominio publico (CC0). Sem garantia de especie alguma.

param(
    # firmware que o disco tinha ANTES do flash (para dizer se mudou)
    [string]$Antes = "3.2.F.2A",
    # so olha discos cujo MN casa com este padrao; "*" = todos
    [string]$Modelo = "*"
)

$ErrorActionPreference = "Continue"

$elevado = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $elevado) {
    Write-Host "ATENCAO: nao esta elevado -- o Identify Controller vai falhar." -ForegroundColor Red
    Write-Host "Abra o PowerShell como Administrador." -ForegroundColor Red
    Write-Host ""
}

$cs = @"
using System;
using System.Runtime.InteropServices;
public class NvmePos {
    [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Auto)]
    public static extern IntPtr CreateFile(string name, uint access, uint share, IntPtr sec,
        uint creation, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool DeviceIoControl(IntPtr h, uint code, byte[] inBuf, uint inSize,
        byte[] outBuf, uint outSize, ref uint returned, IntPtr overlapped);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool CloseHandle(IntPtr h);
    public static byte[] Identify(int driveNum, out string err) {
        err = "";
        IntPtr h = CreateFile("\\\\.\\PhysicalDrive" + driveNum, 0xC0000000u, 3u,
                              IntPtr.Zero, 3u, 0u, IntPtr.Zero);
        if (h.ToInt64() == -1) { err = "CreateFile: " + Marshal.GetLastWin32Error(); return null; }
        try {
            int HDR = 48;
            byte[] buf = new byte[HDR + 4096];
            BitConverter.GetBytes((uint)49).CopyTo(buf, 0);
            BitConverter.GetBytes((uint)0).CopyTo(buf, 4);
            BitConverter.GetBytes((uint)3).CopyTo(buf, 8);
            BitConverter.GetBytes((uint)1).CopyTo(buf, 12);
            BitConverter.GetBytes((uint)1).CopyTo(buf, 16);
            BitConverter.GetBytes((uint)0).CopyTo(buf, 20);
            BitConverter.GetBytes((uint)40).CopyTo(buf, 24);
            BitConverter.GetBytes((uint)4096).CopyTo(buf, 28);
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
Write-Host "========= VERIFICACAO POS-FLASH =========" -ForegroundColor Cyan
Write-Host ""

$achou = $false
foreach ($d in (Get-Disk | Where-Object { $_.BusType -eq 'NVMe' } | Sort-Object Number)) {
    $e = ""; $id = $null
    try { $id = [NvmePos]::Identify($d.Number, [ref]$e) } catch { $e = $_.Exception.Message }
    if ($null -eq $id) {
        Write-Host ("PhysicalDrive{0}: ERRO {1}" -f $d.Number, $e) -ForegroundColor Red
        continue
    }

    $mn   = ([System.Text.Encoding]::ASCII.GetString($id, 24, 40)).Trim()
    $sn   = ([System.Text.Encoding]::ASCII.GetString($id,  4, 20)).Trim()
    $fr   = ([System.Text.Encoding]::ASCII.GetString($id, 64,  8)).Trim()
    $cmic = $id[76]
    $mnan = [BitConverter]::ToUInt32($id, 540)

    Write-Host ("PhysicalDrive{0}  {1}" -f $d.Number, $mn)
    Write-Host ("   SN={0}  FR={1}  CMIC=0x{2:X2}  MNAN={3}" -f $sn, $fr, $cmic, $mnan)

    if ($mn -like $Modelo) {
        $achou = $true
        Write-Host ""

        if ($fr -eq $Antes) {
            Write-Host ("   [X] FIRMWARE: ainda em {0} -- o flash NAO foi aplicado." -f $Antes) -ForegroundColor Red
        } else {
            Write-Host ("   [OK] FIRMWARE: {0} (era {1}) -- flash aplicado." -f $fr, $Antes) -ForegroundColor Green
        }

        if (($cmic -band 0x08) -eq 0) {
            Write-Host ("   [OK] CMIC=0x{0:X2} -- bit ANA DESLIGADO." -f $cmic) -ForegroundColor Green
            Write-Host "        O Linux vai reconhecer o disco nativamente." -ForegroundColor Green
            Write-Host "        Pode remover nvme_core.multipath=0 da linha de boot." -ForegroundColor Green
        } else {
            Write-Host ("   [!] CMIC=0x{0:X2} -- bit ANA (0x08) ainda LIGADO." -f $cmic) -ForegroundColor Yellow
            Write-Host "        O bug do Linux persiste nesta versao de firmware." -ForegroundColor Yellow
            Write-Host "        MANTENHA nvme_core.multipath=0 na linha de boot." -ForegroundColor Yellow
        }
        Write-Host ("   (MNAN={0} e irrelevante -- SSDs saudaveis tambem reportam 0)" -f $mnan) -ForegroundColor DarkGray
    }
    Write-Host ""
}

if (-not $achou) {
    Write-Host ("Nenhum disco casou com o filtro -Modelo '{0}'." -f $Modelo) -ForegroundColor Red
}

Write-Host "=== slots de firmware ===" -ForegroundColor Cyan
Get-PhysicalDisk | Where-Object { $_.BusType -eq 'NVMe' } | ForEach-Object {
    Write-Host ("  {0} | FW={1}" -f $_.FriendlyName, $_.FirmwareVersion)
    try {
        $fi = $_ | Get-StorageFirmwareInformation -ErrorAction Stop
        Write-Host ("     SupportsUpdate={0} Slots={1} SlotAtivo={2}" -f `
            $fi.SupportsUpdate, $fi.NumberOfSlots, $fi.ActiveSlotNumber)
    } catch { Write-Host "     (sem info -- precisa elevacao)" }
}
Write-Host ""
