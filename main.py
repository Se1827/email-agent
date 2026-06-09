from fastapi import FastAPI
from graph_routes import graph_router

app = FastAPI(title="Graph Test")
app.include_router(graph_router, prefix="/api/graph", tags=["Microsoft Graph"])
