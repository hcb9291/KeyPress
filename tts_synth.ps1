# ---------------------------------------------------------------------------
#  tts_synth.ps1  -  text to speech helper (Windows built-in voices)
#
#  This file is ASCII-only on purpose.
#
#  Usage:
#     powershell -File tts_synth.ps1 -List
#         prints one line per installed voice:  <DisplayName>|<Language>
#
#     powershell -File tts_synth.ps1 -Text "..." -Out "C:\path\out.wav" [-Voice "Microsoft Yaoyao"]
#         synthesizes the text into a .wav file. exit code 0 = ok
# ---------------------------------------------------------------------------

param(
    [switch]$List,
    [string]$Text = "",
    [string]$Out = "",
    [string]$Voice = ""
)

$ErrorActionPreference = "Stop"

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and
    $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Await($op, $type) {
    $task = $asTaskGeneric.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    return $task.Result
}

$null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType=WindowsRuntime]

if ($List) {
    foreach ($v in [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices) {
        "{0}|{1}" -f $v.DisplayName, $v.Language
    }
    exit 0
}

if (-not $Text -or -not $Out) { exit 2 }

$synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer

if ($Voice) {
    $target = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices |
              Where-Object { $_.DisplayName -eq $Voice } | Select-Object -First 1
    if ($target) { $synth.Voice = $target }
}

$stream = Await ($synth.SynthesizeTextToStreamAsync($Text)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])

$reader = New-Object Windows.Storage.Streams.DataReader($stream)
$null = Await ($reader.LoadAsync([uint32]$stream.Size)) ([uint32])

$bytes = New-Object byte[] ([int]$stream.Size)
$reader.ReadBytes($bytes)
$reader.Dispose()

[System.IO.File]::WriteAllBytes($Out, $bytes)
exit 0
