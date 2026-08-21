#Requires -Version 5.1
#Requires -RunAsAdministrator

# --- Konfigurasi ---
# Path ke file passphrase terenkripsi yang Anda buat di Langkah 1
$EncryptedPassphraseFile = "C:\S1\SentinelOnePass.xml" # PASTIKAN PATH INI SESUAI

$Passphrase = "" # Akan diisi dari file terenkripsi

# Mencoba mengambil dan mendekripsi passphrase dari file XML
try {
    if (-not (Test-Path $EncryptedPassphraseFile)) {
        throw "File passphrase terenkripsi tidak ditemukan di '$EncryptedPassphraseFile'. Jalankan skrip Create-EncryptedPassphrase.ps1 terlebih dahulu sebagai pengguna yang benar."
    }

    # Impor SecureString dari file XML
    $ImportedSecurePass = Import-CliXml -Path $EncryptedPassphraseFile -ErrorAction Stop
    
    # Konversi SecureString ke plain text
    # Ini adalah objek System.Security.SecureString, kita perlu mengambil passwordnya
    # Cara standar untuk mengubah SecureString ke plain text:
    $Ptr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($ImportedSecurePass)
    $Passphrase = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($Ptr)
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Ptr) # Membersihkan dari memori

    if ([string]::IsNullOrWhiteSpace($Passphrase)) {
        throw "Gagal mendekripsi passphrase atau passphrase kosong setelah dekripsi."
    }
    Write-Host "Passphrase berhasil diambil dan didekripsi dari file '$EncryptedPassphraseFile'."

} catch {
    Write-Warning "PERINGATAN: Gagal mendapatkan passphrase dari file terenkripsi '$EncryptedPassphraseFile'. Error: $($_.Exception.Message)"
    Write-Warning "Skrip akan mencoba menggunakan passphrase hardcoded di bawah ini (TIDAK AMAN untuk produksi)."
    # Fallback ke passphrase hardcoded jika gagal (sama seperti sebelumnya)
    $Passphrase = "JHON GRAD SHOT JOT WET KANT GAS SHOT BONN FROM GET DUCK" # <-- GANTI INI JIKA PERLU!
    if ($Passphrase -eq "JHON GRAD SHOT JOT WET KANT GAS SHOT BONN FROM GET DUCK") {
        Write-Error "KESALAHAN KRITIS: Anda masih menggunakan passphrase contoh (hardcoded). Harap perbaiki masalah pengambilan passphrase terenkripsi."
        # exit 1
    }
    Write-Warning "PERINGATAN KEAMANAN: Passphrase di-hardcode dalam skrip. Ini sangat tidak disarankan."
}

# Path ke SentinelCtl.exe
$SentinelCtlPath = ""
$ExecutableName = "SentinelCtl.exe" # Nama file yang benar

# 1. Coba temukan dari registry (lebih dinamis dan seringkali akurat)
try {
    $S1AgentReg = Get-ItemProperty -Path "HKLM:\SOFTWARE\SentinelOne\Agent" -ErrorAction SilentlyContinue
    if ($S1AgentReg -and $S1AgentReg.InstallPath) {
        $RegPath = Join-Path -Path $S1AgentReg.InstallPath -ChildPath $ExecutableName
        if (Test-Path $RegPath) {
            $SentinelCtlPath = $RegPath
            Write-Host "Info: $ExecutableName ditemukan via registry: $SentinelCtlPath"
        }
    }
} catch {
    Write-Warning "Peringatan: Tidak dapat mengakses registry untuk path SentinelOne: $($_.Exception.Message)"
}

# 2. Jika registry gagal, coba cari di path umum dengan memperhitungkan versi folder
if (-not $SentinelCtlPath) {
    Write-Host "Info: $ExecutableName tidak ditemukan via registry. Mencoba pencarian folder..."
    $AgentBaseDir = "C:\Program Files\SentinelOne\"
    if (Test-Path $AgentBaseDir) {
        $AgentDirectory = Get-ChildItem -Path $AgentBaseDir -Directory -Filter "Sentinel Agent*" | Sort-Object Name -Descending | Select-Object -First 1
        if ($AgentDirectory) {
            $PotentialPath = Join-Path -Path $AgentDirectory.FullName -ChildPath $ExecutableName
            if (Test-Path $PotentialPath) {
                $SentinelCtlPath = $PotentialPath
                Write-Host "Info: $ExecutableName ditemukan di direktori agen (versi terbaru): $SentinelCtlPath"
            }
        }
    }
}

