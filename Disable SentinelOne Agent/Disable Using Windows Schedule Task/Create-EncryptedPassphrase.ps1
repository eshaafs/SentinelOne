#Requires -RunAsAdministrator

# Tentukan path tempat Anda ingin menyimpan file passphrase terenkripsi
# Pastikan path ini aman dan hanya bisa diakses oleh akun yang berwenang (Admin Anda)
$EncryptedFilePath = "C:\S1\SentinelOnePass.xml" # Anda bisa ganti path dan nama filenya

Write-Host "Anda akan diminta memasukkan passphrase SentinelOne."
Write-Host "Passphrase ini akan dienkripsi dan disimpan ke: $EncryptedFilePath"
Write-Host "HANYA pengguna yang membuat file ini ($(whoami)) yang dapat mendekripsinya di mesin ini."
Write-Host ""

# Meminta passphrase dengan aman
$SecurePass = Read-Host -Prompt "Masukkan Passphrase SentinelOne Anda" -AsSecureString

if ($SecurePass.Length -eq 0) {
    Write-Error "Passphrase tidak boleh kosong. Proses dibatalkan."
    exit 1
}

# Ekspor SecureString ke file XML terenkripsi
try {
    $SecurePass | Export-CliXml -Path $EncryptedFilePath -ErrorAction Stop
    Write-Host ""
    Write-Host "BERHASIL: Passphrase telah dienkripsi dan disimpan ke '$EncryptedFilePath'."
    Write-Host "PENTING: Jaga file ini dengan aman. Anda mungkin ingin mengatur izin NTFS pada file ini"
    Write-Host "         agar hanya dapat dibaca oleh akun Administrator yang menjalankan skrip SentinelOne."
} catch {
    Write-Error "GAGAL menyimpan passphrase terenkripsi. Error: $($_.Exception.Message)"
}
