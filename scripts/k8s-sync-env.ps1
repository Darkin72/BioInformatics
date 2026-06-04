param(
    [string]$Namespace = "default",
    [string]$EnvFile = ".env",
    [switch]$RestartApps
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$envPath = Join-Path $repoRoot $EnvFile
if (-not (Test-Path $envPath)) {
    throw "Env file not found: $envPath"
}

function Read-DotEnv {
    param([string]$Path)

    $values = @{}
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or $line -notmatch "=") {
            return
        }

        $parts = $line -split "=", 2
        $key = $parts[0].Trim()
        $value = $parts[1]
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $values[$key] = $value
    }

    return $values
}

$dotenv = Read-DotEnv -Path $envPath

$configDefaults = [ordered]@{
    HOST = "0.0.0.0"
    PORT = "8000"
    JWT_EXPIRES_SECONDS = "3600"
    CORS_ALLOWED_ORIGINS = "http://localhost:30174,http://127.0.0.1:30174,http://localhost:5174,http://127.0.0.1:5174"
    KAFKA_BOOTSTRAP_SERVERS = "kafka:9092"
    KAFKA_RAW_INPUT_TOPIC = "protein.raw-input.v1"
    KAFKA_VALIDATED_INPUT_TOPIC = "protein.validated-input.v1"
    KAFKA_REQUEST_STATUS_TOPIC = "request_status"
    KAFKA_PREDICTION_TOPIC = "prediction_result"
    KAFKA_DEAD_LETTER_TOPIC = "dead_letter"
    RABBITMQ_EXCHANGE = "command_exchange"
    RABBITMQ_INFERENCE_QUEUE = "inference_jobs"
    RABBITMQ_RETRY_QUEUE = "retry_inference"
    RABBITMQ_NOTIFICATION_QUEUE = "notification_queue"
    CASSANDRA_HOST = "cassandra"
    CASSANDRA_HOSTS = "cassandra"
    CASSANDRA_PORT = "9042"
    CASSANDRA_KEYSPACE = "protein_rt"
    POSTGRES_DB = "protein_metadata"
    POSTGRES_USER = "protein"
    ADMIN_USERNAME = "admin"
    CAFA6_HEALTH_URL = ""
    CAFA6_PREDICT_URL = ""
    CAFA6_GRAPH_AWARE_PREDICT_SSE_URL = ""
    CAFA6_STREAM_PREDICT_SSE_URL = ""
    CAFA6_STREAM_BATCH_SIZE = "400"
    CAFA6_STREAM_TIMEOUT_SECONDS = "900"
    CAFA6_TOP_K = "20"
    CAFA6_TIMEOUT_SECONDS = "60"
    USER_STORE_PATH = "/app/tmp/auth_users.json"
    INFERENCE_WORKER_CONCURRENCY = "4"
    INFERENCE_WORKER_PREFETCH = "4"
    INFERENCE_WORKER_RABBITMQ_HEARTBEAT = "0"
    INFERENCE_WORKER_BLOCKED_CONNECTION_TIMEOUT = "1800"
    SPARK_MASTER_URL = "spark://spark-master:7077"
    VITE_API_BASE_URL = "http://localhost:8001"
    VITE_EVENTS_BASE_URL = "http://localhost:8004"
    CHOKIDAR_USEPOLLING = "true"
    WATCHPACK_POLLING = "true"
}

$secretDefaults = [ordered]@{
    JWT_SECRET = "dev-local-change-before-shipping"
    ADMIN_PASSWORD = "admin123"
    POSTGRES_PASSWORD = "protein"
    RABBITMQ_DEFAULT_USER = "protein"
    RABBITMQ_DEFAULT_PASS = "protein"
    RABBITMQ_ERLANG_COOKIE = "bioinformatics-local-rabbitmq-cookie"
    DATABASE_URL = "postgresql://protein:protein@postgres:5432/protein_metadata"
    RABBITMQ_URL = "amqp://protein:protein@rabbitmq:5672/"
}

$configKeys = @($configDefaults.Keys)
$secretKeys = @($secretDefaults.Keys)

$configArgs = @("create", "configmap", "bioinformatics-config", "-n", $Namespace, "--dry-run=client", "-o", "yaml")
foreach ($key in $configKeys) {
    $value = $configDefaults[$key]
    if ($dotenv.ContainsKey($key)) { $value = $dotenv[$key] }
    $configArgs += "--from-literal=$key=$value"
}

$secretArgs = @("create", "secret", "generic", "bioinformatics-secret", "-n", $Namespace, "--dry-run=client", "-o", "yaml")
foreach ($key in $secretKeys) {
    $value = $secretDefaults[$key]
    if ($dotenv.ContainsKey($key)) { $value = $dotenv[$key] }
    $secretArgs += "--from-literal=$key=$value"
}

& kubectl @configArgs | kubectl apply -f -
if ($LASTEXITCODE -ne 0) { throw "Failed to apply bioinformatics-config" }

& kubectl @secretArgs | kubectl apply -f -
if ($LASTEXITCODE -ne 0) { throw "Failed to apply bioinformatics-secret" }

Write-Host "Synced Kubernetes ConfigMap/Secret from $EnvFile." -ForegroundColor Green
Write-Host "Config keys synced: $(($configKeys | Where-Object { $dotenv.ContainsKey($_) }).Count)"
Write-Host "Secret keys synced: $(($secretKeys | Where-Object { $dotenv.ContainsKey($_) }).Count)"

if ($RestartApps) {
    kubectl -n $Namespace rollout restart `
        deployment/serving-api `
        deployment/replay-service `
        deployment/inference-worker `
        deployment/retry-worker `
        deployment/notification-service `
        deployment/frontend `
        deployment/spark-streaming

    if ($LASTEXITCODE -ne 0) { throw "Failed to restart app deployments" }
}
