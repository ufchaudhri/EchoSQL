# Redis Setup Guide for EchoSQL

This guide helps you install and configure Redis for embedding and query result caching.

## Why Redis?

Redis provides fast in-memory caching for:
- **Embedding cache**: Store query embeddings for similarity search (40-60% cache hit rate)
- **Query result cache**: Cache SQL results for 5-10 minutes to reduce database load
- **Sub-millisecond latency**: Cache hits return results in <1ms vs 500-1000ms for LLM inference

---

## Installation Options

### Option 1: Chocolatey Package Manager (Easiest, No GitHub Needed)

**Step 1: Install Chocolatey** (if not already installed)

```powershell
# Open PowerShell as Administrator
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```

**Step 2: Install Redis**

```powershell
choco install redis
# This installs Redis 8.8.0 (latest maintained build)
```

**Step 3: Verify Installation**

```bash
redis-cli ping
# Should return: PONG

redis-cli --version
# Should show: redis-cli v8.8.0 or higher
```

**Connection String**: `localhost:6379` (default, no password)

✅ **Easiest option - one command, auto-updates, no GitHub needed**

---

### Option 2: Direct Download - redis-windows (No GitHub Needed)

If you prefer a standalone executable:

**Step 1: Download Redis 7.2.14**

```powershell
# Download directly (no GitHub access required)
$url = "https://github.com/redis-windows/redis-windows/releases/download/7.2.14/Redis-7.2.14-Windows-x64-msys2.zip"
$output = "$env:USERPROFILE\Downloads\Redis-7.2.14.zip"
(New-Object System.Net.WebClient).DownloadFile($url, $output)

# Extract
Expand-Archive $output -DestinationPath "C:\Program Files\Redis"
```

**Step 2: Install as Windows Service**

```powershell
cd "C:\Program Files\Redis"
redis-server --service-install redis.windows-service.conf --service-name Redis
redis-server --service-start
```

**Step 3: Verify**

```bash
redis-cli ping
# Should return: PONG
```

---

### Option 3: Docker (Clean, No Native Installation)

**Step 1: Install Docker Desktop**

Download from: https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe

**Step 2: Run Redis Container**

```bash
docker run --name redis-echosql -d -p 6379:6379 redis:7.4.9
```

**Step 3: Verify**

```bash
docker exec redis-echosql redis-cli ping
# Should return: PONG
```

---

### Option 4: WSL 2 (Windows Subsystem for Linux)

**Step 1: Enable WSL**

```powershell
# Open PowerShell as Administrator
wsl --install
# Restart your computer when prompted
```

**Step 2: Install Redis in WSL**

```bash
# In WSL terminal
sudo apt update
sudo apt install redis-server

# Start Redis
redis-server
# Should show: Ready to accept connections
```

**Step 3: Access from Windows**

```bash
# In Windows PowerShell (while WSL Redis is running)
redis-cli -h $(wsl hostname -I | awk '{print $1}') ping
# Should return: PONG
```

**Step 4: Connection String (from Windows app)**

```
<WSL_IP>:6379  (e.g., 172.31.30.80:6379)
# Get WSL IP: wsl hostname -I
```

---

### Option 5: Memurai (Commercial Alternative)

**Step 1: Start Redis Container**

```bash
docker run -d --name redis -p 6379:6379 redis/redis-stack:latest
```

**Step 2: Verify**

```bash
redis-cli ping
# Should return: PONG
```

**Step 3: Connection String**

```
localhost:6379
```

---

### Option 4: Docker Desktop + WSL 2 (Production-Ready)

Enterprise-grade Redis for Windows with commercial support:

**Website**: https://www.memurai.com/

**Benefits**:
- Full Redis compatibility
- 24/7 professional support
- Windows Services integration
- Free trial available

**Note**: Only needed if you require commercial support. For development, Chocolatey or redis-windows are sufficient.

---

## Configuration

### Step 1: Copy Environment Template

```bash
cd backend
cp .env.example .env
```

### Step 2: Edit `.env` File

```bash
# Edit with your text editor and set Redis connection
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Cache settings
EMBEDDING_CACHE_TTL_HOURS=24        # How long to keep embedding cache
QUERY_RESULT_CACHE_TTL_MINUTES=5    # How long to keep query results
```

### Step 3: Adjust Cache TTLs Based on Your Needs

| Setting | Default | Notes |
|---------|---------|-------|
| `EMBEDDING_CACHE_TTL_HOURS` | 24 | Keep embedding vectors 1 day. Higher = more cache hits |
| `QUERY_RESULT_CACHE_TTL_MINUTES` | 5 | Keep query results 5 min. Lower = more fresh data |
| `EMBEDDING_CACHE_ENABLED` | true | Enable/disable embedding caching |
| `QUERY_RESULT_CACHE_ENABLED` | true | Enable/disable result caching |

---

## Python Setup

### Step 1: Update Requirements

The `requirements.txt` already includes Redis packages:

```
redis>=5.0.0
redis[hiredis]>=5.0.0
```

