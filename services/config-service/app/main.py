from fastapi import FastAPI, HTTPException

from .persistence import persist_config
from .schemas import ConfigUpdate
from .settings import Settings, load_settings

app = FastAPI(title="Config Service", version="1.0.0")


@app.get("/health", tags=["Monitoring"])
def health() -> dict:
    return {"status": "ok"}


@app.get("/config/current", response_model=Settings, tags=["Configuration"])
def get_current_config():
    return load_settings()


@app.post("/config/update", response_model=Settings, tags=["Configuration"])
def update_config(payload: ConfigUpdate):
    current_settings = load_settings()
    updated_data = current_settings.model_dump()
    updated_data.update(payload.model_dump(exclude_unset=True))

    try:
        new_settings = Settings(**updated_data)
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    persist_config(new_settings)
    return new_settings
