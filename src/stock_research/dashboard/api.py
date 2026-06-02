def run_dashboard_api(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    uvicorn.run("stock_research.dashboard.app:app", host=host, port=port, reload=False)