### Step 2: Install Dependencies

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Step 3: Verify Redis Python Client

```bash
python -c "import redis; print(redis.__version__)"
# Should print version number
```

---

## Usage in Your Application

### Using Redis Cache Service

The `services/redis_cache.py` module provides easy-to-use methods:

```python
from services.redis_cache import RedisCache

# Initialize
cache = RedisCache(host="localhost", port=6379)
cache.connect()

# Cache an embedding
embedding = [0.1, 0.2, 0.3, ...]  # 768-dim vector
cache.cache_embedding(
    query="total balance",
    embedding=embedding,
    ttl_hours=24
)

# Retrieve from cache
cached = cache.get_embedding("total balance")
if cached:
    embedding = cached["embedding"]
    print("Cache hit!")
else:
    print("Cache miss - need to compute embedding")

# Cache query results
cache.cache_query_result(
    sql_query="SELECT SUM(balance) FROM accounts",
    result={"total": 50000},
    ttl_minutes=5
)

# Retrieve query result
result = cache.get_query_result("SELECT SUM(balance) FROM accounts")
if result:
    print(f"Cached result: {result['result']}")

# Get cache statistics
stats = cache.get_stats()
print(f"Memory used: {stats['used_memory']}")
print(f"Total keys: {stats['db_keys']}")

# Clear cache
cache.clear_cache(pattern="embedding:*")  # Clear only embeddings
cache.clear_cache()  # Clear everything
```

### Async Usage

```python
from services.redis_cache import get_redis_cache

cache = get_redis_cache()
await cache.connect_async()

# Async caching
await cache.cache_embedding_async(query, embedding)
await cache.cache_query_result_async(sql, result)

# Async retrieval
cached_embedding = await cache.get_embedding_async(query)
cached_result = await cache.get_query_result_async(sql)

await cache.close_async()
```

---

## Monitoring Redis

### Check Redis Status

```bash
# Connection info
redis-cli info server

# Memory usage
redis-cli info memory

# Cache keys
redis-cli keys "*"
redis-cli keys "embedding:*"
redis-cli keys "query_result:*"

# Database size
redis-cli dbsize

# Clear cache
redis-cli flushdb  # WARNING: Clears everything
redis-cli FLUSHDB  # Same
```

### Monitor Real-Time Activity

```bash
# Watch all commands in real-time
redis-cli monitor
```

### Performance Analysis

```bash
# See slowlog (commands taking >10ms by default)
redis-cli slowlog get 10
redis-cli slowlog reset
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `redis-cli ping` fails | Verify Redis/Memurai is running: Check Windows Services or `tasklist \| findstr memurai` |
| Memurai not in PATH | Restart PowerShell or add `C:\Program Files\Memurai\` to Windows PATH manually |
| Port 6379 already in use | Change `REDIS_PORT` in `.env` to different port (e.g., 6380) |
| Connection timeout | Check Windows Firewall allows port 6379, or use `redis-cli -h localhost -p 6379 ping` |
| Service won't start | Restart Memurai service: `net stop Memurai` then `net start Memurai` |
| Memory issues | Increase max memory in Memurai config: `maxmemory 1gb` |

---

## Performance Expectations

### Cache Hit Performance

```
Embedding cache lookup:  < 1ms
Query result cache:      < 1ms
Redis connection:        < 5ms
Total with DB fetch:     < 50ms
```

### Cache Miss Performance

```
LLM inference:  500-1000ms
SQL execution:  50-500ms
Total:          550-1500ms
```

### Expected Cache Hit Rate

```
After 100 queries:  40-60% hit rate
Reduction in inference calls: ~50%
Overall latency improvement: ~40-50%
```

---

## Production Considerations

For production deployments (beyond MVP):

1. **Persistence**: Enable AOF (Append-Only File) for durability
   ```bash
   # In redis.conf:
   appendonly yes
   appendfsync everysec
   ```

2. **Authentication**: Set Redis password
   ```bash
   # In redis.conf:
   requirepass your_secure_password
   
   # In .env:
   REDIS_PASSWORD=your_secure_password
   ```

3. **Memory Management**:
   ```bash
   # In redis.conf:
   maxmemory 1gb
   maxmemory-policy allkeys-lru  # Remove least recently used keys
   ```

4. **Replication**: For high availability, set up master-replica

5. **Monitoring**: Use Redis Exporter for Prometheus metrics

---

## Next Steps

1. Install Redis using one of the options above
2. Copy and configure `.env` file
3. Install Python dependencies: `pip install -r requirements.txt`
4. Test connection: `python -c "from services.redis_cache import get_redis_cache; cache = get_redis_cache(); cache.connect()"`
5. Start the FastAPI backend and integrate Redis caching

---

**Ready?** Run these commands to get started:

```bash
# Terminal 1: Start Redis
redis-server

# Terminal 2: Verify Redis
redis-cli ping

# Terminal 3: Install and test backend
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -c "from services.redis_cache import get_redis_cache; cache = get_redis_cache(); cache.connect()"
```

All set! Your Redis cache is ready for the FastAPI backend.
