import time
import json
import uuid
from datetime import datetime
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from databases import Database
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set!")
database = Database(DATABASE_URL)

class APILoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        # Read request body (if needed)
        body_bytes = await request.body()
        try:
            request_body = body_bytes.decode("utf-8")
        except Exception:
            request_body = "<binary data>"
        
        response = await call_next(request)
        process_time = time.time() - start_time
        
        # Read response body
        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk
        try:
            response_body_text = response_body.decode("utf-8")
        except Exception:
            response_body_text = "<binary data>"
        
        log_entry = {
            "id": str(uuid.uuid4()),
            "tenant_id": request.headers.get("X-Tenant-ID", "unknown"),
            "user_id": request.headers.get("X-User-ID", "unknown"),
            "endpoint": request.url.path,
            "method": request.method,
            "request_body": request_body,
            "response_status": response.status_code,
            "response_body": response_body_text,
            "timestamp": datetime.utcnow().isoformat(),
            "execution_time": process_time,
        }
        
        query = """
        INSERT INTO api_logs (id, tenant_id, user_id, endpoint, method, request_body, response_status, response_body, timestamp, execution_time)
        VALUES (:id, :tenant_id, :user_id, :endpoint, :method, :request_body, :response_status, :response_body, :timestamp, :execution_time)
        """
        await database.execute(query=query, values=log_entry)
        
        # Reconstruct response (since body_iterator is exhausted)
        return Response(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
