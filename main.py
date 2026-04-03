import uvicorn
from src.app import app
from src.settings import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "src.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        reload_excludes=["output", "output/**", "uploads", "uploads/**", "*.log"],
        log_level="info",
    )