# 3. Fallback ke path dengan wildcard jika metode di atas gagal (seperti pendekatan awal Anda)
if (-not $SentinelCtlPath) {
    Write-Host "Info: $ExecutableName tidak ditemukan di path spesifik. Mencoba dengan wildcard..."
    $SentinelCtlCandidates = Get-ChildItem -Path "C:\Program Files\SentinelOne\Sentinel*\$ExecutableName" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($SentinelCtlCandidates) {
        $SentinelCtlPath = $SentinelCtlCandidates.FullName
        Write-Host "Info: $ExecutableName ditemukan via Get-ChildItem (wildcard di path): $SentinelCtlPath"
    }
}

# Validasi akhir path SentinelCtl.exe
if (-not (Test-Path $SentinelCtlPath)) {
    Write-Error "KESALAHAN: $ExecutableName tidak ditemukan pada path yang dikonfigurasi atau umum. Skrip tidak dapat melanjutkan. Harap perbarui logika penemuan path atau pastikan SentinelOne terinstal dengan benar."
    exit 1 # Hentikan skrip karena komponen vital tidak ditemukan
}

$LogFile = Join-Path -Path $PSScriptRoot -ChildPath "s1_scheduler.log" # Path untuk file log
$Hour = (Get-Date).Hour

# --- Fungsi Logging Terpusat ---
function Write-Log {
    param (
        [string]$Message,
        [ValidateSet("INFO", "WARNING", "ERROR")]
        [string]$Level = "INFO"
    )
    $LogEntry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [$Level] $Message"
    try {
        # INI BAGIAN PENTINGNYA: -Encoding UTF8
        $LogEntry | Out-File -FilePath $LogFile -Append -Encoding UTF8 -ErrorAction Stop
    } catch {
        Write-Warning "Peringatan: Gagal menulis ke file log '$LogFile'. Error: $($_.Exception.Message)"
    }
    Write-Host $LogEntry # Juga tampilkan di konsol
}

# --- Fungsi untuk memeriksa status agen (Opsional, untuk Idempotensi) ---
# Untuk menggunakan ini, Anda perlu tahu output pasti dari `SentinelCtl.exe status`
# Jika `SentinelCtl.exe status -j` tersedia, itu akan memberikan output JSON yang lebih mudah di-parse.
function Get-AgentStatus {
    param ([string]$ControlExe)
    try {
        # Coba gunakan output JSON jika tersedia, karena lebih mudah di-parse
        # $StatusJson = & $ControlExe status -j --output json # Cek sintaks pasti untuk versi Anda
        # if ($LASTEXITCODE -eq 0 -and $StatusJson) {
        #     $StatusObj = $StatusJson | ConvertFrom-Json
        #     # Asumsi ada properti seperti $StatusObj.agent.status atau $StatusObj.status
        #     if ($StatusObj.agent_running -eq $false -or $StatusObj.agent_disabled -eq $true) { # Sesuaikan properti ini
        #         return "Disabled"
        #     } elseif ($StatusObj.agent_running -eq $true) {
        #         return "Enabled"
        #     }
        # } else {
        #     # Fallback ke parsing teks biasa jika JSON gagal atau tidak tersedia
        # }

        $StatusResult = & $ControlExe status # Jalankan perintah status
        # Contoh parsing teks (SANGAT PERLU DISESUAIKAN dengan output aktual)
        if ($StatusResult -join " " -match "Agent is disabled") { # Gabungkan array string jika outputnya multiple lines
            return "Disabled"
        } elseif ($StatusResult -join " " -match "Agent is currently enabled and running|Agent is enabled|Agent is active") { # Sesuaikan string ini
            return "Enabled"
        } else {
            Write-Log -Message "Tidak dapat menentukan status agen dari output: $($StatusResult -join ' ')" -Level WARNING
            return "Unknown"
        }
    } catch {
        Write-Log -Message "Gagal menjalankan '$($ControlExe) status': $($_.Exception.Message)" -Level ERROR
        return "Error"
    }
}


