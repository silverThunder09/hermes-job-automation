# Local Windows.Media.Ocr bridge. Reads one UTF-8 JSON request on stdin and
# writes one UTF-8 JSON result on stdout (or a JSON error on stderr).
# Keep this file ASCII-compatible for Windows PowerShell 5.1 without a BOM.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$stream = $null
$bitmap = $null
$errorCode = 'OCR_ERROR'

try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
    $null = [Windows.Storage.FileAccessMode, Windows.Storage, ContentType = WindowsRuntime]
    $null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapPixelFormat, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapAlphaMode, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
    $null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType = WindowsRuntime]

    # Pick only AsTask<TResult>(IAsyncOperation<TResult>), not action/progress overloads.
    $script:asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and
            $_.GetGenericArguments().Count -eq 1 -and
            $_.GetParameters().Count -eq 1 -and
            $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
        } | Select-Object -First 1
    if ($null -eq $script:asTask) {
        throw 'The WinRT IAsyncOperation AsTask bridge is unavailable.'
    }
    function Wait-WinRT {
        param([object]$Operation, [type]$ResultType)
        $task = $script:asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
        return $task.GetAwaiter().GetResult()
    }

    $errorCode = 'INVALID_REQUEST'
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    if ($null -eq $request -or $request.image_path -isnot [string] -or
        [string]::IsNullOrWhiteSpace($request.image_path) -or
        $request.language -isnot [string] -or
        $request.language -notmatch '^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$') {
        throw 'Expected image_path and a language tag (for example ko) as JSON strings.'
    }
    $imagePath = $request.image_path
    if (-not [IO.Path]::IsPathRooted($imagePath) -or -not [IO.File]::Exists($imagePath)) {
        throw 'Image path must refer to an existing local file using an absolute path.'
    }
    if ([IO.Path]::GetExtension($imagePath).ToLowerInvariant() -notin
        @('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.gif')) {
        throw 'Unsupported image extension. Use PNG, JPEG, BMP, TIFF or GIF.'
    }

    $errorCode = 'LANGUAGE_UNAVAILABLE'
    $requestedLanguage = New-Object Windows.Globalization.Language($request.language)
    if (-not [Windows.Media.Ocr.OcrEngine]::IsLanguageSupported($requestedLanguage)) {
        $available = @([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages |
            ForEach-Object { $_.LanguageTag }) -join ', '
        throw "OCR language '$($request.language)' is not installed/supported. Available: $available. Install its Windows OCR language capability in Settings before retrying."
    }
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($requestedLanguage)
    if ($null -eq $engine) {
        throw "Cannot create the Windows OCR engine for language '$($request.language)'."
    }

    $errorCode = 'IMAGE_DECODE_ERROR'
    $file = Wait-WinRT ([Windows.Storage.StorageFile]::GetFileFromPathAsync($imagePath)) ([Windows.Storage.StorageFile])
    $stream = Wait-WinRT ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Wait-WinRT ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $width = [int64]$decoder.PixelWidth
    $height = [int64]$decoder.PixelHeight
    $maxDimension = [int64][Windows.Media.Ocr.OcrEngine]::MaxImageDimension
    $errorCode = 'IMAGE_TOO_LARGE'
    if ($width -gt $maxDimension -or $height -gt $maxDimension) {
        throw "Image is ${width}x${height}; Windows OCR accepts at most $maxDimension pixels per dimension. Split a COPY into overlapping smaller images, or resize a COPY. No pixels were truncated and the original was not modified."
    }
    $errorCode = 'MULTIFRAME_IMAGE'
    if ($decoder.FrameCount -ne 1) {
        throw 'Multi-frame/page images are not supported. Export each frame/page to a separate PNG copy and OCR each image.'
    }
    $errorCode = 'IMAGE_DECODE_ERROR'
    $bitmap = Wait-WinRT ($decoder.GetSoftwareBitmapAsync(
        [Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8,
        [Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied
    )) ([Windows.Graphics.Imaging.SoftwareBitmap])

    $errorCode = 'RECOGNITION_ERROR'
    $result = Wait-WinRT ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $lines = @(
        foreach ($line in $result.Lines) {
            $left = [double]::PositiveInfinity
            $top = [double]::PositiveInfinity
            $right = [double]::NegativeInfinity
            $bottom = [double]::NegativeInfinity
            $words = @(
                foreach ($word in $line.Words) {
                    $rect = $word.BoundingRect
                    $left = [Math]::Min($left, $rect.X)
                    $top = [Math]::Min($top, $rect.Y)
                    $right = [Math]::Max($right, $rect.X + $rect.Width)
                    $bottom = [Math]::Max($bottom, $rect.Y + $rect.Height)
                    [ordered]@{
                        text = $word.Text
                        bounding_box = [ordered]@{
                            x = $rect.X; y = $rect.Y
                            width = $rect.Width; height = $rect.Height
                        }
                    }
                }
            )
            $box = $null
            if ($words.Count -gt 0) {
                $box = [ordered]@{
                    x = $left; y = $top
                    width = $right - $left; height = $bottom - $top
                }
            }
            [ordered]@{ text = $line.Text; bounding_box = $box; words = $words }
        }
    )
    $payload = [ordered]@{
        engine = 'Windows.Media.Ocr'
        language = $engine.RecognizerLanguage.LanguageTag
        width = [int]$bitmap.PixelWidth
        height = [int]$bitmap.PixelHeight
        text = $result.Text
        lines = $lines
        requires_review = $true
        warning = 'Windows.Media.Ocr does not provide confidence scores. OCR text and all derived fields require manual review; no extracted field is verified.'
    }
    $outputJson = $payload | ConvertTo-Json -Depth 12 -Compress
    [Console]::Out.WriteLine($outputJson)
}
catch {
    $failure = [ordered]@{ error = [ordered]@{ code = $errorCode; message = $_.Exception.Message } }
    [Console]::Error.WriteLine(($failure | ConvertTo-Json -Depth 4 -Compress))
    exit 1
}
finally {
    if ($null -ne $bitmap) { $bitmap.Dispose() }
    if ($null -ne $stream) { $stream.Dispose() }
}
