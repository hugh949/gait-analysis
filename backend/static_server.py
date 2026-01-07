"""
Simple static file server for frontend
Serves the React app from the dist directory
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

app = FastAPI()

# Get the directory where static files are located
static_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

# Serve static files
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=os.path.join(static_dir, "assets")), name="static")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve SPA - all routes return index.html"""
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"error": "Frontend not found"}


