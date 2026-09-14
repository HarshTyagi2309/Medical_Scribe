from fastapi import FastAPI
import traceback

app = FastAPI()
startup_error = None

try:
    from backend.main import app as real_app
    app = real_app

except Exception as e:
    startup_error = {
        "status": "startup_failed",
        "error": str(e),
        "error_type": type(e).__name__,
        "traceback": traceback.format_exc(),
    }

    @app.get("/health")
    def diagnostic_health():
        return startup_error
