param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$libraryPath = Join-Path $ProjectRoot 'private\native\arm64-v8a-libeboSignature.so'
$envPath = Join-Path $ProjectRoot '.env'
$expectedLibraryHash = '698170B29DE4139F4784A83CFA7FD17F9A719A80E066CC8AA78162B257E1EE5F'

if (-not (Test-Path -LiteralPath $libraryPath)) { throw "Missing $libraryPath" }
if (-not (Test-Path -LiteralPath $envPath)) { throw "Missing $envPath" }

$actualHash = (Get-FileHash -LiteralPath $libraryPath -Algorithm SHA256).Hash
if ($actualHash -ne $expectedLibraryHash) {
    throw 'The native library version changed; refusing to use version-specific offsets.'
}

$bytes = [IO.File]::ReadAllBytes($libraryPath)
# The attached phone has the prod_cn flavor. In libeboSignature.so, the native
# loadSignatureResources(FLAVOR_PROD, true) branch selects these CN production keys.
$payloadKey = [Text.Encoding]::ASCII.GetString($bytes, 0xEB2C, 16)
$signKey = [Text.Encoding]::ASCII.GetString($bytes, 0xF210, 16)

foreach ($item in @($payloadKey, $signKey)) {
    if ($item.Length -ne 16 -or $item -notmatch '^[\x20-\x7E]{16}$') {
        throw 'Extracted key did not pass the expected format check.'
    }
}

$contents = [IO.File]::ReadAllText($envPath)
$contents = [regex]::Replace($contents, '(?m)^EBO_PAYLOAD_KEY=.*$', "EBO_PAYLOAD_KEY=$payloadKey")
$contents = [regex]::Replace($contents, '(?m)^EBO_SIGN_KEY=.*$', "EBO_SIGN_KEY=$signKey")
[IO.File]::WriteAllText($envPath, $contents, [Text.UTF8Encoding]::new($false))

$payloadHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($payloadKey))).Substring(0, 12)
$signHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($signKey))).Substring(0, 12)
Write-Host "Imported payload/sign keys into .env (hashes $payloadHash / $signHash; values hidden)."
