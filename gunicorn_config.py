import os
import psutil

# Gunicorn Configuration
bind = "0.0.0.0:8080"
workers = 1
timeout = 300
accesslog = "-"
errorlog = "-"
# Use /dev/shm for worker temp files to avoid disk I/O latency in Docker
worker_tmp_dir = "/dev/shm"

# Memory limit in MB (Safe margin for 512MB container)
# 380MB allows ~130MB overhead for OS and other processes
MEMORY_LIMIT_MB = 380 

def post_request(worker, req, environ, resp):
    """
    Check memory usage after every request.
    If it exceeds the limit, trigger a graceful restart.
    """
    try:
        process = psutil.Process(os.getpid())
        # RSS is Resident Set Size (physical memory used)
        mem_usage = process.memory_info().rss / 1024 / 1024 
        
        if mem_usage > MEMORY_LIMIT_MB:
            worker.log.warning(f"Worker memory usage ({mem_usage:.2f} MB) exceeded limit ({MEMORY_LIMIT_MB} MB). Restarting worker...")
            # Setting alive to False triggers Gunicorn to replace the worker
            worker.alive = False
    except Exception as e:
        worker.log.error(f"Error checking memory usage: {str(e)}")
