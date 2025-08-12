from fastapi import FastAPI, HTTPException
from .settings import load_settings, Settings
from .schemas import ConfigUpdate

app = FastAPI(title="Config Service", version="0.1.0")

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

@app.get("/config/current", response_model=Settings)
def get_current_config():
    return load_settings().model_copy()

@app.post("/config/update", response_model=Settings)
def update_config(payload: ConfigUpdate):
    # Merge & validate against Settings model, then persist to file
    settings = load_settings()
    data = settings.model_dump()
    data.update({k: v for k, v in payload.model_dump().items() if v is not None})
    try:
        new_settings = Settings(**data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Persist
    from .persistence import persist_config
    persist_config(new_settings)
    return new_settings