# --- Fungsi Disable Agent ---
function Disable-SentinelAgent {
    param (
        [string]$ControlExeToUse,
        [string]$AgentPassphrase
    )
    
    # Cek status saat ini (Idempotensi) - Aktifkan jika fungsi Get-AgentStatus sudah disesuaikan
    # $CurrentStatus = Get-AgentStatus -ControlExe $ControlExeToUse
    # if ($CurrentStatus -eq "Disabled") {
    #     Write-Log -Message "Agen sudah dalam status DISABLED. Tidak ada tindakan yang diambil."
    #     return $true # Indikasikan sukses (atau tidak ada tindakan)
    # } elseif ($CurrentStatus -eq "Error") {
    #     Write-Log -Message "Tidak dapat memverifikasi status agen sebelum menonaktifkan karena error. Akan tetap mencoba menonaktifkan." -Level WARNING
    # }

    Write-Log -Message "Mencoba menonaktifkan agen SentinelOne..."
    try {
        # Penting: Pastikan Anda menggunakan parameter yang benar untuk versi SentinelCtl.exe Anda
        & $ControlExeToUse disable_agent -k "$AgentPassphrase"
        if ($LASTEXITCODE -eq 0) {
            Write-Log -Message "Agen BERHASIL DINONAKTIFKAN."
            return $true
        } else {
            # Coba tangkap output error jika ada
            $ErrorOutput = $Error | Select-Object -First 1
            Write-Log -Message "Gagal menonaktifkan agen. Exit code: $LASTEXITCODE. Output: $($ErrorOutput | Out-String)" -Level ERROR
            return $false
        }
    } catch {
        Write-Log -Message "Error kritis saat menjalankan '$($ControlExeToUse) disable_agent': $($_.Exception.Message)" -Level ERROR
        return $false
    }
}

# --- Fungsi Enable Agent ---
function Enable-SentinelAgent {
    param (
        [string]$ControlExeToUse
    )

    # Cek status saat ini (Idempotensi) - Aktifkan jika fungsi Get-AgentStatus sudah disesuaikan
    # $CurrentStatus = Get-AgentStatus -ControlExe $ControlExeToUse
    # if ($CurrentStatus -eq "Enabled") {
    #     Write-Log -Message "Agen sudah dalam status ENABLED. Tidak ada tindakan yang diambil."
    #     return $true
    # } elseif ($CurrentStatus -eq "Error") {
    #     Write-Log -Message "Tidak dapat memverifikasi status agen sebelum mengaktifkan karena error. Akan tetap mencoba mengaktifkan." -Level WARNING
    # }

    Write-Log -Message "Mencoba mengaktifkan agen SentinelOne..."
    try {
        & $ControlExeToUse enable_agent
        if ($LASTEXITCODE -eq 0) {
            Write-Log -Message "Agen BERHASIL DIAKTIFKAN."
            return $true
        } else {
            $ErrorOutput = $Error | Select-Object -First 1
            Write-Log -Message "Gagal mengaktifkan agen. Exit code: $LASTEXITCODE. Output: $($ErrorOutput | Out-String)" -Level ERROR
            return $false
        }
    } catch {
        Write-Log -Message "Error kritis saat menjalankan '$($ControlExeToUse) enable_agent': $($_.Exception.Message)" -Level ERROR
        return $false
    }
}

# --- Logika Jadwal Utama ---
Write-Log -Message "===== Skrip Penjadwalan SentinelOne Dimulai ====="
Write-Log -Message "Jam saat ini: $Hour:00."
Write-Log -Message "SentinelCtl Path: $SentinelCtlPath"
Write-Log -Message "Log File: $LogFile"

if ([string]::IsNullOrWhiteSpace($Passphrase) -and ($Hour -ge 8 -and $Hour -lt 16)) {
    Write-Log -Message "Passphrase kosong dan skrip dijadwalkan untuk menonaktifkan agen. Ini akan gagal. Harap periksa konfigurasi passphrase." -Level ERROR
    Write-Log -Message "===== Skrip Penjadwalan SentinelOne Selesai dengan Kesalahan Konfigurasi ====="
    exit 1
}

# Jadwal: 08:00 (8 AM) sampai 15:59 (sebelum 4 PM) adalah jam kerja (agen NONAKTIF)
# Di luar jam itu, agen AKTIF
if ($Hour -ge 8 -and $Hour -lt 16) {
    Write-Log -Message "Dalam jam kerja (08:00 - 15:59). Target: Nonaktifkan agen."
    Disable-SentinelAgent -ControlExeToUse $SentinelCtlPath -AgentPassphrase $Passphrase
} else {
    Write-Log -Message "Di luar jam kerja. Target: Aktifkan agen."
    Enable-SentinelAgent -ControlExeToUse $SentinelCtlPath
}

Write-Log -Message "===== Skrip Penjadwalan SentinelOne Selesai ====="